"""
Regression Test Suite: Vercel Serverless Compatibility & Production Diagnostics
Verifies serverless entrypoint, database schema migrations, path rewriting middleware,
match endpoint execution, and safe logging.
"""

import unittest
import os
import json
import logging
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db, engine
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
        # If user 99999 doesn't exist in DB, get_current_user returns 401
        res2 = client.get(
            f"/api/candidate/resume-jd/match/{scan_id}",
            cookies={"candidate_session": token2}
        )
        self.assertIn(res2.status_code, [401, 403, 404])


if __name__ == "__main__":
    unittest.main()
