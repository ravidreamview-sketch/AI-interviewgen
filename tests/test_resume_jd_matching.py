"""
Phase 5B Test Suite: Multi-Dimensional Resume ↔ JD Matching Engine
Tests all required scenarios:
1. Exact required skill match
2. Missing required skill
3. Partial skill match
4. Preferred skill evaluation
5. HIGH importance weighting (1.0)
6. MEDIUM importance weighting (0.6)
7. LOW importance weighting (0.3)
8. Critical gap detection
9. Anti-masking rule (critical gap visible even when overall_score >= 80)
10. Production evidence (Level 1: 100% credit)
11. Responsibility evidence (Level 2: 85-90% credit)
12. Project evidence (Level 3: 70% credit)
13. Skills-section-only evidence (Level 4: 40-50% credit)
14. Weak contextual evidence (Level 5: 20-30% credit)
15. No evidence (Level 6: 0% credit, resume_evidence=None)
16. Experience partial match (4 yrs vs 5 yrs -> ~80%)
17. Domain match
18. Responsibility match
19. Semantic related skill (FastAPI + AsyncIO)
20. Unrelated technology is not treated as equivalent (Docker!=K8s, Redis!=Kafka, SQL!=PostgreSQL, React!=Angular)
21. LOW confidence for sparse resume
22. HIGH confidence for rich evidence
23. Insufficient JD data handling
24. Insufficient resume data handling
25. No LLM provider (deterministic execution)
26. Deterministic fallback consistency
27. No fabricated evidence
28. Acceptance test example (Senior Backend Engineer with Python, FastAPI, Postgres, Kafka, K8s)
"""

import os
import sys
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.models import (
    NormalizedJobDescription,
    NormalizedResume,
    ResumeWorkExperience,
    ResumeProject,
    SkillMatrixItem,
    ResumeJDMatchResult,
)
from app.matching_service import (
    calculate_resume_jd_match,
    normalize_resume,
    classify_skill_evidence,
    evaluate_experience_match,
    evaluate_domain_match,
    evaluate_responsibilities_match,
)


