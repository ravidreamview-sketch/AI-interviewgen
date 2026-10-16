"""
Phase 5C Test Suite: Match Result Persistence & API
Tests all required scenarios:
1. Authenticated match creation
2. Unauthenticated match creation (401)
3. Authenticated retrieval
4. Cross-user retrieval rejection (404 without data leak)
5. Nonexistent scan_id handling (404)
6. Scan ownership integrity (current_user.id strictly enforced)
7. Scan_id uniqueness
8. Database result persistence integrity
9. Exact result retrieval (no recalculation on GET)
10. Matching version persistence ("match-v1.0.0")
11. Match creation with public JD URL
12. Missing input validation (400)
13. Candidate scan history endpoint and tenant isolation
"""

import os
import sys
import json
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount, ResumeScan
from app.security import hash_password, create_access_token
from app.auth_deps import FAILED_LOGIN_ATTEMPTS
from app.models import (
    NormalizedJobDescription,
    NormalizedResume,
    ResumeWorkExperience,
    ResumeJDMatchRequest,
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


class TestPhase5CMatchPersistenceAndAPI(unittest.TestCase):

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
            password_hash=hash_password("AliceSecure123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        # Seed Candidate B (for cross-user isolation tests)
        candidate_b = UserAccount(
            email="candidate_b@example.com",
            full_name="Bob Candidate",
            password_hash=hash_password("BobSecure123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add_all([candidate_a, candidate_b])
        db.commit()
        db.refresh(candidate_a)
        db.refresh(candidate_b)

        self.candidate_a_id = candidate_a.id
        self.candidate_a_email = candidate_a.email
        self.candidate_b_id = candidate_b.id
        self.candidate_b_email = candidate_b.email
        db.close()

        token_a = create_access_token({"sub": self.candidate_a_id, "email": self.candidate_a_email, "role": "candidate"})
        self.auth_headers_a = {"Authorization": f"Bearer {token_a}"}

        token_b = create_access_token({"sub": self.candidate_b_id, "email": self.candidate_b_email, "role": "candidate"})
        self.auth_headers_b = {"Authorization": f"Bearer {token_b}"}

        self.sample_jd_text = """
        Job Title: Senior Backend Engineer
        Company: CloudTech Inc.
        Experience: 5+ years
        Required Skills: Python, FastAPI, PostgreSQL, Kafka, Kubernetes
        Preferred Skills: Redis, AWS
        Domain: FinTech
        Responsibilities:
        - Design high-throughput microservices in Python and FastAPI.
        - Manage production PostgreSQL databases.
        - Implement event streaming with Kafka.
        """

        self.sample_resume_text = """
        Alice Candidate
        alice@example.com | (555) 012-3456
        Summary:
        Senior Backend Engineer with 5 years experience in Python, FastAPI, PostgreSQL, and Docker.
        Experience:
        Senior Software Engineer at PayStream FinTech (2019-2024)
        - Designed and deployed high-throughput microservices using Python and FastAPI in production.
        - Managed production PostgreSQL database clusters with high availability.
        - Built caching layer with Redis.
        - Containerized applications with Docker.
        Education:
        - B.S. in Computer Science
        """

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=engine)

    # --------------------------------------------------------------------------
    # 1. Authenticated Match Creation
    # --------------------------------------------------------------------------
    def test_01_authenticated_match_creation(self):
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text,
            "source_type": "paste"
        }
        response = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("scan_id", data)
        self.assertTrue(data["scan_id"].startswith("scan_"))
        self.assertEqual(data["matching_engine_version"], "match-v1.0.0")
        self.assertGreater(data["overall_match_score"], 0.0)
        self.assertIn(data["match_confidence"], ["HIGH", "MEDIUM", "LOW"])
        self.assertIn("sub_scores", data)
        self.assertIn("skill_matrix", data)
        self.assertIn("critical_gaps", data)
        self.assertIn("recommendations", data)
        self.assertEqual(data["source_type"], "paste")

    # --------------------------------------------------------------------------
    # 2. Unauthenticated Match Creation
    # --------------------------------------------------------------------------
    def test_02_unauthenticated_match_creation(self):
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text
        }
        # No Authorization header provided
        response = client.post("/api/candidate/resume-jd/match", json=payload)
        self.assertEqual(response.status_code, 401)

    # --------------------------------------------------------------------------
    # 3. Authenticated Retrieval
    # --------------------------------------------------------------------------
    def test_03_authenticated_retrieval(self):
        # First create match as Candidate A
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text
        }
        create_resp = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        self.assertEqual(create_resp.status_code, 200)
        scan_id = create_resp.json()["scan_id"]

        # Retrieve match as Candidate A
        get_resp = client.get(f"/api/candidate/resume-jd/match/{scan_id}", headers=self.auth_headers_a)
        self.assertEqual(get_resp.status_code, 200)
        retrieved_data = get_resp.json()

        self.assertEqual(retrieved_data["scan_id"], scan_id)
        self.assertEqual(retrieved_data["overall_match_score"], create_resp.json()["overall_match_score"])
        self.assertEqual(retrieved_data["matching_engine_version"], "match-v1.0.0")
        self.assertEqual(len(retrieved_data["skill_matrix"]), len(create_resp.json()["skill_matrix"]))

    # --------------------------------------------------------------------------
    # 4. Cross-User Retrieval Rejection (Tenant Isolation)
    # --------------------------------------------------------------------------
    def test_04_cross_user_retrieval_rejection(self):
        # Candidate A creates a scan
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text
        }
        create_resp = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        self.assertEqual(create_resp.status_code, 200)
        scan_id_a = create_resp.json()["scan_id"]

        # Candidate B attempts to retrieve Candidate A's scan
        cross_resp = client.get(f"/api/candidate/resume-jd/match/{scan_id_a}", headers=self.auth_headers_b)
        # MUST return 404 without leaking whether record exists
        self.assertEqual(cross_resp.status_code, 404)
        self.assertIn("not found or access denied", cross_resp.json()["detail"].lower())

    # --------------------------------------------------------------------------
    # 5. Nonexistent Scan ID
    # --------------------------------------------------------------------------
    def test_05_nonexistent_scan_id(self):
        response = client.get("/api/candidate/resume-jd/match/scan_fake_1234567890", headers=self.auth_headers_a)
        self.assertEqual(response.status_code, 404)

    # --------------------------------------------------------------------------
    # 6. Scan Ownership Cannot Be Spoofed
    # --------------------------------------------------------------------------
    def test_06_scan_ownership_cannot_be_spoofed(self):
        # Candidate A tries to spoof user_id as Candidate B's id in payload
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text,
            "user_id": self.candidate_b_id  # Injected user_id attempt
        }
        create_resp = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        self.assertEqual(create_resp.status_code, 200)
        scan_id = create_resp.json()["scan_id"]

        # Inspect database directly
        db = TestingSessionLocal()
        scan = db.query(ResumeScan).filter(ResumeScan.scan_id == scan_id).first()
        self.assertIsNotNone(scan)
        # Must be strictly Candidate A's ID
        self.assertEqual(scan.user_id, self.candidate_a_id)
        self.assertNotEqual(scan.user_id, self.candidate_b_id)
        db.close()

    # --------------------------------------------------------------------------
    # 7. Scan ID Uniqueness
    # --------------------------------------------------------------------------
    def test_07_scan_id_uniqueness(self):
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text
        }
        resp1 = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        resp2 = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

        id1 = resp1.json()["scan_id"]
        id2 = resp2.json()["scan_id"]
        self.assertNotEqual(id1, id2)

    # --------------------------------------------------------------------------
    # 8. Database Result Persistence Integrity
    # --------------------------------------------------------------------------
    def test_08_result_persistence_integrity(self):
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text,
            "source_type": "paste"
        }
        resp = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        scan_id = resp.json()["scan_id"]

        db = TestingSessionLocal()
        record = db.query(ResumeScan).filter(ResumeScan.scan_id == scan_id).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.matching_engine_version, "match-v1.0.0")
        self.assertEqual(record.user_id, self.candidate_a_id)
        self.assertIsNotNone(record.sub_scores)
        self.assertIsNotNone(record.skill_matrix)
        self.assertIsNotNone(record.critical_gaps)
        self.assertIsNotNone(record.normalized_jd)
        self.assertIsNotNone(record.normalized_resume)

        # Validate that JSON deserializes properly
        sub_scores = json.loads(record.sub_scores)
        self.assertIn("required_skills", sub_scores)
        self.assertIn("experience", sub_scores)

        matrix = json.loads(record.skill_matrix)
        self.assertTrue(any(item["skill"] == "Python" for item in matrix))
        self.assertTrue(any(item["skill"] == "Kafka" for item in matrix))
        db.close()

    # --------------------------------------------------------------------------
    # 9. Exact Result Retrieval Integrity
    # --------------------------------------------------------------------------
    def test_09_exact_result_retrieval_integrity(self):
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text
        }
        post_resp = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        post_data = post_resp.json()
        scan_id = post_data["scan_id"]

        get_resp = client.get(f"/api/candidate/resume-jd/match/{scan_id}", headers=self.auth_headers_a)
        get_data = get_resp.json()

        # Check all fields match exactly between POST and GET
        self.assertEqual(post_data["overall_match_score"], get_data["overall_match_score"])
        self.assertEqual(post_data["match_confidence"], get_data["match_confidence"])
        self.assertEqual(post_data["sub_scores"], get_data["sub_scores"])
        self.assertEqual(post_data["critical_gaps"], get_data["critical_gaps"])
        self.assertEqual(post_data["recommendations"], get_data["recommendations"])
        self.assertEqual(post_data["target_role"], get_data["target_role"])

    # --------------------------------------------------------------------------
    # 10. Matching Version Persistence
    # --------------------------------------------------------------------------
    def test_10_matching_version_persistence(self):
        payload = {
            "resume_text": self.sample_resume_text,
            "jd_text": self.sample_jd_text
        }
        resp = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        self.assertEqual(resp.json()["matching_engine_version"], "match-v1.0.0")

        scan_id = resp.json()["scan_id"]
        get_resp = client.get(f"/api/candidate/resume-jd/match/{scan_id}", headers=self.auth_headers_a)
        self.assertEqual(get_resp.json()["matching_engine_version"], "match-v1.0.0")

    # --------------------------------------------------------------------------
    # 11. Match Creation with Public JD URL (Mocked Fetch)
    # --------------------------------------------------------------------------
    @patch("app.main.safe_fetch_job_url")
    def test_11_match_with_public_jd_url(self, mock_safe_fetch):
        mock_safe_fetch.return_value = {
            "success": True,
            "extracted_text": "Job Title: Staff Python Architect\nRequired Skills: Python, Distributed Systems, Microservices",
            "content_type": "text/html",
            "resolved_ip": "93.184.216.34",
            "source_url": "https://example.com/careers/staff-python"
        }

        payload = {
            "resume_text": self.sample_resume_text,
            "jd_url": "https://example.com/careers/staff-python"
        }
        resp = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers_a)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("scan_id", data)
        self.assertEqual(data["source_type"], "public_url")
        self.assertEqual(data["source_url"], "https://example.com/careers/staff-python")

    # --------------------------------------------------------------------------
    # 12. Missing Inputs Validation
    # --------------------------------------------------------------------------
    def test_12_missing_inputs_validation(self):
        # Missing resume
        resp1 = client.post("/api/candidate/resume-jd/match", json={"jd_text": self.sample_jd_text}, headers=self.auth_headers_a)
        self.assertEqual(resp1.status_code, 400)
        self.assertIn("Resume content is required", resp1.json()["detail"])

        # Missing JD
        resp2 = client.post("/api/candidate/resume-jd/match", json={"resume_text": self.sample_resume_text}, headers=self.auth_headers_a)
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("Job description is required", resp2.json()["detail"])

    # --------------------------------------------------------------------------
    # 13. Candidate Scan History Endpoint & Isolation
    # --------------------------------------------------------------------------
    def test_13_candidate_history_endpoint(self):
        # Candidate A creates 2 scans
        payload1 = {"resume_text": self.sample_resume_text, "jd_text": self.sample_jd_text, "target_role": "Backend Engineer"}
        payload2 = {"resume_text": self.sample_resume_text, "jd_text": self.sample_jd_text, "target_role": "Platform Engineer"}
        client.post("/api/candidate/resume-jd/match", json=payload1, headers=self.auth_headers_a)
        client.post("/api/candidate/resume-jd/match", json=payload2, headers=self.auth_headers_a)

        # Candidate B creates 1 scan
        payload3 = {"resume_text": self.sample_resume_text, "jd_text": self.sample_jd_text, "target_role": "Frontend Engineer"}
        client.post("/api/candidate/resume-jd/match", json=payload3, headers=self.auth_headers_b)

        # Candidate A requests history
        resp_a = client.get("/api/candidate/resume-jd/history", headers=self.auth_headers_a)
        self.assertEqual(resp_a.status_code, 200)
        history_a = resp_a.json()
        self.assertEqual(len(history_a), 2)
        # Should not contain Candidate B's scan
        self.assertFalse(any(item["target_role"] == "Frontend Engineer" for item in history_a))

        # Candidate B requests history
        resp_b = client.get("/api/candidate/resume-jd/history", headers=self.auth_headers_b)
        self.assertEqual(resp_b.status_code, 200)
        history_b = resp_b.json()
        self.assertEqual(len(history_b), 1)
        self.assertEqual(history_b[0]["target_role"], "Frontend Engineer")


if __name__ == "__main__":
    unittest.main()
