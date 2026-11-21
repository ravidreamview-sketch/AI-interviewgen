"""
Phase 1 Learner Intelligence Profile & Competency Framework Test Suite
=====================================================================
Validates:
1. Standardized 5-tier proficiency taxonomy mappings and edge-case boundary clamping.
2. Multi-role competency framework catalog integrity.
3. Strict evidence classification (VERIFIED vs ASSESSED vs SELF_REPORTED vs NOT_EVIDENCED).
4. Deterministic skill gap calculation engine and priority hierarchy.
5. Zero-hallucination resume synchronization logic.
6. LearnerProfile database model structure, constraints, and relationships.
7. API route handlers for profile CRUD, self-reporting, gaps, and resume sync.
"""

import json
import unittest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.db_models import (
    UserAccount,
    LearnerProfile,
    CandidateSkillAnalytics,
    MockInterview,
    ResumeScan,
)
from app.services.learner_intelligence_service import (
    PROFICIENCY_LEVELS,
    ROLE_COMPETENCY_FRAMEWORKS,
    score_to_proficiency,
    level_to_baseline_score,
    get_role_competency_framework,
    classify_skill_evidence,
    calculate_learner_skill_gaps,
    sync_profile_from_resume_scan,
)
from app.api.v1.learners import (
    get_or_create_learner_profile,
    format_profile_out,
    get_profile,
    update_profile,
    self_report_skill,
    delete_self_reported_skill,
    get_competency_matrix,
    get_skill_gaps,
    sync_resume,
    UpdateProfileRequest,
    SelfReportedSkillIn,
)


class TestProficiencyTaxonomy(unittest.TestCase):
    """Test 5-tier proficiency taxonomy rules and boundary clamping."""

    def test_level_1_beginner_mapping(self):
        level, title = score_to_proficiency(0.0)
        self.assertEqual(level, 1)
        self.assertEqual(title, "Beginner")

        level, title = score_to_proficiency(35.5)
        self.assertEqual(level, 1)
        self.assertEqual(title, "Beginner")

    def test_level_2_basic_mapping(self):
        level, title = score_to_proficiency(40.0)
        self.assertEqual(level, 2)
        self.assertEqual(title, "Basic")

        level, title = score_to_proficiency(58.0)
        self.assertEqual(level, 2)
        self.assertEqual(title, "Basic")

    def test_level_3_intermediate_mapping(self):
        level, title = score_to_proficiency(60.0)
        self.assertEqual(level, 3)
        self.assertEqual(title, "Intermediate")

        level, title = score_to_proficiency(72.0)
        self.assertEqual(level, 3)
        self.assertEqual(title, "Intermediate")

    def test_level_4_advanced_mapping(self):
        level, title = score_to_proficiency(75.0)
        self.assertEqual(level, 4)
        self.assertEqual(title, "Advanced")

        level, title = score_to_proficiency(88.0)
        self.assertEqual(level, 4)
        self.assertEqual(title, "Advanced")

    def test_level_5_expert_mapping(self):
        level, title = score_to_proficiency(90.0)
        self.assertEqual(level, 5)
        self.assertEqual(title, "Expert")

        level, title = score_to_proficiency(100.0)
        self.assertEqual(level, 5)
        self.assertEqual(title, "Expert")

    def test_out_of_bounds_score_clamping(self):
        # Negative scores clamp to Level 1 Beginner
        level, title = score_to_proficiency(-15.0)
        self.assertEqual(level, 1)
        self.assertEqual(title, "Beginner")

        # Scores > 100 clamp to Level 5 Expert
        level, title = score_to_proficiency(150.0)
        self.assertEqual(level, 5)
        self.assertEqual(title, "Expert")

    def test_level_to_baseline_score(self):
        self.assertEqual(level_to_baseline_score(1), 25.0)
        self.assertEqual(level_to_baseline_score(2), 50.0)
        self.assertEqual(level_to_baseline_score(3), 68.0)
        self.assertEqual(level_to_baseline_score(4), 82.0)
        self.assertEqual(level_to_baseline_score(5), 95.0)
        # Clamped out of range
        self.assertEqual(level_to_baseline_score(0), 25.0)
        self.assertEqual(level_to_baseline_score(10), 95.0)


class TestCompetencyFrameworkCatalog(unittest.TestCase):
    """Test competency framework retrieval and structure."""

    def test_catalog_contains_standard_roles(self):
        roles = [
            "Full-Stack Engineer",
            "Backend Engineer (Python / Cloud)",
            "Frontend Engineer (React / Next.js)",
            "AI / Machine Learning Engineer",
            "DevOps / Cloud Engineer",
        ]
        for role in roles:
            framework = get_role_competency_framework(role)
            self.assertGreaterEqual(len(framework), 4)
            for item in framework:
                self.assertIn("skill", item)
                self.assertIn("category", item)
                self.assertIn("target_level", item)
                self.assertIn("role_criticality", item)
                self.assertIn("desc", item)
                self.assertIn(item["target_level"], [1, 2, 3, 4, 5])

    def test_framework_fallback_for_unknown_role(self):
        framework = get_role_competency_framework("Unknown Specialty Role")
        self.assertGreaterEqual(len(framework), 4)
        skills = [f["skill"] for f in framework]
        self.assertIn("PostgreSQL & Database Design", skills)


