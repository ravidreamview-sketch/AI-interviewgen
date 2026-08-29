"""
Automated Test Suite for AI Answer Evaluator Engine
Tests:
1. Presets endpoint (GET /api/evaluator/presets)
2. Single Answer Evaluation (POST /api/evaluator/evaluate) with STAR breakdown
3. Evaluator scoring heuristics, dimensions, strengths, weaknesses, and model rewrite
4. Authenticated candidate history persistence
5. Static route serving (/Answer-evaluator.html)
"""

import unittest
import json
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount, MockInterview
from app.security import hash_password, create_access_token
from app.evaluator_service import get_curated_presets, evaluate_candidate_answer


class TestAnswerEvaluator(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def setUp(self):
        self.db = self.TestingSessionLocal()
        self.db.query(MockInterview).delete()
        self.db.query(UserAccount).delete()
        self.db.commit()

        # Seed Test Candidate
        self.candidate = UserAccount(
            email="eval_candidate@example.com",
            password_hash=hash_password("Pass123!"),
            full_name="Evaluation Candidate",
            role="candidate",
            plan_tier="pro",
            created_at=datetime.utcnow()
        )
        self.db.add(self.candidate)
        self.db.commit()
        self.db.refresh(self.candidate)

        token = create_access_token({"sub": self.candidate.id, "role": "candidate"})
        self.auth_client = TestClient(app, cookies={"candidate_session": token})

    def tearDown(self):
        self.db.close()

    def test_get_evaluator_presets(self):
        """Verify GET /api/evaluator/presets returns curated presets."""
        resp = self.client.get("/api/evaluator/presets")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("categories", data)
        self.assertIn("presets", data)
        self.assertIn("roles", data)
        self.assertIn("Backend & Distributed Systems", data["presets"])
        self.assertTrue(len(data["presets"]["Backend & Distributed Systems"]) >= 2)

    def test_evaluate_strong_answer(self):
        """Verify POST /api/evaluator/evaluate on a high-fidelity STAR answer."""
        payload = {
            "question": "How do you design an idempotent payment processing API to prevent double-charging during network timeouts?",
            "answer": (
                "In my previous role at a fintech platform, we faced duplicate payment risks during client network timeouts at 35,000 RPS. "
                "My task was to build a zero-duplicate idempotency pipeline with strict sub-50ms p99 latency SLAs. "
                "I implemented an Idempotency-Key HTTP header protocol stored in Redis with distributed locks (Redlock) and a 120-second TTL. "
                "If a duplicate key arrived while the transaction was in-flight, our gateway streamed the in-progress promise or returned HTTP 409 Conflict. "
                "Once completed, the validated payload was persisted with database-level atomic upserts. "
                "As a result, we eliminated duplicate transaction chargebacks by 100%, reduced incident tickets by 45%, and saved $150K in customer refunds."
            ),
            "role": "Backend & Distributed Systems",
            "seniority": "Senior (5-8 yrs)",
            "company_tier": "FAANG / Tier-1"
        }
        resp = self.client.post("/api/evaluator/evaluate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertGreaterEqual(data["overall_score"], 75)
        self.assertIn("star_breakdown", data)
        self.assertGreaterEqual(data["star_breakdown"]["situation_score"], 15)
        self.assertGreaterEqual(data["star_breakdown"]["task_score"], 15)
        self.assertGreaterEqual(data["star_breakdown"]["action_score"], 15)
        self.assertGreaterEqual(data["star_breakdown"]["result_score"], 15)
        self.assertIn("dimensions", data)
        self.assertIn("technical_accuracy", data["dimensions"])
        self.assertTrue(len(data["strengths"]) >= 1)
        self.assertTrue(len(data["model_answer"]) > 50)
        self.assertTrue(len(data["actionable_improvements"]) >= 1)

    def test_evaluate_weak_answer(self):
        """Verify POST /api/evaluator/evaluate correctly flags short/vague answers."""
        payload = {
            "question": "How do you optimize a slow database query?",
            "answer": "I will check the database and add an index to the table.",
            "role": "Backend & Distributed Systems",
            "seniority": "Senior (5-8 yrs)"
        }
        resp = self.client.post("/api/evaluator/evaluate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertLessEqual(data["overall_score"], 70)
        self.assertTrue(len(data["weaknesses"]) >= 1)

    def test_authenticated_evaluation_persists_to_history(self):
        """Verify that authenticated evaluations save to candidate mock history."""
        payload = {
            "question": "Tell me about a time you resolved a major production incident.",
            "answer": "When our cache cluster failed, I initiated our incident bridge, failed over to the replica cluster in 90 seconds, and updated our circuit breakers.",
            "role": "Behavioral & Engineering Leadership",
            "seniority": "Staff / Principal (8+ yrs)"
        }
        resp = self.auth_client.post("/api/evaluator/evaluate", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("saved_to_history", False))

        # Check DB record
        record = self.db.query(MockInterview).filter(MockInterview.user_id == self.candidate.id).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.interview_mode, "answer_evaluator")

    def test_serve_answer_evaluator_html(self):
        """Verify /Answer-evaluator.html endpoint serves the HTML page."""
        resp = self.client.get("/Answer-evaluator.html")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("AI Answer Evaluator", resp.text)
        self.assertIn("runAnswerEvaluation", resp.text)


if __name__ == "__main__":
    unittest.main()
