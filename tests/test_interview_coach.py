import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.database import Base, get_db
from app.db_models import (
    CandidateMistakesLedger,
    CandidateSkillAnalytics,
    CoachSession,
    InterviewHistory,
    MockInterview,
    ResumeScan,
    UserAccount,
)
from app.main import app
from app.security import create_access_token, hash_password


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestInterviewCoach(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with TestingSessionLocal() as db:
            self.candidate = UserAccount(
                email="coach_candidate@example.com",
                full_name="Coach Candidate",
                password_hash=hash_password("CoachPass123!"),
                role="candidate",
                is_active=True,
            )
            self.other_candidate = UserAccount(
                email="other_coach_candidate@example.com",
                password_hash=hash_password("OtherPass123!"),
                role="candidate",
                is_active=True,
            )
            db.add_all([self.candidate, self.other_candidate])
            db.commit()
            self.candidate_id = self.candidate.id
            self.other_candidate_id = self.other_candidate.id

        self.login_as(self.candidate_id, "coach_candidate@example.com")

    def tearDown(self):
        client.cookies.clear()
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)

    @staticmethod
    def login_as(user_id, email):
        token = create_access_token({
            "sub": user_id,
            "email": email,
            "role": "candidate",
        })
        client.cookies.set("candidate_session", token)

    def test_coach_page_routes_and_sidebar_are_integrated(self):
        for path in ("/interview-coach", "/Interview-coach.html"):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('class="nav-link active"', response.text)
            self.assertIn('href="/interview-coach"', response.text)
            self.assertNotIn("72%", response.text)
            self.assertIn('id="coachNewConversation"', response.text)
            self.assertIn('id="coachReadinessValue"', response.text)

    def test_chat_requires_authentication(self):
        client.cookies.clear()
        with patch.dict(os.environ, {"DEV_AUTH_BYPASS": "false"}):
            response = client.post("/api/coach/chat", json={"message": "Help me prepare"})
        self.assertEqual(response.status_code, 401)

    @patch("app.main.generate_coach_reply", return_value="Practice concise STAR answers.")
    def test_chat_persists_and_restores_conversation(self, generate_reply):
        response = client.post(
            "/api/coach/chat",
            json={"message": "What should I practice today?"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["message"], "Practice concise STAR answers.")
        self.assertIsInstance(data["conversation_id"], int)
        generate_reply.assert_called_once()

        history = client.get("/api/coach/conversation")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["conversation_id"], data["conversation_id"])
        self.assertEqual(
            [item["role"] for item in history.json()["messages"]],
            ["user", "assistant"],
        )

        new_conversation = client.post("/api/coach/conversations")
        self.assertEqual(new_conversation.status_code, 200)
        new_id = new_conversation.json()["conversation_id"]
        self.assertNotEqual(new_id, data["conversation_id"])

        conversations = client.get("/api/coach/conversations")
        self.assertEqual(conversations.status_code, 200)
        self.assertEqual(
            {item["conversation_id"] for item in conversations.json()["conversations"]},
            {new_id, data["conversation_id"]},
        )
        previous = client.get(f"/api/coach/conversations/{data['conversation_id']}")
        self.assertEqual(previous.status_code, 200)
        self.assertEqual(len(previous.json()["messages"]), 2)

    def test_context_is_candidate_scoped_and_readiness_requires_real_data(self):
        empty_context = client.get("/api/coach/context")
        self.assertEqual(empty_context.status_code, 200)
        self.assertEqual(empty_context.json()["candidate"]["id"], self.candidate_id)
        self.assertIsNone(empty_context.json()["readiness"]["score"])

        with TestingSessionLocal() as db:
            db.add_all([
                InterviewHistory(
                    user_id=self.candidate_id,
                    role="Product Designer",
                    experience="Senior",
                    skills="UX research,Product thinking",
                    difficulty="Hard",
                    questions="1. How would you validate a new product concept?",
                ),
                InterviewHistory(
                    user_id=self.other_candidate_id,
                    role="Unrelated private role",
                    experience="Senior",
                    skills="Secret",
                    difficulty="Hard",
                    questions="1. Private candidate question",
                ),
                MockInterview(
                    user_id=self.candidate_id,
                    role="Product Designer",
                    score=64,
                    technical_accuracy=70,
                    communication_clarity=60,
                    star_depth=65,
                    confidence_score=62,
                    status="completed",
                ),
                MockInterview(
                    user_id=self.candidate_id,
                    role="Unfinished mock interview",
                    score=0,
                    status="in_progress",
                ),
                ResumeScan(
                    user_id=self.candidate_id,
                    target_role="Product Designer",
                    overall_match_score=78,
                    matched_skills='["UX research"]',
                    missing_skills='["Product analytics"]',
                ),
            ])
            db.commit()

        context = client.get("/api/coach/context")
        self.assertEqual(context.status_code, 200)
        data = context.json()
        self.assertEqual(data["candidate"]["target_role"], "Product Designer")
        self.assertEqual(data["candidate"]["experience"], "Senior")
        self.assertEqual(data["interview_stats"]["questions_generated"], 1)
        self.assertEqual(data["interview_stats"]["completed_interviews"], 1)
        self.assertEqual(len(data["recent_interviews"]), 1)
        self.assertEqual(data["recent_questions"][0]["question"], "How would you validate a new product concept?")
        self.assertEqual(data["resume_match"]["missing_skills"], ["Product analytics"])
        self.assertEqual(data["readiness"]["score"], 44)
        self.assertNotIn("Unrelated private role", str(data))
        self.assertNotIn("Unfinished mock interview", str(data))
        self.assertNotIn("Private candidate question", str(data))

    def test_candidate_cannot_use_another_candidates_conversation(self):
        with TestingSessionLocal() as db:
            conversation = CoachSession(user_id=self.other_candidate_id)
            db.add(conversation)
            db.commit()
            other_conversation_id = conversation.id

        response = client.post(
            "/api/coach/chat",
            json={
                "message": "Continue this conversation",
                "conversation_id": other_conversation_id,
            },
        )
        self.assertEqual(response.status_code, 404)
        get_response = client.get(f"/api/coach/conversations/{other_conversation_id}")
        self.assertEqual(get_response.status_code, 404)

    def test_coach_prompt_uses_saved_candidate_practice_data(self):
        with TestingSessionLocal() as db:
            db.add_all([
                CandidateSkillAnalytics(
                    user_id=self.candidate_id,
                    skill="System design",
                    score=42,
                    trend="declining",
                ),
                CandidateMistakesLedger(
                    user_id=self.candidate_id,
                    adaptive_session_id="coach-test-session",
                    skill="System design",
                    description="Needs clearer trade-off analysis.",
                    severity="medium",
                ),
                MockInterview(
                    user_id=self.candidate_id,
                    role="Backend Engineer",
                    score=61,
                    transcript="Missed the database partitioning trade-off.",
                ),
                ResumeScan(
                    user_id=self.candidate_id,
                    target_role="Backend Engineer",
                    overall_match_score=70,
                    missing_skills="Distributed systems",
                ),
            ])
            db.commit()

        with patch(
            "app.coach_service.generate_ai_questions",
            return_value="Practice distributed systems trade-offs.",
        ) as provider:
            response = client.post(
                "/api/coach/chat",
                json={"message": "What should I improve?"},
            )

        self.assertEqual(response.status_code, 200)
        prompt = provider.call_args.args[0]
        self.assertIn("System design: 42.0/100 (declining, identified)", prompt)
        self.assertIn("Needs clearer trade-off analysis.", prompt)
        self.assertIn("Missed the database partitioning trade-off.", prompt)
        self.assertIn("Distributed systems", prompt)

    def test_chat_rejects_invalid_payload_and_provider_errors_are_sanitized(self):
        too_long = client.post(
            "/api/coach/chat",
            json={"message": "x" * 2001},
        )
        self.assertEqual(too_long.status_code, 422)

        with patch(
            "app.main.generate_coach_reply",
            side_effect=RuntimeError("private provider configuration"),
        ):
            response = client.post(
                "/api/coach/chat",
                json={"message": "Please help me prepare"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private provider configuration", response.text)
        self.assertIn("temporarily unavailable", response.json()["detail"])
        self.assertIsInstance(response.json()["conversation_id"], int)


if __name__ == "__main__":
    unittest.main()
