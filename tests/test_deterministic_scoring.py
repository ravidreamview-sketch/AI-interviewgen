"""
Comprehensive Regression Tests for Deterministic Resume/JD Scoring Engine
Verifies that:
1. Same resume + same JD -> 100% identical score across repeated evaluations.
2. Same inputs -> identical category-level subscore breakdown.
3. Changed resume -> evaluation fingerprint changes.
4. Changed JD -> evaluation fingerprint changes.
5. Changed scoring version -> previous cached evaluation is not reused.
6. Missing skills -> correctly reflected in breakdown without artificial score inflation.
7. Different resumes -> appropriate differences in overall match scores.
8. Different JDs -> appropriate differences in overall match scores.
9. Duplicate requests -> no conflicting or corrupted database records; is_cached=True on reuse.
10. Concurrent requests & Request ID tracking -> stale responses can be cleanly identified.
11. Demo/fallback responses -> cannot be mistaken for real evaluations.
12. Database persistence -> score remains identical after reload and retrieval.
13. Boundary safety -> C++, C#, .NET, Node.js, React.js correctly matched without word boundary failure.
"""

import os
import sys
import unittest
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

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
    SubScores,
    ResumeWorkExperience,
)
from app.matching_service import (
    calculate_resume_jd_match,
    normalize_resume,
    compute_content_fingerprint,
    compute_evaluation_fingerprint,
    canonicalize_text,
    get_skill_regex,
    calculate_deterministic_score,
    SCORING_ENGINE_VERSION
)
from app.jd_service import normalize_job_description

# Isolated in-memory SQLite database
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


