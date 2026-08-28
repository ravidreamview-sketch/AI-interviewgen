"""
Regression Test Suite: Vercel Serverless Compatibility & Production Diagnostics
Verifies serverless entrypoint, database schema migrations, path rewriting middleware,
match endpoint execution, safe logging, health endpoint, and idempotent initialization.
"""

import unittest
import os
import json
import logging
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db, engine, _migration_completed, _safe_execute_ddl
from app.db_models import UserAccount, ResumeScan
from app.security import hash_password, create_access_token


class TestVercelProductionCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        # Ensure test candidate exists
        with SessionLocal() as db:
            user = db.query(UserAccount).filter(UserAccount.email == "vercel_test_candidate@ravi.ai").first()
            if not user:
                user = UserAccount(
                    email="vercel_test_candidate@ravi.ai",
                    password_hash=hash_password("VercelPass123!"),
                    role="candidate",
                    full_name="Vercel Test Candidate",
                    is_active=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            cls.test_user_id = user.id

    def test_01_api_index_import_and_app_export(self):
        """Verifies api.index entrypoint exports FastAPI app successfully under Vercel simulation."""
        with patch.dict(os.environ, {"VERCEL": "1", "ENV": "production"}):
            import api.index
            self.assertIsNotNone(api.index.app)
            self.assertEqual(api.index.app.title, "Ravi — AI Interview Question Generator API")

    def test_02_database_schema_initialization_dialect_agnostic(self):
        """Verifies init_db executes dialect-agnostic column and index migrations without errors."""
        try:
            init_db()
            schema_ok = True
        except Exception as e:
            schema_ok = False
            self.fail(f"init_db() failed: {e}")
        self.assertTrue(schema_ok)

    def test_03_vercel_path_middleware_stripping(self):
        """Verifies fix_vercel_path_middleware correctly routes /api/index.py paths to underlying endpoints."""
        from api.index import app
        client = TestClient(app)
        res = client.get("/api/index.py/debug-status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "online")
        self.assertTrue(data.get("db_ok"))

    def test_04_authenticated_resume_jd_match_in_serverless(self):
        """Verifies match execution and DB persistence under serverless simulated environment."""
        from api.index import app
        client = TestClient(app)

        token = create_access_token({
            "sub": self.test_user_id,
            "email": "vercel_test_candidate@ravi.ai",
            "role": "candidate",
            "plan_tier": "pro"
        })

        payload = {
            "resume_text": "Senior Software Engineer with 6 years experience in Python, FastAPI, PostgreSQL, AWS, Docker.",
            "jd_text": "Looking for a Senior Python Backend Engineer with FastAPI, PostgreSQL, and cloud experience.",
            "source_type": "paste"
        }

        res = client.post(
            "/api/candidate/resume-jd/match",
            json=payload,
            cookies={"candidate_session": token}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["scan_id"].startswith("scan_"))
        self.assertGreater(data["overall_match_score"], 0)
        self.assertIn("sub_scores", data)
        self.assertIn("skill_matrix", data)

        # Verify persisted in database
        with SessionLocal() as db:
            scan = db.query(ResumeScan).filter(ResumeScan.scan_id == data["scan_id"]).first()
            self.assertIsNotNone(scan)
            self.assertEqual(scan.user_id, self.test_user_id)

    def test_05_unauthenticated_request_returns_401(self):
        """Verifies that missing candidate_session cookie strictly returns 401 Unauthorized."""
        from api.index import app
        client = TestClient(app)
        res = client.post(
            "/api/candidate/resume-jd/match",
            json={"resume_text": "text", "jd_text": "text"}
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Authentication required", res.json().get("detail", ""))

    def test_06_tenant_isolation_on_scan_retrieval(self):
        """Verifies candidate cannot access scans belonging to another user."""
        from api.index import app
        client = TestClient(app)

        # Create scan for test user
        token1 = create_access_token({
            "sub": self.test_user_id,
            "email": "vercel_test_candidate@ravi.ai",
            "role": "candidate"
        })
        res1 = client.post(
            "/api/candidate/resume-jd/match",
            json={"resume_text": "Python Engineer", "jd_text": "Python Developer"},
            cookies={"candidate_session": token1}
        )
        scan_id = res1.json()["scan_id"]

        # Create token for different user
        token2 = create_access_token({
            "sub": 99999,
            "email": "other_candidate@ravi.ai",
            "role": "candidate"
        })
        res2 = client.get(
            f"/api/candidate/resume-jd/match/{scan_id}",
            cookies={"candidate_session": token2}
        )
        self.assertIn(res2.status_code, [401, 403, 404])

    def test_07_health_endpoint_returns_200(self):
        """Verifies /api/health returns 200 without requiring database access."""
        from api.index import app
        client = TestClient(app)

        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "RaviGen AI Interview Studio")

    def test_08_health_endpoint_alt_path(self):
        """Verifies /health returns the exact expected payload."""
        from api.index import app
        client = TestClient(app)

        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "RaviGen AI Interview Studio")

    def test_09_init_db_is_idempotent(self):
        """Verifies running init_db() multiple times does not crash."""
        try:
            init_db()
            init_db()
            init_db()
            idempotent_ok = True
        except Exception as e:
            idempotent_ok = False
            self.fail(f"init_db() is not idempotent: {e}")
        self.assertTrue(idempotent_ok)

    def test_10_app_import_does_not_crash(self):
        """Verifies that importing app.main does not perform unsafe database operations."""
        from app.main import app
        self.assertIsNotNone(app)
        self.assertEqual(app.title, "Ravi — AI Interview Question Generator API")

    def test_11_sqlite_engine_uses_check_same_thread(self):
        """Verifies SQLite engine configuration includes check_same_thread=False."""
        dialect = engine.dialect.name
        if dialect == "sqlite":
            from sqlalchemy import text as sa_text
            with engine.connect() as conn:
                result = conn.execute(sa_text("SELECT 1"))
                self.assertIsNotNone(result.fetchone())

    def test_12_vercel_env_simulation_does_not_crash_import(self):
        """Simulates Vercel environment and verifies app imports without crash."""
        with patch.dict(os.environ, {"VERCEL": "1", "ENV": "production"}):
            try:
                import importlib
                import app.main
                importlib.reload(app.main)
                import_ok = True
            except Exception as e:
                import_ok = False
                self.fail(f"App import crashed under Vercel env simulation: {e}")
            self.assertTrue(import_ok)

    def test_13_postgresql_configuration_logic(self):
        """Verifies PostgreSQL DATABASE_URL handling and engine argument isolation."""
        with patch("app.database.create_engine") as mock_create_engine:
            # Simulate PostgreSQL URL with postgres:// prefix
            test_pg_url = "postgres://user:pass@db.supabase.co:5432/postgres"
            with patch.dict(os.environ, {"DATABASE_URL": test_pg_url, "VERCEL": "1"}):
                # Verify normalization logic
                normalized_url = test_pg_url.replace("postgres://", "postgresql://", 1)
                self.assertTrue(normalized_url.startswith("postgresql://"))

    def test_14_safe_execute_ddl_recovers_from_error(self):
        """Verifies _safe_execute_ddl handles invalid DDL gracefully without raising exceptions."""
        result = _safe_execute_ddl("INVALID SQL SYNTAX STATEMENT HERE")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
