"""Dashboard HTML delivery and separate API entitlement guards."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_deps import get_current_user, is_local_demo_access_enabled
from app.database import engine
from app.database import Base, get_db
from app.db_models import UserAccount
from app.main import app


class DashboardHtmlRoutingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as db:
            self.candidate = UserAccount(
                email="dashboard-candidate@example.test",
                password_hash="test-hash",
                role="candidate",
                plan_tier="pro",
                is_active=True,
            )
            self.admin = UserAccount(
                email="dashboard-admin@example.test",
                password_hash="test-hash",
                role="admin",
                plan_tier="enterprise",
                is_active=True,
            )
            self.inactive_candidate = UserAccount(
                email="inactive-dashboard-candidate@example.test",
                password_hash="test-hash",
                role="candidate",
                is_active=False,
            )
            db.add_all([self.candidate, self.admin, self.inactive_candidate])
            db.commit()
            self.candidate_id = self.candidate.id
            self.admin_id = self.admin.id
            self.inactive_candidate_id = self.inactive_candidate.id

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides.pop(get_current_user, None)
        self.client = TestClient(
            app,
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 50000),
        )

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        self.client.close()
        self.engine.dispose()

    def _use_user(self, user_id: int):
        def get_user():
            with self.Session() as db:
                return db.get(UserAccount, user_id)
        app.dependency_overrides[get_current_user] = get_user

    @staticmethod
    def _local_demo_environment(enabled="true"):
        return patch.dict("os.environ", {
            "ENV": "test",
            "LOCAL_DEMO_ACCESS": enabled,
            "DEV_AUTH_BYPASS": "false",
            "VERCEL": "",
            "AWS_LAMBDA_FUNCTION_NAME": "",
            "K_SERVICE": "",
            "DYNO": "",
            "RENDER": "",
            "RAILWAY_ENVIRONMENT": "",
            "FLY_APP_NAME": "",
            "WEBSITE_INSTANCE_ID": "",
        }, clear=False)

    def test_dashboard_html_returns_html_for_an_authenticated_candidate(self):
        self._use_user(self.candidate_id)

        response = self.client.get("/Dashboard.html")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Interview Studio Dashboard", response.text)
        self.assertIn("const API_BASE = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';", response.text)
        self.assertNotIn("An active, administrator-approved subscription", response.text)

    def test_vercel_rewrite_path_is_dispatched_to_the_dashboard_html_route(self):
        self._use_user(self.candidate_id)

        response = self.client.get("/api/index.py?__path=/Dashboard.html")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Interview Studio Dashboard", response.text)

    def test_local_preview_opens_all_candidate_module_pages_without_entitlement(self):
        self._use_user(self.candidate_id)
        page_routes = {
            "/Candidate-dashboard.html": "Candidate Dashboard",
            "/Interview-studio.html": "Interview Studio",
            "/Answer-evaluator.html": "Answer Evaluator",
            "/Mock-interview.html": "Mock Interview",
            "/Resume-match.html": "Resume",
            "/Company-playbooks.html": "Company",
            "/Interview history.html": "Interview History",
            "/Interview-coach.html": "Interview Coach",
        }

        with self._local_demo_environment():
            for path, page_title in page_routes.items():
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertIn("text/html", response.headers["content-type"])
                    self.assertIn(page_title.casefold(), response.text.casefold())

    def test_production_module_pages_still_require_approved_entitlement(self):
        self._use_user(self.candidate_id)

        with patch.dict("os.environ", {
            "ENV": "production", "LOCAL_DEMO_ACCESS": "true", "VERCEL": "1",
        }, clear=False):
            response = self.client.get("/Interview-studio.html")

        self.assertEqual(response.status_code, 402, response.text)

    def test_explicit_local_demo_mode_allows_paid_feature_api_after_sign_in(self):
        self._use_user(self.candidate_id)

        with self._local_demo_environment():
            response = self.client.get("/api/interview/providers")

        self.assertEqual(response.status_code, 200, response.text)

    def test_local_demo_mode_still_requires_authentication(self):
        with self._local_demo_environment():
            response = self.client.get("/api/interview/providers")

        self.assertEqual(response.status_code, 401, response.text)

    def test_local_demo_mode_still_rejects_inactive_and_non_candidate_accounts(self):
        with self._local_demo_environment():
            self._use_user(self.inactive_candidate_id)
            inactive = self.client.get("/api/interview/providers")
            self.assertEqual(inactive.status_code, 403, inactive.text)

            self._use_user(self.admin_id)
            administrator = self.client.get("/api/interview/providers")
            self.assertEqual(administrator.status_code, 403, administrator.text)

    def test_local_setting_alone_does_not_enable_access_in_unknown_or_hosted_runtime(self):
        self._use_user(self.candidate_id)
        cases = (
            {"ENV": "", "LOCAL_DEMO_ACCESS": "true", "VERCEL": ""},
            {"ENV": "local", "LOCAL_DEMO_ACCESS": "true", "VERCEL": "1"},
        )

        for environment in cases:
            with self.subTest(environment=environment), patch.dict("os.environ", environment, clear=False):
                response = self.client.get("/api/interview/providers")
                self.assertEqual(response.status_code, 402, response.text)

    def test_local_demo_access_is_disabled_when_setting_is_unset(self):
        self._use_user(self.candidate_id)

        with self._local_demo_environment(enabled=""):
            response = self.client.get("/api/interview/providers")

        self.assertEqual(response.status_code, 402, response.text)

    def test_local_demo_access_fails_closed_for_non_sqlite_database_engine(self):
        with self._local_demo_environment(), patch.object(engine.dialect, "name", "postgresql"):
            self.assertFalse(is_local_demo_access_enabled())

    def test_local_runtime_requires_loopback_client_and_host(self):
        local_scope = {
            "type": "http", "method": "GET", "scheme": "http", "path": "/",
            "raw_path": b"/", "query_string": b"", "headers": [(b"host", b"127.0.0.1:8002")],
            "client": ("127.0.0.1", 51000), "server": ("127.0.0.1", 8002),
        }
        public_scope = {
            **local_scope,
            "headers": [(b"host", b"demo.example.com")],
            "client": ("203.0.113.20", 51000),
            "server": ("demo.example.com", 443),
            "scheme": "https",
        }
        with self._local_demo_environment(), patch.dict("os.environ", {"ENV": "local"}, clear=False):
            self.assertTrue(is_local_demo_access_enabled(Request(local_scope)))
            self.assertFalse(is_local_demo_access_enabled(Request(public_scope)))

    def test_dashboard_html_requires_authentication_and_candidate_role(self):
        anonymous = self.client.get("/Dashboard.html")
        self.assertEqual(anonymous.status_code, 401)

        self._use_user(self.admin_id)
        administrator = self.client.get("/Dashboard.html")
        self.assertEqual(administrator.status_code, 403)

    def test_dashboard_api_keeps_authentication_and_subscription_checks(self):
        anonymous = self.client.get("/api/candidate/dashboard")
        self.assertEqual(anonymous.status_code, 401)

        self._use_user(self.candidate_id)
        candidate = self.client.get("/api/candidate/dashboard")
        self.assertEqual(candidate.status_code, 402, candidate.text)

    def test_paid_feature_api_remains_denied_without_an_approved_subscription(self):
        self._use_user(self.candidate_id)

        with patch.dict("os.environ", {"ENV": "local", "LOCAL_DEMO_ACCESS": "false"}, clear=False):
            response = self.client.post("/generate", json={
                "role": "Engineer",
                "experience": "3 years",
                "skills": ["Python"],
                "difficulty": "Medium",
                "number_of_questions": 1,
            })

        self.assertEqual(response.status_code, 402, response.text)


if __name__ == "__main__":
    unittest.main()
