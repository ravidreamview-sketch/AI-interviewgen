"""Ensure failed application initialization remains retryable."""

import os
os.environ["PYTHON_DOTENV_DISABLED"] = "true"

import unittest
from unittest.mock import patch

from app import database


class InitializationFailureTests(unittest.TestCase):
    def setUp(self):
        self.old_migration_completed = database._migration_completed
        self.old_db_initialized = database._db_initialized
        database._migration_completed = False
        database._db_initialized = False

    def tearDown(self):
        database._migration_completed = self.old_migration_completed
        database._db_initialized = self.old_db_initialized

    def test_init_failure_is_not_marked_complete(self):
        with patch.object(database, "_create_legacy_tables", side_effect=OSError("isolated injected failure")):
            with self.assertRaises(RuntimeError):
                database.init_db()
        self.assertFalse(database._migration_completed)

    def test_get_db_initialization_failure_does_not_mark_guard_initialized(self):
        with patch.object(database, "init_db", side_effect=RuntimeError("isolated injected failure")):
            with self.assertRaises(RuntimeError):
                next(database.get_db())
        self.assertFalse(database._db_initialized)

    def test_initialization_guard_retries_after_failure(self):
        calls = []

        def fail_once():
            calls.append("attempt")
            if len(calls) == 1:
                raise RuntimeError("isolated injected failure")
            database._migration_completed = True

        with patch.object(database, "init_db", side_effect=fail_once):
            with self.assertRaises(RuntimeError):
                database.ensure_db_initialized()
            database.ensure_db_initialized()
        self.assertEqual(len(calls), 2)
        self.assertTrue(database._db_initialized)


if __name__ == "__main__":
    unittest.main()
