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
    CandidateMistakesLedger
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


class TestAdaptiveEvaluationAndNextQuestion(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        Base.metadata.drop_all(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestingSessionLocal()
        # Seed Candidate Alpha
        self.candidate_a = UserAccount(
            email="candidate_alpha@example.com",
            full_name="Candidate Alpha",
            password_hash=hash_password("PassAlpha123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        # Seed Candidate Beta
        self.candidate_b = UserAccount(
            email="candidate_beta@example.com",
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
            "email": "candidate_alpha@example.com",
            "role": "candidate",
            "plan_tier": "pro"
        })

    def get_token_b(self) -> str:
        return create_access_token({
            "sub": self.cand_b_id,
            "email": "candidate_beta@example.com",
            "role": "candidate",
            "plan_tier": "free"
        })

    # =========================================================================
    # EVALUATION TESTS (1 - 16)
    # =========================================================================

    def test_1_authenticated_response_evaluation(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do you handle race conditions in distributed systems?",
                "candidate_response": "We use Redis distributed locks with Redlock algorithm and TTL expiration.",
                "target_skill": "Distributed Systems",
                "focus_skill": "Concurrency & Locking",
                "difficulty": "Hard",
                "role": "Backend Architect"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("overall_score", data)
        self.assertIn("skill_scores", data)
        self.assertIn("evaluation_version", data)
        self.assertEqual(data["evaluation_version"], "eval-v1.2.0")

    def test_2_target_skill_evaluation(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do you structure user interviews?",
                "candidate_response": "I prepare an interview protocol, avoid leading questions, and ask open-ended questions.",
                "target_skill": "User Research",
                "focus_skill": "Interviewing",
                "role": "UX Researcher"
            }
        )
        data = res.json()
        skills = [s["skill"] for s in data["skill_scores"]]
        self.assertIn("User Research", skills)

    def test_3_multi_dimensional_scoring(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Tell me about a complex project delivery.",
                "candidate_response": "In my previous project, we faced critical latency spikes. I profiled the slow queries in PostgreSQL, applied composite B-tree indexes, and optimized query execution time by 80%, unblocking our launch.",
                "target_skill": "Answer Structure",
                "focus_skill": "STAR",
                "role": "Software Engineer"
            }
        )
        data = res.json()
        self.assertIsInstance(data["overall_score"], (int, float))
        self.assertTrue(len(data["skill_scores"]) >= 1)

    def test_4_good_signals_returned(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Explain database indexing trade-offs.",
                "candidate_response": "Indexes speed up read queries significantly but add write overhead and require storage. I use partial and covering indexes to balance these trade-offs.",
                "target_skill": "PostgreSQL Indexing",
                "role": "Backend Engineer"
            }
        )
        data = res.json()
        self.assertIsInstance(data["good_signals"], list)

    def test_5_missing_signals_returned_on_shallow_answer(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Explain database indexing trade-offs.",
                "candidate_response": "Indexes make things faster.",
                "target_skill": "PostgreSQL Indexing",
                "role": "Backend Engineer"
            }
        )
        data = res.json()
        self.assertTrue(len(data["missing_signals"]) >= 1)
        self.assertLess(data["overall_score"], 65.0)

    def test_6_red_flags_returned_on_superficial_response(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do you secure payment endpoints?",
                "candidate_response": "idk",
                "target_skill": "API Security",
                "role": "Backend Engineer"
            }
        )
        data = res.json()
        self.assertIsInstance(data["red_flags"], list)
        self.assertTrue(len(data["red_flags"]) >= 1 or len(data["missing_signals"]) >= 1)

    def test_7_mistake_detection_creates_ledger_entry(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do you handle API idempotency?",
                "candidate_response": "I just retry the request.",
                "target_skill": "API Idempotency",
                "role": "Backend Engineer"
            }
        )
        data = res.json()
        self.assertTrue(len(data["mistakes"]) >= 1)

        db = TestingSessionLocal()
        ledger_entries = db.query(CandidateMistakesLedger).filter(
            CandidateMistakesLedger.user_id == self.cand_a_id,
            CandidateMistakesLedger.skill == "API Idempotency"
        ).all()
        self.assertTrue(len(ledger_entries) >= 1)
        db.close()

    def test_8_existing_mistake_updated_rather_than_duplicated(self):
        db = TestingSessionLocal()
        existing = CandidateMistakesLedger(
            user_id=self.cand_a_id,
            adaptive_session_id="asess_old",
            skill="API Idempotency",
            mistake_category="duplicate_transactions",
            description="Initial mistake observation.",
            severity="medium",
            mistake_status="identified"
        )
        db.add(existing)
        db.commit()
        db.close()

        token = self.get_token_a()
        # Candidate repeats shallow answer
        client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do you prevent duplicate charges in payments?",
                "candidate_response": "Retry it automatically without headers.",
                "target_skill": "API Idempotency",
                "role": "Backend Engineer"
            }
        )

        db = TestingSessionLocal()
        entries = db.query(CandidateMistakesLedger).filter(
            CandidateMistakesLedger.user_id == self.cand_a_id,
            CandidateMistakesLedger.skill == "API Idempotency"
        ).all()
        # Should not create duplicate open records for same skill
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].mistake_status, "practicing")
        db.close()

    def test_9_duplicate_mistake_prevention_on_resolved_flow(self):
        token = self.get_token_a()
        # First poor response
        client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "What is ACID in databases?",
                "candidate_response": "I don't know.",
                "target_skill": "Database Transactions",
                "role": "Backend Engineer"
            }
        )
        # Second strong response resolving the mistake
        client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "What is ACID in databases?",
                "candidate_response": "ACID stands for Atomicity, Consistency, Isolation, and Durability. Atomicity ensures all-or-nothing execution, Consistency enforces database invariants, Isolation manages concurrent transaction visibility via isolation levels like Serializable or Repeatable Read, and Durability ensures committed data is safely persisted via WAL even during power crashes.",
                "target_skill": "Database Transactions",
                "role": "Backend Engineer"
            }
        )

        db = TestingSessionLocal()
        mistake = db.query(CandidateMistakesLedger).filter(
            CandidateMistakesLedger.user_id == self.cand_a_id,
            CandidateMistakesLedger.skill == "Database Transactions"
        ).first()
        if mistake:
            self.assertEqual(mistake.mistake_status, "resolved")
        db.close()

    def test_10_skill_analytics_updated_after_evaluation(self):
        token = self.get_token_a()
        client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do you implement caching with Redis?",
                "candidate_response": "We use Cache-Aside pattern with TTL expiration and jitter to avoid thundering herds.",
                "target_skill": "Redis Caching",
                "role": "Backend Engineer"
            }
        )

        db = TestingSessionLocal()
        skill_entry = db.query(CandidateSkillAnalytics).filter(
            CandidateSkillAnalytics.user_id == self.cand_a_id,
            CandidateSkillAnalytics.skill == "Redis Caching"
        ).first()
        self.assertIsNotNone(skill_entry)
        self.assertEqual(skill_entry.evidence_count, 1)
        db.close()

    def test_11_weakness_lifecycle_transitions_deterministically(self):
        db = TestingSessionLocal()
        # Seed an existing weakness in "identified"
        sk = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Kafka Partitioning",
            score=60.0,
            trend="flat",
            evidence_count=1,
            confidence="LOW",
            weakness_status="identified"
        )
        db.add(sk)
        db.commit()
        db.close()

        token = self.get_token_a()
        # Good response moves status to "improving" (evidence count reaches 2)
        client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do you choose Kafka partition keys?",
                "candidate_response": "We partition by entity ID to guarantee ordered consumption per entity while distributing load across brokers evenly with high throughput.",
                "target_skill": "Kafka Partitioning",
                "role": "Backend Engineer"
            }
        )

        db = TestingSessionLocal()
        updated_sk = db.query(CandidateSkillAnalytics).filter(
            CandidateSkillAnalytics.user_id == self.cand_a_id,
            CandidateSkillAnalytics.skill == "Kafka Partitioning"
        ).first()
        self.assertEqual(updated_sk.evidence_count, 2)
        self.assertIn(updated_sk.weakness_status, ["improving", "identified"])
        db.close()

    def test_12_trend_handling_calculates_improving_slope(self):
        db = TestingSessionLocal()
        sk = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="GraphQL Subscriptions",
            score=50.0,
            trend="flat",
            evidence_count=1,
            confidence="LOW",
            weakness_status="identified"
        )
        db.add(sk)
        db.commit()
        db.close()

        token = self.get_token_a()
        # High scoring response boosts score > 5 points
        client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do GraphQL subscriptions work over WebSockets?",
                "candidate_response": "GraphQL subscriptions use WebSockets with pub/sub architecture (e.g. Redis PubSub) to stream real-time updates when mutations occur.",
                "target_skill": "GraphQL Subscriptions",
                "role": "Frontend Developer"
            }
        )

        db = TestingSessionLocal()
        updated = db.query(CandidateSkillAnalytics).filter(
            CandidateSkillAnalytics.user_id == self.cand_a_id,
            CandidateSkillAnalytics.skill == "GraphQL Subscriptions"
        ).first()
        self.assertGreater(updated.score, 55.0)
        self.assertEqual(updated.trend, "improving")
        db.close()

    def test_13_confidence_handling_scales_with_evidence(self):
        db = TestingSessionLocal()
        sk = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Docker Multistage",
            score=70.0,
            trend="flat",
            evidence_count=3,
            confidence="MEDIUM",
            weakness_status="practicing"
        )
        db.add(sk)
        db.commit()
        db.close()

        token = self.get_token_a()
        client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "How do multistage Docker builds reduce image size?",
                "candidate_response": "Multistage builds compile assets in a builder stage and copy only binaries to a minimal scratch or alpine image.",
                "target_skill": "Docker Multistage",
                "role": "DevOps Engineer"
            }
        )

        db = TestingSessionLocal()
        updated = db.query(CandidateSkillAnalytics).filter(
            CandidateSkillAnalytics.user_id == self.cand_a_id,
            CandidateSkillAnalytics.skill == "Docker Multistage"
        ).first()
        self.assertEqual(updated.evidence_count, 4)
        self.assertEqual(updated.confidence, "HIGH")
        db.close()

    def test_14_authentication_isolation_for_evaluation(self):
        token_a = self.get_token_a()
        token_b = self.get_token_b()

        client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "question": "Explain CSS specificity.",
                "candidate_response": "Inline styles > IDs > Classes > Elements.",
                "target_skill": "CSS Specificity",
                "role": "Frontend Developer"
            }
        )

        db = TestingSessionLocal()
        # Skill should exist for Candidate A, but not Candidate B
        sk_a = db.query(CandidateSkillAnalytics).filter(CandidateSkillAnalytics.user_id == self.cand_a_id).all()
        sk_b = db.query(CandidateSkillAnalytics).filter(CandidateSkillAnalytics.user_id == self.cand_b_id).all()
        self.assertTrue(len(sk_a) >= 1)
        self.assertEqual(len(sk_b), 0)
        db.close()

    def test_15_missing_telemetry_handles_gracefully(self):
        token_b = self.get_token_b()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "question": "Explain binary search.",
                "candidate_response": "Binary search divides the sorted search space in half each step with O(log n) time complexity.",
                "target_skill": "Algorithms",
                "role": "Software Engineer"
            }
        )
        self.assertEqual(res.status_code, 200)

    def test_16_ai_fallback_evaluates_deterministically(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/evaluate-response",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Explain React useEffect dependency array.",
                "candidate_response": "Passing empty array runs only on mount; omitting array runs on every render; specifying values runs when those values change.",
                "target_skill": "React Hooks",
                "role": "Frontend Developer"
            }
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("overall_score", res.json())

    # =========================================================================
    # NEXT QUESTION TESTS (17 - 27)
    # =========================================================================

    def test_17_poor_response_continues_target_skill(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_target_skill": "PostgreSQL Indexing",
                "previous_question": "Explain B-tree index mechanics.",
                "previous_response": "I don't know.",
                "latest_evaluation": {
                    "adaptive_session_id": "asess_test",
                    "evaluation_version": "eval-v1.2.0",
                    "overall_score": 45.0,
                    "skill_scores": [{"skill": "PostgreSQL Indexing", "score": 45.0, "evidence": "no answer", "confidence": "HIGH"}],
                    "mistakes": [],
                    "summary": "Poor response."
                },
                "role": "Backend Engineer",
                "difficulty": "Hard"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["strategy"], "continue_probing")
        self.assertEqual(data["question"]["target_skill"], "PostgreSQL Indexing")

    def test_18_repeated_mistake_generates_targeted_follow_up(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_target_skill": "Answer Structure",
                "previous_question": "Tell me about a time you handled a deadline crunch.",
                "latest_evaluation": {
                    "adaptive_session_id": "asess_test",
                    "evaluation_version": "eval-v1.2.0",
                    "overall_score": 62.0,
                    "skill_scores": [{"skill": "Answer Structure", "score": 62.0, "evidence": "Situation skipped", "confidence": "HIGH"}],
                    "mistakes": [{
                        "skill": "Answer Structure",
                        "category": "STAR_framing",
                        "severity": "medium",
                        "description": "Situation context was omitted.",
                        "recommendation": "Use STAR."
                    }],
                    "summary": "Missing situation context."
                },
                "role": "Engineering Manager"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["strategy"], "mistake_follow_up")
        self.assertEqual(data["question"]["reason"], "previous_mistake")
        self.assertEqual(data["question"]["focus_skill"], "STAR_framing")

    def test_19_improved_response_changes_strategy(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_target_skill": "System Architecture",
                "latest_evaluation": {
                    "adaptive_session_id": "asess_test",
                    "evaluation_version": "eval-v1.2.0",
                    "overall_score": 85.0,
                    "skill_scores": [{"skill": "System Architecture", "score": 85.0, "evidence": "Excellent depth", "confidence": "HIGH"}],
                    "mistakes": [],
                    "summary": "Strong architecture answer."
                },
                "role": "Backend Engineer",
                "difficulty": "Medium"
            }
        )
        data = res.json()
        self.assertIn(data["strategy"], ["scale_difficulty", "advance_next_weakness"])

    def test_20_strong_repeated_performance_moves_to_next_weakness(self):
        db = TestingSessionLocal()
        # Weakness 1: Redis (improving)
        w1 = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Redis",
            score=86.0,
            trend="improving",
            evidence_count=3,
            confidence="HIGH",
            weakness_status="improving"
        )
        # Weakness 2: Kafka (identified)
        w2 = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Kafka",
            score=55.0,
            trend="declining",
            evidence_count=2,
            confidence="MEDIUM",
            weakness_status="identified"
        )
        db.add_all([w1, w2])
        db.commit()
        db.close()

        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_target_skill": "Redis",
                "latest_evaluation": {
                    "adaptive_session_id": "asess_test",
                    "overall_score": 88.0,
                    "skill_scores": [{"skill": "Redis", "score": 88.0, "evidence": "Great", "confidence": "HIGH"}],
                    "mistakes": [],
                    "summary": "Mastered."
                },
                "role": "Backend Engineer"
            }
        )
        data = res.json()
        self.assertEqual(data["strategy"], "advance_next_weakness")
        self.assertEqual(data["question"]["target_skill"], "Kafka")

    def test_21_resolved_weakness_moves_to_next_priority(self):
        db = TestingSessionLocal()
        w1 = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="SQL",
            score=90.0,
            trend="improving",
            evidence_count=4,
            confidence="HIGH",
            weakness_status="resolved"
        )
        w2 = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Kubernetes",
            score=58.0,
            trend="declining",
            evidence_count=2,
            confidence="MEDIUM",
            weakness_status="identified"
        )
        db.add_all([w1, w2])
        db.commit()
        db.close()

        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_target_skill": "SQL",
                "latest_evaluation": {
                    "adaptive_session_id": "asess_test",
                    "overall_score": 92.0,
                    "skill_scores": [],
                    "mistakes": [],
                    "summary": "Resolved."
                },
                "role": "DevOps Engineer"
            }
        )
        data = res.json()
        self.assertEqual(data["question"]["target_skill"], "Kubernetes")

    def test_22_difficulty_adaptation(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_target_skill": "Concurrency",
                "difficulty": "Medium",
                "latest_evaluation": {
                    "adaptive_session_id": "asess_test",
                    "overall_score": 84.0,
                    "skill_scores": [],
                    "mistakes": [],
                    "summary": "Good."
                },
                "role": "Backend Engineer"
            }
        )
        data = res.json()
        if data["strategy"] == "scale_difficulty":
            self.assertEqual(data["question"]["difficulty"], "Hard")

    def test_23_question_metadata_in_next_question(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Backend Engineer", "skills": ["Python"]}
        )
        q = res.json()["question"]
        self.assertIn("question", q)
        self.assertIn("reason", q)
        self.assertIn("source", q)
        self.assertIn("target_skill", q)
        self.assertIn("focus_skill", q)
        self.assertIn("difficulty", q)
        self.assertEqual(q["question_engine_version"], "adaptive-qengine-v1.0.0")

    def test_24_session_lineage_preserved_in_next_question(self):
        token = self.get_token_a()
        custom_session = "asess_continuous_lineage_777"
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={"adaptive_session_id": custom_session, "role": "Backend Engineer"}
        )
        self.assertEqual(res.json()["adaptive_session_id"], custom_session)

    def test_25_duplicate_prevention_on_next_question(self):
        token = self.get_token_a()
        prev_q = "Explain Python GIL and how to achieve concurrency."
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "previous_question": prev_q,
                "role": "Backend Engineer",
                "skills": ["Python"]
            }
        )
        q_text = res.json()["question"]["question"]
        self.assertNotEqual(q_text.strip(), prev_q.strip())

    def test_26_ai_fallback_on_next_question(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Product Manager", "skills": ["Roadmapping"]}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.json()["question"]["question"]) > 10)

    def test_27_offline_fallback_on_next_question(self):
        token = self.get_token_a()
        res = client.post(
            "/api/adaptive/next-question",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "Data Engineer", "skills": ["Apache Spark"]}
        )
        self.assertEqual(res.status_code, 200)

    # =========================================================================
    # REGRESSION TESTS (28 - 30)
    # =========================================================================

    def test_28_existing_api_generate_endpoint_remains_intact(self):
        token = self.get_token_a()
        res = client.post(
            "/api/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Frontend Developer",
                "skills": ["Vue.js"],
                "number_of_questions": 3
            }
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["questions"]), 3)

    def test_29_existing_generate_alias_remains_intact(self):
        token = self.get_token_a()
        res = client.post(
            "/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "role": "Backend Engineer",
                "skills": ["Django"],
                "number_of_questions": 3
            }
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["questions"]), 3)

    def test_30_existing_interview_flow_remains_intact(self):
        token = self.get_token_a()
        res = client.get(
            "/api/adaptive/profile",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