class TestResumeJDMatchingEngine(unittest.TestCase):

    # --------------------------------------------------------------------------
    # 1. Exact Required Skill Match
    # --------------------------------------------------------------------------
    def test_01_exact_required_skill_match(self):
        jd = NormalizedJobDescription(
            job_title="Senior Python Engineer",
            required_skills=["Python", "FastAPI"]
        )
        resume = normalize_resume("""
        John Doe - Senior Backend Developer
        Experience:
        Senior Software Engineer at Acme Corp (2020-2024)
        - Built high-performance microservices using Python and FastAPI for production systems.
        - Deployed scalable REST APIs handling 10k RPS.
        """)
        result = calculate_resume_jd_match(jd, resume)
        self.assertGreaterEqual(result.sub_scores.required_skills, 85.0)
        python_item = next(item for item in result.skill_matrix if item.skill == "Python")
        self.assertEqual(python_item.gap_status, "matched")
        self.assertGreaterEqual(python_item.match_score, 85.0)
        self.assertIn("Python", python_item.resume_evidence)

    # --------------------------------------------------------------------------
    # 2. Missing Required Skill
    # --------------------------------------------------------------------------
    def test_02_missing_required_skill(self):
        jd = NormalizedJobDescription(
            job_title="Cloud Engineer",
            required_skills=["Kubernetes", "Golang"]
        )
        resume = normalize_resume("""
        Jane Smith
        Experience:
        Frontend Developer (2021-2024)
        - Developed web applications with React, HTML, CSS, and JavaScript.
        """)
        result = calculate_resume_jd_match(jd, resume)
        k8s_item = next(item for item in result.skill_matrix if item.skill == "Kubernetes")
        self.assertEqual(k8s_item.gap_status, "gap")
        self.assertEqual(k8s_item.match_score, 0.0)
        self.assertIsNone(k8s_item.resume_evidence)
        self.assertEqual(k8s_item.evidence_level, 6)

    # --------------------------------------------------------------------------
    # 3. Partial Skill Match
    # --------------------------------------------------------------------------
    def test_03_partial_skill_match(self):
        jd = NormalizedJobDescription(
            job_title="Data Engineer",
            required_skills=["Apache Spark"]
        )
        # Mentioned only in skills list without project or production bullets (Level 4)
        resume = normalize_resume("""
        Data Analyst
        Skills: Python, SQL, Apache Spark, Tableau
        Experience:
        - Created SQL dashboards and data visualizations in Tableau.
        """)
        result = calculate_resume_jd_match(jd, resume)
        spark_item = next(item for item in result.skill_matrix if item.skill == "Apache Spark")
        self.assertEqual(spark_item.evidence_level, 4)
        self.assertEqual(spark_item.gap_status, "partial")
        self.assertGreaterEqual(spark_item.match_score, 40.0)
        self.assertLessEqual(spark_item.match_score, 50.0)

    # --------------------------------------------------------------------------
    # 4. Preferred Skill Evaluation
    # --------------------------------------------------------------------------
    def test_04_preferred_skill(self):
        jd = NormalizedJobDescription(
            job_title="Backend Developer",
            required_skills=["Python"],
            preferred_skills=["GraphQL", "Redis"]
        )
        resume = normalize_resume("""
        Backend Developer
        Experience:
        - Developed Python services.
        - Used Redis for caching and session management in projects.
        """)
        result = calculate_resume_jd_match(jd, resume)
        self.assertIsNotNone(result.sub_scores.preferred_skills)
        redis_item = next(item for item in result.skill_matrix if item.skill == "Redis")
        self.assertEqual(redis_item.importance, "MEDIUM")

    # --------------------------------------------------------------------------
    # 5. HIGH Importance Weighting
    # --------------------------------------------------------------------------
    def test_05_high_importance_weighting(self):
        from app.matching_service import IMPORTANCE_WEIGHTS
        self.assertEqual(IMPORTANCE_WEIGHTS["HIGH"], 1.0)

    # --------------------------------------------------------------------------
    # 6. MEDIUM Importance Weighting
    # --------------------------------------------------------------------------
    def test_06_medium_importance_weighting(self):
        from app.matching_service import IMPORTANCE_WEIGHTS
        self.assertEqual(IMPORTANCE_WEIGHTS["MEDIUM"], 0.6)

    # --------------------------------------------------------------------------
    # 7. LOW Importance Weighting
    # --------------------------------------------------------------------------
    def test_07_low_importance_weighting(self):
        from app.matching_service import IMPORTANCE_WEIGHTS
        self.assertEqual(IMPORTANCE_WEIGHTS["LOW"], 0.3)

    # --------------------------------------------------------------------------
    # 8. Critical Gap Detection
    # --------------------------------------------------------------------------
    def test_08_critical_gap_detection(self):
        jd = NormalizedJobDescription(
            job_title="Event Streaming Engineer",
            required_skills=["Kafka"]
        )
        resume = normalize_resume("""
        Developer
        Skills: Python, Django, PostgreSQL
        Experience:
        - Built web applications using Django.
        """)
        result = calculate_resume_jd_match(jd, resume)
        self.assertTrue(any("Kafka" in cg for cg in result.critical_gaps))

    # --------------------------------------------------------------------------
    # 9. Anti-Masking Rule (Score >= 80 does NOT hide High-Importance Gap)
    # --------------------------------------------------------------------------
    def test_09_anti_masking_rule(self):
        jd = NormalizedJobDescription(
            job_title="Senior Distributed Systems Engineer",
            experience_required="5+ years",
            domain_requirements=["FinTech"],
            responsibilities=[
                "Architect high-throughput event processing engines.",
                "Design PostgreSQL relational database schemas."
            ],
            required_skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "Kafka"]
        )
        resume = normalize_resume("""
        Senior Software Engineer (6 years experience)
        Domain: FinTech Payment Systems
        Experience:
        Senior Engineer at PayFlow FinTech (2018-2024)
        - Architected high-throughput transaction engines in Python and FastAPI.
        - Deployed containerized microservices to production AWS ECS with Docker.
        - Managed mission-critical production PostgreSQL clusters with zero downtime.
        - Designed PostgreSQL relational database schemas and optimized indexing.
        """)
        result = calculate_resume_jd_match(jd, resume)
        # Strong match in 5/6 skills + experience + domain + responsibilities can push score high
        self.assertGreaterEqual(result.overall_match_score, 75.0)
        # CRITICAL: Kafka MUST appear under critical gaps despite high score
        self.assertTrue(any("Kafka" in cg for cg in result.critical_gaps))
        # Kafka matrix item is Level 6 with None evidence
        kafka_item = next(item for item in result.skill_matrix if item.skill == "Kafka")
        self.assertEqual(kafka_item.evidence_level, 6)
        self.assertIsNone(kafka_item.resume_evidence)

    # --------------------------------------------------------------------------
    # 10. Level 1: Direct Production Experience (100% Credit)
    # --------------------------------------------------------------------------
    def test_10_production_evidence(self):
        resume = normalize_resume("""
        Experience:
        - Architected and managed production Kubernetes clusters handling 50k RPS.
        """)
        lvl, strength, snippet, credit = classify_skill_evidence("Kubernetes", resume, resume.raw_text)
        self.assertEqual(lvl, 1)
        self.assertEqual(strength, "HIGH")
        self.assertEqual(credit, 1.00)
        self.assertIsNotNone(snippet)
        self.assertIn("production", snippet.lower())

    # --------------------------------------------------------------------------
    # 11. Level 2: Core Responsibility / Major Achievement (85-90% Credit)
    # --------------------------------------------------------------------------
    def test_11_responsibility_evidence(self):
        resume = normalize_resume("""
        Experience:
        - Designed and implemented microservices using FastAPI and PostgreSQL.
        """)
        lvl, strength, snippet, credit = classify_skill_evidence("FastAPI", resume, resume.raw_text)
        self.assertEqual(lvl, 2)
        self.assertEqual(strength, "HIGH")
        self.assertGreaterEqual(credit, 0.85)
        self.assertLessEqual(credit, 0.90)

    # --------------------------------------------------------------------------
    # 12. Level 3: Project / Implementation Experience (70% Credit)
    # --------------------------------------------------------------------------
    def test_12_project_evidence(self):
        resume = normalize_resume("""
        Projects:
        E-Commerce Microservices:
        - Implemented Redis pub/sub queue for background task processing.
        """)
        lvl, strength, snippet, credit = classify_skill_evidence("Redis", resume, resume.raw_text)
        self.assertEqual(lvl, 3)
        self.assertEqual(strength, "MEDIUM")
        self.assertEqual(credit, 0.70)

    # --------------------------------------------------------------------------
    # 13. Level 4: Skills Section Mention Only (40-50% Credit)
    # --------------------------------------------------------------------------
    def test_13_skills_section_only_evidence(self):
        resume = normalize_resume("""
        Summary:
        Backend developer.
        Technical Skills:
        Python, Django, Celery, RabbitMQ, Docker
        Experience:
        - Developed web endpoints in Python.
        """)
        lvl, strength, snippet, credit = classify_skill_evidence("RabbitMQ", resume, resume.raw_text)
        self.assertEqual(lvl, 4)
        self.assertEqual(strength, "LOW")
        self.assertGreaterEqual(credit, 0.40)
        self.assertLessEqual(credit, 0.50)

    # --------------------------------------------------------------------------
    # 14. Level 5: Weak Contextual / Adjacent Mention (20-30% Credit)
    # --------------------------------------------------------------------------
    def test_14_weak_contextual_evidence(self):
        resume = normalize_resume("""
        Experience:
        - Gained familiarity and basic knowledge of Terraform during cloud migration training.
        """)
        lvl, strength, snippet, credit = classify_skill_evidence("Terraform", resume, resume.raw_text)
        self.assertEqual(lvl, 5)
        self.assertEqual(strength, "LOW")
        self.assertGreaterEqual(credit, 0.20)
        self.assertLessEqual(credit, 0.30)

    # --------------------------------------------------------------------------
    # 15. Level 6: No Evidence (0% Credit, resume_evidence=None)
    # --------------------------------------------------------------------------
    def test_15_no_evidence(self):
        resume = normalize_resume("""
        Experience:
        - Built frontend UIs in React.
        """)
        lvl, strength, snippet, credit = classify_skill_evidence("Rust", resume, resume.raw_text)
        self.assertEqual(lvl, 6)
        self.assertEqual(strength, "NONE")
        self.assertEqual(credit, 0.00)
        self.assertIsNone(snippet)

    # --------------------------------------------------------------------------
    # 16. Experience Partial Match
    # --------------------------------------------------------------------------
    def test_16_experience_partial_match(self):
        jd = NormalizedJobDescription(experience_required="5 years")
        resume = normalize_resume("Software Engineer with 4 years of experience.")
        score, msg = evaluate_experience_match(jd, resume)
        # 4 / 5 = 80%
        self.assertAlmostEqual(score, 80.0, delta=2.0)
        self.assertIn("Partial experience match", msg)

    # --------------------------------------------------------------------------
    # 17. Domain Match
    # --------------------------------------------------------------------------
    def test_17_domain_match(self):
        jd = NormalizedJobDescription(domain_requirements=["FinTech", "B2B SaaS"])
        resume = normalize_resume("""
        Senior Engineer at FinTech Corp.
        Developed B2B SaaS billing platform for financial institutions.
        """)
        score, msg = evaluate_domain_match(jd, resume, resume.raw_text)
        self.assertGreaterEqual(score, 85.0)
        self.assertIn("Matched domains", msg)

    # --------------------------------------------------------------------------
    # 18. Responsibility Match
    # --------------------------------------------------------------------------
    def test_18_responsibility_match(self):
        jd = NormalizedJobDescription(responsibilities=[
            "Design and build scalable REST APIs.",
            "Optimize relational database performance and queries.",
            "Collaborate with DevOps team for automated CI/CD pipelines."
        ])
        resume = normalize_resume("""
        Experience:
        - Designed and built scalable REST APIs in Python.
        - Optimized database performance and complex SQL queries.
        - Collaborated with DevOps engineers to configure CI/CD pipelines.
        """)
        score, msg = evaluate_responsibilities_match(jd, resume, resume.raw_text)
        self.assertGreaterEqual(score, 85.0)

    # --------------------------------------------------------------------------
    # 19. Semantic Related Skill (FastAPI + AsyncIO)
    # --------------------------------------------------------------------------
    def test_19_semantic_related_skill(self):
        resume = normalize_resume("""
        Experience:
        - Developed asynchronous Python backend services using async and await event loops.
        """)
        lvl, strength, snippet, credit = classify_skill_evidence("AsyncIO", resume, resume.raw_text)
        self.assertIn(lvl, (2, 3, 5))
        self.assertGreater(credit, 0.0)

    # --------------------------------------------------------------------------
    # 20. Unrelated Technology Is NOT Treated as Equivalent
    # --------------------------------------------------------------------------
    def test_20_unrelated_technology_not_equivalent(self):
        # 1. Docker != Kubernetes
        resume_docker = normalize_resume("Experience: Built container images with Docker.")
        lvl_k8s, _, snippet_k8s, credit_k8s = classify_skill_evidence("Kubernetes", resume_docker, resume_docker.raw_text)
        self.assertEqual(lvl_k8s, 6)
        self.assertEqual(credit_k8s, 0.0)
        self.assertIsNone(snippet_k8s)

        # 2. Redis != Kafka
        resume_redis = normalize_resume("Experience: Used Redis for caching.")
        lvl_kafka, _, snippet_kafka, credit_kafka = classify_skill_evidence("Kafka", resume_redis, resume_redis.raw_text)
        self.assertEqual(lvl_kafka, 6)
        self.assertEqual(credit_kafka, 0.0)
        self.assertIsNone(snippet_kafka)

        # 3. SQL != PostgreSQL
        resume_sql = normalize_resume("Experience: Wrote basic SQL queries.")
        lvl_psql, _, _, credit_psql = classify_skill_evidence("PostgreSQL", resume_sql, resume_sql.raw_text)
        self.assertEqual(lvl_psql, 6)
        self.assertEqual(credit_psql, 0.0)

        # 4. React != Angular
        resume_react = normalize_resume("Experience: Built Single Page Apps with React.")
        lvl_ng, _, _, credit_ng = classify_skill_evidence("Angular", resume_react, resume_react.raw_text)
        self.assertEqual(lvl_ng, 6)
        self.assertEqual(credit_ng, 0.0)

    # --------------------------------------------------------------------------
    # 21. LOW Confidence for Sparse Resume
    # --------------------------------------------------------------------------
    def test_21_low_confidence_for_sparse_resume(self):
        jd = NormalizedJobDescription(
            job_title="Software Engineer",
            required_skills=["Python", "SQL"]
        )
        sparse_resume = normalize_resume("Python developer.")
        result = calculate_resume_jd_match(jd, sparse_resume)
        self.assertEqual(result.match_confidence, "LOW")

    # --------------------------------------------------------------------------
    # 22. HIGH Confidence for Rich Evidence
    # --------------------------------------------------------------------------
    def test_22_high_confidence_for_rich_evidence(self):
        jd = NormalizedJobDescription(
            job_title="Senior Python Developer",
            experience_required="4 years",
            required_skills=["Python", "FastAPI", "PostgreSQL"]
        )
        rich_resume = normalize_resume("""
        Alex Vance - Senior Software Engineer
        alex@example.com | (555) 019-2834
        Summary:
        Senior backend engineer with 5 years of experience building distributed systems in Python and FastAPI.
        Experience:
        Senior Backend Engineer at Tech Innovations (2020 - 2024)
        - Architected and deployed production microservices using Python and FastAPI.
        - Managed production PostgreSQL database clusters and optimized high-load query performance.
        - Deployed scalable containerized services with Docker to AWS ECS.
        - Led a team of 4 engineers and performed code reviews.
        Projects:
        - Real-time analytics dashboard with Python and PostgreSQL.
        Education:
        - B.S. in Computer Science
        """)
        result = calculate_resume_jd_match(jd, rich_resume)
        self.assertEqual(result.match_confidence, "HIGH")

    # --------------------------------------------------------------------------
    # 23. Insufficient JD Data Handling
    # --------------------------------------------------------------------------
    def test_23_insufficient_jd_data(self):
        sparse_jd = NormalizedJobDescription(job_title="General Role")
        resume = normalize_resume("Experienced developer in Python.")
        result = calculate_resume_jd_match(sparse_jd, resume)
        self.assertIsInstance(result, ResumeJDMatchResult)
        self.assertGreaterEqual(result.overall_match_score, 0.0)

    # --------------------------------------------------------------------------
    # 24. Insufficient Resume Data Handling
    # --------------------------------------------------------------------------
    def test_24_insufficient_resume_data(self):
        jd = NormalizedJobDescription(
            job_title="Staff Architect",
            required_skills=["Distributed Systems", "Go", "Kubernetes"]
        )
        empty_resume = normalize_resume("")
        result = calculate_resume_jd_match(jd, empty_resume)
        self.assertIsInstance(result, ResumeJDMatchResult)
        self.assertEqual(result.match_confidence, "LOW")
        self.assertGreaterEqual(len(result.critical_gaps), 1)

    # --------------------------------------------------------------------------
    # 25. No LLM Provider (Deterministic Execution)
    # --------------------------------------------------------------------------
    def test_25_no_llm_provider(self):
        # Engine must run with zero environment variables / API keys
        jd = NormalizedJobDescription(
            job_title="Backend Engineer",
            required_skills=["Python", "FastAPI"]
        )
        resume = normalize_resume("Python and FastAPI developer.")
        result = calculate_resume_jd_match(jd, resume)
        self.assertIsNotNone(result.overall_match_score)
        self.assertIsInstance(result.skill_matrix, list)

    # --------------------------------------------------------------------------
    # 26. Deterministic Fallback Consistency
    # --------------------------------------------------------------------------
    def test_26_deterministic_fallback(self):
        jd = NormalizedJobDescription(
            job_title="Lead Architect",
            required_skills=["Java", "Spring Boot", "AWS"]
        )
        resume = normalize_resume("Java and Spring Boot developer with 5 years experience on AWS.")
        result1 = calculate_resume_jd_match(jd, resume)
        result2 = calculate_resume_jd_match(jd, resume)
        self.assertEqual(result1.overall_match_score, result2.overall_match_score)
        self.assertEqual(len(result1.skill_matrix), len(result2.skill_matrix))

    # --------------------------------------------------------------------------
    # 27. No Fabricated Evidence
    # --------------------------------------------------------------------------
    def test_27_no_fabricated_evidence(self):
        jd = NormalizedJobDescription(
            job_title="C++ Systems Engineer",
            required_skills=["C++", "CUDA", "Unreal Engine"]
        )
        resume = normalize_resume("Java developer.")
        result = calculate_resume_jd_match(jd, resume)
        for item in result.skill_matrix:
            self.assertEqual(item.evidence_level, 6)
            self.assertEqual(item.evidence_strength, "NONE")
            self.assertIsNone(item.resume_evidence)

    # --------------------------------------------------------------------------
    # 28. Acceptance Test Example from Specification
    # --------------------------------------------------------------------------
    def test_28_acceptance_test_example(self):
        """
        JD: Senior Backend Engineer
        Required: Python, FastAPI, PostgreSQL, Kafka, Kubernetes
        Resume: 4 years Python, FastAPI, PostgreSQL, Redis, Docker

        Expected:
        - Python -> strong match
        - FastAPI -> strong match
        - PostgreSQL -> strong match
        - Kafka -> critical gap
        - Kubernetes -> critical gap
        - Redis must NOT equal Kafka
        - Docker must NOT equal Kubernetes
        - No fabricated production experience for Kafka or Kubernetes
        """
        jd = NormalizedJobDescription(
            job_title="Senior Backend Engineer",
            experience_required="5 years",
            required_skills=["Python", "FastAPI", "PostgreSQL", "Kafka", "Kubernetes"]
        )
        resume = normalize_resume("""
        Backend Engineer (4 years experience)
        Experience:
        Backend Software Engineer (2020 - 2024)
        - Developed scalable microservices using Python and FastAPI in production.
        - Designed and optimized PostgreSQL database queries and schemas.
        - Implemented Redis for distributed caching.
        - Containerized backend services with Docker.
        """)
        result = calculate_resume_jd_match(jd, resume)

        # 1. Python -> strong match
        python_item = next(item for item in result.skill_matrix if item.skill == "Python")
        self.assertEqual(python_item.gap_status, "matched")
        self.assertGreaterEqual(python_item.match_score, 85.0)

        # 2. FastAPI -> strong match
        fastapi_item = next(item for item in result.skill_matrix if item.skill == "FastAPI")
        self.assertEqual(fastapi_item.gap_status, "matched")
        self.assertGreaterEqual(fastapi_item.match_score, 85.0)

        # 3. PostgreSQL -> strong match
        postgres_item = next(item for item in result.skill_matrix if item.skill == "PostgreSQL")
        self.assertEqual(postgres_item.gap_status, "matched")
        self.assertGreaterEqual(postgres_item.match_score, 85.0)

        # 4. Kafka -> critical gap (Redis != Kafka)
        kafka_item = next(item for item in result.skill_matrix if item.skill == "Kafka")
        self.assertEqual(kafka_item.evidence_level, 6)
        self.assertEqual(kafka_item.gap_status, "gap")
        self.assertEqual(kafka_item.match_score, 0.0)
        self.assertIsNone(kafka_item.resume_evidence)
        self.assertTrue(any("Kafka" in cg for cg in result.critical_gaps))

        # 5. Kubernetes -> critical gap (Docker != Kubernetes)
        k8s_item = next(item for item in result.skill_matrix if item.skill == "Kubernetes")
        self.assertEqual(k8s_item.evidence_level, 6)
        self.assertEqual(k8s_item.gap_status, "gap")
        self.assertEqual(k8s_item.match_score, 0.0)
        self.assertIsNone(k8s_item.resume_evidence)
        self.assertTrue(any("Kubernetes" in cg for cg in result.critical_gaps))

        # 6. Check recommendations contain actionable gap guidance
        self.assertTrue(any("Kafka" in r for r in result.recommendations))
        self.assertTrue(any("Kubernetes" in r for r in result.recommendations))


if __name__ == "__main__":
    unittest.main()
