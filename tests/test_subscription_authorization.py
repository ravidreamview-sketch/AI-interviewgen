"""Route guard regressions using only a temporary local SQLite database."""

import os
os.environ["PYTHON_DOTENV_DISABLED"] = "true"

import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.auth_deps import get_current_user
from app.db_models import UserAccount


class SubscriptionAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as db:
            self.candidate = UserAccount(
                email="route-candidate@example.invalid", password_hash="hash",
                role="candidate", plan_tier="enterprise", is_active=True,
            )
            db.add(self.candidate)
            db.commit()
            self.candidate_id = self.candidate.id
        self.client = TestClient(app)
        app.dependency_overrides[get_db] = self.override_db

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        self.client.close()
        self.engine.dispose()

    def override_db(self):
        with self.Session() as db:
            yield db

    def test_paid_evaluator_api_rejects_anonymous_requests(self):
        response = self.client.post("/api/evaluator/evaluate", json={})
        self.assertEqual(response.status_code, 401)

    def test_paid_interview_provider_api_rejects_anonymous_requests(self):
        response = self.client.get("/api/interview/providers")
        self.assertEqual(response.status_code, 401)

    def test_paid_generation_api_denies_candidate_with_only_legacy_plan_label(self):
        with self.Session() as db:
            candidate = db.get(UserAccount, self.candidate_id)
        app.dependency_overrides[get_current_user] = lambda: candidate
        response = self.client.post("/generate", json={
            "role": "Engineer", "experience": "3 years", "skills": ["Python"],
            "difficulty": "Medium", "number_of_questions": 1,
        })
        self.assertEqual(response.status_code, 402)

    def test_paid_private_html_requires_entitlement(self):
        with self.Session() as db:
            candidate = db.get(UserAccount, self.candidate_id)
        app.dependency_overrides[get_current_user] = lambda: candidate
        response = self.client.get("/candidate/dashboard")
        self.assertEqual(response.status_code, 402)

    def test_direct_private_html_url_requires_admin_role(self):
        response = self.client.get("/Admin.html")
        self.assertEqual(response.status_code, 401)

    def test_candidate_cannot_call_admin_subscription_assignment(self):
        with self.Session() as db:
            candidate = db.get(UserAccount, self.candidate_id)
        app.dependency_overrides[get_current_user] = lambda: candidate
        response = self.client.post("/api/admin/subscriptions", json={})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