class TestEvidenceClassificationAndGaps(unittest.TestCase):
    """Test evidence classification and deterministic gap calculations."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # Create test user
        self.user = UserAccount(
            email="learner@test.com",
            full_name="Alex Learner",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_classify_skill_evidence_not_evidenced(self):
        evidence = classify_skill_evidence(
            skill_name="Kubernetes",
            analytics_records=[],
            mock_interviews=[],
            self_reported_data={},
        )
        self.assertEqual(evidence["evidence_type"], "NOT_EVIDENCED")
        self.assertEqual(evidence["level"], 0)
        self.assertFalse(evidence["is_verified"])

    def test_classify_skill_evidence_self_reported(self):
        self_reported = {
            "Docker": {
                "level": 3,
                "level_title": "Intermediate",
                "baseline_score": 68.0,
                "notes": "Used in personal project",
            }
        }
        evidence = classify_skill_evidence(
            skill_name="Docker",
            analytics_records=[],
            mock_interviews=[],
            self_reported_data=self_reported,
        )
        self.assertEqual(evidence["evidence_type"], "SELF_REPORTED")
        self.assertEqual(evidence["level"], 3)
        self.assertFalse(evidence["is_verified"])
        self.assertEqual(evidence["confidence"], "UNVERIFIED")

    def test_classify_skill_evidence_assessed(self):
        analytics = [
            CandidateSkillAnalytics(
                user_id=self.user.id,
                skill="Python / Core Backend",
                score=78.5,
                confidence="HIGH",
                trend="improving",
                weakness_status="proficient",
            )
        ]
        evidence = classify_skill_evidence(
            skill_name="Python / Core Backend",
            analytics_records=analytics,
            mock_interviews=[],
            self_reported_data={},
        )
        self.assertEqual(evidence["evidence_type"], "ASSESSED")
        self.assertEqual(evidence["level"], 4)
        self.assertEqual(evidence["level_title"], "Advanced")
        self.assertEqual(evidence["score"], 78.5)
        self.assertTrue(evidence["is_verified"])

    def test_classify_skill_evidence_verified_via_mock(self):
        mocks = [
            MockInterview(
                user_id=self.user.id,
                role="Full-Stack Engineer",
                score=88.0,
                technical_accuracy=86.0,
                status="completed",
                transcript="The candidate demonstrated excellent understanding of REST APIs & HTTP protocols.",
            )
        ]
        analytics = [
            CandidateSkillAnalytics(
                user_id=self.user.id,
                skill="REST APIs & HTTP",
                score=85.0,
                confidence="HIGH",
            )
        ]
        evidence = classify_skill_evidence(
            skill_name="REST APIs & HTTP",
            analytics_records=analytics,
            mock_interviews=mocks,
            self_reported_data={},
        )
        self.assertEqual(evidence["evidence_type"], "VERIFIED")
        self.assertEqual(evidence["level"], 4)
        self.assertTrue(evidence["is_verified"])

    def test_skill_gap_calculation_and_prioritization(self):
        # Add high-score assessment for Python, none for others
        self.db.add(
            CandidateSkillAnalytics(
                user_id=self.user.id,
                skill="Python / Core Backend",
                score=82.0,
                confidence="HIGH",
            )
        )
        self.db.commit()

        gaps = calculate_learner_skill_gaps(
            user_id=self.user.id,
            target_role="Backend Engineer (Python / Cloud)",
            db=self.db,
            self_reported_skills={},
        )

        self.assertIsInstance(gaps, list)
        self.assertGreater(len(gaps), 0)

        # Check prioritization sorting (CRITICAL -> HIGH -> MODERATE -> LOW -> ON_TRACK)
        priorities = [g["priority"] for g in gaps]
        priority_weights = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3, "ON_TRACK": 4}
        numeric_priorities = [priority_weights[p] for p in priorities]
        self.assertEqual(numeric_priorities, sorted(numeric_priorities))

        # Check Python / Core Backend is ON_TRACK because score 82.0 is Level 4 meeting target level 4
        python_gap = next((g for g in gaps if g["skill"] == "Python / Core Backend"), None)
        self.assertIsNotNone(python_gap)
        self.assertEqual(python_gap["current_level"], 4)
        self.assertEqual(python_gap["target_level"], 4)
        self.assertEqual(python_gap["gap_level"], 0)
        self.assertEqual(python_gap["priority"], "ON_TRACK")


class TestResumeSyncZeroHallucination(unittest.TestCase):
    """Test resume synchronization guarantees zero fabrication of data."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.user = UserAccount(
            email="resumetester@test.com",
            full_name="Jordan Tester",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_sync_no_scans_returns_none(self):
        result = sync_profile_from_resume_scan(user_id=self.user.id, db=self.db)
        self.assertIsNone(result)

    def test_sync_extracts_only_scanned_attributes(self):
        scan = ResumeScan(
            scan_id="scan-xyz-123",
            user_id=self.user.id,
            target_role="Cloud DevOps Engineer",
            match_score=85.0,
            matched_skills="Docker, Kubernetes, AWS, Terraform",
            normalized_resume=json.dumps({
                "total_years_experience": 3.5,
                "education": [{"degree": "B.Tech Computer Science"}],
            }),
        )
        self.db.add(scan)
        self.db.commit()

        result = sync_profile_from_resume_scan(user_id=self.user.id, db=self.db)
        self.assertIsNotNone(result)
        self.assertEqual(result["scan_id"], "scan-xyz-123")
        self.assertEqual(result["target_role"], "Cloud DevOps Engineer")
        self.assertEqual(result["match_score"], 85.0)
        self.assertEqual(result["years_of_experience"], 3.5)
        self.assertEqual(result["education"], "B.Tech Computer Science")
        self.assertEqual(len(result["extracted_skills"]), 4)


