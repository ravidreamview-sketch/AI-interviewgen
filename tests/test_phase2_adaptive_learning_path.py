"""
Phase 2 Adaptive Learning Path Agent Test Suite
================================================
Validates:
1. Personalized Roadmap Generation based on profile, target role, and competency gaps.
2. Differentiation / Non-identical Roadmaps across different user profiles and gap types.
3. Candidate Mistakes Remediation: Unresolved mistakes trigger targeted recovery modules.
4. Tenant Isolation / Ownership Enforcement on learning paths.
5. Progress Tracking: Activity completion, module %, milestone unlocking, and roadmap progress.
6. Continuous Adaptation with Progress Preservation: Completed activities are never erased.
7. Next Recommended Activity & Upcoming Queue resolution.
8. API Route Handlers for active roadmap, generation, adaptation, and progress updates.
9. Strict Pydantic Schema Validation for all generated roadmap structures.
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
    CandidateMistakesLedger,
    MockInterview,
    AdaptiveRoadmap,
)
from app.services.adaptive_path_service import (
    LearningActivity,
    LearningMilestone,
    LearningModule,
    AdaptiveRoadmapData,
    generate_adaptive_learning_path,
    update_learning_path_with_evidence,
    track_activity_progress,
    get_next_recommended_activity,
)
from app.api.v1.paths import (
    get_active_roadmap,
    generate_roadmap_endpoint,
    adapt_roadmap_endpoint,
    update_activity_progress_endpoint,
    get_next_recommendation_endpoint,
    get_roadmap_history_endpoint,
    GeneratePathRequest,
    AdaptPathRequest,
    UpdateActivityProgressRequest,
)


class TestAdaptiveRoadmapGeneration(unittest.TestCase):
    """Test personalized roadmap generation and schema validation."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # User 1: Backend Engineer with high experience
        self.user_backend = UserAccount(
            email="backend_learner@test.com",
            full_name="Sam Backend",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user_backend)
        self.db.commit()
        self.db.refresh(self.user_backend)

        profile_backend = LearnerProfile(
            user_id=self.user_backend.id,
            target_role="Backend Engineer (Python / Cloud)",
            target_level="Senior",
            years_of_experience=4.0,
        )
        self.db.add(profile_backend)

        # User 2: Full-Stack Engineer Fresher
        self.user_fullstack = UserAccount(
            email="fullstack_learner@test.com",
            full_name="Robin Fullstack",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user_fullstack)
        self.db.commit()
        self.db.refresh(self.user_fullstack)

        profile_fullstack = LearnerProfile(
            user_id=self.user_fullstack.id,
            target_role="Full-Stack Engineer",
            target_level="Junior",
            years_of_experience=0.5,
        )
        self.db.add(profile_fullstack)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_generate_roadmap_schema_compliance(self):
        roadmap = generate_adaptive_learning_path(
            user_id=self.user_backend.id,
            db=self.db,
            target_role="Backend Engineer (Python / Cloud)",
        )

        self.assertIsInstance(roadmap, AdaptiveRoadmapData)
        self.assertTrue(roadmap.roadmap_id.startswith("path_"))
        self.assertEqual(roadmap.target_role, "Backend Engineer (Python / Cloud)")
        self.assertGreaterEqual(len(roadmap.modules), 1)

        # Validate sequence indices and activities
        for i, mod in enumerate(roadmap.modules, start=1):
            self.assertEqual(mod.sequence_index, i)
            self.assertGreaterEqual(len(mod.activities), 1)
            self.assertIsNotNone(mod.milestone)
            for act in mod.activities:
                self.assertIn(act.activity_type, [
                    "interactive_concept",
                    "code_exercise",
                    "system_design_challenge",
                    "architecture_review",
                    "knowledge_check",
                ])

    def test_personalization_non_identical_roadmaps(self):
        # Generate for Backend Engineer
        backend_roadmap = generate_adaptive_learning_path(
            user_id=self.user_backend.id,
            db=self.db,
            target_role="Backend Engineer (Python / Cloud)",
        )
        # Generate for Full-Stack Engineer
        fullstack_roadmap = generate_adaptive_learning_path(
            user_id=self.user_fullstack.id,
            db=self.db,
            target_role="Full-Stack Engineer",
        )

        self.assertNotEqual(backend_roadmap.target_role, fullstack_roadmap.target_role)
        self.assertNotEqual(backend_roadmap.title, fullstack_roadmap.title)

        backend_skills = [s for m in backend_roadmap.modules for s in m.targeted_skills]
        fullstack_skills = [s for m in fullstack_roadmap.modules for s in m.targeted_skills]

        self.assertIn("Python / Core Backend", backend_skills)
        self.assertIn("TypeScript & React", fullstack_skills)

    def test_mistakes_ledger_triggers_remediation_module(self):
        # Add unresolved mistakes in concurrency for user_backend
        mistake = CandidateMistakesLedger(
            user_id=self.user_backend.id,
            adaptive_session_id="session_test_01",
            skill="Python / Core Backend",
            mistake_category="Asyncio Concurrency Bottleneck",
            description="Blocked event loop with synchronous time.sleep inside coroutine",
            mistake_status="identified",
        )
        self.db.add(mistake)
        self.db.commit()

        roadmap = generate_adaptive_learning_path(
            user_id=self.user_backend.id,
            db=self.db,
            target_role="Backend Engineer (Python / Cloud)",
        )

        first_module = roadmap.modules[0]
        self.assertEqual(first_module.title, "Rapid Remediation & Mistake Resolution")
        self.assertEqual(first_module.gap_priority, "CRITICAL")
        self.assertIn("Asyncio Concurrency Bottleneck", first_module.targeted_skills)


