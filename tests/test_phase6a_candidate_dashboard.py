"""
Phase 6A: Candidate Dashboard Real-Time Data Integration Test Suite

Tests:
1. Authenticated dashboard access & schema compliance
2. Unauthenticated request rejection (401 Unauthorized)
3. Strict tenant isolation (User A cannot see User B's data)
4. New user zero-state handling
5. Questions practiced calculation
6. Mock interviews count calculation
7. Average score calculation & division-by-zero safety
8. Preparation streak calculation & same-day deduplication
9. Latest ResumeScan retrieval & gap parsing
10. Privacy verification: raw resume/JD content excluded
11. Recent activity ordering & max-10 limit
12. Readiness formula accuracy (0-100 range)
13. Route aliases compatibility
"""

import unittest
from datetime import datetime, timezone, timedelta
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.db_models import (
    UserAccount,
    InterviewHistory,
    MockInterview,
    ResumeScan,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
)
from app.security import hash_password, create_access_token
from app.dashboard_service import (
    calculate_streak,
    calculate_readiness,
    parse_questions_count,
)


class TestPhase6ACandidateDashboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # In-memory SQLite for testing
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
        # Clean test tables
        self.db.query(CandidateMistakesLedger).delete()
        self.db.query(CandidateSkillAnalytics).delete()
        self.db.query(ResumeScan).delete()
        self.db.query(MockInterview).delete()
        self.db.query(InterviewHistory).delete()
        self.db.query(UserAccount).delete()
        self.db.commit()

        # Seed User A (Alice - Candidate)
        self.user_a = UserAccount(
            email="alice@example.com",
            full_name="Alice Candidate",
            password_hash=hash_password("AlicePass123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        # Seed User B (Bob - Candidate)
        self.user_b = UserAccount(
            email="bob@example.com",
            full_name="Bob Candidate",
            password_hash=hash_password("BobPass123!"),
            role="candidate",
            plan_tier="free",
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()
        self.db.refresh(self.user_a)
        self.db.refresh(self.user_b)

        # Tokens
        self.token_a = create_access_token(data={"sub": str(self.user_a.id), "email": self.user_a.email, "role": self.user_a.role})
        self.token_b = create_access_token(data={"sub": str(self.user_b.id), "email": self.user_b.email, "role": self.user_b.role})

    def tearDown(self):
        self.db.close()

    def test_1_authenticated_dashboard_access_and_schema(self):
        """1. Authenticated request succeeds with HTTP 200 and conforms to schema."""
        response = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["user"]["email"], "alice@example.com")
        self.assertEqual(data["user"]["name"], "Alice Candidate")
        self.assertEqual(data["user"]["plan_tier"], "pro")
        self.assertIn("preparation_readiness", data)
        self.assertIn("questions_practiced", data)
        self.assertIn("mock_interviews", data)
        self.assertIn("average_score", data)
        self.assertIn("preparation_streak", data)
        self.assertIn("competency_scores", data)
        self.assertIn("recommended_focus", data)
        self.assertIn("recent_activity", data)

    def test_2_unauthenticated_request_returns_401(self):
        """2. Unauthenticated request returns HTTP 401 Unauthorized."""
        response = self.client.get("/api/candidate/dashboard")
        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())

    def test_3_strict_tenant_isolation_user_a_vs_user_b(self):
        """3. User A cannot see User B's metrics, activity, or resume scans."""
        # Give User A 2 mock interviews
        mock_a = MockInterview(
            user_id=self.user_a.id,
            role="Product Designer",
            score=90.0,
            technical_accuracy=88.0,
            status="completed",
            created_at=datetime.now(timezone.utc)
        )
        # Give User B 5 mock interviews and a resume scan
        mock_b = MockInterview(
            user_id=self.user_b.id,
            role="DevOps Engineer",
            score=75.0,
            technical_accuracy=70.0,
            status="completed",
            created_at=datetime.now(timezone.utc)
        )
        scan_b = ResumeScan(
            scan_id="scan_bob_999",
            user_id=self.user_b.id,
            target_role="DevOps Specialist",
            overall_match_score=85.0,
            skill_gaps=json.dumps(["Kubernetes", "Terraform"]),
            created_at=datetime.now(timezone.utc)
        )
        self.db.add_all([mock_a, mock_b, scan_b])
        self.db.commit()

        # Query User A dashboard
        res_a = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        data_a = res_a.json()
        self.assertEqual(data_a["mock_interviews"], 1)
        self.assertEqual(data_a["average_score"], 90.0)
        self.assertIsNone(data_a["resume_match"])  # User A has no scan

        # Query User B dashboard
        res_b = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_b}"}
        )
        data_b = res_b.json()
        self.assertEqual(data_b["mock_interviews"], 1)
        self.assertEqual(data_b["average_score"], 75.0)
        self.assertIsNotNone(data_b["resume_match"])
        self.assertEqual(data_b["resume_match"]["latest_scan_id"], "scan_bob_999")
        self.assertEqual(data_b["resume_match"]["target_role"], "DevOps Specialist")

    def test_4_new_user_zero_state_and_safe_defaults(self):
        """4. New user with no activity returns 0s and safe empty lists without crashing."""
        res = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["preparation_readiness"], 0)
        self.assertEqual(data["questions_practiced"], 0)
        self.assertEqual(data["mock_interviews"], 0)
        self.assertEqual(data["average_score"], 0.0)
        self.assertEqual(data["preparation_streak"], 0)
        self.assertIsNone(data["resume_match"])
        self.assertEqual(data["recommended_focus"], [])
        self.assertEqual(data["recent_activity"], [])

    def test_5_questions_practiced_calculation(self):
        """5. Questions practiced sums questions accurately across sessions."""
        h1 = InterviewHistory(
            user_id=self.user_a.id,
            role="Backend Engineer",
            experience="3 Years",
            skills="Python, FastAPI",
            difficulty="Hard",
            questions="1. What is GIL in Python?\n2. Explain async/await.\n3. How does FastAPI dependency injection work?",
            created_at=datetime.now(timezone.utc)
        )
        h2 = InterviewHistory(
            user_id=self.user_a.id,
            role="Backend Engineer",
            experience="3 Years",
            skills="SQLAlchemy",
            difficulty="Hard",
            questions=json.dumps(["Q1 text", "Q2 text", "Q3 text", "Q4 text"]),
            created_at=datetime.now(timezone.utc)
        )
        self.db.add_all([h1, h2])
        self.db.commit()

        res = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        data = res.json()
        self.assertEqual(data["questions_practiced"], 7)  # 3 + 4

    def test_6_mock_interviews_count_and_average_score(self):
        """6 & 7. Mock interviews count and average score arithmetic mean calculation."""
        m1 = MockInterview(
            user_id=self.user_a.id,
            role="Frontend Dev",
            score=80.0,
            technical_accuracy=85.0,
            status="completed",
            created_at=datetime.now(timezone.utc)
        )
        m2 = MockInterview(
            user_id=self.user_a.id,
            role="Frontend Dev",
            score=90.0,
            technical_accuracy=95.0,
            status="completed",
            created_at=datetime.now(timezone.utc)
        )
        s1 = CandidateSkillAnalytics(
            user_id=self.user_a.id,
            skill="React",
            score=70.0,
            trend="improving"
        )
        self.db.add_all([m1, m2, s1])
        self.db.commit()

        res = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        data = res.json()
        self.assertEqual(data["mock_interviews"], 2)
        # Average of 80, 90, 70 = 80.0
        self.assertEqual(data["average_score"], 80.0)

    def test_8_preparation_streak_calculation(self):
        """8. Consecutive active days streak in UTC with same-day deduplication."""
        now = datetime.now(timezone.utc)
        today = now.date()

        # Active today (2 activities)
        h_today_1 = InterviewHistory(user_id=self.user_a.id, role="Dev", experience="1y", skills="Py", difficulty="M", questions="1. Q1", created_at=now)
        h_today_2 = InterviewHistory(user_id=self.user_a.id, role="Dev", experience="1y", skills="Py", difficulty="M", questions="1. Q2", created_at=now - timedelta(hours=2))

        # Active yesterday
        h_yest = InterviewHistory(user_id=self.user_a.id, role="Dev", experience="1y", skills="Py", difficulty="M", questions="1. Q3", created_at=now - timedelta(days=1))

        # Active 2 days ago
        h_2days = InterviewHistory(user_id=self.user_a.id, role="Dev", experience="1y", skills="Py", difficulty="M", questions="1. Q4", created_at=now - timedelta(days=2))

        # Gap on day 3, active on day 4
        h_4days = InterviewHistory(user_id=self.user_a.id, role="Dev", experience="1y", skills="Py", difficulty="M", questions="1. Q5", created_at=now - timedelta(days=4))

        self.db.add_all([h_today_1, h_today_2, h_yest, h_2days, h_4days])
        self.db.commit()

        res = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        data = res.json()
        # Today, Yesterday, 2 days ago = 3-day consecutive streak
        self.assertEqual(data["preparation_streak"], 3)

    def test_9_latest_resume_scan_and_privacy_checks(self):
        """9 & 10. Latest resume scan retrieved; raw resume & JD text strictly excluded."""
        scan1 = ResumeScan(
            scan_id="scan_old_111",
            user_id=self.user_a.id,
            target_role="Junior Designer",
            overall_match_score=60.0,
            skill_gaps=json.dumps(["Figma"]),
            critical_gaps=json.dumps(["Design Systems"]),
            normalized_resume="PRIVATE RESUME CONTENT",
            normalized_jd="PRIVATE JD CONTENT",
            created_at=datetime.now(timezone.utc) - timedelta(days=5)
        )
        scan2 = ResumeScan(
            scan_id="scan_new_222",
            user_id=self.user_a.id,
            target_role="Lead Product Designer",
            overall_match_score=88.5,
            match_confidence="HIGH",
            skill_gaps=json.dumps(["Figma Variables", "Tokens"]),
            critical_gaps=json.dumps(["Design Systems Architecture"]),
            normalized_resume="PRIVATE RESUME CONTENT 2",
            normalized_jd="PRIVATE JD CONTENT 2",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        self.db.add_all([scan1, scan2])
        self.db.commit()

        res = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        data = res.json()
        self.assertIsNotNone(data["resume_match"])
        self.assertEqual(data["resume_match"]["latest_scan_id"], "scan_new_222")
        self.assertEqual(data["resume_match"]["target_role"], "Lead Product Designer")
        self.assertEqual(data["resume_match"]["overall_match_score"], 88.5)
        self.assertEqual(data["resume_match"]["match_confidence"], "HIGH")
        self.assertIn("Figma Variables", data["resume_match"]["top_skill_gaps"])
        self.assertIn("Design Systems Architecture", data["resume_match"]["critical_gaps"])

        # Privacy check: Ensure private text is nowhere in serialized response
        raw_json = res.text
        self.assertNotIn("PRIVATE RESUME CONTENT", raw_json)
        self.assertNotIn("PRIVATE JD CONTENT", raw_json)

    def test_10_recent_activity_ordering_and_limit(self):
        """11. Recent activity returns merged chronological events up to limit of 10."""
        now = datetime.now(timezone.utc)
        # Create 12 distinct activities
        for i in range(12):
            self.db.add(InterviewHistory(
                user_id=self.user_a.id,
                role=f"Role #{i}",
                experience="2y",
                skills="Test",
                difficulty="Medium",
                questions=f"1. Question {i}",
                created_at=now - timedelta(minutes=i * 10)
            ))
        self.db.commit()

        res = self.client.get(
            "/api/candidate/dashboard",
            headers={"Authorization": f"Bearer {self.token_a}"}
        )
        data = res.json()
        self.assertLessEqual(len(data["recent_activity"]), 10)
        self.assertEqual(len(data["recent_activity"]), 10)
        # Most recent first
        self.assertEqual(data["recent_activity"][0]["title"], "Question Practice (Role #0)")

    def test_11_readiness_formula_deterministic_ranges(self):
        """12 & 13. Preparation readiness calculation formula adheres to 0-100 bounded output."""
        # 0 activity -> 0
        self.assertEqual(calculate_readiness(0, 0, 0.0, None), 0)

        # Full activity with 30+ questions, 3+ mocks, 100 avg score, 100 resume
        r_full = calculate_readiness(30, 3, 100.0, 100.0)
        self.assertEqual(r_full, 100)

        # Partial activity
        r_partial = calculate_readiness(15, 1, 80.0, 70.0)
        self.assertTrue(0 <= r_partial <= 100)

        # Extreme values clamped to 100
        r_extreme = calculate_readiness(100, 20, 100.0, 100.0)
        self.assertEqual(r_extreme, 100)

    def test_12_route_aliases_and_cookie_auth(self):
        """14. Candidate dashboard accessible via candidate_session cookie and route aliases."""
        # Test cookie-based authentication
        self.client.cookies.set("candidate_session", self.token_a)
        res_cookie = self.client.get("/api/candidate/dashboard")
        self.assertEqual(res_cookie.status_code, 200)

        # Test alias /candidate/dashboard
        res_alias = self.client.get("/candidate/dashboard")
        self.assertEqual(res_alias.status_code, 200)
        self.client.cookies.clear()


if __name__ == "__main__":
    unittest.main()