class TestLearnerProfileAPI(unittest.TestCase):
    """Test full API router logic and profile lifecycle."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.user = UserAccount(
            email="api_learner@test.com",
            full_name="Taylor API",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_get_or_create_learner_profile(self):
        profile = get_or_create_learner_profile(self.user, self.db)
        self.assertIsNotNone(profile.id)
        self.assertEqual(profile.user_id, self.user.id)
        self.assertEqual(profile.target_role, "Full-Stack Engineer")

        # Fetch again should return the same profile
        profile2 = get_or_create_learner_profile(self.user, self.db)
        self.assertEqual(profile.id, profile2.id)

    def test_update_profile(self):
        req = UpdateProfileRequest(
            target_role="AI / Machine Learning Engineer",
            target_level="Senior",
            career_goals="Transition from general backend to deep ML systems.",
            education_level="Master's in Data Science",
            institution="Tech University",
            graduation_year=2023,
            years_of_experience=4.5,
            current_role="Backend Engineer",
            current_company="Acme Corp",
            preferred_learning_goals=["Transformers", "Distributed Training"],
            career_interests=["LLM Fine-tuning", "Vector Search"],
        )
        res = update_profile(req=req, user=self.user, db=self.db)
        self.assertEqual(res.target_role, "AI / Machine Learning Engineer")
        self.assertEqual(res.target_level, "Senior")
        self.assertEqual(res.years_of_experience, 4.5)
        self.assertEqual(res.current_role, "Backend Engineer")
        self.assertIn("Transformers", res.preferred_learning_goals)

    def test_self_report_skill_and_delete(self):
        req = SelfReportedSkillIn(
            skill="Redis Caching",
            level=3,
            notes="Implemented write-through caching in production",
        )
        report_res = self_report_skill(req=req, user=self.user, db=self.db)
        self.assertTrue(report_res["success"])
        self.assertEqual(report_res["level"], 3)
        self.assertEqual(report_res["level_title"], "Intermediate")
        self.assertFalse(report_res["is_verified"])
        self.assertEqual(report_res["evidence_type"], "SELF_REPORTED")

        # Verify profile has the skill
        profile = get_or_create_learner_profile(self.user, self.db)
        skills = json.loads(profile.self_reported_skills)
        self.assertIn("Redis Caching", skills)

        # Delete the skill
        del_res = delete_self_reported_skill("Redis Caching", user=self.user, db=self.db)
        self.assertTrue(del_res["success"])

        # Verify removed
        profile_after = get_or_create_learner_profile(self.user, self.db)
        skills_after = json.loads(profile_after.self_reported_skills)
        self.assertNotIn("Redis Caching", skills_after)

    def test_get_competency_matrix_endpoint(self):
        matrix = get_competency_matrix(
            role="Backend Engineer (Python / Cloud)",
            user=self.user,
            db=self.db,
        )
        self.assertIsInstance(matrix, list)
        self.assertGreater(len(matrix), 0)
        skills = [item.skill for item in matrix]
        self.assertIn("PostgreSQL & Database Design", skills)

    def test_sync_resume_endpoint_flow(self):
        scan = ResumeScan(
            scan_id="scan-sync-api-999",
            user_id=self.user.id,
            target_role="Full-Stack Engineer",
            match_score=88.5,
            matched_skills="Python, TypeScript, React, SQL",
            normalized_resume=json.dumps({
                "total_years_experience": 5.0,
                "education": [{"degree": "B.S. in Computer Science"}],
            }),
        )
        self.db.add(scan)
        self.db.commit()

        sync_out = sync_resume(scan_id="scan-sync-api-999", user=self.user, db=self.db)
        self.assertTrue(sync_out.success)
        self.assertEqual(sync_out.scan_id, "scan-sync-api-999")
        self.assertEqual(sync_out.years_of_experience, 5.0)

        # Verify profile was updated
        profile = get_or_create_learner_profile(self.user, self.db)
        self.assertEqual(profile.years_of_experience, 5.0)
        self.assertEqual(profile.education_level, "B.S. in Computer Science")
        self.assertEqual(profile.latest_scan_id, "scan-sync-api-999")


if __name__ == "__main__":
    unittest.main()
