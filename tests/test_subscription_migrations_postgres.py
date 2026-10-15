"""Opt-in PostgreSQL integration tests using an owned, disposable schema only.

Provision a disposable PostgreSQL database manually, then set TEST_POSTGRES_URL
and TEST_POSTGRES_CONFIRM_DISPOSABLE=YES_I_CREATED_A_DISPOSABLE_TEST_DATABASE.
The harness never falls back to DATABASE_URL and drops only its random schema.
"""

import os
import re
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError


CONFIRMATION = "YES_I_CREATED_A_DISPOSABLE_TEST_DATABASE"
DB_NAME_MARKER = re.compile(r"(?:^|[_-])(?:test|testing|disposable|tmp)(?:[_-]|$)", re.I)


def _validated_test_url():
    """Validate all safeguards before returning a URL that may be connected."""
    raw_url = os.environ.get("TEST_POSTGRES_URL", "").strip()
    if not raw_url:
        raise unittest.SkipTest("TEST_POSTGRES_URL is not set; PostgreSQL integration tests were not run")
    try:
        test_url = make_url(raw_url)
        configured_url = os.environ.get("DATABASE_URL", "").strip()
        production_url = make_url(configured_url) if configured_url else None
    except Exception as exc:
        raise RuntimeError("Invalid PostgreSQL test URL configuration; URL values were not displayed") from exc

    if test_url == production_url:
        raise RuntimeError("TEST_POSTGRES_URL must differ from DATABASE_URL")
    if test_url.get_backend_name() != "postgresql":
        raise RuntimeError("TEST_POSTGRES_URL must use PostgreSQL")
    if not DB_NAME_MARKER.search(test_url.database or ""):
        raise RuntimeError("PostgreSQL test database name must contain a delimited test/disposable/tmp marker")
    if os.environ.get("TEST_POSTGRES_CONFIRM_DISPOSABLE") != CONFIRMATION:
        raise RuntimeError("Explicit disposable-database confirmation is required")
    return test_url


class PostgreSQLSubscriptionMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = _validated_test_url()
        # Import application models only after URL safeguards pass. Importing
        # database.py constructs the normal engine but no connection is opened.
        from app import database
        from app.db_models import PaymentVerification, Subscription, SubscriptionPlan, UserAccount
        from scripts import migrate

        cls.database = database
        cls.PaymentVerification = PaymentVerification
        cls.Subscription = Subscription
        cls.SubscriptionPlan = SubscriptionPlan
        cls.UserAccount = UserAccount
        cls.migrate = migrate

    def setUp(self):
        self.schema = f"aisub_test_{uuid4().hex}"
        admin_engine = create_engine(self.url)
        try:
            with admin_engine.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        finally:
            admin_engine.dispose()

        self.engine = create_engine(self.url, pool_pre_ping=False)
        schema = self.schema

        @event.listens_for(self.engine, "connect")
        def set_owned_schema(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f'SET search_path TO "{schema}"')
            finally:
                cursor.close()

    def tearDown(self):
        self.engine.dispose()
        # Drop only the random schema created by this test. Never drop a database.
        admin_engine = create_engine(self.url)
        try:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            admin_engine.dispose()

    def _legacy_and_upgrade(self):
        self.database._create_legacy_tables(self.engine)
        return self.migrate.run_migration_command(self.engine, "upgrade")

    def test_migration_status_constraints_and_postgresql_currency_checks(self):
        self.assertEqual(self._legacy_and_upgrade(), ["0001"])
        self.assertTrue(self.migrate.run_migration_command(self.engine, "status")[0]["applied"])
        tables = set(inspect(self.engine).get_table_names())
        self.assertTrue({"subscription_plans", "subscriptions", "payment_verifications"}.issubset(tables))
        with self.engine.begin() as connection:
            with self.assertRaises(IntegrityError):
                connection.execute(
                    self.SubscriptionPlan.__table__.insert().values(
                        code="bad-currency", name="Bad", duration_days=30,
                        price_minor=1000, currency="U1D",
                    )
                )
        self.assertIn(
            "ck_currency_postgres_ascii_currency",
            {item.get("name") for item in inspect(self.engine).get_check_constraints("subscription_plans")},
        )
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            plan_id = connection.execute(
                self.SubscriptionPlan.__table__.insert().values(
                    code="pg-plan", name="PG Plan", duration_days=30,
                    price_minor=1000, currency="USD",
                ).returning(self.SubscriptionPlan.id)
            ).scalar_one()
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    self.Subscription.__table__.insert().values(
                        user_id=999999, plan_id=plan_id, status="pending", starts_at=now,
                        ends_at=now + timedelta(days=30), plan_code_snapshot="pg-plan",
                        plan_name_snapshot="PG Plan", amount_minor_snapshot=1000,
                        currency_snapshot="USD", auto_renew=False,
                    )
                )
        with self.engine.begin() as connection:
            user_id = connection.execute(
                self.UserAccount.__table__.insert().values(
                    email="pg-check-test@example.invalid", password_hash="test-hash",
                    role="candidate", plan_tier="free", is_active=True,
                ).returning(self.UserAccount.id)
            ).scalar_one()
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    self.Subscription.__table__.insert().values(
                        user_id=user_id, plan_id=plan_id, status="active", starts_at=now,
                        ends_at=now + timedelta(days=30), plan_code_snapshot="pg-plan",
                        plan_name_snapshot="PG Plan", amount_minor_snapshot=1000,
                        currency_snapshot="USD", auto_renew=False,
                    )
                )

    def test_forced_failure_rolls_back_ddl_history_and_releases_lock(self):
        self.database._create_legacy_tables(self.engine)
        actual = self.migrate._load_migration()

        def fail_after_ddl(connection):
            actual.module.upgrade(connection)
            raise RuntimeError("simulated PostgreSQL migration failure")

        failed = self.migrate.Migration(
            actual.version, actual.name, actual.checksum,
            SimpleNamespace(upgrade=fail_after_ddl, downgrade=actual.module.downgrade),
            actual.expected_tables,
        )
        with patch.object(self.migrate, "_migration_registry", return_value=(failed,)):
            with self.assertRaisesRegex(RuntimeError, "simulated PostgreSQL migration failure"):
                self.migrate.run_migration_command(self.engine, "upgrade")

        tables = set(inspect(self.engine).get_table_names())
        self.assertNotIn("schema_migrations", tables)
        self.assertNotIn("subscription_plans", tables)
        self.assertEqual(self.migrate.run_migration_command(self.engine, "upgrade"), ["0001"])

    def test_concurrent_migration_attempts_serialize_on_advisory_lock(self):
        self.database._create_legacy_tables(self.engine)
        results, errors = [], []

        def run_migration():
            engine = create_engine(self.url, pool_pre_ping=False)
            schema = self.schema
            @event.listens_for(engine, "connect")
            def use_schema(dbapi_connection, _record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(f'SET search_path TO "{schema}"')
                finally:
                    cursor.close()
            try:
                results.append(self.migrate.run_migration_command(engine, "upgrade"))
            except Exception as exc:
                errors.append(exc)
            finally:
                engine.dispose()

        threads = [threading.Thread(target=run_migration) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=45)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertCountEqual(results, [["0001"], []])

    def test_waiting_runner_recovers_after_locked_runner_rolls_back(self):
        self.database._create_legacy_tables(self.engine)
        actual = self.migrate._load_migration()
        entered = threading.Event()
        results, errors = [], []
        shared = self.migrate.Migration(
            actual.version, actual.name, actual.checksum,
            SimpleNamespace(upgrade=actual.module.upgrade, downgrade=actual.module.downgrade),
            actual.expected_tables,
        )

        def run():
            engine = create_engine(self.url, pool_pre_ping=False)
            schema = self.schema
            @event.listens_for(engine, "connect")
            def use_schema(dbapi_connection, _record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(f'SET search_path TO "{schema}"')
                finally:
                    cursor.close()
            try:
                results.append(self.migrate.run_migration_command(engine, "upgrade"))
            except Exception as exc:
                errors.append(exc)
            finally:
                engine.dispose()

        def fail_first(connection):
            actual.module.upgrade(connection)
            if threading.current_thread().name == "locked-failure":
                entered.set()
                time.sleep(0.4)
                raise RuntimeError("simulated PostgreSQL rollback")

        shared.module.upgrade = fail_first
        with patch.object(self.migrate, "_migration_registry", return_value=(shared,)):
            first = threading.Thread(target=run, name="locked-failure")
            second = threading.Thread(target=run, name="waiting-success")
            first.start()
            self.assertTrue(entered.wait(timeout=15))
            second.start()
            first.join(timeout=45)
            second.join(timeout=45)

        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertRegex(str(errors[0]), "simulated PostgreSQL rollback")
        self.assertEqual(results, [["0001"]])

    def test_empty_downgrade_allowed_and_populated_history_refused(self):
        self.assertEqual(self._legacy_and_upgrade(), ["0001"])
        self.assertTrue(
            self.migrate.run_migration_command(
                self.engine, "downgrade", version="0001", confirm_empty=True
            )
        )
        self.assertNotIn("subscriptions", inspect(self.engine).get_table_names())

        self.assertEqual(self._legacy_and_upgrade(), ["0001"])
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            user_id = connection.execute(
                self.UserAccount.__table__.insert().values(
                    email="pg-test@example.invalid", password_hash="test-hash", role="candidate",
                    plan_tier="free", is_active=True,
                ).returning(self.UserAccount.id)
            ).scalar_one()
            plan_id = connection.execute(
                self.SubscriptionPlan.__table__.insert().values(
                    code="test-plan", name="Test Plan", duration_days=30,
                    price_minor=1000, currency="USD",
                ).returning(self.SubscriptionPlan.id)
            ).scalar_one()
            connection.execute(
                self.Subscription.__table__.insert().values(
                    user_id=user_id, plan_id=plan_id, status="pending", starts_at=now,
                    ends_at=now + timedelta(days=30), plan_code_snapshot="test-plan",
                    plan_name_snapshot="Test Plan", amount_minor_snapshot=1000,
                    currency_snapshot="USD", auto_renew=False,
                )
            )
        with self.assertRaisesRegex(RuntimeError, "contains 1 row"):
            self.migrate.run_migration_command(
                self.engine, "downgrade", version="0001", confirm_empty=True
            )
        self.assertIn("subscriptions", inspect(self.engine).get_table_names())


if __name__ == "__main__":
    unittest.main()
