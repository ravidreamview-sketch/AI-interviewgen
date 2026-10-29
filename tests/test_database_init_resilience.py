import os
import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, text
from app import database
from app.database import (
    PG_ADVISORY_LOCK_ID,
    _acquire_advisory_lock,
    _release_advisory_lock,
    _advisory_lock_guard,
    _cleanup_orphaned_postgres_sequences,
    _table_exists,
    _is_production_mode,
    _run_account_bootstrap,
    ensure_db_initialized,
    init_db,
    SessionLocal,
    Base,
)
from app import db_models


class TestDatabaseInitResilience(unittest.TestCase):
    """Test suite verifying startup resilience, concurrency controls, and secure account bootstrapping."""

    def setUp(self):
        # Reset in-memory tracking flags
        database._migration_completed = False
        database._db_initialized = False

    def test_01_advisory_lock_id_constant(self):
        """Verifies PostgreSQL advisory lock constant is a valid unique 64-bit/32-bit integer."""
        self.assertEqual(PG_ADVISORY_LOCK_ID, 1492026841)
        self.assertIsInstance(PG_ADVISORY_LOCK_ID, int)

    def test_02_advisory_lock_sqlite_bypass(self):
        """Verifies advisory locks are bypassed cleanly for non-PostgreSQL dialects (e.g. SQLite)."""
        mock_conn = MagicMock()
        acquired = _acquire_advisory_lock(mock_conn, "sqlite")
        self.assertFalse(acquired)
        mock_conn.execute.assert_not_called()

        # Releasing when not acquired does nothing
        _release_advisory_lock(mock_conn, "sqlite", False)
        mock_conn.execute.assert_not_called()

    def test_03_advisory_lock_postgresql_flow(self):
        """Verifies advisory lock acquires and releases with exact lock ID on PostgreSQL dialect."""
        mock_conn = MagicMock()

        # Test acquire
        acquired = _acquire_advisory_lock(mock_conn, "postgresql")
        self.assertTrue(acquired)
        mock_conn.execute.assert_called_once()
        args, kwargs = mock_conn.execute.call_args
        self.assertIn("pg_advisory_lock", str(args[0]))
        params = kwargs if kwargs else (args[1] if len(args) > 1 else {})
        self.assertEqual(params.get("lock_id"), PG_ADVISORY_LOCK_ID)

        # Test release
        mock_conn.reset_mock()
        _release_advisory_lock(mock_conn, "postgresql", True)
        mock_conn.execute.assert_called_once()
        args, kwargs = mock_conn.execute.call_args
        self.assertIn("pg_advisory_unlock", str(args[0]))
        params = kwargs if kwargs else (args[1] if len(args) > 1 else {})
        self.assertEqual(params.get("lock_id"), PG_ADVISORY_LOCK_ID)

    def test_04_advisory_lock_guard_context_manager(self):
        """Verifies _advisory_lock_guard acquires lock and guarantees release in finally block."""
        mock_conn = MagicMock()

        with _advisory_lock_guard(mock_conn, "postgresql") as lock_acquired:
            self.assertTrue(lock_acquired)
            self.assertEqual(mock_conn.execute.call_count, 1)

        # After exiting block, release must have been executed
        self.assertEqual(mock_conn.execute.call_count, 2)
        release_args, release_kwargs = mock_conn.execute.call_args
        self.assertIn("pg_advisory_unlock", str(release_args[0]))

    def test_05_advisory_lock_guard_releases_on_exception(self):
        """Verifies _advisory_lock_guard unlocks even when an exception is raised inside context."""
        mock_conn = MagicMock()

        with self.assertRaises(RuntimeError):
            with _advisory_lock_guard(mock_conn, "postgresql"):
                raise RuntimeError("Simulated migration failure")

        # Unlock must still have been called
        self.assertEqual(mock_conn.execute.call_count, 2)
        release_args, _ = mock_conn.execute.call_args
        self.assertIn("pg_advisory_unlock", str(release_args[0]))

    def test_06_ensure_db_initialized_failure_does_not_set_flag(self):
        """Verifies ensure_db_initialized leaves _db_initialized=False and re-raises on failure."""
        database._db_initialized = False

        with patch("app.database.init_db", side_effect=RuntimeError("Database connection timed out")):
            with self.assertRaises(RuntimeError):
                ensure_db_initialized()

            # Flag must NOT be set to True on failure
            self.assertFalse(database._db_initialized)

    def test_07_ensure_db_initialized_retry_after_failure(self):
        """Verifies ensure_db_initialized retries on subsequent call after a transient failure."""
        database._db_initialized = False
        call_count = [0]

        def flaky_init():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Transient connection blip")
            # Second call succeeds
            database._migration_completed = True

        with patch("app.database.init_db", side_effect=flaky_init):
            # First call fails
            with self.assertRaises(RuntimeError):
                ensure_db_initialized()
            self.assertFalse(database._db_initialized)

            # Second call succeeds and sets flag
            ensure_db_initialized()
            self.assertTrue(database._db_initialized)
            self.assertEqual(call_count[0], 2)

    def test_08_orphaned_postgres_sequence_cleanup_sql(self):
        """Verifies _cleanup_orphaned_postgres_sequences targets user_invitations and candidate_answer_attempts sequences."""
        mock_conn = MagicMock()
        _cleanup_orphaned_postgres_sequences(mock_conn)

        mock_conn.execute.assert_called_once()
        sql_text = str(mock_conn.execute.call_args[0][0])
        self.assertIn("user_invitations_id_seq", sql_text)
        self.assertIn("candidate_answer_attempts_id_seq", sql_text)
        self.assertIn("DROP SEQUENCE IF EXISTS", sql_text)

    def test_09_table_exists_helper(self):
        """Verifies _table_exists accurately detects existing tables in current database."""
        # Ensure schema exists
        init_db()
        self.assertTrue(_table_exists("user_accounts"))
        self.assertTrue(_table_exists("user_invitations"))
        self.assertTrue(_table_exists("candidate_answer_attempts"))
        self.assertFalse(_table_exists("non_existent_table_xyz"))

    def test_10_production_mode_detection(self):
        """Verifies _is_production_mode accurately checks ENV and serverless platform variables."""
        orig_env = os.environ.get("ENV")
        orig_vercel = os.environ.get("VERCEL")
        try:
            os.environ.pop("ENV", None)
            os.environ.pop("VERCEL", None)
            self.assertFalse(_is_production_mode())

            os.environ["ENV"] = "production"
            self.assertTrue(_is_production_mode())

            os.environ["ENV"] = "development"
            self.assertFalse(_is_production_mode())

            os.environ["VERCEL"] = "1"
            self.assertTrue(_is_production_mode())
        finally:
            if orig_env is not None:
                os.environ["ENV"] = orig_env
            else:
                os.environ.pop("ENV", None)
            if orig_vercel is not None:
                os.environ["VERCEL"] = orig_vercel
            else:
                os.environ.pop("VERCEL", None)

    def test_11_production_bootstrap_does_not_provision_default_demo_credentials(self):
        """Verifies production mode does NOT provision hardcoded demo admin or demo candidate."""
        orig_env = os.environ.get("ENV")
        orig_email = os.environ.get("SUPER_ADMIN_EMAIL")
        orig_pass = os.environ.get("SUPER_ADMIN_PASSWORD")
        os.environ["ENV"] = "production"
        os.environ.pop("SUPER_ADMIN_EMAIL", None)
        os.environ.pop("SUPER_ADMIN_PASSWORD", None)

        try:
            # Use isolated session
            with SessionLocal() as db:
                # Remove any existing demo accounts
                db.query(db_models.UserAccount).filter(
                    db_models.UserAccount.email.in_(["admin@example.com", "candidate@example.com"])
                ).delete(synchronize_session=False)
                db.commit()

                _run_account_bootstrap()

                # Verify demo credentials were NOT created
                demo_admin = db.query(db_models.UserAccount).filter(db_models.UserAccount.email == "admin@example.com").first()
                demo_cand = db.query(db_models.UserAccount).filter(db_models.UserAccount.email == "candidate@example.com").first()
                self.assertIsNone(demo_admin)
                self.assertIsNone(demo_cand)
        finally:
            if orig_env is not None:
                os.environ["ENV"] = orig_env
            else:
                os.environ.pop("ENV", None)
            if orig_email is not None:
                os.environ["SUPER_ADMIN_EMAIL"] = orig_email
            if orig_pass is not None:
                os.environ["SUPER_ADMIN_PASSWORD"] = orig_pass

    def test_12_production_bootstrap_provisions_configured_super_admin(self):
        """Verifies production mode provisions super admin when explicitly configured via environment."""
        orig_env = os.environ.get("ENV")
        orig_email = os.environ.get("SUPER_ADMIN_EMAIL")
        orig_pass = os.environ.get("SUPER_ADMIN_PASSWORD")

        os.environ["ENV"] = "production"
        os.environ["SUPER_ADMIN_EMAIL"] = "configured_prod_admin@enterprise.org"
        os.environ["SUPER_ADMIN_PASSWORD"] = "SecureEnterprisePass999!"

        try:
            with SessionLocal() as db:
                # Clear all super admins to test initial provisioning
                db.query(db_models.UserAccount).filter(
                    db_models.UserAccount.role == "super_admin"
                ).delete(synchronize_session=False)
                db.commit()

                _run_account_bootstrap()

                created = db.query(db_models.UserAccount).filter(
                    db_models.UserAccount.email == "configured_prod_admin@enterprise.org"
                ).first()
                self.assertIsNotNone(created)
                self.assertEqual(created.role, "super_admin")
                self.assertEqual(created.plan_tier, "enterprise")

                # Candidate demo account must still be absent
                cand = db.query(db_models.UserAccount).filter(db_models.UserAccount.email == "candidate@example.com").first()
                self.assertIsNone(cand)
        finally:
            if orig_env is not None:
                os.environ["ENV"] = orig_env
            else:
                os.environ.pop("ENV", None)
            if orig_email is not None:
                os.environ["SUPER_ADMIN_EMAIL"] = orig_email
            else:
                os.environ.pop("SUPER_ADMIN_EMAIL", None)
            if orig_pass is not None:
                os.environ["SUPER_ADMIN_PASSWORD"] = orig_pass
            else:
                os.environ.pop("SUPER_ADMIN_PASSWORD", None)

    def test_13_production_bootstrap_preserves_existing_credentials(self):
        """Verifies production mode never overwrites existing super admin credentials."""
        from app.security import hash_password, verify_password

        orig_env = os.environ.get("ENV")
        os.environ["ENV"] = "production"
        os.environ["SUPER_ADMIN_EMAIL"] = "another_admin@enterprise.org"
        os.environ["SUPER_ADMIN_PASSWORD"] = "DifferentPassword123!"

        try:
            with SessionLocal() as db:
                # Clear existing super admins and create a specific baseline
                db.query(db_models.UserAccount).filter(
                    db_models.UserAccount.role == "super_admin"
                ).delete(synchronize_session=False)
                existing = db_models.UserAccount(
                    email="initial_super@enterprise.org",
                    password_hash=hash_password("OriginalPassword123!"),
                    role="super_admin",
                    plan_tier="enterprise",
                    is_active=True,
                )
                db.add(existing)
                db.commit()
                db.refresh(existing)

                orig_hash = existing.password_hash
                orig_email = existing.email

                _run_account_bootstrap()

                # Re-check super admin
                after = db.query(db_models.UserAccount).filter(db_models.UserAccount.role == "super_admin").first()
                self.assertEqual(after.email, orig_email)
                self.assertEqual(after.password_hash, orig_hash)
                self.assertTrue(verify_password("OriginalPassword123!", after.password_hash))
        finally:
            if orig_env is not None:
                os.environ["ENV"] = orig_env
            else:
                os.environ.pop("ENV", None)
            os.environ.pop("SUPER_ADMIN_EMAIL", None)
            os.environ.pop("SUPER_ADMIN_PASSWORD", None)


if __name__ == "__main__":
    unittest.main()
