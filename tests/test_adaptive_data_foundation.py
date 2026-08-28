import unittest
import os
import sys
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.database import Base, get_db, init_db
from app.db_models import (
    UserAccount,
    InterviewHistory,
    CandidateSkillAnalytics,
    CandidateMistakesLedger
)
from app.models import (
    InterviewRequest,
    WeaknessStatusEnum,
    MistakeStatusEnum,
    ConfidenceLevelEnum,
    MistakeSeverityEnum,
    TrendSlopeEnum,
    QuestionReasonEnum,
    SkillAnalyticsCreate,
    SkillAnalyticsResponse,
    MistakeLedgerCreate,
    MistakeLedgerResponse,
    DEFAULT_QUESTION_ENGINE_VERSION,
    DEFAULT_EVALUATION_VERSION
)
from app.security import hash_password

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


class TestAdaptiveDataFoundation(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        Base.metadata.drop_all(bind=test_engine)
        Base.metadata.create_all(bind=test_engine)

        db = TestingSessionLocal()
        # Seed test candidate user
        candidate = UserAccount(
            email="adaptive_candidate@example.com",
            full_name="Adaptive Test Candidate",
            password_hash=hash_password("CandidatePass123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        self.candidate_id = candidate.id
        db.close()

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.pop(get_db, None)

    def test_enums_definitions(self):
        """Verify all adaptive lifecycle and metadata enums have correct members."""
        self.assertEqual(
            [e.value for e in WeaknessStatusEnum],
            ["identified", "practicing", "improving", "resolved"]
        )
        self.assertEqual(
            [e.value for e in MistakeStatusEnum],
            ["identified", "practicing", "resolved"]
        )
        self.assertEqual(
            [e.value for e in ConfidenceLevelEnum],
            ["LOW", "MEDIUM", "HIGH"]
        )
        self.assertEqual(
            [e.value for e in MistakeSeverityEnum],
            ["low", "medium", "high", "critical"]
        )
        self.assertEqual(
            [e.value for e in TrendSlopeEnum],
            ["improving", "flat", "declining"]
        )
        self.assertEqual(
            [e.value for e in QuestionReasonEnum],
            [
                "role_requirement",
                "resume_skill",
                "jd_requirement",
                "candidate_weakness",
                "previous_mistake",
                "low_score",
                "practice_goal",
                "follow_up"
            ]
        )

    def test_candidate_skill_analytics_crud(self):
        """Verify candidate_skill_analytics table creation, fields, and persistence."""
        db = TestingSessionLocal()

        analytics_entry = CandidateSkillAnalytics(
            user_id=self.candidate_id,
            skill="PostgreSQL Indexing",
            score=62.5,
            trend="declining",
            role_relevance=1.0,
            evidence_count=2,
            confidence="HIGH",
            weakness_status="identified",
            adaptive_session_id="asess_test_101",
            first_detected_at=datetime.utcnow(),
            last_updated_at=datetime.utcnow()
        )
        db.add(analytics_entry)
        db.commit()
        db.refresh(analytics_entry)

        self.assertIsNotNone(analytics_entry.id)
        self.assertEqual(analytics_entry.user_id, self.candidate_id)
        self.assertEqual(analytics_entry.skill, "PostgreSQL Indexing")
        self.assertEqual(analytics_entry.score, 62.5)
        self.assertEqual(analytics_entry.confidence, "HIGH")
        self.assertEqual(analytics_entry.weakness_status, "identified")
        self.assertEqual(analytics_entry.adaptive_session_id, "asess_test_101")

        # Test Pydantic serialization
        res_model = SkillAnalyticsResponse(
            id=analytics_entry.id,
            user_id=analytics_entry.user_id,
            skill=analytics_entry.skill,
            score=analytics_entry.score,
            trend=analytics_entry.trend,
            role_relevance=analytics_entry.role_relevance,
            evidence_count=analytics_entry.evidence_count,
            confidence=analytics_entry.confidence,
            weakness_status=analytics_entry.weakness_status,
            adaptive_session_id=analytics_entry.adaptive_session_id,
            first_detected_at=analytics_entry.first_detected_at.isoformat(),
            last_updated_at=analytics_entry.last_updated_at.isoformat()
        )
        self.assertEqual(res_model.skill, "PostgreSQL Indexing")
        self.assertEqual(res_model.weakness_status, "identified")

        db.close()

    def test_candidate_mistakes_ledger_crud(self):
        """Verify candidate_mistakes_ledger table creation, fields, and persistence."""
        db = TestingSessionLocal()

        # Create source interview history sitting
        interview = InterviewHistory(
            user_id=self.candidate_id,
            adaptive_session_id="asess_test_102",
            role="Backend Engineer",
            experience="5 Years",
            skills="PostgreSQL, Redis",
            difficulty="Hard",
            questions="1. How do you design an idempotent payment API?",
            question_engine_version=DEFAULT_QUESTION_ENGINE_VERSION
        )
        db.add(interview)
        db.commit()
        db.refresh(interview)

        mistake = CandidateMistakesLedger(
            user_id=self.candidate_id,
            interview_id=interview.id,
            adaptive_session_id="asess_test_102",
            skill="PostgreSQL Indexing",
            mistake_category="concurrency_control",
            description="Failed to account for connection pool exhaustion during traffic surges.",
            evidence="Candidate proposed unbounded connection spawning without PgBouncer.",
            severity="high",
            recommendation="Implement connection pooling with queue limits and health check timeouts.",
            mistake_status="identified",
            evaluation_version=DEFAULT_EVALUATION_VERSION
        )
        db.add(mistake)
        db.commit()
        db.refresh(mistake)

        self.assertIsNotNone(mistake.id)
        self.assertEqual(mistake.user_id, self.candidate_id)
        self.assertEqual(mistake.interview_id, interview.id)
        self.assertEqual(mistake.adaptive_session_id, "asess_test_102")
        self.assertEqual(mistake.severity, "high")
        self.assertEqual(mistake.mistake_status, "identified")
        self.assertEqual(mistake.evaluation_version, DEFAULT_EVALUATION_VERSION)

        # Test Pydantic serialization
        res_model = MistakeLedgerResponse(
            id=mistake.id,
            user_id=mistake.user_id,
            interview_id=mistake.interview_id,
            adaptive_session_id=mistake.adaptive_session_id,
            skill=mistake.skill,
            mistake_category=mistake.mistake_category,
            description=mistake.description,
            evidence=mistake.evidence,
            severity=mistake.severity,
            recommendation=mistake.recommendation,
            mistake_status=mistake.mistake_status,
            evaluation_version=mistake.evaluation_version,
            created_at=mistake.created_at.isoformat()
        )
        self.assertEqual(res_model.severity, "high")
        self.assertEqual(res_model.mistake_status, "identified")

        db.close()

    def test_interview_history_adaptive_lineage_fields(self):
        """Verify interview_history retains lightweight schema while supporting adaptive lineage."""
        db = TestingSessionLocal()

        interview = InterviewHistory(
            user_id=self.candidate_id,
            adaptive_session_id="asess_test_103",
            role="GenAI Architect",
            experience="5 Years",
            skills="LLMs, RAG, LangGraph",
            difficulty="Hard",
            questions="1. How do you implement hybrid vector search with BM25?",
            question_engine_version="qengine-v2.0.0"
        )
        db.add(interview)
        db.commit()
        db.refresh(interview)

        self.assertEqual(interview.user_id, self.candidate_id)
        self.assertEqual(interview.adaptive_session_id, "asess_test_103")
        self.assertEqual(interview.question_engine_version, "qengine-v2.0.0")

        db.close()

    def test_legacy_interview_request_backward_compatibility(self):
        """Ensure legacy client payloads without adaptive fields parse cleanly."""
        legacy_payload = {
            "role": "Frontend Developer",
            "experience": "3-5 Years",
            "skills": ["React", "TypeScript"],
            "difficulty": "Medium",
            "number_of_questions": 5
        }
        req = InterviewRequest(**legacy_payload)
        self.assertEqual(req.role, "Frontend Developer")
        self.assertIsNone(req.adaptive_session_id)
        self.assertIsNone(req.resume_text)
        self.assertIsNone(req.jd_text)
        self.assertEqual(req.practice_goal, "balanced")

    def test_extended_interview_request_with_adaptive_fields(self):
        """Ensure extended payloads with adaptive lineage parse cleanly."""
        extended_payload = {
            "role": "Staff Backend Engineer",
            "experience": "8+ Years",
            "skills": ["Python", "Distributed Systems"],
            "difficulty": "Brutal",
            "number_of_questions": 10,
            "adaptive_session_id": "asess_longitudinal_77",
            "resume_text": "Experienced building event-driven microservices...",
            "jd_text": "Requires Kafka, Kubernetes, gRPC...",
            "practice_goal": "weakness_remediation"
        }
        req = InterviewRequest(**extended_payload)
        self.assertEqual(req.role, "Staff Backend Engineer")
        self.assertEqual(req.adaptive_session_id, "asess_longitudinal_77")
        self.assertEqual(req.practice_goal, "weakness_remediation")

    def test_sqlite_migration_columns_check(self):
        """Verify that SQLite migration queries successfully ensure columns on interview_history."""
        with test_engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(interview_history)"))
            columns = {row[1]: row[2] for row in result.fetchall()}
            self.assertIn("id", columns)
            self.assertIn("user_id", columns)
            self.assertIn("adaptive_session_id", columns)
            self.assertIn("question_engine_version", columns)
            self.assertIn("created_at", columns)

            result_skill = conn.execute(text("PRAGMA table_info(candidate_skill_analytics)"))
            skill_cols = {row[1]: row[2] for row in result_skill.fetchall()}
            self.assertIn("user_id", skill_cols)
            self.assertIn("skill", skill_cols)
            self.assertIn("weakness_status", skill_cols)
            self.assertIn("confidence", skill_cols)

            result_mistake = conn.execute(text("PRAGMA table_info(candidate_mistakes_ledger)"))
            mistake_cols = {row[1]: row[2] for row in result_mistake.fetchall()}
            self.assertIn("user_id", mistake_cols)
            self.assertIn("adaptive_session_id", mistake_cols)
            self.assertIn("mistake_status", mistake_cols)
            self.assertIn("evaluation_version", mistake_cols)

    def test_legacy_generate_endpoint_backward_compatibility(self):
        """Verify that existing POST /api/generate endpoint continues to work without regression."""
        # Log in candidate
        login_res = client.post("/api/candidate/login", json={
            "email": "adaptive_candidate@example.com",
            "password": "CandidatePass123!"
        })
        self.assertEqual(login_res.status_code, 200)

        # Call /api/generate with legacy payload
        gen_res = client.post("/api/generate", json={
            "role": "Frontend Developer",
            "experience": "3 Years",
            "skills": ["React", "TypeScript"],
            "difficulty": "Medium",
            "number_of_questions": 5
        })
        self.assertEqual(gen_res.status_code, 200)
        data = gen_res.json()
        self.assertIn("id", data)
        self.assertIn("questions", data)
        self.assertEqual(len(data["questions"]), 5)
        self.assertIn("questions_details", data)
        self.assertEqual(data["user_id"], self.candidate_id)


if __name__ == "__main__":
    unittest.main()
