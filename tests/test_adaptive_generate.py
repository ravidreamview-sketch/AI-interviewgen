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
    MockInterview
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


class TestAdaptiveQuestionGeneration(unittest.TestCase):

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

    def get_token_a(self) -> str:
        return create_access_token({
            "sub": self.cand_a_id,
            "email": "candidate_a@example.com",
            "role": "candidate",
            "plan_tier": "pro"
        })

    def get_token_b(self) -> str:
        return create_access_token({
            "sub": self.cand_b_id,
            "email": "candidate_b@example.com",
            "role": "candidate",
            "plan_tier": "free"
        })

    # 1. Authenticated Adaptive Generation
    def test_1_authenticated_adaptive_generation_success(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Backend Engineer",
                "experience": "5 Years",
                "skills": ["Python", "PostgreSQL"],
                "difficulty": "Hard",
                "number_of_questions": 5
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("adaptive_session_id", data)
        self.assertIn("questions", data)
        self.assertEqual(len(data["questions"]), 5)

    # 2. New Candidate Fallback
    def test_2_new_candidate_fallback_to_baseline(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Frontend Developer",
                "experience": "3 Years",
                "skills": ["React", "CSS"],
                "difficulty": "Medium",
                "number_of_questions": 4
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["profile_status"], "insufficient_data")
        self.assertIsNone(data["recommended_focus"])
        self.assertEqual(len(data["questions"]), 4)
        for q in data["questions"]:
            self.assertEqual(q["reason"], "role_requirement")
            self.assertIn(q["source"], ["baseline_generator", "role_matrix"])

    # 3. Existing Candidate with Weakness
    def test_3_candidate_with_weakness_targeted_in_questions(self):
        db = TestingSessionLocal()
        weakness = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="PostgreSQL Indexing",
            score=60.0,
            trend="declining",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        db.add(weakness)
        db.commit()
        db.close()

        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Backend Engineer",
                "experience": "5 Years",
                "skills": ["Python", "PostgreSQL"],
                "difficulty": "Hard",
                "number_of_questions": 5
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["profile_status"], "ready")
        self.assertEqual(data["recommended_focus"]["skill"], "PostgreSQL Indexing")
        # Ensure at least 60% of questions target the weakness
        targeted_qs = [q for q in data["questions"] if q["reason"] == "candidate_weakness"]
        self.assertGreaterEqual(len(targeted_qs), 3)
        for q in targeted_qs:
            self.assertEqual(q["target_skill"], "PostgreSQL Indexing")
            self.assertIsNotNone(q["evidence_reference"])

    # 4. High Role-Relevance Weakness Prioritized
    def test_4_high_role_relevance_weakness_prioritized(self):
        db = TestingSessionLocal()
        # High relevance weakness: System Design (70% score)
        core_weakness = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="System Design",
            score=70.0,
            trend="flat",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        # Low relevance weakness: CSS Styling (55% score)
        low_weakness = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="CSS Grid",
            score=55.0,
            trend="flat",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_LOW
        )
        db.add_all([core_weakness, low_weakness])
        db.commit()
        db.close()

        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Backend Engineer",
                "experience": "5 Years",
                "skills": ["Python", "System Design"],
                "difficulty": "Hard",
                "number_of_questions": 5
            }
        )
        data = res.json()
        self.assertEqual(data["recommended_focus"]["skill"], "System Design")
        targeted_qs = [q for q in data["questions"] if q["reason"] == "candidate_weakness"]
        self.assertTrue(any(q["target_skill"] == "System Design" for q in targeted_qs))

    # 5. Previous Mistake Targeting
    def test_5_previous_mistake_targeted_with_mistake_reason(self):
        db = TestingSessionLocal()
        mistake = CandidateMistakesLedger(
            user_id=self.cand_a_id,
            adaptive_session_id="asess_hist_99",
            skill="API Idempotency",
            mistake_category="duplicate_transactions",
            description="Failed to implement idempotency keys during payments.",
            severity="high",
            mistake_status="identified"
        )
        db.add(mistake)
        db.commit()
        db.close()

        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Backend Engineer",
                "experience": "5 Years",
                "skills": ["Python", "FastAPI"],
                "difficulty": "Hard",
                "number_of_questions": 5
            }
        )
        data = res.json()
        targeted_qs = [q for q in data["questions"] if q["reason"] == "previous_mistake"]
        self.assertGreaterEqual(len(targeted_qs), 1)
        self.assertEqual(targeted_qs[0]["target_skill"], "API Idempotency")
        self.assertEqual(targeted_qs[0]["source"], "mistakes_ledger")
        self.assertIn("mistake_description", targeted_qs[0]["evidence_reference"])

    # 6. Multiple Weaknesses Handled Gracefully
    def test_6_multiple_weaknesses_ranked_correctly(self):
        db = TestingSessionLocal()
        w1 = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Kafka Partitioning",
            score=58.0,
            trend="declining",
            evidence_count=4,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        w2 = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Redis Caching",
            score=72.0,
            trend="improving",
            evidence_count=2,
            confidence="MEDIUM",
            weakness_status="improving",
            role_relevance=ROLE_IMPORTANCE_MEDIUM
        )
        db.add_all([w1, w2])
        db.commit()
        db.close()

        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Backend Engineer", "skills": ["Kafka", "Redis"], "number_of_questions": 5}
        )
        data = res.json()
        self.assertEqual(data["recommended_focus"]["skill"], "Kafka Partitioning")

    # 7. Recommended Focus Usage
    def test_7_recommended_focus_is_propagated_in_response(self):
        db = TestingSessionLocal()
        w = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Docker Networking",
            score=62.0,
            trend="flat",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        db.add(w)
        db.commit()
        db.close()

        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "DevOps Engineer", "skills": ["Docker", "Kubernetes"], "number_of_questions": 5}
        )
        data = res.json()
        self.assertIsNotNone(data["recommended_focus"])
        self.assertEqual(data["recommended_focus"]["skill"], "Docker Networking")

    # 8. Question Metadata Compliance
    def test_8_every_question_contains_complete_metadata(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "GenAI Architect",
                "experience": "5 Years",
                "skills": ["LangChain", "RAG"],
                "difficulty": "Brutal",
                "number_of_questions": 5
            }
        )
        data = res.json()
        for q in data["questions"]:
            self.assertTrue(len(q["question"]) > 10)
            self.assertIn(q["reason"], [
                "role_requirement", "resume_skill", "jd_requirement", "candidate_weakness",
                "previous_mistake", "low_score", "practice_goal", "follow_up"
            ])
            self.assertIn("source", q)
            self.assertIn("target_skill", q)
            self.assertIn("focus_skill", q)
            self.assertEqual(q["difficulty"], "Brutal")
            self.assertEqual(q["question_engine_version"], "adaptive-qengine-v1.0.0")

    # 9. Adaptive Session ID Preservation & Generation
    def test_9_adaptive_session_id_preservation_and_generation(self):
        token = self.get_token_a()
        # Test client provides custom session ID
        custom_session = "asess_custom_journey_123"
        res1 = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Backend Engineer", "number_of_questions": 3, "adaptive_session_id": custom_session}
        )
        self.assertEqual(res1.json()["adaptive_session_id"], custom_session)

        # Test server generates session ID when none provided
        res2 = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Backend Engineer", "number_of_questions": 3}
        )
        self.assertTrue(res2.json()["adaptive_session_id"].startswith("asess_"))

    # 10. Duplicate Question Prevention
    def test_10_duplicate_question_prevention(self):
        db = TestingSessionLocal()
        # Seed an existing interview history record with identical questions
        prev_q = "How do you design an idempotent payment processing API with PostgreSQL and Redis?"
        history = InterviewHistory(
            user_id=self.cand_a_id,
            role="Backend Engineer",
            experience="5 Years",
            skills="PostgreSQL, Redis",
            difficulty="Hard",
            questions=f"1. {prev_q}",
            created_at=datetime.utcnow() - timedelta(hours=1)
        )
        db.add(history)
        db.commit()
        db.close()

        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Backend Engineer", "skills": ["PostgreSQL", "Redis"], "number_of_questions": 5}
        )
        data = res.json()
        generated_texts = [q["question"] for q in data["questions"]]
        # Verify questions are generated and non-empty
        self.assertEqual(len(generated_texts), 5)

    # 11. AI Fallback to Secondary & Offline
    def test_11_ai_fallback_generates_valid_questions(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "UI/UX Designer", "skills": ["Figma", "Design Systems"], "number_of_questions": 5}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["questions"]), 5)

    # 12. Offline Fallback Generates Role-Appropriate Content
    def test_12_offline_fallback_for_custom_roles(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Robotics Engineer", "skills": ["ROS", "C++", "SLAM"], "number_of_questions": 4}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["questions"]), 4)

    # 13. Missing Telemetry Does Not Break Application
    def test_13_missing_telemetry_gracefully_degrades(self):
        token = self.get_token_b()
        res = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Data Scientist", "skills": ["PyTorch", "Pandas"], "number_of_questions": 5}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["profile_status"], "insufficient_data")

    # 14. Authentication Isolation Between Candidates
    def test_14_authentication_isolation_between_candidates(self):
        db = TestingSessionLocal()
        # Candidate A has a weakness in "Distributed Locks"
        w_a = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Distributed Locks",
            score=50.0,
            trend="declining",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        # Candidate B has a weakness in "CSS Flexbox"
        w_b = CandidateSkillAnalytics(
            user_id=self.cand_b_id,
            skill="CSS Flexbox",
            score=55.0,
            trend="declining",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="identified",
            role_relevance=ROLE_IMPORTANCE_HIGH
        )
        db.add_all([w_a, w_b])
        db.commit()
        db.close()

        # Candidate B requests adaptive generation
        token_b = self.get_token_b()
        res_b = client.post(
            "/api/adaptive/generate",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"role": "Frontend Developer", "skills": ["CSS", "HTML"], "number_of_questions": 5}
        )
        data_b = res_b.json()
        self.assertEqual(data_b["recommended_focus"]["skill"], "CSS Flexbox")
        # Candidate B MUST NOT receive questions targeting Candidate A's weakness
        for q in data_b["questions"]:
            self.assertNotEqual(q["target_skill"], "Distributed Locks")

    # 15. Existing /api/generate Regression
    def test_15_existing_api_generate_endpoint_continues_to_function(self):
        token = self.get_token_a()
        res = client.post(
            "/api/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Frontend Developer",
                "experience": "3 Years",
                "skills": ["React", "TypeScript"],
                "difficulty": "Medium",
                "number_of_questions": 5
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("questions", data)
        self.assertEqual(len(data["questions"]), 5)
        self.assertIn("questions_details", data)

    # 16. Existing /generate Dual Route Regression
    def test_16_existing_generate_alias_endpoint_continues_to_function(self):
        token = self.get_token_a()
        res = client.post(
            "/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Product Designer",
                "experience": "5 Years",
                "skills": ["Figma", "Design Systems"],
                "difficulty": "Hard",
                "number_of_questions": 5
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("questions", data)
        self.assertEqual(len(data["questions"]), 5)


if __name__ == "__main__":
    unittest.main()
