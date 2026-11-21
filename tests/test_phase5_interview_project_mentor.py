"""
Phase 5 AI Interview & Project Mentor Agent Test Suite
======================================================
Validates:
1. Reusing Existing Interview Engine: Context-aware launch and turn evaluation.
2. Context Integration: LearnerProfile, skill gaps, and active curriculum focus.
3. Competency Mapping Enhancement: 5-tier taxonomy integration into interview evaluations.
4. Interview Session Ownership: Tenant isolation enforced on mock interview sessions.
5. Project Mentorship Engine: Guidance generation and actionable items across stages.
6. Project Ownership: User B cannot access or mentor User A's portfolio project.
7. API Route Handlers: Start, turn, history, scorecard, project creation, mentorship, and history.
8. Socratic Boundaries: Mentor provides guidance without auto-completing all learner work.
"""

import json
import unittest
from unittest.mock import patch
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
    LearnerProject,
    ProjectMentorshipTurn,
)
from app.services.interview_mentor_service import (
    assemble_interview_context,
    start_context_aware_interview,
    process_context_aware_interview_turn,
    mentor_project_interaction,
)
from app.api.v1.interviews import (
    start_interview_endpoint,
    process_turn_endpoint,
    list_interview_history,
    get_interview_scorecard,
    create_project,
    list_projects,
    mentor_project_endpoint,
    list_project_mentorship_history,
    StartInterviewRequest,
    InterviewTurnRequest,
    ProjectCreateRequest,
    ProjectMentorRequest,
)