class TestProgressTrackingAndPreservation(unittest.TestCase):
    """Test progress tracking, milestone unlocking, and continuous adaptation preservation."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.user = UserAccount(
            email="tracker@test.com",
            full_name="Alex Tracker",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        self.roadmap = generate_adaptive_learning_path(
            user_id=self.user.id,
            db=self.db,
            target_role="Full-Stack Engineer",
        )

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_track_activity_progress(self):
        first_mod = self.roadmap.modules[0]
        first_act = first_mod.activities[0]

        result = track_activity_progress(
            roadmap_id=self.roadmap.roadmap_id,
            activity_id=first_act.id,
            status="completed",
            user_id=self.user.id,
            db=self.db,
            score=95.0,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["new_status"], "completed")
        self.assertGreater(result["module_progress"], 0.0)
        self.assertGreater(result["roadmap_progress"], 0.0)
        self.assertEqual(result["completed_count"], 1)

    def test_continuous_adaptation_preserves_completed_progress(self):
        # 1. Complete first activity
        first_act = self.roadmap.modules[0].activities[0]
        track_activity_progress(
            roadmap_id=self.roadmap.roadmap_id,
            activity_id=first_act.id,
            status="completed",
            user_id=self.user.id,
            db=self.db,
            score=100.0,
        )

        # 2. Trigger adaptation (e.g. following new assessment)
        adapted_roadmap = update_learning_path_with_evidence(
            user_id=self.user.id,
            db=self.db,
            roadmap_id=self.roadmap.roadmap_id,
            trigger_reason="New Mock Interview Assessment Completed",
        )

        # 3. Assert completed activity was NOT erased
        matching_act = None
        for m in adapted_roadmap.modules:
            for a in m.activities:
                if a.id == first_act.id or a.title == first_act.title:
                    matching_act = a
                    break
            if matching_act:
                break

        self.assertIsNotNone(matching_act)
        self.assertEqual(matching_act.status, "completed")
        self.assertIsNotNone(matching_act.completed_at)
        self.assertGreater(adapted_roadmap.overall_progress, 0.0)

    def test_next_recommended_activity(self):
        rec = get_next_recommended_activity(
            roadmap_id=self.roadmap.roadmap_id,
            user_id=self.user.id,
            db=self.db,
        )

        self.assertIsNotNone(rec["current_activity"])
        self.assertIsNotNone(rec["current_module"])
        self.assertIsInstance(rec["upcoming_queue"], list)


class TestRoadmapTenantIsolationAndAPI(unittest.TestCase):
    """Test authorization, tenant isolation, and API route handlers."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # User A
        self.user_a = UserAccount(
            email="user_a@test.com",
            full_name="User Alpha",
            password_hash="test_hash",
            role="candidate",
        )
        # User B
        self.user_b = UserAccount(
            email="user_b@test.com",
            full_name="User Bravo",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()
        self.db.refresh(self.user_a)
        self.db.refresh(self.user_b)

        self.roadmap_a = generate_adaptive_learning_path(
            user_id=self.user_a.id,
            db=self.db,
            target_role="Full-Stack Engineer",
        )

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_tenant_isolation_user_b_cannot_mutate_user_a_roadmap(self):
        first_act = self.roadmap_a.modules[0].activities[0]

        # User B attempts to complete User A's activity
        with self.assertRaises(ValueError):
            track_activity_progress(
                roadmap_id=self.roadmap_a.roadmap_id,
                activity_id=first_act.id,
                status="completed",
                user_id=self.user_b.id,  # Unauthorized user
                db=self.db,
            )

    def test_api_active_roadmap_and_generation(self):
        # User B has no roadmap yet, get_active_roadmap should auto-synthesize
        active_b = get_active_roadmap(user=self.user_b, db=self.db)
        self.assertIsNotNone(active_b)
        self.assertEqual(active_b.target_role, "Full-Stack Engineer")

        # Explicit generation endpoint
        gen_req = GeneratePathRequest(
            target_role="AI / Machine Learning Engineer",
            focus_areas=["LLM Systems", "Vector Search"],
        )
        new_b = generate_roadmap_endpoint(req=gen_req, user=self.user_b, db=self.db)
        self.assertEqual(new_b.target_role, "AI / Machine Learning Engineer")

    def test_api_adapt_and_history(self):
        adapt_req = AdaptPathRequest(
            roadmap_id=self.roadmap_a.roadmap_id,
            trigger_reason="Completed System Design Module",
        )
        adapted = adapt_roadmap_endpoint(req=adapt_req, user=self.user_a, db=self.db)
        self.assertIsNotNone(adapted)

        # Check history endpoint
        history = get_roadmap_history_endpoint(user=self.user_a, db=self.db)
        self.assertIsInstance(history, list)
        self.assertGreater(len(history), 0)
        self.assertGreater(len(history[0]["adaptations"]), 0)


if __name__ == "__main__":
    unittest.main()
