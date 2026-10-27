import unittest
import os
import sys
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount
from app.security import (
    hash_password,
    create_access_token,
    decode_access_token,
    _load_jwt_secrets,
)
from app.auth_deps import FAILED_LOGIN_ATTEMPTS

# Isolated in-memory SQLite database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


client = TestClient(app)


class TestCandidateSessionPersistence(unittest.TestCase):
    """
    Regression test suite verifying:
    1. Login authentication and session cookie establishment
    2. Multi-instance serverless token decoding compatibility
    3. Multi-page protected navigation without session drop
    4. Page refresh session restoration
    5. Expiration and invalid token rejection
    6. Non-auth error isolation (non-auth error does not destroy session)
    7. Multi-cookie priority resolution (stale admin cookie cannot mask valid candidate session)
    """

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        FAILED_LOGIN_ATTEMPTS.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        # Seed test candidate
        candidate = UserAccount(
            email="candidate.persistence@example.com",
            full_name="Persistent Candidate",
            password_hash=hash_password("CandidateSecret123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add(candidate)
        db.commit()
        self.candidate_id = candidate.id
        db.close()

    def tearDown(self):
        client.cookies.clear()
        app.dependency_overrides.clear()

    def test_01_login_success_and_cookie_establishment(self):
        """Test 1: Valid credentials authenticate and establish session cookie."""
        # 1. Invalid credentials rejected
        bad_res = client.post("/api/candidate/login", json={
            "email": "candidate.persistence@example.com",
            "password": "WrongPassword!"
        })
        self.assertEqual(bad_res.status_code, 401)

        # 2. Valid credentials authenticate
        good_res = client.post("/api/candidate/login", json={
            "email": "candidate.persistence@example.com",
            "password": "CandidateSecret123!"
        })
        self.assertEqual(good_res.status_code, 200)
        data = good_res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("user", {}).get("email"), "candidate.persistence@example.com")

        # 3. Cookie is established
        self.assertIn("candidate_session", client.cookies)
        token_val = client.cookies.get("candidate_session")
        self.assertTrue(token_val)

        # 4. Auth state is immediately recognized
        me_res = client.get("/api/candidate/me")
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json().get("user", {}).get("email"), "candidate.persistence@example.com")

    def test_02_multi_instance_serverless_token_decoding(self):
        """
        Test 2: Verifies that multiple serverless instances sharing the same
        runtime environment derive identical secrets and can decode each other's tokens.
        """
        secrets_worker_a = _load_jwt_secrets()
        secrets_worker_b = _load_jwt_secrets()
        self.assertEqual(secrets_worker_a, secrets_worker_b)
        self.assertGreaterEqual(len(secrets_worker_a), 1)

        # Token created by instance A
        payload = {"sub": self.candidate_id, "email": "candidate.persistence@example.com", "role": "candidate"}
        token_from_a = create_access_token(payload)

        # Decoded by instance B
        decoded = decode_access_token(token_from_a)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.get("sub"), self.candidate_id)
        self.assertEqual(decoded.get("email"), "candidate.persistence@example.com")

    def test_03_protected_page_navigation(self):
        """
        Test 3: User logs in once and navigates across all authorized pages/endpoints
        without unexpected logout.
        """
        login_res = client.post("/api/candidate/login", json={
            "email": "candidate.persistence@example.com",
            "password": "CandidateSecret123!"
        })
        self.assertEqual(login_res.status_code, 200)

        # Navigation sequence across candidate studio endpoints
        navigation_targets = [
            ("/api/candidate/me", 200),
            ("/api/candidate/dashboard", 200),
            ("/candidate/dashboard", 200),
            ("/candidate/interview-studio", 200),
            ("/candidate/mock-interview", 200),
            ("/candidate/interview-coach", 200),
            ("/candidate/resume-match", 200),
            ("/candidate/history", 200),
            ("/history", 200),
            ("/api/mock-interview/history", 200),
            ("/api/coach/context", 200),
            ("/api/candidate/me", 200),
            ("/api/candidate/dashboard", 200),
        ]

        for path, expected_status in navigation_targets:
            res = client.get(path)
            self.assertEqual(
                res.status_code,
                expected_status,
                f"Failed navigation to {path}: received {res.status_code} instead of {expected_status}"
            )
            # Ensure candidate cookie remains preserved
            self.assertIn("candidate_session", client.cookies)

    def test_04_page_refresh_session_restoration(self):
        """Test 4: Page refresh verifies and restores session correctly."""
        client.post("/api/candidate/login", json={
            "email": "candidate.persistence@example.com",
            "password": "CandidateSecret123!"
        })
        for _ in range(5):
            res_me = client.get("/api/candidate/me")
            self.assertEqual(res_me.status_code, 200)
            res_dash = client.get("/api/candidate/dashboard")
            self.assertEqual(res_dash.status_code, 200)

    def test_05_authentication_expiration_and_tampering(self):
        """Test 5: Expired or tampered sessions are rejected with 401."""
        # 1. Expired token
        expired_token = create_access_token(
            {"sub": self.candidate_id, "role": "candidate"},
            expires_delta=timedelta(seconds=-10)
        )
        client.cookies.set("candidate_session", expired_token)
        res = client.get("/api/candidate/me")
        self.assertEqual(res.status_code, 401)

        # 2. Tampered token signature
        parts = expired_token.split(".")
        tampered_token = f"{parts[0]}.{parts[1]}.badsignaturehere"
        client.cookies.set("candidate_session", tampered_token)
        res2 = client.get("/api/candidate/me")
        self.assertEqual(res2.status_code, 401)

    def test_06_non_auth_error_does_not_clear_session(self):
        """Test 6: A 404 or bad parameter request does NOT destroy a valid session."""
        client.post("/api/candidate/login", json={
            "email": "candidate.persistence@example.com",
            "password": "CandidateSecret123!"
        })

        # Request to non-existent endpoint
        res_404 = client.get("/api/non-existent-endpoint-xyz")
        self.assertEqual(res_404.status_code, 404)

        # Subsequent authorized request still succeeds
        res_auth = client.get("/api/candidate/me")
        self.assertEqual(res_auth.status_code, 200)

    def test_07_multi_cookie_priority_resolution(self):
        """
        Test 7: When a browser carries both a valid candidate_session and a stale
        or invalid admin_session, the valid candidate_session is still accepted.
        """
        valid_candidate_tok = create_access_token({"sub": self.candidate_id, "role": "candidate"})
        stale_admin_tok = "invalid.stale.admin.cookie.value"

        client.cookies.set("candidate_session", valid_candidate_tok)
        client.cookies.set("admin_session", stale_admin_tok)

        res = client.get("/api/candidate/me")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("user", {}).get("email"), "candidate.persistence@example.com")


if __name__ == "__main__":
    unittest.main()