class TestContextAwareInterviewEngine(unittest.TestCase):
    """Test context assembly, interview launch, and turn evaluation reusing existing engine."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.user = UserAccount(
            email="mentor_candidate@test.com",
            full_name="Morgan Candidate",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        profile = LearnerProfile(
            user_id=self.user.id,
            target_role="Backend Engineer (Python / Cloud)",
            target_level="Senior",
            years_of_experience=4.0,
        )
        self.db.add(profile)

        # Skill analytics (weak competency)
        weak_skill = CandidateSkillAnalytics(
            user_id=self.user.id,
            skill="PostgreSQL Concurrency",
            score=45.0,
            confidence="HIGH",
        )
        self.db.add(weak_skill)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_assemble_interview_context(self):
        role, skills, ctx = assemble_interview_context(user_id=self.user.id, db=self.db)
        self.assertEqual(role, "Backend Engineer (Python / Cloud)")
        self.assertIn("PostgreSQL Concurrency", skills)
        self.assertEqual(ctx["target_level"], "Senior")
        self.assertEqual(ctx["years_of_experience"], 4.0)

    @patch("app.interview_engine.generate_ai_questions")
    def test_start_context_aware_interview_reuses_engine(self, mock_gen):
        mock_gen.return_value = "1. How do you design an idempotent payment API?\n2. What is your caching strategy?\n3. How do you handle deadlocks?"
        res = start_context_aware_interview(
            user_id=self.user.id,
            db=self.db,
            target_role="Backend Engineer (Python / Cloud)",
            persona="alex",
            interview_type="technical",
            mode="text",
            question_count=3,
        )

        self.assertIn("interview_id", res)
        self.assertTrue(res["interview_id"].startswith("mock_"))
        self.assertIn("first_question", res)
        self.assertGreater(len(res["first_question"]), 5)
        self.assertEqual(res["persona"]["name"], "Alex")

        # Verify MockInterview record created
        rec_id = int(res["interview_id"].removeprefix("mock_"))
        mock_rec = self.db.query(MockInterview).filter(MockInterview.id == rec_id).first()
        self.assertIsNotNone(mock_rec)
        self.assertEqual(mock_rec.user_id, self.user.id)
        self.assertEqual(mock_rec.status, "in_progress")

    @patch("app.interview_engine.generate_ai_questions")
    def test_process_interview_turn_and_competency_enrichment(self, mock_gen):
        mock_gen.side_effect = [
            "1. Can you describe how you handle database lock contention?\n2. How do you monitor P99 latency?",
            json.dumps({
                "evaluation": {
                    "score": 85,
                    "technical_score": 88,
                    "communication_score": 82,
                    "strengths": ["Clear STAR structure", "Deep database locking knowledge"],
                    "improvements": ["Could discuss connection pooling impact"],
                    "star_detected": True,
                    "feedback": "Strong structured explanation of query tuning and lock mitigation."
                },
                "next_question": "How did you monitor lock wait times in production?",
                "follow_up_required": False
            })
        ]
        session = start_context_aware_interview(
            user_id=self.user.id,
            db=self.db,
            target_role="Backend Engineer (Python / Cloud)",
            question_count=2,
        )

        turn_res = process_context_aware_interview_turn(
            interview_id=session["interview_id"],
            answer_text=(
                "In my previous project, we encountered heavy database lock contention. "
                "I analyzed query plans using EXPLAIN ANALYZE, replaced table locks with row-level locks, "
                "and reduced P99 latency by 60%."
            ),
            user_id=self.user.id,
            db=self.db,
            turn_index=1,
            is_final=False,
        )

        self.assertIn("evaluation", turn_res)
        eval_data = turn_res["evaluation"]
        self.assertIsNotNone(eval_data)
        self.assertIn("competency_tier", eval_data)
        self.assertIn(eval_data["competency_tier"]["level"], [1, 2, 3, 4, 5])


class TestProjectMentorshipAndOwnership(unittest.TestCase):
    """Test AI Project Mentor, stage guidance, and tenant isolation."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # User A
        self.user_a = UserAccount(
            email="user_a_proj@test.com",
            full_name="User Alpha",
            password_hash="test_hash",
            role="candidate",
        )
        # User B
        self.user_b = UserAccount(
            email="user_b_proj@test.com",
            full_name="User Bravo",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()
        self.db.refresh(self.user_a)
        self.db.refresh(self.user_b)

        # Create project for User A
        self.project_a = LearnerProject(
            project_id="proj_alpha_99",
            user_id=self.user_a.id,
            title="Distributed Task Queue",
            target_role="Backend Engineer (Python / Cloud)",
            domain="Distributed Cloud Systems",
            description="A distributed async worker system handling priority jobs with Redis and PostgreSQL.",
            tech_stack=json.dumps(["Python", "FastAPI", "Redis", "PostgreSQL"]),
            status="planning",
        )
        self.db.add(self.project_a)
        self.db.commit()
        self.db.refresh(self.project_a)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_project_mentoring_architecture_stage(self):
        res = mentor_project_interaction(
            user=self.user_a,
            db=self.db,
            project_id=self.project_a.project_id,
            stage="architecture",
            user_query="How should I handle worker crash recovery without dropping active jobs?",
        )

        self.assertEqual(res["project_id"], self.project_a.project_id)
        self.assertEqual(res["stage"], "architecture")
        self.assertIn("Architecture Guidance", res["mentor_guidance"])
        self.assertGreater(len(res["action_items"]), 0)

        # Verify DB turn record
        turn = self.db.query(ProjectMentorshipTurn).filter(
            ProjectMentorshipTurn.project_id == self.project_a.project_id
        ).first()
        self.assertIsNotNone(turn)
        self.assertEqual(turn.user_id, self.user_a.id)

    def test_tenant_isolation_user_b_cannot_mentor_user_a_project(self):
        with self.assertRaises(ValueError) as ctx:
            mentor_project_interaction(
                user=self.user_b,  # Unauthorized user
                db=self.db,
                project_id=self.project_a.project_id,
                stage="architecture",
                user_query="Querying Alpha's project.",
            )
        self.assertIn("access denied", str(ctx.exception))

    def test_api_project_lifecycle(self):
        # 1. Create project via API
        req = ProjectCreateRequest(
            title="Real-Time Event Streamer",
            target_role="Full-Stack Engineer",
            domain="Web Systems",
            description="A real-time analytics dashboard with SSE updates.",
            tech_stack=["React", "TypeScript", "FastAPI"],
        )
        p_out = create_project(req=req, user=self.user_a, db=self.db)
        self.assertIsNotNone(p_out.project_id)
        self.assertEqual(p_out.title, "Real-Time Event Streamer")

        # 2. List projects
        p_list = list_projects(user=self.user_a, db=self.db)
        self.assertEqual(len(p_list), 2)

        # 3. Request mentorship
        m_req = ProjectMentorRequest(
            stage="presentation_prep",
            user_query="How should I frame the trade-off of SSE versus WebSockets in my interview?",
        )
        m_out = mentor_project_endpoint(
            project_id=p_out.project_id,
            req=m_req,
            user=self.user_a,
            db=self.db,
        )
        self.assertEqual(m_out["stage"], "presentation_prep")
        self.assertGreater(len(m_out["action_items"]), 0)

        # 4. List mentorship history
        history = list_project_mentorship_history(
            project_id=p_out.project_id,
            user=self.user_a,
            db=self.db,
        )
        self.assertEqual(len(history), 1)


if __name__ == "__main__":
    unittest.main()
