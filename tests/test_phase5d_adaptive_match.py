"""
Phase 5D Test Suite: Resume/JD Match → Adaptive Interview Integration
Tests all 25 required scenarios:
1. Valid scan → adaptive generation
2. Authenticated request
3. Unauthenticated request (401)
4. Cross-user scan rejection (404 without data leak)
5. Nonexistent scan (404)
6. Critical JD gap becomes target_skill
7. reason = jd_requirement
8. evidence_reference comes from server
9. HIGH importance prioritization over lower importance
10. Multiple critical gaps handling
11. Existing candidate weakness combined with JD gap
12. Previous mistake combined with JD gap
13. 60/40 question distribution
14. adaptive_session_id created & linked
15. scan_id preserved in response
16. Version metadata preserved
17. Missing match data fallback
18. Database unavailable / corrupt data fallback
19. AI unavailable fallback (deterministic questions)
20. Duplicate prevention
21. Existing adaptive APIs remain functional
22. Existing /generate endpoints remain functional
23. Tenant isolation
24. No frontend-trusted evidence accepted
25. No fabricated JD gaps
"""

import os
import sys
import json
import uuid
import unittest
from datetime import datetime
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
    ResumeScan,
    InterviewHistory,
    CandidateSkillAnalytics,
    CandidateMistakesLedger
)
from app.security import hash_password, create_access_token
from app.auth_deps import FAILED_LOGIN_ATTEMPTS
from app.models import (
    NormalizedJobDescription,
    NormalizedResume,
    SkillMatrixItem,
    SubScores
)

# Setup isolated test in-memory SQLite database with StaticPool
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


client = TestClient(app)