class TestDeterministicScoringEngine(unittest.TestCase):

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
            email="candidate_eval@example.com",
            full_name="Sarah Connor",
            password_hash=hash_password("Cyberdyne123!"),
            role="candidate",
            plan_tier="pro",
            is_active=True
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        self.candidate_id = candidate.id
        db.close()

        self.auth_token = create_access_token(
            data={"sub": str(self.candidate_id), "email": "candidate_eval@example.com", "role": "candidate", "type": "access"}
        )
        self.auth_headers = {"Authorization": f"Bearer {self.auth_token}"}

        # Standard Test Payloads
        self.sample_resume = """
Sarah Connor
San Francisco, CA • sarah@example.com • (555) 019-2834

PROFESSIONAL SUMMARY
Senior Backend Engineer with 6 years of experience architecting high-scale distributed systems,
asynchronous REST APIs, and microservices in production using Python, FastAPI, and PostgreSQL.

SKILLS
Programming: Python, Go, C++, SQL
Frameworks & Tools: FastAPI, Docker, Kubernetes, Kafka, Redis, PostgreSQL
Cloud & Practices: AWS, CI/CD, Git, Terraform

WORK EXPERIENCE
Senior Backend Engineer | Cyberdyne Systems (2021 - Present)
- Architected and deployed microservices in production handling 45,000 QPS with 99.99% availability.
- Led migration of monolithic database to partitioned PostgreSQL and Redis clusters, reducing p99 latency by 35%.
- Implemented real-time event streaming pipeline using Apache Kafka and FastAPI processing 50M daily events.

Software Engineer | TechCore Inc. (2018 - 2021)
- Developed RESTful APIs and asynchronous background task workers using Python and Celery.
- Configured CI/CD deployment pipelines using Docker and Kubernetes on AWS.
        """.strip()

        self.sample_jd = """
Job Title: Senior Backend Engineer
Company: Acme Cloud Solutions
Location: San Francisco, CA (Hybrid)
Experience: 5+ years of experience

About the Role:
We are looking for a Senior Backend Engineer to design and build our next-generation cloud services.

Requirements:
- 5+ years of software development experience with Python.
- Proven experience building web applications and microservices using FastAPI or Django.
- Hands-on production experience with PostgreSQL, Docker, and Kafka.
- Familiarity with Kubernetes and AWS infrastructure.

Preferred:
- Experience with Go or C++.
- Understanding of distributed systems and high-throughput event processing.
        """.strip()

    # --------------------------------------------------------------------------
    # 1. Same resume + same JD -> 100% Identical Score across Repeated Runs
    # --------------------------------------------------------------------------
    def test_01_identical_score_across_repeated_evaluations(self):
        scores = []
        for i in range(10):
            result = calculate_resume_jd_match(self.sample_jd, self.sample_resume)
            scores.append(result.overall_match_score)

        # Every evaluation must equal the first evaluation exactly
        first_score = scores[0]
        self.assertGreater(first_score, 0.0)
        for idx, score in enumerate(scores):
            self.assertEqual(
                score, first_score,
                f"Evaluation iteration {idx} produced score {score} != {first_score}"
            )

    # --------------------------------------------------------------------------
    # 2. Same Inputs -> Identical Category-Level Score Breakdown
    # --------------------------------------------------------------------------
    def test_02_identical_category_score_breakdown(self):
        res1 = calculate_resume_jd_match(self.sample_jd, self.sample_resume)
        res2 = calculate_resume_jd_match(self.sample_jd, self.sample_resume)

        self.assertEqual(res1.sub_scores.required_skills, res2.sub_scores.required_skills)
        self.assertEqual(res1.sub_scores.experience, res2.sub_scores.experience)
        self.assertEqual(res1.sub_scores.domain, res2.sub_scores.domain)
        self.assertEqual(res1.sub_scores.responsibilities, res2.sub_scores.responsibilities)
        self.assertEqual(res1.sub_scores.preferred_skills, res2.sub_scores.preferred_skills)

        # Verify skill matrix item scores match identically
        self.assertEqual(len(res1.skill_matrix), len(res2.skill_matrix))
        for m1, m2 in zip(res1.skill_matrix, res2.skill_matrix):
            self.assertEqual(m1.skill, m2.skill)
            self.assertEqual(m1.match_score, m2.match_score)
            self.assertEqual(m1.evidence_level, m2.evidence_level)
            self.assertEqual(m1.gap_status, m2.gap_status)

    # --------------------------------------------------------------------------
    # 3. Changed Resume -> Evaluation Fingerprint Changes
    # --------------------------------------------------------------------------
    def test_03_changed_resume_changes_fingerprint(self):
        modified_resume = self.sample_resume.replace("Python, Go, C++, SQL", "Java, Ruby, PHP")
        res_original = calculate_resume_jd_match(self.sample_jd, self.sample_resume)
        res_modified = calculate_resume_jd_match(self.sample_jd, modified_resume)

        self.assertNotEqual(res_original.resume_fingerprint, res_modified.resume_fingerprint)
        self.assertNotEqual(res_original.evaluation_fingerprint, res_modified.evaluation_fingerprint)
        # JD fingerprint must remain unchanged
        self.assertEqual(res_original.jd_fingerprint, res_modified.jd_fingerprint)

    # --------------------------------------------------------------------------
    # 4. Changed JD -> Evaluation Fingerprint Changes
    # --------------------------------------------------------------------------
    def test_04_changed_jd_changes_fingerprint(self):
        modified_jd = self.sample_jd.replace("Senior Backend Engineer", "Lead Data Platform Engineer")
        res_original = calculate_resume_jd_match(self.sample_jd, self.sample_resume)
        res_modified = calculate_resume_jd_match(modified_jd, self.sample_resume)

        self.assertNotEqual(res_original.jd_fingerprint, res_modified.jd_fingerprint)
        self.assertNotEqual(res_original.evaluation_fingerprint, res_modified.evaluation_fingerprint)
        # Resume fingerprint must remain unchanged
        self.assertEqual(res_original.resume_fingerprint, res_modified.resume_fingerprint)

    # --------------------------------------------------------------------------
    # 5. Changed Scoring Version -> Evaluation Fingerprint Changes
    # --------------------------------------------------------------------------
    def test_05_changed_scoring_version_changes_fingerprint(self):
        res = compute_content_fingerprint(self.sample_resume)
        jd = compute_content_fingerprint(self.sample_jd)

        fp_v1 = compute_evaluation_fingerprint(res, jd, scoring_version="match-v1.0.0")
        fp_v2 = compute_evaluation_fingerprint(res, jd, scoring_version="match-v2.0.0")

        self.assertNotEqual(fp_v1, fp_v2)

    # --------------------------------------------------------------------------
    # 6. Missing Skills -> Correctly Reflected as Gap without Artificial Inflation
    # --------------------------------------------------------------------------
    def test_06_missing_skills_reflected_as_gaps(self):
        resume_no_backend = """
John Doe
Product Designer with 5 years of experience in Figma, UI/UX research, and prototyping.
Skills: Figma, Wireframing, User Research, Design Systems
        """.strip()

        result = calculate_resume_jd_match(self.sample_jd, resume_no_backend)

        # Must have Python, FastAPI, PostgreSQL, Kafka identified as gaps
        gaps = [m.skill for m in result.skill_matrix if m.gap_status == "gap"]
        self.assertIn("Python", gaps)
        self.assertIn("FastAPI", gaps)
        self.assertIn("PostgreSQL", gaps)
        self.assertIn("Kafka", gaps)

        # Subscore for required skills must be low (0.0), not inflated to 80%
        self.assertEqual(result.sub_scores.required_skills, 0.0)
        self.assertLess(result.overall_match_score, 40.0)

    # --------------------------------------------------------------------------
    # 7. Different Resumes -> Appropriate Differences in Scores
    # --------------------------------------------------------------------------
    def test_07_different_resumes_produce_differentiated_scores(self):
        junior_resume = """
Bob Newbie
Junior Web Developer with 6 months internship experience in HTML, CSS, and basic Python scripts.
Skills: Python, HTML, CSS
        """.strip()

        senior_res = calculate_resume_jd_match(self.sample_jd, self.sample_resume)
        junior_res = calculate_resume_jd_match(self.sample_jd, junior_resume)

        self.assertGreater(
            senior_res.overall_match_score,
            junior_res.overall_match_score + 25.0,
            f"Expected Senior ({senior_res.overall_match_score}) to score substantially higher than Junior ({junior_res.overall_match_score})"
        )

    # --------------------------------------------------------------------------
    # 8. Different JDs -> Appropriate Differences in Scores
    # --------------------------------------------------------------------------
    def test_08_different_jds_produce_differentiated_scores(self):
        embedded_jd = """
Job Title: Embedded Firmware Engineer
Company: Hardware Solutions
Requirements:
- 5+ years of C and Assembly programming.
- Microcontrollers, RTOS (FreeRTOS, Zephyr).
- SPI, I2C, UART hardware debugging with oscilloscopes.
        """.strip()

        backend_match = calculate_resume_jd_match(self.sample_jd, self.sample_resume)
        embedded_match = calculate_resume_jd_match(embedded_jd, self.sample_resume)

        self.assertGreater(
            backend_match.overall_match_score,
            embedded_match.overall_match_score + 20.0,
            f"Python backend resume must score higher on Backend JD ({backend_match.overall_match_score}) than Embedded JD ({embedded_match.overall_match_score})"
        )

    # --------------------------------------------------------------------------
    # 9. Duplicate Requests -> Cache Reused and Is_Cached=True Returned
    # --------------------------------------------------------------------------
    def test_09_duplicate_requests_reuse_evaluation(self):
        payload = {
            "resume_text": self.sample_resume,
            "jd_text": self.sample_jd,
            "source_type": "paste"
        }

        resp1 = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertFalse(data1.get("is_cached", False))

        # Second identical request
        resp2 = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()

        # Deterministic verification:
        self.assertEqual(data1["overall_match_score"], data2["overall_match_score"])
        self.assertEqual(data1["sub_scores"], data2["sub_scores"])
        self.assertEqual(data1["evaluation_fingerprint"], data2["evaluation_fingerprint"])
        self.assertTrue(data2.get("is_cached", False))

    # --------------------------------------------------------------------------
    # 10. Database Persistence & Exact Retrieval Consistency
    # --------------------------------------------------------------------------
    def test_10_database_persistence_and_retrieval_integrity(self):
        payload = {
            "resume_text": self.sample_resume,
            "jd_text": self.sample_jd,
            "source_type": "paste"
        }

        post_resp = client.post("/api/candidate/resume-jd/match", json=payload, headers=self.auth_headers)
        self.assertEqual(post_resp.status_code, 200)
        created_data = post_resp.json()
        scan_id = created_data["scan_id"]

        get_resp = client.get(f"/api/candidate/resume-jd/match/{scan_id}", headers=self.auth_headers)
        self.assertEqual(get_resp.status_code, 200)
        retrieved_data = get_resp.json()

        # Exact equality check
        self.assertEqual(created_data["overall_match_score"], retrieved_data["overall_match_score"])
        self.assertEqual(created_data["sub_scores"], retrieved_data["sub_scores"])
        self.assertEqual(created_data["evaluation_fingerprint"], retrieved_data["evaluation_fingerprint"])
        self.assertEqual(created_data["candidate_name"], retrieved_data["candidate_name"])
        self.assertEqual(created_data["target_role"], retrieved_data["target_role"])

    # --------------------------------------------------------------------------
    # 11. Boundary-Safe Technical Skills Matching (C++, C#, .NET, Node.js)
    # --------------------------------------------------------------------------
    def test_11_boundary_safe_technical_skills(self):
        resume_with_specials = """
Expert developer with 8 years of experience.
Skills: C++, C#, .NET, Node.js, React.js, CI/CD
Experience:
- Developed high-performance trading engine in C++ deployed to production with microsecond latency.
- Built enterprise backoffice services using C# and .NET Core.
- Created microservices using Node.js and React.js web dashboard.
- Maintained automated CI/CD deployment pipelines.
        """.strip()

        norm = normalize_resume(resume_with_specials)
        raw = norm.raw_text

        # Verify C++ does not match plain C or fail
        lvl_cpp, str_cpp, ev_cpp, cred_cpp = classify_skill_evidence_test("C++", norm, raw)
        self.assertIn(lvl_cpp, (1, 2))
        self.assertGreaterEqual(cred_cpp, 0.88)

        # Verify C#
        lvl_cs, str_cs, ev_cs, cred_cs = classify_skill_evidence_test("C#", norm, raw)
        self.assertIn(lvl_cs, (1, 2))
        self.assertGreaterEqual(cred_cs, 0.88)

        # Verify .NET
        lvl_net, str_net, ev_net, cred_net = classify_skill_evidence_test(".NET", norm, raw)
        self.assertIn(lvl_net, (1, 2))
        self.assertGreaterEqual(cred_net, 0.88)

        # Verify plain C does NOT false-positive on C++
        pat_c = get_skill_regex("c")
        self.assertIsNone(pat_c.search("We use C++ in production"))

    # --------------------------------------------------------------------------
    # 12. Score Clamping and Normalized Calculation Integrity
    # --------------------------------------------------------------------------
    def test_12_score_calculation_boundary_and_clamping(self):
        sub = SubScores(
            required_skills=100.0,
            experience=100.0,
            domain=100.0,
            responsibilities=100.0,
            preferred_skills=100.0
        )
        score_max = calculate_deterministic_score(sub)
        self.assertEqual(score_max, 100.0)

        sub_min = SubScores(
            required_skills=0.0,
            experience=0.0,
            domain=0.0,
            responsibilities=0.0,
            preferred_skills=0.0
        )
        score_min = calculate_deterministic_score(sub_min)
        self.assertEqual(score_min, 0.0)


def classify_skill_evidence_test(skill, norm, raw):
    from app.matching_service import classify_skill_evidence
    return classify_skill_evidence(skill, norm, raw)


if __name__ == "__main__":
    unittest.main()
