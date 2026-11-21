"""
Real-World Scenarios API Router (Phase 4)
=========================================
Provides endpoints for:
1. Scenario Discovery (`GET /list`).
2. Scenario Detail View (`GET /{scenario_id}`).
3. Generating personalized scenarios (`POST /generate`).
4. Submitting solutions for automated rubric evaluation (`POST /{scenario_id}/submit`).
5. Retrieving past submission evaluations (`GET /{scenario_id}/submissions`).
6. Enforcing ownership boundaries and zero untrusted code execution.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user_from_token
from app.db_models import (
    UserAccount,
    RealWorldScenario,
    ScenarioSubmissionRecord,
)
from app.services.scenario_generation_service import (
    ScenarioData,
    SubmissionEvaluationResult,
    generate_personalized_scenario,
    evaluate_scenario_submission,
)

router = APIRouter()


# ==============================================================================
# SCHEMAS
# ==============================================================================

class GenerateScenarioRequest(BaseModel):
    category: Optional[str] = Field(None, pattern=r"^(technical_problem|coding_challenge|debugging_scenario|api_challenge|system_design|problem_solving|project_task)$")
    difficulty: Optional[str] = Field(None, pattern=r"^(Beginner|Intermediate|Advanced|Expert)$")
    target_role: Optional[str] = Field(None, min_length=2, max_length=255)


class ScenarioDetailOut(BaseModel):
    scenario_id: str
    title: str
    category: str
    domain: str
    target_role: str
    difficulty: str
    difficulty_level: int
    context: str
    problem_statement: str
    required_skills: List[str]
    objectives: List[str]
    instructions: List[str]
    constraints: List[str]
    deliverables: List[str]
    rubric: Dict[str, Any]
    success_criteria: List[str]
    hints: List[str]
    is_completed: bool
    created_at: str


class SubmitSolutionRequest(BaseModel):
    solution_text: str = Field(..., min_length=20, max_length=10000, description="Candidate solution write-up and explanation")
    code_submission: Optional[str] = Field(None, max_length=20000, description="Optional code snippet or implementation")
    architectural_notes: Optional[str] = Field(None, max_length=5000, description="Optional architectural decisions or trade-off notes")


class SubmissionEvaluationOut(BaseModel):
    submission_id: str
    scenario_id: str
    status: str
    overall_score: float
    dimension_scores: Dict[str, float]
    strengths: List[str]
    areas_for_improvement: List[str]
    evidence: str
    feedback: str
    recommended_next_steps: List[str]
    evaluation_disclaimer: str
    evaluated_at: str


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.get("/list", response_model=List[ScenarioDetailOut], summary="List real-world scenarios")
def list_scenarios(
    category: Optional[str] = Query(None, description="Filter by category"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Returns the learner's available practical challenges.
    Auto-generates initial scenarios if the learner has none yet.
    """
    query = db.query(RealWorldScenario).filter(RealWorldScenario.user_id == user.id)
    if isinstance(category, str) and category:
        query = query.filter(RealWorldScenario.category == category)

    scenarios = query.order_by(RealWorldScenario.created_at.desc()).all()

    if not scenarios:
        # Auto-generate initial scenario for candidate
        init_scen = generate_personalized_scenario(user_id=user.id, db=db)
        scenarios = db.query(RealWorldScenario).filter(RealWorldScenario.user_id == user.id).all()

    results = []
    for s in scenarios:
        results.append(
            ScenarioDetailOut(
                scenario_id=s.scenario_id,
                title=s.title,
                category=s.category,
                domain=s.domain,
                target_role=s.target_role,
                difficulty=s.difficulty,
                difficulty_level=s.difficulty_level,
                context=s.context,
                problem_statement=s.problem_statement,
                required_skills=json.loads(s.required_skills) if s.required_skills else [],
                objectives=json.loads(s.objectives) if s.objectives else [],
                instructions=json.loads(s.instructions) if s.instructions else [],
                constraints=json.loads(s.constraints) if s.constraints else [],
                deliverables=json.loads(s.deliverables) if s.deliverables else [],
                rubric=json.loads(s.rubric) if s.rubric else {},
                success_criteria=json.loads(s.success_criteria) if s.success_criteria else [],
                hints=json.loads(s.hints) if s.hints else [],
                is_completed=s.is_completed,
                created_at=s.created_at.isoformat(),
            )
        )
    return results


