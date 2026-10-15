"""Persistence and ownership tests for generated interview question papers.

All requests use an isolated in-memory SQLite database. Subscription entitlement
is mocked only so these tests can focus on persistence; candidate authentication
and role validation still run through the normal dependency chain.
"""

import os
import unittest
from unittest.mock import patch

# Pin the application's import-time database engine to local SQLite before
# importing app modules. Request dependencies below use a separate in-memory DB.
_pinned_environment = {
    name: os.environ.get(name)
    for name in ("ENV", "DATABASE_URL", "LOCAL_DEMO_ACCESS", "DEV_AUTH_BYPASS")
}
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LOCAL_DEMO_ACCESS"] = "0"
os.environ["DEV_AUTH_BYPASS"] = "0"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import database
from app.db_models import InterviewHistory, UserAccount
from app.main import app
from app.security import create_access_token
from app.services import AIProviderError

for _name, _value in _pinned_environment.items():
    if _value is None:
        os.environ.pop(_name, None)
    else:
        os.environ[_name] = _value


class TestQuestionGenerationPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        cls.override_get_db = override_get_db
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        db = self.SessionLocal()
        db.query(InterviewHistory).delete()
        db.query(UserAccount).delete()
        self.candidate_a = UserAccount(
            email="candidate-a@example.test",
            full_name="Candidate A",
            password_hash="test-only-unused",
            role="candidate",
            plan_tier="free",
            is_active=True,
        )
        self.candidate_b = UserAccount(
            email="candidate-b@example.test",
            full_name="Candidate B",
            password_hash="test-only-unused",
            role="candidate",
            plan_tier="free",
            is_active=True,
        )
        db.add_all([self.candidate_a, self.candidate_b])
        db.commit()
        self.user_a_id = self.candidate_a.id
        self.user_b_id = self.candidate_b.id
        self.token_a = create_access_token({"sub": str(self.user_a_id), "email": self.candidate_a.email, "role": "candidate"})
        self.token_b = create_access_token({"sub": str(self.user_b_id), "email": self.candidate_b.email, "role": "candidate"})
        db.close()
        self.entitlement_patch = patch("app.subscription_service.ensure_candidate_entitlement", return_value=None)
        self.entitlement_patch.start()

    def tearDown(self):
        self.entitlement_patch.stop()

    def headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def request_payload(self):
        return {
            "role": "Backend Engineer",
            "experience": "5 Years",
            "skills": ["Python", "FastAPI"],
            "difficulty": "Hard",
            "interview_type": "System Design",
            "company": "Example Corp",
            "number_of_questions": 2,
        }

    def test_generated_questions_persist_and_dashboard_counts_saved_session(self):
        generated = "1. How would you design a resilient task queue?\n2. Explain idempotency in distributed APIs."
        with patch("app.main.generate_ai_questions", return_value=generated):
            response = self.client.post("/api/generate", headers=self.headers(self.token_a), json=self.request_payload())

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertGreater(payload["id"], 0)
        self.assertEqual(payload["questions"], [
            "How would you design a resilient task queue?",
            "Explain idempotency in distributed APIs.",
        ])
        self.assertEqual(payload["interview_type"], "System Design")
        self.assertEqual(payload["company"], "Example Corp")
        self.assertEqual(payload["requested_question_count"], 2)

        # A fresh ORM session and subsequent HTTP request see the committed record.
        with self.SessionLocal() as db:
            saved = db.query(InterviewHistory).filter_by(id=payload["id"]).one()
            self.assertEqual(saved.user_id, self.user_a_id)
            self.assertIn("How would you design a resilient task queue?", saved.questions)
            self.assertEqual(saved.interview_type, "System Design")
            self.assertEqual(saved.company, "Example Corp")

        detail = self.client.get(f"/api/history/{payload['id']}", headers=self.headers(self.token_a))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["questions"], payload["questions"])

        dashboard = self.client.get("/api/candidate/dashboard", headers=self.headers(self.token_a))
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        data = dashboard.json()
        self.assertEqual(data["questions_practiced"], 2)
        self.assertEqual(data["question_generation_sessions"], 1)
        question_activity = next(item for item in data["recent_activity"] if item["type"] == "question_practice")
        self.assertEqual(question_activity["record_id"], payload["id"])

    def test_candidates_only_list_and_open_their_own_saved_sessions(self):
        with patch(
            "app.main.generate_ai_questions",
            return_value="1. Candidate A private question\n2. Candidate A follow-up question",
        ):
            response = self.client.post("/api/generate", headers=self.headers(self.token_a), json=self.request_payload())
        self.assertEqual(response.status_code, 200, response.text)
        saved_id = response.json()["id"]

        list_b = self.client.get("/api/history", headers=self.headers(self.token_b))
        self.assertEqual(list_b.status_code, 200)
        self.assertEqual(list_b.json(), [])
        detail_b = self.client.get(f"/api/history/{saved_id}", headers=self.headers(self.token_b))
        self.assertEqual(detail_b.status_code, 404)

    def test_generation_failure_does_not_create_a_history_record(self):
        provider_key = "private-provider-key"
        with patch(
            "app.main.generate_ai_questions",
            side_effect=AIProviderError("Provider rejected request safely", 503, "authentication"),
        ):
            response = self.client.post("/api/generate", headers=self.headers(self.token_a), json=self.request_payload())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get("X-AI-Error-Category"), "authentication")
        self.assertNotIn(provider_key, response.text)
        self.assertNotIn("Authorization", response.text)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(InterviewHistory).count(), 0)

    def test_provider_failure_categories_are_returned_without_changing_error_body(self):
        failures = (
            (AIProviderError("Credentials rejected safely.", 503, "authentication"), 503, "authentication"),
            (AIProviderError("Configured model rejected safely.", 502, "model_or_request_configuration"), 502, "model_or_request_configuration"),
            (AIProviderError("Provider rate limit reached safely.", 503, "rate_limit_or_quota"), 503, "rate_limit_or_quota"),
            (AIProviderError("Provider timed out safely.", 504, "timeout"), 504, "timeout"),
            (AIProviderError("Provider response was malformed.", 502, "malformed_response"), 502, "malformed_response"),
        )

        for error, expected_status, expected_category in failures:
            with self.subTest(category=expected_category), patch(
                "app.main.generate_ai_questions",
                side_effect=error,
            ):
                response = self.client.post(
                    "/api/generate",
                    headers=self.headers(self.token_a),
                    json=self.request_payload(),
                )

            self.assertEqual(response.status_code, expected_status)
            self.assertEqual(response.headers.get("X-AI-Error-Category"), expected_category)
            self.assertEqual(response.json()["detail"], str(error))

    def test_persistence_failure_is_reported_and_rolled_back(self):
        with patch(
            "app.main.generate_ai_questions",
            return_value="1. A generated question\n2. A second generated question",
        ), patch.object(
            Session, "commit", side_effect=RuntimeError("simulated isolated DB write failure")
        ):
            response = self.client.post("/api/generate", headers=self.headers(self.token_a), json=self.request_payload())
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Generated questions could not be saved. Please retry.")
        with self.SessionLocal() as db:
            self.assertEqual(db.query(InterviewHistory).count(), 0)

    def test_additive_schema_upgrade_preserves_existing_interview_rows(self):
        migration_engine = create_engine("sqlite:///:memory:")
        with migration_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE interview_history ("
                "id INTEGER PRIMARY KEY, user_id INTEGER, adaptive_session_id VARCHAR, "
                "role VARCHAR NOT NULL, experience VARCHAR NOT NULL, skills TEXT NOT NULL, "
                "difficulty VARCHAR NOT NULL, questions TEXT NOT NULL, "
                "question_engine_version VARCHAR, created_at DATETIME)"
            ))
            connection.execute(text(
                "INSERT INTO interview_history (id, role, experience, skills, difficulty, questions) "
                "VALUES (1, 'Engineer', '3 years', 'Python', 'Hard', '1. Existing saved question')"
            ))

        try:
            with patch.object(database, "engine", migration_engine):
                database._run_migration_interview_history("sqlite")
            columns = {column["name"] for column in inspect(migration_engine).get_columns("interview_history")}
            self.assertTrue({"interview_type", "company", "requested_question_count"}.issubset(columns))
            with migration_engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("SELECT questions FROM interview_history WHERE id = 1")).scalar_one(),
                    "1. Existing saved question",
                )
        finally:
            migration_engine.dispose()


if __name__ == "__main__":
    unittest.main()