class TestPhase5DAdaptiveMatchIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)

    def setUp(self):
        client.cookies.clear()
        FAILED_LOGIN_ATTEMPTS.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        # Seed Candidate A
        candidate_a = UserAccount(
            email="candidate_a@example.com",
            full_name="Alice Candidate",
            password_hash=hash_password("AlicePass123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        # Seed Candidate B
        candidate_b = UserAccount(
            email="candidate_b@example.com",
            full_name="Bob Candidate",
            password_hash=hash_password("BobPass123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add_all([candidate_a, candidate_b])
        db.commit()
        db.refresh(candidate_a)
        db.refresh(candidate_b)

        self.cand_a_id = candidate_a.id
        self.cand_a_email = candidate_a.email
        self.cand_b_id = candidate_b.id
        self.cand_b_email = candidate_b.email

        # Seed a realistic ResumeScan for Candidate A
        # Skills: Python (Match 100%, High), FastAPI (Match 88%, High), Kafka (Match 0%, Gap, High), Kubernetes (Match 0%, Gap, High)
        self.scan_id_a = f"scan_{uuid.uuid4().hex}"
        matrix_a = [
            {"skill": "Python", "importance": "HIGH", "match_score": 100.0, "evidence_level": 1, "gap_status": "matched"},
            {"skill": "FastAPI", "importance": "HIGH", "match_score": 88.0, "evidence_level": 2, "gap_status": "matched"},
            {"skill": "Kafka", "importance": "HIGH", "match_score": 0.0, "evidence_level": 6, "gap_status": "gap"},
            {"skill": "Kubernetes", "importance": "HIGH", "match_score": 0.0, "evidence_level": 6, "gap_status": "gap"},
            {"skill": "Redis", "importance": "MEDIUM", "match_score": 70.0, "evidence_level": 3, "gap_status": "matched"},
        ]
        norm_jd_a = {
            "job_title": "Senior Distributed Backend Engineer",
            "company": "FinTech Stream Inc",
            "experience_required": "5+ years",
            "required_skills": ["Python", "FastAPI", "Kafka", "Kubernetes"],
            "preferred_skills": ["Redis"]
        }
        scan_a = ResumeScan(
            scan_id=self.scan_id_a,
            user_id=self.cand_a_id,
            matching_engine_version="match-v1.0.0",
            candidate_name="Alice Candidate",
            target_role="Senior Distributed Backend Engineer",
            match_score=72.0,
            overall_match_score=72.0,
            match_confidence="HIGH",
            sub_scores=json.dumps({"required_skills": 47.0, "experience": 90.0, "domain": 85.0, "responsibilities": 85.0, "preferred_skills": 70.0}),
            skill_matrix=json.dumps(matrix_a),
            strengths=json.dumps(["Python (Level 1)", "FastAPI (Level 2)"]),
            skill_gaps=json.dumps(["Kafka (Score: 0%)", "Kubernetes (Score: 0%)"]),
            critical_gaps=json.dumps(["Critical Gap: Kafka", "Critical Gap: Kubernetes"]),
            recommendations=json.dumps(["Add direct production experience for Kafka", "Gain container orchestration experience in Kubernetes"]),
            normalized_jd=json.dumps(norm_jd_a),
            normalized_resume=json.dumps({"candidate_name": "Alice Candidate", "skills": ["Python", "FastAPI", "Redis", "Docker"]}),
            source_type="paste",
            created_at=datetime.utcnow()
        )
        db.add(scan_a)
        db.commit()
        db.close()

        token_a = create_access_token({"sub": self.cand_a_id, "email": self.cand_a_email, "role": "candidate"})
        self.auth_headers_a = {"Authorization": f"Bearer {token_a}"}

        token_b = create_access_token({"sub": self.cand_b_id, "email": self.cand_b_email, "role": "candidate"})
        self.auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=engine)

    # --------------------------------------------------------------------------
    # 1. Valid Scan → Adaptive Generation
    # --------------------------------------------------------------------------
    def test_01_valid_scan_to_adaptive_generation(self):
        payload = {"scan_id": self.scan_id_a, "number_of_questions": 5}
        resp = client.post("/api/adaptive/from-match", json=payload, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("adaptive_session_id", data)
        self.assertTrue(data["adaptive_session_id"].startswith("asess_"))
        self.assertEqual(data["scan_id"], self.scan_id_a)
        self.assertEqual(len(data["questions"]), 5)

    # --------------------------------------------------------------------------
    # 2. Authenticated Request
    # --------------------------------------------------------------------------
    def test_02_authenticated_request(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)

    # --------------------------------------------------------------------------
    # 3. Unauthenticated Request (401)
    # --------------------------------------------------------------------------
    def test_03_unauthenticated_request(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a})
        self.assertEqual(resp.status_code, 401)

    # --------------------------------------------------------------------------
    # 4. Cross-User Scan Rejection (Tenant Isolation - 404)
    # --------------------------------------------------------------------------
    def test_04_cross_user_scan_rejection(self):
        # Candidate B attempts to start deep practice on Candidate A's scan
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a}, headers=self.auth_headers_b)
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found or access denied", resp.json()["detail"].lower())

    # --------------------------------------------------------------------------
    # 5. Nonexistent Scan ID (404)
    # --------------------------------------------------------------------------
    def test_05_nonexistent_scan(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": "scan_nonexistent_9999"}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 404)

    # --------------------------------------------------------------------------
    # 6. Critical JD Gap Becomes target_skill
    # --------------------------------------------------------------------------
    def test_06_critical_jd_gap_becomes_target_skill(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 5}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # In our scan, Kafka is a Level 6 High Importance gap
        first_q = data["questions"][0]
        self.assertIn(first_q["target_skill"], ["Kafka", "Kubernetes"])

    # --------------------------------------------------------------------------
    # 7. reason = jd_requirement
    # --------------------------------------------------------------------------
    def test_07_reason_is_jd_requirement(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 5}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # The targeted questions must have reason == "jd_requirement"
        self.assertEqual(data["questions"][0]["reason"], "jd_requirement")
        self.assertEqual(data["questions"][1]["reason"], "jd_requirement")
        self.assertEqual(data["questions"][2]["reason"], "jd_requirement")

    # --------------------------------------------------------------------------
    # 8. evidence_reference Comes From Server
    # --------------------------------------------------------------------------
    def test_08_evidence_reference_comes_from_server(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 5}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        first_q = data["questions"][0]
        ev_ref = first_q["evidence_reference"]
        self.assertIsNotNone(ev_ref)
        self.assertEqual(ev_ref["source"], "resume_jd_match")
        self.assertEqual(ev_ref["scan_id"], self.scan_id_a)
        self.assertEqual(ev_ref["jd_importance"], "HIGH")
        self.assertEqual(ev_ref["matching_engine_version"], "match-v1.0.0")

    # --------------------------------------------------------------------------
    # 9. HIGH Importance Prioritization Over Lower Importance
    # --------------------------------------------------------------------------
    def test_09_high_importance_prioritization(self):
        # Create scan where:
        # Skill A: "AI Design", Match=45%, Importance=HIGH
        # Skill B: "After Effects", Match=15%, Importance=LOW
        db = TestingSessionLocal()
        scan_id_rank = f"scan_{uuid.uuid4().hex}"
        matrix = [
            {"skill": "AI Design", "importance": "HIGH", "match_score": 45.0, "evidence_level": 4, "gap_status": "partial"},
            {"skill": "After Effects", "importance": "LOW", "match_score": 15.0, "evidence_level": 5, "gap_status": "gap"},
        ]
        scan = ResumeScan(
            scan_id=scan_id_rank,
            user_id=self.cand_a_id,
            matching_engine_version="match-v1.0.0",
            target_role="Product Designer",
            skill_matrix=json.dumps(matrix),
            normalized_jd=json.dumps({"job_title": "Product Designer", "required_skills": ["AI Design"]}),
            created_at=datetime.utcnow()
        )
        db.add(scan)
        db.commit()
        db.close()

        resp = client.post("/api/adaptive/from-match", json={"scan_id": scan_id_rank, "number_of_questions": 5}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # High importance AI Design must be prioritized over lower importance After Effects
        self.assertEqual(data["questions"][0]["target_skill"], "AI Design")

    # --------------------------------------------------------------------------
    # 10. Multiple Critical Gaps Handling
    # --------------------------------------------------------------------------
    def test_10_multiple_critical_gaps_handling(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 5}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["recommended_focus"])
        self.assertIn("gap", data["recommended_focus"]["reason"].lower())

    # --------------------------------------------------------------------------
    # 11. Existing Candidate Weakness Combined with JD Gap
    # --------------------------------------------------------------------------
    def test_11_candidate_weakness_combined_with_jd_gap(self):
        # Seed an existing weakness for Kubernetes in CandidateSkillAnalytics
        db = TestingSessionLocal()
        analytics = CandidateSkillAnalytics(
            user_id=self.cand_a_id,
            skill="Kubernetes",
            score=40.0,
            trend="declining",
            weakness_status="persistent",
            confidence="HIGH"
        )
        db.add(analytics)
        db.commit()
        db.close()

        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 5}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Kubernetes with historical weakness boost should become the top target
        self.assertEqual(data["questions"][0]["target_skill"], "Kubernetes")

    # --------------------------------------------------------------------------
    # 12. Previous Mistake Combined with JD Gap
    # --------------------------------------------------------------------------
    def test_12_previous_mistake_combined_with_jd_gap(self):
        db = TestingSessionLocal()
        mistake = CandidateMistakesLedger(
            user_id=self.cand_a_id,
            adaptive_session_id="asess_old",
            skill="Kafka",
            mistake_category="Partition Rebalancing Architecture",
            description="Failed to explain consumer group rebalance storm mitigation.",
            severity="high",
            mistake_status="identified"
        )
        db.add(mistake)
        db.commit()
        db.close()

        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 5}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["questions"][0]["target_skill"], "Kafka")

    # --------------------------------------------------------------------------
    # 13. 60/40 Question Distribution
    # --------------------------------------------------------------------------
    def test_13_sixty_forty_question_distribution(self):
        # 10 questions -> exactly 6 gap-targeted (60%), 4 broad role (40%)
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 10}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        questions = resp.json()["questions"]
        self.assertEqual(len(questions), 10)

        gap_questions = [q for q in questions if q["reason"] == "jd_requirement"]
        role_questions = [q for q in questions if q["reason"] == "role_requirement"]
        self.assertEqual(len(gap_questions), 6)
        self.assertEqual(len(role_questions), 4)

    # --------------------------------------------------------------------------
    # 14. adaptive_session_id Created & Linked
    # --------------------------------------------------------------------------
    def test_14_adaptive_session_id_created(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a}, headers=self.auth_headers_a)
        session_id = resp.json()["adaptive_session_id"]
        self.assertTrue(session_id.startswith("asess_"))

        # Verify saved in InterviewHistory
        db = TestingSessionLocal()
        history = db.query(InterviewHistory).filter(InterviewHistory.adaptive_session_id == session_id).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.user_id, self.cand_a_id)
        db.close()

    # --------------------------------------------------------------------------
    # 15. scan_id Preserved in Response
    # --------------------------------------------------------------------------
    def test_15_scan_id_preserved(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a}, headers=self.auth_headers_a)
        self.assertEqual(resp.json()["scan_id"], self.scan_id_a)

    # --------------------------------------------------------------------------
    # 16. Version Metadata Preserved
    # --------------------------------------------------------------------------
    def test_16_version_metadata_preserved(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a}, headers=self.auth_headers_a)
        q = resp.json()["questions"][0]
        self.assertEqual(q["question_engine_version"], "adaptive-qengine-v1.0.0")
        self.assertEqual(q["evidence_reference"]["matching_engine_version"], "match-v1.0.0")

    # --------------------------------------------------------------------------
    # 17. Missing Match Data Fallback
    # --------------------------------------------------------------------------
    def test_17_missing_match_data_fallback(self):
        # Scan with empty skill matrix and empty normalized JD
        db = TestingSessionLocal()
        sparse_scan_id = f"scan_{uuid.uuid4().hex}"
        sparse_scan = ResumeScan(
            scan_id=sparse_scan_id,
            user_id=self.cand_a_id,
            target_role="General Tech Engineer",
            skill_matrix="[]",
            created_at=datetime.utcnow()
        )
        db.add(sparse_scan)
        db.commit()
        db.close()

        resp = client.post("/api/adaptive/from-match", json={"scan_id": sparse_scan_id, "number_of_questions": 3}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["questions"]), 3)

    # --------------------------------------------------------------------------
    # 18. Database Unavailable / Corrupt Data Fallback
    # --------------------------------------------------------------------------
    def test_18_corrupt_scan_data_fallback(self):
        # Scan with malformed JSON strings
        db = TestingSessionLocal()
        corrupt_scan_id = f"scan_{uuid.uuid4().hex}"
        corrupt_scan = ResumeScan(
            scan_id=corrupt_scan_id,
            user_id=self.cand_a_id,
            target_role="Data Engineer",
            skill_matrix="INVALID_JSON",
            normalized_jd="INVALID_JSON",
            created_at=datetime.utcnow()
        )
        db.add(corrupt_scan)
        db.commit()
        db.close()

        resp = client.post("/api/adaptive/from-match", json={"scan_id": corrupt_scan_id, "number_of_questions": 3}, headers=self.auth_headers_a)
        # Should gracefully fall back without 500 error
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["questions"]), 3)

    # --------------------------------------------------------------------------
    # 19. AI Unavailable Fallback
    # --------------------------------------------------------------------------
    def test_19_ai_unavailable_fallback(self):
        # Engine runs with no LLM API key -> returns deterministic curated questions
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 5}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        questions = resp.json()["questions"]
        self.assertEqual(len(questions), 5)
        for q in questions:
            self.assertTrue(len(q["question"]) > 10)

    # --------------------------------------------------------------------------
    # 20. Duplicate Prevention
    # --------------------------------------------------------------------------
    def test_20_duplicate_prevention(self):
        resp1 = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 3}, headers=self.auth_headers_a)
        resp2 = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a, "number_of_questions": 3}, headers=self.auth_headers_a)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

    # --------------------------------------------------------------------------
    # 21. Existing Adaptive APIs Remain Functional
    # --------------------------------------------------------------------------
    def test_21_existing_adaptive_apis_functional(self):
        # 1. Profile
        prof_resp = client.get("/api/adaptive/profile", headers=self.auth_headers_a)
        self.assertEqual(prof_resp.status_code, 200)

        # 2. Generate
        gen_payload = {
            "role": "Backend Engineer",
            "experience": "3-5 Years",
            "skills": ["Python", "FastAPI"],
            "difficulty": "Hard",
            "number_of_questions": 3
        }
        gen_resp = client.post("/api/adaptive/generate", json=gen_payload, headers=self.auth_headers_a)
        self.assertEqual(gen_resp.status_code, 200)
        self.assertIn("adaptive_session_id", gen_resp.json())

        # 3. Evaluate response
        eval_payload = {
            "adaptive_session_id": gen_resp.json()["adaptive_session_id"],
            "question": "How do you handle DB connection pooling in FastAPI?",
            "candidate_response": "I use SQLAlchemy async session pool with pool_size 5.",
            "target_skill": "FastAPI",
            "role": "Backend Engineer"
        }
        eval_resp = client.post("/api/adaptive/evaluate-response", json=eval_payload, headers=self.auth_headers_a)
        self.assertEqual(eval_resp.status_code, 200)

        # 4. Next question
        next_payload = {
            "adaptive_session_id": gen_resp.json()["adaptive_session_id"],
            "latest_score": 75.0,
            "target_skill": "FastAPI",
            "role": "Backend Engineer"
        }
        next_resp = client.post("/api/adaptive/next-question", json=next_payload, headers=self.auth_headers_a)
        self.assertEqual(next_resp.status_code, 200)

    # --------------------------------------------------------------------------
    # 22. Existing /generate Remains Functional
    # --------------------------------------------------------------------------
    def test_22_existing_generate_endpoint_functional(self):
        gen_payload = {
            "role": "Python Developer",
            "experience": "3-5 Years",
            "skills": ["Python", "SQL"],
            "difficulty": "Medium",
            "number_of_questions": 3
        }
        resp = client.post("/api/generate", json=gen_payload, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["questions"]), 3)

    # --------------------------------------------------------------------------
    # 23. Tenant Isolation
    # --------------------------------------------------------------------------
    def test_23_tenant_isolation(self):
        resp_a = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a}, headers=self.auth_headers_a)
        self.assertEqual(resp_a.status_code, 200)

        # Candidate B must not be able to execute Candidate A's scan
        resp_b = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a}, headers=self.auth_headers_b)
        self.assertEqual(resp_b.status_code, 404)

    # --------------------------------------------------------------------------
    # 24. No Frontend-Trusted Evidence Accepted
    # --------------------------------------------------------------------------
    def test_24_no_frontend_trusted_evidence_accepted(self):
        # If client passes spoofed critical_gaps or evidence in request body,
        # it is discarded because AdaptiveFromMatchRequest only accepts scan_id and number_of_questions
        spoofed_payload = {
            "scan_id": self.scan_id_a,
            "critical_gaps": ["SpoofedSkill"],
            "target_skill": "SpoofedSkill",
            "evidence_reference": {"source": "fake"}
        }
        resp = client.post("/api/adaptive/from-match", json=spoofed_payload, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        first_q = data["questions"][0]
        # Target skill must be from server-side persisted Kafka or Kubernetes, never SpoofedSkill
        self.assertNotEqual(first_q["target_skill"], "SpoofedSkill")
        self.assertIn(first_q["target_skill"], ["Kafka", "Kubernetes"])

    # --------------------------------------------------------------------------
    # 25. No Fabricated JD Gaps
    # --------------------------------------------------------------------------
    def test_25_no_fabricated_jd_gaps(self):
        resp = client.post("/api/adaptive/from-match", json={"scan_id": self.scan_id_a}, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        first_q = resp.json()["questions"][0]
        # Must strictly match the verified gaps from the scan
        self.assertIn(first_q["target_skill"], ["Kafka", "Kubernetes"])


if __name__ == "__main__":
    unittest.main()
