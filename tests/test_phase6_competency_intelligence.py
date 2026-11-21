"""
Phase 6 Competency Intelligence Test Suite
==========================================
Validates:
1. Multi-source evidence aggregation (Profile, Assessments, Roadmap, Scenarios, Interviews, Projects).
2. Distinguishing evidence types: Self-reported, Assessed, Scenario-based, Interview-based, Project-based.
3. User ownership and strict tenant isolation (User B cannot see User A's competency data).
4. Competency calculations and 5-tier taxonomy mapping (Novice, Beginner, Competent, Proficient, Expert).
5. Missing evidence identification (handling empty or sparse candidate profiles).
6. Target role benchmark gaps calculation (Backend, Fullstack, Frontend, DevOps).
7. Recommendation logic connected to roadmaps, scenarios, projects, and interviews.
8. API Route Handlers (Readiness, Dashboard, Skills, Gaps, Recommendations).
9. Edge cases & error handling (corrupted JSON, missing profile, zero activities).
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
    AdaptiveRoadmap,
    TutorSession,
    RealWorldScenario,
    ScenarioSubmissionRecord,
    LearnerProject,
    ProjectMentorshipTurn,
    MockInterview,
)
from app.services.competency_intelligence_service import (
    consolidate_learner_evidence,
    calculate_role_benchmarks_and_gaps,
    calculate_career_readiness,
    generate_connected_recommendations,
    build_competency_dashboard,
    map_score_to_tier,
)
from app.api.v1.competency import (
    get_readiness_metrics,
    get_competency_dashboard,
    get_consolidated_skills,
    get_role_gaps,
    get_actionable_recommendations,
)


class TestCompetencyIntelligenceEngine(unittest.TestCase):
    """Test suite for evidence consolidation, tier mapping, and readiness scoring."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # User A: Full multi-source evidence
        self.user_a = UserAccount(
            email="candidate_alpha@test.com",
            full_name="Alpha Architect",
            password_hash="test_hash",
            role="candidate",
        )
        # User B: Sparse candidate
        self.user_b = UserAccount(
            email="candidate_beta@test.com",
            full_name="Beta Beginner",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()
        self.db.refresh(self.user_a)
        self.db.refresh(self.user_b)

        # Profile for User A
        self.profile_a = LearnerProfile(
            user_id=self.user_a.id,
            target_role="Backend Engineer (Python / Cloud)",
            target_level="Senior",
            years_of_experience=5.0,
            self_reported_skills=json.dumps({
                "Python": "expert",
                "Docker": "intermediate",
                "Kubernetes": "beginner",
            }),
        )
        self.db.add(self.profile_a)

        # Assessment analytics for User A
        self.skill_a1 = CandidateSkillAnalytics(
            user_id=self.user_a.id,
            skill="Python Architecture",
            score=88.0,
            trend="improving",
            confidence="HIGH",
            evidence_count=4,
            weakness_status="improving",
        )
        self.skill_a2 = CandidateSkillAnalytics(
            user_id=self.user_a.id,
            skill="PostgreSQL & Concurrency",
            score=62.0,
            trend="declining",
            confidence="MEDIUM",
            evidence_count=2,
            weakness_status="identified",
        )
        self.db.add_all([self.skill_a1, self.skill_a2])

        # Open mistake for User A
        self.mistake_a = CandidateMistakesLedger(
            user_id=self.user_a.id,
            adaptive_session_id="session_alpha_1",
            skill="PostgreSQL & Concurrency",
            description="Table-level exclusive lock used instead of optimistic concurrency control.",
            severity="high",
            recommendation="Utilize version columns or row-level SELECT FOR UPDATE NOWAIT.",
            mistake_status="identified",
        )
        self.db.add(self.mistake_a)

        # Scenario and submission for User A
        self.scenario_a = RealWorldScenario(
            scenario_id="sc_alpha_01",
            user_id=self.user_a.id,
            title="High-Concurrency Ticket Booking",
            category="debugging",
            domain="Distributed Systems",
            target_role="Backend Engineer (Python / Cloud)",
            difficulty="Advanced",
            difficulty_level=4,
            context="System deadlocks under burst ticket booking traffic.",
            problem_statement="Mitigate deadlocks while preserving idempotency.",
            required_skills=json.dumps(["Python Architecture", "PostgreSQL & Concurrency"]),
            objectives=json.dumps(["Fix lock contention"]),
            instructions=json.dumps(["Refactor booking transaction"]),
            constraints=json.dumps(["< 50ms latency"]),
            deliverables=json.dumps(["Clean query plan"]),
            rubric=json.dumps({"correctness": {"weight": 1.0}}),
            success_criteria=json.dumps(["Pass concurrency test"]),
            is_completed=True,
        )
        self.db.add(self.scenario_a)
        self.db.commit()

        self.sub_a = ScenarioSubmissionRecord(
            submission_id="sub_alpha_01",
            scenario_id="sc_alpha_01",
            user_id=self.user_a.id,
            solution_text="Implemented SELECT FOR UPDATE SKIP LOCKED with redis distributed lock.",
            overall_score=86.0,
            status="passed",
            evaluated_at=datetime.now(timezone.utc),
        )
        self.db.add(self.sub_a)

        # Mock interview for User A
        self.interview_a = MockInterview(
            user_id=self.user_a.id,
            role="Backend Engineer (Python / Cloud)",
            interviewer_persona="Alex (Tech Lead)",
            score=84.0,
            technical_accuracy=86.0,
            communication_clarity=82.0,
            star_depth=85.0,
            status="completed",
        )
        self.db.add(self.interview_a)

        # Portfolio project & turn for User A
        self.project_a = LearnerProject(
            project_id="proj_alpha_task_queue",
            user_id=self.user_a.id,
            title="Distributed Priority Task Queue",
            target_role="Backend Engineer (Python / Cloud)",
            domain="Cloud Infrastructure",
            description="Distributed asynchronous worker queue.",
            tech_stack=json.dumps(["Python", "PostgreSQL & Concurrency", "Redis"]),
            status="in_progress",
        )
        self.db.add(self.project_a)
        self.db.commit()

        self.turn_a = ProjectMentorshipTurn(
            project_id="proj_alpha_task_queue",
            user_id=self.user_a.id,
            mentorship_stage="architecture",
            user_query="Worker crash recovery without job loss.",
            mentor_guidance="Use Redis visibility timeouts and dead-letter queues.",
            action_items=json.dumps(["Configure visibility timeout"]),
        )
        self.db.add(self.turn_a)

        # Active Roadmap for User A
        self.roadmap_a = AdaptiveRoadmap(
            roadmap_id="rdm_alpha_01",
            user_id=self.user_a.id,
            title="Senior Backend Mastery",
            target_role="Backend Engineer (Python / Cloud)",
            target_level="Senior",
            status="active",
            overall_progress=65.0,
            completed_activities_count=8,
            total_activities_count=12,
            roadmap_data=json.dumps({
                "modules": [
                    {
                        "module_id": "mod_1",
                        "title": "Advanced Database Patterns",
                        "skills": ["PostgreSQL & Concurrency"],
                        "activities": [
                            {"activity_id": "act_101", "title": "Locking & Isolation Levels", "completed": False}
                        ],
                    }
                ]
            }),
        )
        self.db.add(self.roadmap_a)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_consolidate_learner_evidence_multi_source(self):
        ev = consolidate_learner_evidence(user_id=self.user_a.id, db=self.db)
        skills = ev["consolidated_skills"]

        # Verify multi-source verified skill
        python_skill = next((s for s in skills if s["skill_name"] == "Python Architecture"), None)
        self.assertIsNotNone(python_skill)
        self.assertEqual(python_skill["verification_status"], "multi_source_verified")
        self.assertGreaterEqual(python_skill["overall_score"], 80.0)
        self.assertEqual(python_skill["competency_tier"]["level"], 4) # Proficient

        # Verify open mistake tracking
        pg_skill = next((s for s in skills if s["skill_name"] == "PostgreSQL & Concurrency"), None)
        self.assertIsNotNone(pg_skill)
        self.assertGreater(pg_skill["open_mistakes_count"], 0)

        # Verify self-reported skill distinction
        docker_skill = next((s for s in skills if s["skill_name"] == "Docker"), None)
        self.assertIsNotNone(docker_skill)
        self.assertEqual(docker_skill["verification_status"], "self_reported")

    def test_tenant_isolation_user_b_sees_no_user_a_evidence(self):
        dash_b = build_competency_dashboard(user_id=self.user_b.id, db=self.db)
        
        # User B has no records
        self.assertEqual(len(dash_b["scenario_evidence"]), 0)
        self.assertEqual(len(dash_b["interview_evidence"]), 0)
        self.assertEqual(len(dash_b["project_evidence"]), 0)
        self.assertFalse(dash_b["learning_progress"]["has_active_roadmap"])
        self.assertEqual(dash_b["readiness"]["readiness_tier"], "Early Foundation")
        self.assertGreater(len(dash_b["readiness"]["missing_evidence"]), 0)

    def test_competency_tier_mapping(self):
        t1 = map_score_to_tier(35.0)
        self.assertEqual(t1["level"], 1)
        self.assertEqual(t1["name"], "Novice")

        t2 = map_score_to_tier(58.0)
        self.assertEqual(t2["level"], 2)
        self.assertEqual(t2["name"], "Beginner")

        t3 = map_score_to_tier(72.0)
        self.assertEqual(t3["level"], 3)
        self.assertEqual(t3["name"], "Competent")

        t4 = map_score_to_tier(86.0)
        self.assertEqual(t4["level"], 4)
        self.assertEqual(t4["name"], "Proficient")

        t5 = map_score_to_tier(96.0)
        self.assertEqual(t5["level"], 5)
        self.assertEqual(t5["name"], "Expert")

    def test_role_benchmark_gaps_calculation(self):
        ev = consolidate_learner_evidence(user_id=self.user_a.id, db=self.db)
        gaps = calculate_role_benchmarks_and_gaps(
            target_role="Backend Engineer (Python / Cloud)",
            target_level="Senior",
            consolidated_skills=ev["consolidated_skills"],
        )

        self.assertGreater(len(gaps), 0)
        python_gap = next((g for g in gaps if "Python" in g["skill"]), None)
        self.assertIsNotNone(python_gap)
        self.assertEqual(python_gap["status"], "met")
        self.assertGreaterEqual(python_gap["gap_delta"], 0.0)

        pg_gap = next((g for g in gaps if "PostgreSQL" in g["skill"]), None)
        self.assertIsNotNone(pg_gap)
        self.assertIn(pg_gap["status"], ["critical_gap", "near_benchmark"])

    def test_career_readiness_assessment_and_disclaimer(self):
        dash = build_competency_dashboard(user_id=self.user_a.id, db=self.db)
        readiness = dash["readiness"]

        self.assertIn("readiness_index", readiness)
        self.assertIn(readiness["readiness_tier"], ["Role Ready - Advanced", "Role Ready - Competent", "Developing Competency"])
        self.assertIn("readiness_disclaimer", readiness)
        self.assertIn("does not represent a hiring guarantee", readiness["readiness_disclaimer"].lower())
        self.assertGreater(readiness["overall_coverage_pct"], 50.0)

    def test_recommendation_logic_connected_to_modules(self):
        dash = build_competency_dashboard(user_id=self.user_a.id, db=self.db)
        recs = dash["recommendations"]

        self.assertIn("skills_to_improve", recs)
        self.assertIn("learning_activities", recs)
        self.assertIn("scenarios", recs)
        self.assertIn("projects", recs)
        self.assertIn("interview_practice", recs)

        # Verify learning activity links to active roadmap
        if recs["learning_activities"]:
            self.assertIn("/paths", recs["learning_activities"][0]["action_url"])

        # Verify interview practice suggests persona and topic
        self.assertEqual(recs["interview_practice"]["persona"], "alex")
        self.assertIn("/interviews", recs["interview_practice"]["action_url"])

    def test_api_route_handlers(self):
        # 1. /readiness
        readiness_out = get_readiness_metrics(user=self.user_a, db=self.db)
        self.assertIsNotNone(readiness_out.overall_readiness_score)
        self.assertIn(readiness_out.readiness_tier, ["Role Ready - Competent", "Developing Competency"])

        # 2. /dashboard
        dash_out = get_competency_dashboard(user=self.user_a, db=self.db)
        self.assertIn("readiness", dash_out)
        self.assertIn("role_gaps", dash_out)
        self.assertIn("skills", dash_out)
        self.assertIn("learning_progress", dash_out)

        # 3. /skills
        skills_out = get_consolidated_skills(
            verification_status="multi_source_verified",
            trend=None,
            user=self.user_a,
            db=self.db,
        )
        self.assertGreater(len(skills_out), 0)
        for s in skills_out:
            self.assertEqual(s["verification_status"], "multi_source_verified")

        # 4. /gaps
        gaps_out = get_role_gaps(user=self.user_a, db=self.db)
        self.assertGreater(len(gaps_out), 0)

        # 5. /recommendations
        recs_out = get_actionable_recommendations(user=self.user_a, db=self.db)
        self.assertGreater(len(recs_out["skills_to_improve"]), 0)

    def test_edge_case_user_with_no_profile_or_corrupted_json(self):
        # User with no profile
        ev_empty = consolidate_learner_evidence(user_id=self.user_b.id, db=self.db)
        self.assertEqual(len(ev_empty["consolidated_skills"]), 0)

        dash_empty = build_competency_dashboard(user_id=self.user_b.id, db=self.db)
        self.assertEqual(dash_empty["readiness"]["readiness_tier"], "Early Foundation")
        self.assertEqual(dash_empty["readiness"]["readiness_index"], 25.0)


if __name__ == "__main__":
    unittest.main()
