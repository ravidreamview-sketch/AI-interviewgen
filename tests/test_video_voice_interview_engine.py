"""
Automated Test Suite for Real-Time Video + Voice Conversational AI Interview Engine
Tests:
1. Session Initialization (POST /api/interview/start)
2. Turn Answer Evaluation and Contextual Follow-up (POST /api/interview/{id}/answer)
3. Session Finalization and Scorecard Generation (POST /api/interview/{id}/complete)
4. Active Providers Query (GET /api/interview/providers)
5. Tenant Ownership & Isolation Controls
6. STT, TTS, and Avatar Abstraction Layer Fallbacks
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
from app.speech_service import get_stt_provider, BrowserSpeechProvider
from app.tts_service import get_tts_provider, BrowserSynthesisTTSProvider
from app.avatar_service import get_avatar_provider, InteractiveCanvasAvatarProvider


class TestVideoVoiceInterviewEngine(unittest.TestCase):

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

        # Seed Test Candidate 1
        self.candidate1 = UserAccount(
            email="candidate1@example.com",
            password_hash=hash_password("Pass123!"),
            full_name="Candidate One",
            role="candidate",
            plan_tier="pro",
            created_at=datetime.utcnow()
        )
        # Seed Test Candidate 2 (for tenant isolation test)
        self.candidate2 = UserAccount(
            email="candidate2@example.com",
            password_hash=hash_password("Pass123!"),
            full_name="Candidate Two",
            role="candidate",
            plan_tier="free",
            created_at=datetime.utcnow()
        )
        self.db.add(self.candidate1)
        self.db.add(self.candidate2)
        self.db.commit()
        self.db.refresh(self.candidate1)
        self.db.refresh(self.candidate2)

        token1 = create_access_token({"sub": self.candidate1.id, "role": "candidate"})
        token2 = create_access_token({"sub": self.candidate2.id, "role": "candidate"})
        self.client1 = TestClient(app, cookies={"candidate_session": token1})
        self.client2 = TestClient(app, cookies={"candidate_session": token2})

    def tearDown(self):
        self.db.close()

    def test_providers_endpoint(self):
        """Verify GET /api/interview/providers returns active provider capabilities."""
        resp = self.client.get("/api/interview/providers")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("stt", data)
        self.assertIn("tts", data)
        self.assertIn("avatar", data)
        self.assertIn("alex", data["avatar"]["supported_personas"])

    def test_provider_fallbacks(self):
        """Verify provider factories instantiate safe browser/canvas fallbacks."""
        stt = get_stt_provider()
        self.assertIsInstance(stt, BrowserSpeechProvider)
        self.assertTrue(stt.is_available())

        tts = get_tts_provider()
        self.assertIsInstance(tts, BrowserSynthesisTTSProvider)
        self.assertTrue(tts.is_available())

        avatar = get_avatar_provider()
        self.assertIsInstance(avatar, InteractiveCanvasAvatarProvider)
        self.assertTrue(avatar.is_available())
        meta = avatar.get_persona_avatar_metadata("alex")
        self.assertEqual(meta["name"], "Alex")

    def test_interview_session_start_video_voice(self):
        """Verify POST /api/interview/start initializes session with first question."""
        payload = {
            "role": "Python Backend Engineer",
            "skills": ["FastAPI", "PostgreSQL", "System Architecture"],
            "persona": "alex",
            "mode": "video_voice"
        }
        resp = self.client1.post("/api/interview/start", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["interview_id"].startswith("mock_"))
        self.assertTrue(len(data["first_question"]) > 10)
        self.assertEqual(data["persona"]["name"], "Alex")
        self.assertEqual(data["mode"], "video_voice")

    def test_interview_turn_answer_and_followup(self):
        """Verify POST /api/interview/{id}/answer evaluates speech and returns follow-up."""
        # 1. Start Session
        start_payload = {
            "role": "Senior Cloud Architect",
            "skills": ["Distributed Systems", "Kubernetes", "Kafka"],
            "persona": "elena",
            "mode": "video_voice"
        }
        start_res = self.client1.post("/api/interview/start", json=start_payload)
        self.assertEqual(start_res.status_code, 200)
        interview_id = start_res.json()["interview_id"]

        # 2. Answer Turn 1
        ans_payload = {
            "answer_text": "In our architecture, we partitioned Kafka topics by customer ID and implemented dead-letter queues with exponential backoff to handle transient consumer errors at 50,000 requests per second."
        }
        ans_res = self.client1.post(f"/api/interview/{interview_id}/answer", json=ans_payload)
        self.assertEqual(ans_res.status_code, 200)
        ans_data = ans_res.json()
        self.assertIn("evaluation", ans_data)
        self.assertGreaterEqual(ans_data["evaluation"]["score"], 40)
        self.assertIn("next_question", ans_data)
        self.assertTrue(len(ans_data["next_question"]) > 10)

    def test_interview_completion_scorecard(self):
        """Verify POST /api/interview/{id}/complete computes final scorecard and persists."""
        # 1. Start Session
        start_payload = {
            "role": "Engineering Manager",
            "skills": ["Leadership", "STAR Method", "Cross-Functional Collaboration"],
            "persona": "marcus",
            "mode": "voice_only"
        }
        start_res = self.client1.post("/api/interview/start", json=start_payload)
        interview_id = start_res.json()["interview_id"]

        # 2. Submit Turn Answer
        self.client1.post(f"/api/interview/{interview_id}/answer", json={
            "answer_text": "When two senior engineers disagreed on adopting GraphQL, I organized a time-boxed spike where each tested their approach on staging, evaluated latency metrics, and presented findings to the team."
        })

        # 3. Complete Session
        comp_res = self.client1.post(f"/api/interview/{interview_id}/complete")
        self.assertEqual(comp_res.status_code, 200)
        comp_data = comp_res.json()
        self.assertGreaterEqual(comp_data["overall_score"], 50)
        self.assertGreaterEqual(comp_data["technical_score"], 50)
        self.assertGreaterEqual(comp_data["communication_score"], 50)
        self.assertTrue(len(comp_data["strengths"]) >= 1)
        self.assertTrue(len(comp_data["recommendations"]) >= 1)
        self.assertEqual(comp_data["status"], "completed")

        # 4. Verify DB record persisted
        rec_id = int(interview_id.replace("mock_", ""))
        record = self.db.query(MockInterview).filter(MockInterview.id == rec_id).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.user_id, self.candidate1.id)

    def test_tenant_isolation_unauthorized_access(self):
        """Verify Candidate 2 cannot answer or complete Candidate 1's interview session."""
        # Candidate 1 starts an interview
        start_res = self.client1.post("/api/interview/start", json={
            "role": "Product Designer",
            "skills": ["Design Systems", "Figma"],
            "persona": "alex",
            "mode": "video_voice"
        })
        interview_id = start_res.json()["interview_id"]

        # Candidate 2 attempts to submit answer to Candidate 1's interview
        tamper_res = self.client2.post(f"/api/interview/{interview_id}/answer", json={
            "answer_text": "I will try to tamper with candidate 1 session."
        })
        self.assertEqual(tamper_res.status_code, 403)
        self.assertIn("Forbidden", tamper_res.json()["detail"])

        # Candidate 2 attempts to complete Candidate 1's interview
        tamper_comp = self.client2.post(f"/api/interview/{interview_id}/complete")
        self.assertEqual(tamper_comp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