@router.post("/generate", response_model=ScenarioDetailOut, summary="Generate personalized real-world challenge")
def generate_scenario_endpoint(
    req: GenerateScenarioRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Generates a fresh real-world scenario tailored to candidate role and competency gaps."""
    scenario_data = generate_personalized_scenario(
        user_id=user.id,
        db=db,
        category=req.category,
        difficulty=req.difficulty,
        target_role=req.target_role,
    )
    s = db.query(RealWorldScenario).filter(RealWorldScenario.scenario_id == scenario_data.scenario_id).first()
    return ScenarioDetailOut(
        scenario_id=s.scenario_id,
        title=s.title,
        category=s.category,
        domain=s.domain,
        target_role=s.target_role,
        difficulty=s.difficulty,
        difficulty_level=s.difficulty_level,
        context=s.context,
        problem_statement=s.problem_statement,
        required_skills=json.loads(s.required_skills),
        objectives=json.loads(s.objectives),
        instructions=json.loads(s.instructions),
        constraints=json.loads(s.constraints),
        deliverables=json.loads(s.deliverables),
        rubric=json.loads(s.rubric),
        success_criteria=json.loads(s.success_criteria),
        hints=json.loads(s.hints) if s.hints else [],
        is_completed=s.is_completed,
        created_at=s.created_at.isoformat(),
    )


@router.get("/{scenario_id}", response_model=ScenarioDetailOut, summary="Get scenario details")
def get_scenario_detail(
    scenario_id: str,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Fetches details of a specific real-world challenge (enforces ownership)."""
    s = db.query(RealWorldScenario).filter(
        RealWorldScenario.scenario_id == scenario_id,
        RealWorldScenario.user_id == user.id
    ).first()

    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found or access denied.")

    return ScenarioDetailOut(
        scenario_id=s.scenario_id,
        title=s.title,
        category=s.category,
        domain=s.domain,
        target_role=s.target_role,
        difficulty=s.difficulty,
        difficulty_level=s.difficulty_level,
        context=s.context,
        problem_statement=s.problem_statement,
        required_skills=json.loads(s.required_skills),
        objectives=json.loads(s.objectives),
        instructions=json.loads(s.instructions),
        constraints=json.loads(s.constraints),
        deliverables=json.loads(s.deliverables),
        rubric=json.loads(s.rubric),
        success_criteria=json.loads(s.success_criteria),
        hints=json.loads(s.hints) if s.hints else [],
        is_completed=s.is_completed,
        created_at=s.created_at.isoformat(),
    )


@router.post("/{scenario_id}/submit", response_model=SubmissionEvaluationOut, summary="Submit solution for evaluation")
def submit_solution(
    scenario_id: str,
    req: SubmitSolutionRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Submits a candidate solution for automated rubric evaluation.
    Evaluates statically against tailored rubric dimensions without executing code.
    """
    scenario = db.query(RealWorldScenario).filter(
        RealWorldScenario.scenario_id == scenario_id,
        RealWorldScenario.user_id == user.id
    ).first()

    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found or access denied.")

    # Evaluate submission
    eval_result = evaluate_scenario_submission(
        scenario=scenario,
        solution_text=req.solution_text,
        code_submission=req.code_submission,
        architectural_notes=req.architectural_notes,
    )

    submission_id = f"sub_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # Persist submission record
    sub_record = ScenarioSubmissionRecord(
        submission_id=submission_id,
        scenario_id=scenario.scenario_id,
        user_id=user.id,
        solution_text=req.solution_text,
        code_submission=req.code_submission,
        architectural_notes=req.architectural_notes,
        status=eval_result.status,
        overall_score=eval_result.overall_score,
        dimension_scores=json.dumps(eval_result.dimension_scores),
        strengths=json.dumps(eval_result.strengths),
        areas_for_improvement=json.dumps(eval_result.areas_for_improvement),
        evidence=eval_result.evidence,
        feedback=eval_result.feedback,
        recommended_next_steps=json.dumps(eval_result.recommended_next_steps),
        evaluation_disclaimer=eval_result.evaluation_disclaimer,
        evaluated_at=now,
        created_at=now,
    )
    db.add(sub_record)

    if eval_result.status == "passed":
        scenario.is_completed = True
        scenario.updated_at = now

    db.commit()
    db.refresh(sub_record)

    return SubmissionEvaluationOut(
        submission_id=submission_id,
        scenario_id=scenario.scenario_id,
        status=eval_result.status,
        overall_score=eval_result.overall_score,
        dimension_scores=eval_result.dimension_scores,
        strengths=eval_result.strengths,
        areas_for_improvement=eval_result.areas_for_improvement,
        evidence=eval_result.evidence,
        feedback=eval_result.feedback,
        recommended_next_steps=eval_result.recommended_next_steps,
        evaluation_disclaimer=eval_result.evaluation_disclaimer,
        evaluated_at=now.isoformat(),
    )


@router.get("/{scenario_id}/submissions", response_model=List[SubmissionEvaluationOut], summary="List past submissions")
def list_scenario_submissions(
    scenario_id: str,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Returns all past submissions and evaluations for the specified scenario."""
    # Ownership check on parent scenario
    scenario = db.query(RealWorldScenario).filter(
        RealWorldScenario.scenario_id == scenario_id,
        RealWorldScenario.user_id == user.id
    ).first()

    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found or access denied.")

    subs = db.query(ScenarioSubmissionRecord).filter(
        ScenarioSubmissionRecord.scenario_id == scenario_id,
        ScenarioSubmissionRecord.user_id == user.id
    ).order_by(ScenarioSubmissionRecord.created_at.desc()).all()

    results = []
    for s in subs:
        results.append(
            SubmissionEvaluationOut(
                submission_id=s.submission_id,
                scenario_id=s.scenario_id,
                status=s.status,
                overall_score=s.overall_score or 0.0,
                dimension_scores=json.loads(s.dimension_scores) if s.dimension_scores else {},
                strengths=json.loads(s.strengths) if s.strengths else [],
                areas_for_improvement=json.loads(s.areas_for_improvement) if s.areas_for_improvement else [],
                evidence=s.evidence or "",
                feedback=s.feedback or "",
                recommended_next_steps=json.loads(s.recommended_next_steps) if s.recommended_next_steps else [],
                evaluation_disclaimer=s.evaluation_disclaimer or "",
                evaluated_at=s.evaluated_at.isoformat() if s.evaluated_at else "",
            )
        )
    return results
