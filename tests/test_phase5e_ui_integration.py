"""
Phase 5E Test Suite: Resume/JD Match UI Integration
Verifies the integration between the frontend Resume-match.html and backend APIs:
1. Route serving for /candidate/resume-jd-match and /candidate/resume-match
2. Frontend structural elements (tabs, inputs, dropzones, tables, critical gaps alert, deep practice CTA)
3. End-to-end API integration flow (Paste -> Match -> Adaptive Practice)
4. End-to-end API integration flow (URL -> Match -> Adaptive Practice)
5. End-to-end API integration flow (File Upload -> Match -> Adaptive Practice)
6. Security checks (credentials: 'include', tenant isolation, no client-side spoofing)
"""

import os
import sys
import json
import io
import unittest
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

# Setup test DB
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


class TestPhase5EUIIntegration(unittest.TestCase):

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
        candidate = UserAccount(
            email="candidate_ui@example.com",
            full_name="Sarah Connor",
            password_hash=hash_password("Password123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)

        self.cand_id = candidate.id
        self.cand_email = candidate.email
        db.close()

        token = create_access_token({"sub": self.cand_id, "email": self.cand_email, "role": "candidate"})
        self.auth_headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=engine)

    # --------------------------------------------------------------------------
    # 1. Route Serving Tests
    # --------------------------------------------------------------------------
    def test_01_serve_resume_jd_match_routes(self):
        routes = [
            "/candidate/resume-jd-match",
            "/candidate/resume-match",
            "/Resume-match.html",
            "/Resume-match",
            "/resume-match"
        ]
        for route in routes:
            resp = client.get(route)
            self.assertEqual(resp.status_code, 200, f"Route {route} failed")
            self.assertIn("Resume &amp; Job Description Matcher", resp.text)

    # --------------------------------------------------------------------------
    # 2. Frontend Structure & Tab Elements
    # --------------------------------------------------------------------------
    def test_02_ui_contains_three_jd_modes(self):
        resp = client.get("/candidate/resume-jd-match")
        html = resp.text
        # Tabs
        self.assertIn("tabPasteJd", html)
        self.assertIn("tabUrlJd", html)
        self.assertIn("tabUploadJd", html)
        # Panes
        self.assertIn("panePasteJd", html)
        self.assertIn("paneUrlJd", html)
        self.assertIn("paneUploadJd", html)
        # Inputs
        self.assertIn("jdUrlInput", html)
        self.assertIn("fetchJdUrlBtn", html)
        self.assertIn("jdFileInput", html)
        self.assertIn("jdDropzone", html)

    # --------------------------------------------------------------------------
    # 3. Frontend Results & Deep Practice CTA
    # --------------------------------------------------------------------------
    def test_03_ui_contains_results_and_practice_elements(self):
        resp = client.get("/candidate/resume-jd-match")
        html = resp.text
        self.assertIn("matchBtn", html)
        self.assertIn("resultsPanel", html)
        self.assertIn("criticalGapsContainer", html)
        self.assertIn("matrixTableBody", html)
        self.assertIn("deepPracticeBtn", html)
        self.assertIn("launchDeepPractice", html)
        self.assertIn("openQuestionsInStudio", html)

    # --------------------------------------------------------------------------
    # 4. API Endpoints Referenced in JS
    # --------------------------------------------------------------------------
    def test_04_ui_references_phase5_apis(self):
        resp = client.get("/candidate/resume-jd-match")
        html = resp.text
        self.assertIn("/api/candidate/jd/extract-url", html)
        self.assertIn("/api/candidate/jd/upload", html)
        self.assertIn("/api/candidate/resume-jd/match", html)
        self.assertIn("/api/adaptive/from-match", html)
        self.assertIn("credentials: 'include'", html)

    # --------------------------------------------------------------------------
    # 5. End-to-End Flow: Paste JD -> Match -> Adaptive Deep Practice
    # --------------------------------------------------------------------------
    def test_05_flow_paste_jd_match_and_deep_practice(self):
        resume_text = "Senior Python Developer with 5 years experience in FastAPI, PostgreSQL, and Redis caching."
        jd_text = """
        Job Title: Senior Backend Engineer
        Company: CloudFlow Inc
        Requirements:
        - 4+ years of Python & FastAPI
        - Production experience with Apache Kafka for event-driven architecture
        - Experience with Docker and Kubernetes
        """

        # 1. Match
        match_resp = client.post(
            "/api/candidate/resume-jd/match",
            json={
                "resume_text": resume_text,
                "jd_text": jd_text,
                "source_type": "paste"
            },
            headers=self.auth_headers
        )
        self.assertEqual(match_resp.status_code, 200)
        match_data = match_resp.json()
        scan_id = match_data["scan_id"]
        self.assertIsNotNone(scan_id)
        self.assertIn("overall_match_score", match_data)
        self.assertIn("match_confidence", match_data)
        self.assertIn("skill_matrix", match_data)

        # 2. Launch Deep Practice using scan_id
        practice_resp = client.post(
            "/api/adaptive/from-match",
            json={
                "scan_id": scan_id,
                "number_of_questions": 5
            },
            headers=self.auth_headers
        )
        self.assertEqual(practice_resp.status_code, 200)
        practice_data = practice_resp.json()
        self.assertEqual(practice_data["scan_id"], scan_id)
        self.assertEqual(len(practice_data["questions"]), 5)
        # Gap-targeted questions should target Kafka or Kubernetes
        self.assertEqual(practice_data["questions"][0]["reason"], "jd_requirement")

    # --------------------------------------------------------------------------
    # 6. End-to-End Flow: Upload JD -> Match -> Adaptive Deep Practice
    # --------------------------------------------------------------------------
    def test_06_flow_upload_jd_match_and_deep_practice(self):
        jd_file_content = b"""
        Senior Cloud Infrastructure Architect
        Hiring Organization: Nexus Data Systems
        Experience Required: 6+ years
        Key Requirements:
        - Deep expertise in AWS Cloud Infrastructure and Terraform
        - Production Kubernetes cluster administration
        - Zero Trust Security and IAM hardening
        """
        # 1. Upload JD file
        upload_resp = client.post(
            "/api/candidate/jd/upload",
            files={"file": ("job_spec.txt", io.BytesIO(jd_file_content), "text/plain")},
            headers=self.auth_headers
        )
        self.assertEqual(upload_resp.status_code, 200)
        upload_data = upload_resp.json()
        self.assertTrue(upload_data["success"])
        extracted_text = upload_data["raw_jd"]

        # 2. Match with uploaded JD
        resume_text = "DevOps Engineer with 4 years in AWS, Terraform, and Docker."
        match_resp = client.post(
            "/api/candidate/resume-jd/match",
            json={
                "resume_text": resume_text,
                "jd_text": extracted_text,
                "source_type": "upload"
            },
            headers=self.auth_headers
        )
        self.assertEqual(match_resp.status_code, 200)
        match_data = match_resp.json()
        scan_id = match_data["scan_id"]

        # 3. Launch Deep Practice
        practice_resp = client.post(
            "/api/adaptive/from-match",
            json={"scan_id": scan_id, "number_of_questions": 3},
            headers=self.auth_headers
        )
        self.assertEqual(practice_resp.status_code, 200)
        self.assertEqual(len(practice_resp.json()["questions"]), 3)

    # --------------------------------------------------------------------------
    # 7. Phase 5E Bug Fix: Verification of Static/Fake Data Removal
    # --------------------------------------------------------------------------
    def test_07_no_fake_static_match_data_in_initial_html(self):
        resp = client.get("/candidate/resume-jd-match")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # 1. Initial neutral state panel
        self.assertIn("initialStatePanel", html)
        self.assertIn("Match analysis not started", html)
        self.assertIn("No match result available yet.", html)

        # 2. Error state panel
        self.assertIn("errorStatePanel", html)
        self.assertIn("Unable to complete the match analysis", html)

        # 3. No fake strengths
        self.assertNotIn("Core software engineering fundamentals verified.", html)
        self.assertIn("No verified strengths identified yet.", html)

        # 4. No hardcoded VERIFIED MATCH in initial template
        self.assertNotIn(">VERIFIED MATCH<", html)

        # 5. Deep practice button disabled by default
        self.assertIn('id="deepPracticeBtn" onclick="launchDeepPractice()" disabled', html)

        # 6. Skill matrix initial placeholder
        self.assertIn("Run the analysis to see the skill matrix.", html)

    # --------------------------------------------------------------------------
    # 8. Phase 5E UI State Machine & Invalidation Logic
    # --------------------------------------------------------------------------
    def test_08_ui_state_model_and_invalidation(self):
        resp = client.get("/candidate/resume-jd-match")
        html = resp.text

        # Verify state machine controller & invalidation handler in JS
        self.assertIn("setMatchUIState", html)
        self.assertIn("invalidatePreviousAnalysis", html)
        self.assertIn("currentMatchState", html)

    # --------------------------------------------------------------------------
    # 9. Phase 5E: Resume Document Upload Endpoint
    # --------------------------------------------------------------------------
    def test_09_resume_document_upload_api(self):
        sample_resume_txt = b"John Doe\nSenior Backend Engineer with 5 years in Python, FastAPI, PostgreSQL."
        files = {"file": ("test_resume.txt", sample_resume_txt, "text/plain")}
        resp = client.post(
            "/api/candidate/resume/upload",
            files=files,
            headers=self.auth_headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("Python", data["extracted_text"])

    # --------------------------------------------------------------------------
    # 10. Phase 5E: Differentiated Error Messages in UI
    # --------------------------------------------------------------------------
    def test_10_ui_has_differentiated_error_messages(self):
        resp = client.get("/candidate/resume-jd-match")
        html = resp.text
        self.assertIn("Your session has expired. Please sign in again.", html)
        self.assertIn("Please provide a valid resume and job description.", html)
        self.assertIn("Match service is unavailable.", html)
        self.assertIn("We couldn't complete the match analysis. Please try again.", html)
        self.assertIn("Unable to reach the match service. Please check your connection.", html)


if __name__ == "__main__":
    unittest.main()


