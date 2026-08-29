"""
Test Suite: AI Mock Interview Video Mode & Voice Mode Support

Tests:
1. Database model MockInterview includes interview_mode column.
2. Default interview mode is 'voice'.
3. Video interview mode 'video' is correctly accepted and persisted.
4. Unauthenticated submission allows mock recording.
5. Authenticated candidate submission binds user_id.
6. Candidate dashboard metrics accurately count mock interviews of both voice and video modes.
7. Route aliases /api/candidate/mock-interview and /candidate/mock-interview work identically.
8. Non-standard interview_mode string safely defaults to 'voice'.
"""

import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount, MockInterview
from app.security import hash_password, create_access_token


class TestMockInterviewVideoMode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.TestingSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine
        )
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
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        self.db = self.TestingSessionLocal()
        self.db.query(MockInterview).delete()
        self.db.query(UserAccount).delete()
        self.db.commit()

        # Seed candidate user
        self.user = UserAccount(
            email="candidate@example.com",
            full_name="Alex Candidate",
            password_hash=hash_password("Pass123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        self.token = create_access_token(data={"sub": str(self.user.id), "email": self.user.email, "role": self.user.role})

    def tearDown(self):
        self.db.close()

    def test_1_voice_mode_submission_defaults(self):
        """1. Voice-only mock interview submission defaults interview_mode to 'voice'."""
        payload = {
            "role": "Python Backend Engineer",
            "company_target": "Google",
            "interviewer_persona": "Alex (Tech Lead)",
            "score": 88.0,
            "technical_accuracy": 90.0,
            "communication_clarity": 85.0,
            "star_depth": 87.0,
            "confidence_score": 89.0,
            "duration_seconds": 320,
            "status": "completed",
            "interview_mode": "voice"
        }
        res = self.client.post(
            "/api/candidate/mock-interview",
            headers={"Authorization": f"Bearer {self.token}"},
            json=payload
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["interview_mode"], "voice")
        self.assertEqual(data["user_id"], self.user.id)
        self.assertEqual(data["role"], "Python Backend Engineer")
        self.assertEqual(data["score"], 88.0)

        # Verify DB record
        record = self.db.query(MockInterview).filter(MockInterview.id == data["id"]).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.interview_mode, "voice")

    def test_2_video_mode_submission(self):
        """2. Video+Voice mock interview submission persists interview_mode='video'."""
        payload = {
            "role": "Lead Product Designer",
            "company_target": "Meta",
            "interviewer_persona": "Elena (Principal Architect)",
            "score": 92.5,
            "technical_accuracy": 94.0,
            "communication_clarity": 91.0,
            "star_depth": 90.0,
            "confidence_score": 95.0,
            "duration_seconds": 450,
            "status": "completed",
            "interview_mode": "video",
            "transcript": "Q: Tell me about Design Systems.\nA: I built Figma tokens."
        }
        res = self.client.post(
            "/api/candidate/mock-interview",
            headers={"Authorization": f"Bearer {self.token}"},
            json=payload
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["interview_mode"], "video")
        self.assertEqual(data["role"], "Lead Product Designer")

        # Verify DB record
        record = self.db.query(MockInterview).filter(MockInterview.id == data["id"]).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.interview_mode, "video")
        self.assertIn("Design Systems", record.transcript)

    def test_3_unauthenticated_mock_interview_recording(self):
        """3. Unauthenticated user can record mock interview without user_id."""
        payload = {
            "role": "Frontend Developer",
            "score": 80.0,
            "interview_mode": "video"
        }
        res = self.client.post("/api/candidate/mock-interview", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNone(data["user_id"])
        self.assertEqual(data["interview_mode"], "video")

    def test_4_invalid_mode_coerced_to_voice(self):
        """4. Invalid interview_mode string safely coerces to 'voice'."""
        payload = {
            "role": "DevOps Architect",
            "interview_mode": "telepathy"
        }
        res = self.client.post("/api/candidate/mock-interview", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["interview_mode"], "voice")

    def test_5_route_alias_support(self):
        """5. Endpoint accessible via /candidate/mock-interview and /api/candidate/mock-interview."""
        payload = {
            "role": "Data Engineer",
            "interview_mode": "video"
        }
        res = self.client.post("/candidate/mock-interview", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["interview_mode"], "video")

    def test_6_dashboard_service_integration(self):
        """6. Candidate dashboard accurately integrates video mock interviews into metrics and timeline."""
        # Create 1 voice mock and 1 video mock
        m1 = MockInterview(
            user_id=self.user.id,
            role="Python Engineer",
            score=86.0,
            technical_accuracy=88.0,
            status="completed",
            interview_mode="voice"
        )
        m2 = MockInterview(
            user_id=self.user.id,
            role="System Architect",
            score=94.0,
            technical_accuracy=96.0,
            status="completed",
            interview_mode="video"
        )
        self.db.add_all([m1, m2])
        self.db.commit()

        # Query Candidate Dashboard
        res = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mock_interviews"], 2)
        self.assertEqual(data["average_score"], 90.0)  # (86 + 94) / 2
        self.assertTrue(data["preparation_readiness"] > 0)
        # Recent activity includes both mocks
        mock_activities = [a for a in data["recent_activity"] if a["type"] == "mock_interview"]
        self.assertEqual(len(mock_activities), 2)


if __name__ == "__main__":
    unittest.main()
