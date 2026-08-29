import unittest
import os
import sys
import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount
from app.security import hash_password
from app.auth_deps import FAILED_LOGIN_ATTEMPTS

# Setup isolated in-memory SQLite database
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


class TestCandidateLoginHTTP405Fix(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        FAILED_LOGIN_ATTEMPTS.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        # Seed test candidate
        candidate = UserAccount(
            email="candidate@example.com",
            password_hash=hash_password("CandidatePass123!"),
            full_name="Alex Candidate",
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add(candidate)
        db.commit()
        db.close()

    def tearDown(self):
        app.dependency_overrides.clear()
        client.cookies.clear()

    def test_1_post_api_candidate_login_returns_200_and_httponly_cookie(self):
        """
        Verifies POST /api/candidate/login successfully authenticates valid credentials,
        returns HTTP 200 with success status, and sets an HttpOnly candidate_session cookie.
        """
        response = client.post("/api/candidate/login", json={
            "email": "candidate@example.com",
            "password": "CandidatePass123!"
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("role"), "candidate")
        self.assertIn("candidate_session", response.cookies)

        # Inspect raw Set-Cookie header for HttpOnly flag and Path=/
        set_cookie_header = response.headers.get("set-cookie", "")
        self.assertIn("candidate_session=", set_cookie_header)
        self.assertIn("HttpOnly", set_cookie_header)
        self.assertIn("Path=/", set_cookie_header)

    def test_2_post_candidate_login_alias_routes(self):
        """
        Verifies all standard candidate login POST endpoints route correctly to candidate_login.
        """
        for route in ["/candidate/login", "/api/login", "/login"]:
            client.cookies.clear()
            res = client.post(route, json={
                "email": "candidate@example.com",
                "password": "CandidatePass123!"
            })
            self.assertEqual(res.status_code, 200, f"Route {route} failed with status {res.status_code}")
            self.assertTrue(res.json().get("success"))
            self.assertIn("candidate_session", res.cookies)

    def test_3_get_candidate_login_serves_html_without_405(self):
        """
        Verifies GET /api/candidate/login and GET /candidate/login serve the HTML login page
        with HTTP 200 rather than returning HTTP 405 Method Not Allowed.
        """
        for route in ["/api/candidate/login", "/candidate/login", "/login", "/Candidate-login.html"]:
            res = client.get(route)
            self.assertEqual(res.status_code, 200, f"GET route {route} failed with {res.status_code}")
            self.assertIn("text/html", res.headers.get("content-type", ""))
            self.assertIn("Candidate Login", res.text)

    def test_4_frontend_candidate_login_html_contains_prevent_default_and_post_fetch(self):
        """
        Verifies Candidate-login.html includes event.preventDefault() in its submit handler,
        sets method='POST' and action='javascript:void(0);' on the form, and issues a POST fetch to /api/candidate/login.
        """
        root_dir = Path(__file__).resolve().parent.parent
        html_path = root_dir / "Candidate-login.html"
        self.assertTrue(html_path.exists(), "Candidate-login.html not found")

        content = html_path.read_text(encoding="utf-8")

        # Form tag assertions
        self.assertIn('id="candidateLoginForm"', content)
        self.assertIn('method="POST"', content)
        self.assertIn('action="javascript:void(0);"', content)
        self.assertIn('onsubmit="handleCandidateLogin(event)"', content)

        # JavaScript logic assertions
        self.assertIn("event.preventDefault()", content)
        self.assertTrue('fetch("/api/candidate/login"' in content or "fetch('/api/candidate/login'" in content)
        self.assertTrue('method: "POST"' in content or "method: 'POST'" in content)
        self.assertTrue('credentials: "include"' in content or "credentials: 'include'" in content)
        self.assertTrue('"Content-Type": "application/json"' in content or "'Content-Type': 'application/json'" in content)

    def test_5_vercel_json_routing_configuration(self):
        """
        Verifies vercel.json rewrites /api/:path* to /api/index.py ensuring POST /api/candidate/login
        reaches the ASGI backend function without being intercepted by static HTML rewrites.
        """
        root_dir = Path(__file__).resolve().parent.parent
        vercel_json_path = root_dir / "vercel.json"
        self.assertTrue(vercel_json_path.exists(), "vercel.json not found")

        with open(vercel_json_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        rewrites = config.get("rewrites", [])
        api_rewrite = next((r for r in rewrites if r.get("source") in ["/api/:match*", "/api/:path*"]), None)
        self.assertIsNotNone(api_rewrite, "Missing /api/:match* rewrite in vercel.json")
        self.assertTrue(api_rewrite.get("destination", "").startswith("/api/index.py"))
        self.assertIn("__path=", api_rewrite.get("destination", ""))


if __name__ == "__main__":
    unittest.main()
