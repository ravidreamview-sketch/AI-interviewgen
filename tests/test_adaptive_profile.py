import unittest
import os
import sys
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.database import Base, get_db
from app.db_models import (
    UserAccount,
    InterviewHistory,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
    MockInterview,
    ResumeScan
)
from app.security import hash_password, create_access_token
from app.adaptive_service import (
    ROLE_IMPORTANCE_HIGH,
    ROLE_IMPORTANCE_MEDIUM,
    ROLE_IMPORTANCE_LOW
)

# Setup isolated in-memory test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


client = TestClient(app)


class TestAdaptiveCandidateProfile(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        Base.metadata.drop_all(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestingSessionLocal()
        # Seed Candidate A
        self.candidate_a = UserAccount(
            email="candidate_a@example.com",
            full_name="Candidate Alpha",
            password_hash=hash_password("PassAlpha123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        # Seed Candidate B
        self.candidate_b = UserAccount(
            email="candidate_b@example.com",
            full_name="Candidate Beta",
            password_hash=hash_password("PassBeta123!"),
            role="candidate",
            plan_tier="free",
            is_active=True
        )
        db.add_all([self.candidate_a, self.candidate_b])
        db.commit()
        db.refresh(self.candidate_a)
        db.refresh(self.candidate_b)
        self.cand_a_id = self.candidate_a.id
        self.cand_b_id = self.candidate_b.id
        db.close()

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.pop(get_db, None)

    def login_candidate_a(self) -> str:
        return create_access_token({
            "sub": self.cand_a_id,
            "email": "candidate_a@example.com",
            "role": "candidate",
            "plan_tier": "pro"
        })

    def login_candidate_b(self) -> str:
        return create_access_token({
            "sub": self.cand_b_id,
            "email": "candidate_b@example.com",
            "role": "candidate",
            "plan_tier": "free"
        })

    # 1. New Candidate with No Data
    def test_1_new_candidate_with_no_data_returns_empty_state(self):
        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNone(data["readiness_score"])
        self.assertEqual(data["profile_status"], "insufficient_data")
        self.assertEqual(data["interview_count"], 0)
        self.assertIsNone(data["last_interview_score"])
        self.assertIsNone(data["improvement_since_first_interview"])
        self.assertEqual(data["strengths"], [])
        self.assertEqual(data["focus_areas"], [])
        self.assertEqual(data["open_mistakes"], [])
        self.assertIsNone(data["recommended_focus"])

    # 2. Candidate with One Interview
    def test_2_candidate_with_one_interview(self):
        db = TestingSessionLocal()
        mock = MockInterview(
            user_id=self.cand_a_id,
            role="Backend Engineer",
            score=72.0,
            technical_accuracy=70.0,
            communication_clarity=75.0,
            created_at=datetime.utcnow() - timedelta(days=2)
        )
        db.add(mock)
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["interview_count"], 1)
        self.assertEqual(data["last_interview_score"], 72.0)
        self.assertEqual(data["improvement_since_first_interview"], 0.0)
        self.assertEqual(data["readiness_score"], 72.0)

    # 3. Candidate with Multiple Interviews (Longitudinal Improvement)
    def test_3_candidate_with_multiple_interviews_calculates_improvement(self):
        db = TestingSessionLocal()
        mock1 = MockInterview(
            user_id=self.cand_a_id,
            role="Backend Engineer",
            score=65.0,
            created_at=datetime.utcnow() - timedelta(days=10)
        )
        mock2 = MockInterview(
            user_id=self.cand_a_id,
            role="Backend Engineer",
            score=75.0,
            created_at=datetime.utcnow() - timedelta(days=5)
        )
        mock3 = MockInterview(
            user_id=self.cand_a_id,
            role="Backend Engineer",
            score=82.0,
            created_at=datetime.utcnow() - timedelta(days=1)
        )
        db.add_all([mock1, mock2, mock3])
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["interview_count"], 3)
        self.assertEqual(data["last_interview_score"], 82.0)
        self.assertEqual(data["improvement_since_first_interview"], 17.0)  # 82.0 - 65.0 = 17.0

    # 4. Strength Detection (Requires high score AND sufficient evidence)
    def test_4_strength_detection_requires_score_and_evidence(self):
        db = TestingSessionLocal()
        # Single high score with only 1 observation -> should NOT be a strength yet
        skill_single = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Kafka Streams",
            score=90.0,
            evidence_count=1,
            confidence="LOW",
            weakness_status="practicing"
        )
        # High score with 3 observations -> Confirmed Strength
        skill_confirmed = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="System Design",
            score=86.0,
            trend="improving",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="practicing"
        )
        db.add_all([skill_single, skill_confirmed])
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        strength_skills = [s["skill"] for s in data["strengths"]]
        self.assertIn("System Design", strength_skills)
        self.assertNotIn("Kafka Streams", strength_skills)  # Filtered out because evidence_count < 2

    # 5. Weakness Detection & Focus Areas
    def test_5_weakness_detection_evaluates_multi_signals(self):
        db = TestingSessionLocal()
        skill_weak = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="PostgreSQL Indexing",
            score=64.0,
            trend="flat",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        db.add(skill_weak)
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        focus_skills = [f["skill"] for f in data["focus_areas"]]
        self.assertIn("PostgreSQL Indexing", focus_skills)

    # 6. Repeated Weakness Handling
    def test_6_repeated_weakness_receives_appropriate_status(self):
        db = TestingSessionLocal()
        skill_repeated = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Distributed Locking",
            score=58.0,
            trend="flat",
            evidence_count=4,
            confidence="HIGH",
            weakness_status="practicing",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        db.add(skill_repeated)
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        self.assertEqual(data["recommended_focus"]["skill"], "Distributed Locking")
        self.assertIn("repeated weakness", data["recommended_focus"]["reason"].lower())

    # 7. Improving Trend
    def test_7_improving_trend_reflected(self):
        db = TestingSessionLocal()
        skill_improving = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Redis Caching",
            score=74.0,
            trend="improving",
            evidence_count=2,
            confidence="MEDIUM",
            weakness_status="improving"
        )
        db.add(skill_improving)
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        focus_item = next(f for f in data["focus_areas"] if f["skill"] == "Redis Caching")
        self.assertEqual(focus_item["trend"], "improving")
        self.assertEqual(focus_item["status"], "improving")

    # 8. Declining Trend Prioritized in Focus Area
    def test_8_declining_trend_receives_high_priority(self):
        db = TestingSessionLocal()
        skill_declining = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Concurrency Control",
            score=65.0,
            trend="declining",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        db.add(skill_declining)
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        self.assertEqual(data["recommended_focus"]["skill"], "Concurrency Control")
        self.assertEqual(data["recommended_focus"]["priority"], "high")
        self.assertIn("declining", data["recommended_focus"]["reason"].lower())

    # 9. Role Relevance Prioritization (Higher relevance beats lower score with low relevance)
    def test_9_role_relevance_prioritizes_core_pillars(self):
        db = TestingSessionLocal()
        # System Design has 70% score but HIGH relevance (1.0)
        core_skill = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="System Architecture",
            score=70.0,
            trend="flat",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        # CSS Styling has 62% score but LOW relevance (0.3) for Backend
        peripheral_skill = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="CSS Grid Layouts",
            score=62.0,
            trend="flat",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_LOW
        )
        db.add_all([core_skill, peripheral_skill])
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        # System Architecture must win recommended focus because of high role importance
        self.assertEqual(data["recommended_focus"]["skill"], "System Architecture")

    # 10. Confidence Calculation
    def test_10_confidence_levels_adhere_to_evidence(self):
        db = TestingSessionLocal()
        low_conf = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Docker",
            score=65.0,
            evidence_count=1,
            confidence="LOW",
            weakness_status="identified"
        )
        high_conf = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Kubernetes",
            score=65.0,
            evidence_count=4,
            confidence="HIGH",
            weakness_status="practicing"
        )
        db.add_all([low_conf, high_conf])
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        docker = next(f for f in data["focus_areas"] if f["skill"] == "Docker")
        k8s = next(f for f in data["focus_areas"] if f["skill"] == "Kubernetes")
        self.assertEqual(docker["confidence"], "LOW")
        self.assertEqual(k8s["confidence"], "HIGH")

    # 11. Open Mistakes Included
    def test_11_open_mistakes_returned_in_profile(self):
        db = TestingSessionLocal()
        open_m = CandidateMistakesLedger(
            user_id=self.cand_a_id,
            adaptive_session_id="asess_open_1",
            skill="PostgreSQL Indexing",
            mistake_category="concurrency",
            description="Missed lock timeout setting.",
            severity="high",
            mistake_status="identified"
        )
        practicing_m = CandidateMistakesLedger(
            user_id=self.cand_a_id,
            adaptive_session_id="asess_open_2",
            skill="API Design",
            mistake_category="idempotency",
            description="Forgot idempotency keys.",
            severity="medium",
            mistake_status="practicing"
        )
        db.add_all([open_m, practicing_m])
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        self.assertEqual(len(data["open_mistakes"]), 2)
        mistake_skills = [m["skill"] for m in data["open_mistakes"]]
        self.assertIn("PostgreSQL Indexing", mistake_skills)
        self.assertIn("API Design", mistake_skills)

    # 12. Resolved Mistakes Excluded from Open Mistakes
    def test_12_resolved_mistakes_excluded_from_open_mistakes(self):
        db = TestingSessionLocal()
        resolved_m = CandidateMistakesLedger(
            user_id=self.cand_a_id,
            adaptive_session_id="asess_res_1",
            skill="GraphQL",
            mistake_category="n_plus_one",
            description="Resolved N+1 queries using DataLoader.",
            severity="medium",
            mistake_status="resolved",
            resolved_at=datetime.utcnow()
        )
        db.add(resolved_m)
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        self.assertEqual(len(data["open_mistakes"]), 0)

    # 13. Recommended Focus Deterministic Output
    def test_13_recommended_focus_is_deterministic_and_explainable(self):
        db = TestingSessionLocal()
        skill = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Database Sharding",
            score=55.0,
            trend="declining",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        mistake = CandidateMistakesLedger(
            user_id=self.cand_a_id,
            adaptive_session_id="asess_shard_1",
            skill="Database Sharding",
            mistake_category="data_distribution",
            description="Uneven shard key distribution.",
            severity="critical",
            mistake_status="identified"
        )
        db.add_all([skill, mistake])
        db.commit()
        db.close()

        token = self.login_candidate_a()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        rec = data["recommended_focus"]
        self.assertIsNotNone(rec)
        self.assertEqual(rec["skill"], "Database Sharding")
        self.assertEqual(rec["priority"], "high")
        self.assertTrue(len(rec["reason"]) > 10)

    # 14. Authentication Isolation (Tenant Security)
    def test_14_authentication_isolation_between_candidates(self):
        db = TestingSessionLocal()
        # Add private data for Candidate A
        skill_a = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Candidate A Secret Skill",
            score=95.0,
            evidence_count=3,
            confidence="HIGH",
            weakness_status="practicing"
        )
        # Add private data for Candidate B
        skill_b = CandidateSkillAnalytics(
            user_id=self.cand_b_id,
            skill="Candidate B Secret Skill",
            score=50.0,
            evidence_count=2,
            confidence="MEDIUM",
            weakness_status="identified"
        )
        db.add_all([skill_a, skill_b])
        db.commit()
        db.close()

        # Login as Candidate B and query profile
        token_b = self.login_candidate_b()
        res_b = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(res_b.status_code, 200)
        data_b = res_b.json()

        # Verify Candidate B ONLY sees their own skills
        all_skills_b = [s["skill"] for s in data_b["strengths"]] + [f["skill"] for f in data_b["focus_areas"]]
        self.assertIn("Candidate B Secret Skill", all_skills_b)
        self.assertNotIn("Candidate A Secret Skill", all_skills_b)

        # Verify unauthenticated request fails with 401
        client.cookies.clear()
        unauth_res = client.get("/api/adaptive/profile")
        self.assertEqual(unauth_res.status_code, 401)

    # 15. Missing Adaptive Telemetry / Graceful Degradation
    def test_15_graceful_handling_when_telemetry_is_empty(self):
        token = self.login_candidate_b()
        res = client.get("/api/adaptive/profile", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["profile_status"], "insufficient_data")

    # 16. Existing /api/generate Regression Test
    def test_16_existing_generate_endpoint_continues_to_function(self):
        token = self.login_candidate_a()
        gen_res = client.post(
            "/api/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Fullstack Engineer",
                "experience": "5 Years",
                "skills": ["Node.js", "React", "PostgreSQL"],
                "difficulty": "Hard",
                "number_of_questions": 5
            }
        )
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        self.assertIn("questions", data)
        self.assertEqual(len(data["questions"]), 5)
        self.assertEqual(data["user_id"], self.cand_a_id)


if __name__ == "__main__":
    unittest.main()
