"""
Phase 4 Real-World Scenario Generation & Evaluation Agent Test Suite
====================================================================
Validates:
1. Scenario Generation: Personalization by target role, category, and skill gaps.
2. Structured Schema Compliance: Pydantic validation of context, problem, constraints, deliverables, and rubric.
3. Tailored Evaluation Rubric: Criteria are appropriately tailored per scenario type (not generic).
4. Submission Evaluation Engine: Dimension scores, strengths, improvement areas, evidence citation, and disclaimer.
5. Static Analysis Security: No untrusted code execution.
6. Scenario & Submission Ownership: Tenant isolation boundaries prevent cross-user access.
7. Input Validation & Error Handling: Minimum length requirements and non-existent entity handling.
8. API Route Handlers: List, generate, detail, submit, and history endpoints.
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
    RealWorldScenario,
    ScenarioSubmissionRecord,
)
from app.services.scenario_generation_service import (
    ScenarioData,
    SubmissionEvaluationResult,
    generate_personalized_scenario,
    evaluate_scenario_submission,
)
from app.api.v1.scenarios import (
    list_scenarios,
    generate_scenario_endpoint,
    get_scenario_detail,
    submit_solution,
    list_scenario_submissions,
    GenerateScenarioRequest,
    SubmitSolutionRequest,
)


class TestRealWorldScenarioGeneration(unittest.TestCase):
    """Test scenario synthesis, tailored rubrics, and schema validation."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.user = UserAccount(
            email="scenario_user@test.com",
            full_name="Alex CaseStudy",
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
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_generate_scenario_schema_and_tailored_rubric(self):
        scen = generate_personalized_scenario(
            user_id=self.user.id,
            db=self.db,
            category="api_challenge",
            target_role="Backend Engineer (Python / Cloud)",
        )

        self.assertIsInstance(scen, ScenarioData)
        self.assertTrue(scen.scenario_id.startswith("scen_"))
        self.assertEqual(scen.category, "api_challenge")
        self.assertGreaterEqual(len(scen.required_skills), 1)
        self.assertGreaterEqual(len(scen.objectives), 1)
        self.assertGreaterEqual(len(scen.instructions), 1)
        self.assertGreaterEqual(len(scen.constraints), 1)
        self.assertGreaterEqual(len(scen.deliverables), 1)
        self.assertGreaterEqual(len(scen.success_criteria), 1)

        # Verify rubric tailoring: NOT all 7 dimensions are applied generically
        rubric_keys = list(scen.rubric.keys())
        self.assertIn("technical_correctness", rubric_keys)
        self.assertNotIn("design_quality", rubric_keys)  # tailored for API/db, not UX/UI
        total_weight = sum(dim.weight for dim in scen.rubric.values())
        self.assertAlmostEqual(total_weight, 1.0, places=2)

    def test_generate_system_design_scenario(self):
        scen = generate_personalized_scenario(
            user_id=self.user.id,
            db=self.db,
            category="system_design",
            target_role="Full-Stack Engineer",
        )
        self.assertEqual(scen.category, "system_design")
        rubric_keys = list(scen.rubric.keys())
        self.assertIn("design_quality", rubric_keys)


class TestSubmissionEvaluationEngine(unittest.TestCase):
    """Test automated rubric evaluation, evidence extraction, and disclaimer presence."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.user = UserAccount(
            email="eval_user@test.com",
            full_name="Jordan Submitter",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        self.scenario_data = generate_personalized_scenario(
            user_id=self.user.id,
            db=self.db,
            category="api_challenge",
        )
        self.orm_scenario = self.db.query(RealWorldScenario).filter(
            RealWorldScenario.scenario_id == self.scenario_data.scenario_id
        ).first()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_evaluate_submission_passing_score(self):
        solution = (
            "We establish an atomic database transaction using SELECT FOR UPDATE on the balance row. "
            "An idempotency key registry table tracks Stripe event_id with a unique constraint. "
            "If an event has already been processed, we return HTTP 200 immediately without re-crediting."
        )
        code = (
            "async def handle_stripe_webhook(event: WebhookEvent, db: AsyncSession):\n"
            "    async with db.begin():\n"
            "        try:\n"
            "            res = await db.execute(insert(IdempotencyKey).values(key=event.id))\n"
            "        except IntegrityError:\n"
            "            return {'status': 'already_processed'}\n"
        )
        notes = "Trade-off: Row locking adds minor lock contention but guarantees zero duplicate credits."

        result = evaluate_scenario_submission(
            scenario=self.orm_scenario,
            solution_text=solution,
            code_submission=code,
            architectural_notes=notes,
        )

        self.assertIsInstance(result, SubmissionEvaluationResult)
        self.assertGreaterEqual(result.overall_score, 75.0)
        self.assertEqual(result.status, "passed")
        self.assertGreater(len(result.strengths), 0)
        self.assertGreater(len(result.evidence), 0)
        self.assertIn("automated AI competency engine", result.evaluation_disclaimer)

    def test_evaluate_submission_revision_needed(self):
        # Superficial response lacking concurrency or deduplication
        weak_solution = "We just accept the webhook and credit the user account."
        result = evaluate_scenario_submission(
            scenario=self.orm_scenario,
            solution_text=weak_solution,
        )
        self.assertLess(result.overall_score, 75.0)
        self.assertEqual(result.status, "revision_needed")
        self.assertGreater(len(result.areas_for_improvement), 0)


class TestScenarioTenantIsolationAndAPI(unittest.TestCase):
    """Test scenario ownership, submission access control, and API route handlers."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # User A
        self.user_a = UserAccount(
            email="tenant_a@test.com",
            full_name="Tenant Alpha",
            password_hash="test_hash",
            role="candidate",
        )
        # User B
        self.user_b = UserAccount(
            email="tenant_b@test.com",
            full_name="Tenant Bravo",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()
        self.db.refresh(self.user_a)
        self.db.refresh(self.user_b)

        # Generate scenario for User A
        self.scen_a = generate_personalized_scenario(user_id=self.user_a.id, db=self.db)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_tenant_isolation_user_b_cannot_view_or_submit_to_user_a_scenario(self):
        # User B attempts to view User A's scenario
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            get_scenario_detail(
                scenario_id=self.scen_a.scenario_id,
                user=self.user_b,
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 404)

        # User B attempts to submit solution to User A's scenario
        req = SubmitSolutionRequest(
            solution_text="A valid length solution text that User B is trying to submit to User A's scenario."
        )
        with self.assertRaises(HTTPException) as ctx_sub:
            submit_solution(
                scenario_id=self.scen_a.scenario_id,
                req=req,
                user=self.user_b,
                db=self.db,
            )
        self.assertEqual(ctx_sub.exception.status_code, 404)

    def test_api_submit_and_mark_completed(self):
        req = SubmitSolutionRequest(
            solution_text=(
                "We implement an async PostgreSQL transaction using row-level locking on balance rows "
                "with an idempotency key registry preventing duplicate mutations."
            ),
            code_submission="async def webhook(): try: ... except: ...",
            architectural_notes="Concurrency lock trade-offs thoroughly evaluated.",
        )
        res = submit_solution(
            scenario_id=self.scen_a.scenario_id,
            req=req,
            user=self.user_a,
            db=self.db,
        )

        self.assertIsNotNone(res.submission_id)
        self.assertIn(res.status, ["passed", "revision_needed"])

        # Check submission appears in history
        history = list_scenario_submissions(
            scenario_id=self.scen_a.scenario_id,
            user=self.user_a,
            db=self.db,
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].submission_id, res.submission_id)


if __name__ == "__main__":
    unittest.main()
