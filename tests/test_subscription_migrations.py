"""Isolated Stage 1 subscription schema and migration tests."""

import os

# Prevent dotenv from injecting project or production configuration in test runs.
os.environ["PYTHON_DOTENV_DISABLED"] = "true"

import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import CheckConstraint, Column, Integer, MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import database
from app.db_models import (
    AuditLog,
    CandidateSkillAnalytics,
    InterviewHistory,
    MockInterview,
    PaymentVerification,
    ResumeScan,
    Subscription,
    SubscriptionPlan,
    UserAccount,
)
from scripts import migrate


class SubscriptionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(__file__).resolve().parent / f".subscription-test-{uuid4().hex}.sqlite"
        self.extra_engines = []
        self.extra_paths = []
        self.engine = self._engine(self.db_path)

    def tearDown(self):
        for engine in [self.engine, *self.extra_engines]:
            engine.dispose()
        for path in [self.db_path, *self.extra_paths]:
            if path.exists():
                path.unlink()

    @staticmethod
    def _engine(path):
        engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )
        database.configure_sqlite_foreign_keys(engine)
        return engine

    def _create_legacy_schema(self):
        database._create_legacy_tables(self.engine)

    def _insert_legacy_records(self):
        now = datetime.now(timezone.utc)
        with sessionmaker(bind=self.engine)() as session:
            user = UserAccount(
                email="stage1-candidate@example.invalid",
                password_hash="test-hash",
                role="candidate",
                plan_tier="pro",
                is_active=True,
            )
            session.add(user)
            session.flush()
            session.add_all(
                [
                    AuditLog(action="TEST", resource="stage1", user_id=user.id),
                    InterviewHistory(
                        user_id=user.id,
                        role="Engineer",
                        experience="5 years",
                        skills="Python",
                        difficulty="medium",
                        questions="Question 1",
                        created_at=now.replace(tzinfo=None),
                    ),
                    ResumeScan(user_id=user.id, target_role="Engineer"),
                    MockInterview(user_id=user.id, role="Engineer"),
                ]
            )
            session.commit()
            return user.id

    def _insert_plan(self, *, code="pro-monthly", currency="USD", price_minor=2500, duration=30):
        with self.engine.begin() as connection:
            result = connection.execute(
                SubscriptionPlan.__table__.insert().values(
                    code=code,
                    name="Pro Monthly",
                    duration_days=duration,
                    price_minor=price_minor,
                    currency=currency,
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            return result.inserted_primary_key[0]

    def _apply(self):
        return migrate.run_migration_command(self.engine, "upgrade")

    def test_migration_repeatability_and_no_seed_data(self):
        self._create_legacy_schema()
        self._insert_legacy_records()

        self.assertEqual(self._apply(), ["0001"])
        self.assertEqual(self._apply(), [])
        tables = set(inspect(self.engine).get_table_names())
        self.assertTrue({"subscription_plans", "subscriptions", "payment_verifications", "schema_migrations"}.issubset(tables))
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(select(SubscriptionPlan.id)).all(), [])
            self.assertEqual(connection.execute(select(Subscription.id)).all(), [])
            self.assertEqual(connection.execute(select(PaymentVerification.id)).all(), [])
            version = connection.execute(select(migrate.schema_migrations)).mappings().one()
            self.assertEqual(version["version"], "0001")
            self.assertEqual(version["name"], "subscription_foundation")
            self.assertEqual(len(version["checksum"]), 64)

    def test_migration_preserves_existing_account_interview_resume_mock_and_audit_rows(self):
        self._create_legacy_schema()
        user_id = self._insert_legacy_records()
        before = {}
        with self.engine.connect() as connection:
            for table in ("user_accounts", "interview_history", "resume_scans", "mock_interviews", "audit_logs"):
                before[table] = connection.execute(text(f"SELECT * FROM {table}")).mappings().all()

        self._apply()

        with self.engine.connect() as connection:
            for table in before:
                self.assertEqual(connection.execute(text(f"SELECT * FROM {table}")).mappings().all(), before[table])
            self.assertEqual(before["user_accounts"][0]["id"], user_id)

    def test_checksum_mismatch_is_rejected(self):
        self._create_legacy_schema()
        self._apply()
        with self.engine.begin() as connection:
            connection.execute(
                migrate.schema_migrations.update()
                .where(migrate.schema_migrations.c.version == "0001")
                .values(checksum="0" * 64)
            )
        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            migrate.run_migration_command(self.engine, "status")

    def test_schema_drift_missing_index_is_rejected_without_repair(self):
        self._create_legacy_schema()
        self._apply()
        with self.engine.begin() as connection:
            connection.execute(text("DROP INDEX ix_subscriptions_plan_id"))

        with self.assertRaisesRegex(RuntimeError, "missing index ix_subscriptions_plan_id"):
            migrate.run_migration_command(self.engine, "status")
        self.assertNotIn(
            "ix_subscriptions_plan_id",
            {item["name"] for item in inspect(self.engine).get_indexes("subscriptions")},
        )

    def test_schema_validator_detects_missing_critical_check_constraint(self):
        expected = Table(
            "drift_probe",
            MetaData(),
            Column("id", Integer, primary_key=True),
            CheckConstraint("id > 0", name="ck_drift_probe_positive"),
        )
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE drift_probe (id INTEGER PRIMARY KEY)"))
            with self.assertRaisesRegex(RuntimeError, "missing constraints: ck_drift_probe_positive"):
                migrate._validate_table_contract(connection, expected)

    def test_schema_drift_missing_column_is_rejected_without_repair(self):
        self._create_legacy_schema()
        self._apply()
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE subscriptions DROP COLUMN plan_name_snapshot"))

        with self.assertRaisesRegex(RuntimeError, "missing columns: plan_name_snapshot"):
            migrate.run_migration_command(self.engine, "status")
        self.assertNotIn(
            "plan_name_snapshot",
            {column["name"] for column in inspect(self.engine).get_columns("subscriptions")},
        )

    def test_failed_upgrade_rolls_back_tables_and_version(self):
        self._create_legacy_schema()
        real_migration = migrate._load_migration()

        def fail_after_ddl(connection):
            real_migration.module.upgrade(connection)
            raise RuntimeError("simulated migration failure")

        failed = migrate.Migration(
            real_migration.version,
            real_migration.name,
            real_migration.checksum,
            SimpleNamespace(upgrade=fail_after_ddl, downgrade=real_migration.module.downgrade),
        )
        with patch.object(migrate, "_migration_registry", return_value=(failed,)):
            with self.assertRaisesRegex(RuntimeError, "simulated migration failure"):
                migrate.run_migration_command(self.engine, "upgrade")

        tables = set(inspect(self.engine).get_table_names())
        self.assertNotIn("schema_migrations", tables)
        self.assertNotIn("subscription_plans", tables)
        self.assertNotIn("subscriptions", tables)
        self.assertNotIn("payment_verifications", tables)

        self.assertEqual(self._apply(), ["0001"])

    def test_foreign_keys_and_row_constraints(self):
        self._create_legacy_schema()
        user_id = self._insert_legacy_records()
        self._apply()
        plan_id = self._insert_plan()
        now = datetime.now(timezone.utc)

        def assert_rejected(statement):
            with self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(statement)

        assert_rejected(
            SubscriptionPlan.__table__.insert().values(
                code="bad-duration", name="Bad", duration_days=0, price_minor=1, currency="USD"
            )
        )
        assert_rejected(
            SubscriptionPlan.__table__.insert().values(
                code="bad-price", name="Bad", duration_days=1, price_minor=0, currency="USD"
            )
        )
        for currency in ("usd", "U1D", "US", "U$D"):
            assert_rejected(
                SubscriptionPlan.__table__.insert().values(
                    code=f"bad-currency-{currency}", name="Bad", duration_days=1, price_minor=1,
                    currency=currency,
                )
            )
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    SubscriptionPlan.__table__.insert().values(
                        code="pro-monthly", name="Duplicate", duration_days=1, price_minor=1, currency="USD"
                    )
                )

        def insert_subscription(**overrides):
            values = {
                "user_id": user_id,
                "plan_id": plan_id,
                "status": "pending",
                "starts_at": now,
                "ends_at": now + timedelta(days=30),
                "plan_code_snapshot": "pro-monthly",
                "plan_name_snapshot": "Pro Monthly",
                "amount_minor_snapshot": 2500,
                "currency_snapshot": "USD",
                "auto_renew": False,
                "created_at": now,
                "updated_at": now,
            }
            values.update(overrides)
            with self.engine.begin() as connection:
                return connection.execute(Subscription.__table__.insert().values(**values)).inserted_primary_key[0]

        assert_rejected(Subscription.__table__.insert().values(
            user_id=999999, plan_id=plan_id, status="pending", starts_at=now,
            ends_at=now + timedelta(days=1), plan_code_snapshot="p", plan_name_snapshot="P",
            amount_minor_snapshot=1, currency_snapshot="USD", auto_renew=False,
        ))
        assert_rejected(Subscription.__table__.insert().values(
            user_id=user_id, plan_id=999999, status="pending", starts_at=now,
            ends_at=now + timedelta(days=1), plan_code_snapshot="p", plan_name_snapshot="P",
            amount_minor_snapshot=1, currency_snapshot="USD", auto_renew=False,
        ))
        for invalid in (
            {"status": "unknown"},
            {"ends_at": now},
            {"amount_minor_snapshot": 0},
            {"auto_renew": True},
            {"currency_snapshot": "U1D"},
            {"status": "active"},
            {"status": "active", "approved_by_id": user_id},
            {"status": "suspended"},
            {"status": "suspended", "suspended_at": now, "suspended_by_id": user_id},
            {"status": "revoked"},
            {"status": "revoked", "revoked_at": now, "revoked_by_id": user_id},
        ):
            with self.assertRaises(IntegrityError):
                insert_subscription(**invalid)

        first_id = insert_subscription()
        renewal_values = {
            "user_id": user_id,
            "plan_id": plan_id,
            "status": "pending",
            "starts_at": now + timedelta(days=30),
            "ends_at": now + timedelta(days=60),
            "plan_code_snapshot": "p",
            "plan_name_snapshot": "P",
            "amount_minor_snapshot": 1,
            "currency_snapshot": "USD",
            "auto_renew": False,
            "renewal_of_id": first_id,
        }
        with self.engine.begin() as connection:
            connection.execute(Subscription.__table__.insert().values(**renewal_values))
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(Subscription.__table__.insert().values(**renewal_values))

        valid_active = {
            "user_id": user_id,
            "plan_id": plan_id,
            "status": "active",
            "starts_at": now,
            "ends_at": now + timedelta(days=30),
            "plan_code_snapshot": "pro-monthly",
            "plan_name_snapshot": "Pro Monthly",
            "amount_minor_snapshot": 2500,
            "currency_snapshot": "USD",
            "auto_renew": False,
            "approved_by_id": user_id,
            "approved_at": now,
            "created_at": now,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            active_id = connection.execute(Subscription.__table__.insert().values(**valid_active)).inserted_primary_key[0]

        def payment_values(subscription_id, **overrides):
            values = {
                "subscription_id": subscription_id,
                "provider": "manual",
                "provider_reference": f"ref-{subscription_id}",
                "amount_minor": 2500,
                "currency": "USD",
                "status": "pending",
                "created_at": now,
                "updated_at": now,
            }
            values.update(overrides)
            return values

        assert_rejected(PaymentVerification.__table__.insert().values(**payment_values(999999)))
        assert_rejected(PaymentVerification.__table__.insert().values(**payment_values(first_id, amount_minor=0)))
        assert_rejected(PaymentVerification.__table__.insert().values(**payment_values(first_id, currency="U1D")))
        assert_rejected(PaymentVerification.__table__.insert().values(**payment_values(first_id, status="unknown")))
        assert_rejected(
            PaymentVerification.__table__.insert().values(
                **payment_values(
                    first_id,
                    status="verified",
                    status_changed_by_id=user_id,
                    status_changed_at=now,
                    status_reason="verified against evidence",
                )
            )
        )
        assert_rejected(
            PaymentVerification.__table__.insert().values(
                **payment_values(
                    first_id,
                    status="verified",
                    verified_by_id=user_id,
                    status_changed_by_id=user_id,
                    status_changed_at=now,
                    status_reason="verified against evidence",
                )
            )
        )
        assert_rejected(
            PaymentVerification.__table__.insert().values(
                **payment_values(
                    first_id,
                    status="rejected",
                    status_changed_by_id=user_id,
                    status_changed_at=now,
                )
            )
        )
        valid_payment = payment_values(
            active_id,
            status="verified",
            verified_by_id=user_id,
            verified_at=now,
            status_changed_by_id=user_id,
            status_changed_at=now,
            status_reason="verified against evidence",
        )
        with self.engine.begin() as connection:
            connection.execute(PaymentVerification.__table__.insert().values(**valid_payment))
        assert_rejected(PaymentVerification.__table__.insert().values(**valid_payment))
        assert_rejected(
            PaymentVerification.__table__.insert().values(
                **payment_values(
                    first_id,
                    provider="manual",
                    provider_reference=valid_payment["provider_reference"],
                )
            )
        )

    def test_utc_timestamp_round_trip(self):
        self._create_legacy_schema()
        self._apply()
        value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        plan_id = self._insert_plan()
        with sessionmaker(bind=self.engine)() as session:
            plan = session.get(SubscriptionPlan, plan_id)
            plan.created_at = value
            session.commit()
            session.expire(plan)
            self.assertEqual(plan.created_at, value.astimezone(timezone.utc))
            self.assertIsNotNone(plan.created_at.tzinfo)

    def test_concurrent_runners_apply_once(self):
        self._create_legacy_schema()
        results = []
        errors = []

        def run():
            engine = self._engine(self.db_path)
            try:
                results.append(migrate.run_migration_command(engine, "upgrade"))
            except Exception as exc:  # surfaced in assertion in the main test thread
                errors.append(exc)
            finally:
                engine.dispose()

        threads = [threading.Thread(target=run), threading.Thread(target=run)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertCountEqual(results, [["0001"], []])

    def test_lock_recovery_after_failed_concurrent_runner(self):
        self._create_legacy_schema()
        actual = migrate._load_migration()
        first_upgrade_entered = threading.Event()

        shared_migration = migrate.Migration(
            actual.version,
            actual.name,
            actual.checksum,
            SimpleNamespace(upgrade=actual.module.upgrade, downgrade=actual.module.downgrade),
        )
        results = []
        errors = []

        def run():
            engine = self._engine(self.db_path)
            try:
                results.append(migrate.run_migration_command(engine, "upgrade"))
            except Exception as exc:
                errors.append(exc)
            finally:
                engine.dispose()

        with patch.object(migrate, "_migration_registry", return_value=(shared_migration,)):
            first = threading.Thread(target=run, name="first-fails")
            second = threading.Thread(target=run, name="second-recovers")

            def signal_first_lock(connection):
                actual.module.upgrade(connection)
                if threading.current_thread().name == "first-fails":
                    first_upgrade_entered.set()
                    time.sleep(0.2)
                    raise RuntimeError("simulated crash before commit")

            shared_migration.module.upgrade = signal_first_lock
            first.start()
            self.assertTrue(first_upgrade_entered.wait(timeout=10))
            second.start()
            first.join(timeout=20)
            second.join(timeout=20)

        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertRegex(str(errors[0]), "simulated crash")
        self.assertEqual(results, [["0001"]])
        self.assertEqual(migrate.run_migration_command(self.engine, "status")[0]["applied"], True)

    def test_guarded_downgrade_empty_schema_and_refuse_history(self):
        self._create_legacy_schema()
        self._apply()
        with self.assertRaisesRegex(RuntimeError, "confirm-empty"):
            migrate.run_migration_command(self.engine, "downgrade", version="0001")
        self.assertTrue(
            migrate.run_migration_command(
                self.engine, "downgrade", version="0001", confirm_empty=True
            )
        )
        tables = set(inspect(self.engine).get_table_names())
        self.assertNotIn("subscription_plans", tables)
        self.assertNotIn("subscriptions", tables)
        self.assertNotIn("payment_verifications", tables)
        self.assertIn("user_accounts", tables)

        self._apply()
        user_id = self._insert_legacy_records()
        plan_id = self._insert_plan()
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            connection.execute(
                Subscription.__table__.insert().values(
                    user_id=user_id,
                    plan_id=plan_id,
                    status="pending",
                    starts_at=now,
                    ends_at=now + timedelta(days=30),
                    plan_code_snapshot="pro-monthly",
                    plan_name_snapshot="Pro Monthly",
                    amount_minor_snapshot=2500,
                    currency_snapshot="USD",
                    auto_renew=False,
                )
            )
        with self.assertRaisesRegex(RuntimeError, "contains 1 row"):
            migrate.run_migration_command(
                self.engine, "downgrade", version="0001", confirm_empty=True
            )
        with self.engine.connect() as connection:
            self.assertEqual(len(connection.execute(select(Subscription.id)).all()), 1)
            self.assertEqual(connection.execute(select(migrate.schema_migrations.c.version)).scalar_one(), "0001")

    def test_startup_and_first_database_request_do_not_create_subscription_tables(self):
        startup_engine = self._engine(self.db_path)
        startup_session = sessionmaker(bind=startup_engine, autoflush=False, autocommit=False)
        original_completed = database._migration_completed
        original_initialized = database._db_initialized
        try:
            database._migration_completed = False
            database._db_initialized = False
            with patch.object(database, "engine", startup_engine), patch.object(
                database, "SessionLocal", startup_session
            ), patch.dict(os.environ, {"SUPER_ADMIN_EMAIL": "", "SUPER_ADMIN_PASSWORD": ""}):
                database.init_db()
                tables = set(inspect(startup_engine).get_table_names())
                self.assertNotIn("subscription_plans", tables)
                self.assertNotIn("subscriptions", tables)
                self.assertNotIn("payment_verifications", tables)

                database._db_initialized = False
                db_generator = database.get_db()
                session = next(db_generator)
                session.close()
                try:
                    next(db_generator)
                except StopIteration:
                    pass

                tables = set(inspect(startup_engine).get_table_names())
                self.assertNotIn("subscription_plans", tables)
                self.assertNotIn("subscriptions", tables)
                self.assertNotIn("payment_verifications", tables)
        finally:
            database._migration_completed = original_completed
            database._db_initialized = original_initialized
            startup_engine.dispose()

        self.assertEqual(self._apply(), ["0001"])
        tables = set(inspect(self.engine).get_table_names())
        self.assertTrue({"subscription_plans", "subscriptions", "payment_verifications"}.issubset(tables))

    def test_normal_sqlite_application_engine_hook_enforces_foreign_keys(self):
        self._create_legacy_schema()
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1)

        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    CandidateSkillAnalytics.__table__.insert().values(
                        user_id=999999, skill="orphan", score=1, role_relevance=1,
                        evidence_count=1, confidence="LOW", weakness_status="identified",
                    )
                )

    def test_get_db_fallback_uses_allowlist_and_enforces_foreign_keys(self):
        fallback_path = self.db_path.with_name(f".fallback-test-{uuid4().hex}.sqlite")
        self.extra_paths.append(fallback_path)

        def isolated_fallback_engine(_url, **kwargs):
            engine = create_engine(
                f"sqlite:///{fallback_path.as_posix()}",
                connect_args={"check_same_thread": False, "timeout": 15},
            )
            self.extra_engines.append(engine)
            return engine

        generator = None
        try:
            with patch.object(database, "ensure_db_initialized", return_value=None), patch.object(
                database, "SessionLocal", side_effect=RuntimeError("force fallback")
            ), patch.object(database, "create_engine", side_effect=isolated_fallback_engine):
                generator = database.get_db()
                session = next(generator)
                fallback_engine = self.extra_engines[-1]
                tables = set(inspect(fallback_engine).get_table_names())
                self.assertIn("user_accounts", tables)
                self.assertNotIn("subscription_plans", tables)
                self.assertNotIn("subscriptions", tables)
                self.assertNotIn("payment_verifications", tables)
                self.assertEqual(
                    session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1
                )
                with self.assertRaises(IntegrityError):
                    session.add(
                        CandidateSkillAnalytics(
                            user_id=999999, skill="orphan", score=1, role_relevance=1,
                            evidence_count=1, confidence="LOW", weakness_status="identified",
                        )
                    )
                    session.commit()
        finally:
            if generator is not None:
                generator.close()


if __name__ == "__main__":
    unittest.main()
