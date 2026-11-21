"""
Agent Orchestration API Router (Phase 7)
========================================
Endpoints for coordinating multi-agent workflows, monitoring, and agent discovery:
1. `GET /registry`: Lists all 6 registered platform agents and their execution contracts.
2. `POST /workflows/interview-feedback`: Runs interview feedback & adaptive competency loop.
3. `POST /workflows/scenario-evaluation`: Runs scenario grading & competency update loop.
4. `POST /workflows/diagnostic-onboarding`: Runs profile creation & roadmap initialization loop.
5. `POST /workflows/project-mentor`: Runs project mentorship & competency update loop.
6. `GET /metrics`: Aggregated AI execution metrics, latency, token usage, and cost tracking.
7. `GET /workflows/{workflow_id}`: Inspects execution status of an asynchronous/staged workflow run.
"""

from __future__ import annotations

import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user_from_token
from app.db_models import UserAccount, AgentWorkflowRun
from app.core.agent_registry import AgentRegistry
from app.services.orchestration_service import (
    run_interview_feedback_workflow,
    run_scenario_evaluation_workflow,
    run_diagnostic_onboarding_workflow,
    run_project_mentorship_workflow,
    get_orchestration_monitoring_metrics,
)

router = APIRouter()


# ------------------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------------------

class InterviewFeedbackWorkflowRequest(BaseModel):
    interview_id: str = Field(..., min_length=3)
    candidate_answer: str = Field(..., min_length=2, max_length=10000)
    turn_index: int = Field(1, ge=1)
    is_final: bool = False


class ScenarioEvaluationWorkflowRequest(BaseModel):
    scenario_id: str = Field(..., min_length=3)
    solution_text: str = Field(..., min_length=5, max_length=15000)
    code_submission: Optional[str] = Field(None, max_length=30000)


class DiagnosticOnboardingWorkflowRequest(BaseModel):
    target_role: str = Field("Backend Engineer (Python / Cloud)", min_length=2, max_length=255)
    target_level: str = Field("Mid-Level", min_length=2, max_length=50)
    skills: List[str] = Field(default_factory=lambda: ["Python Architecture", "PostgreSQL & Concurrency"])


class ProjectMentorshipWorkflowRequest(BaseModel):
    project_id: str = Field(..., min_length=3)
    stage: str = Field("architecture", pattern=r"^(planning|requirements|architecture|debugging|design_review|presentation_prep)$")
    user_query: str = Field(..., min_length=5, max_length=5000)


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------

@router.get("/registry", summary="List Agent Registry Catalog", tags=["Agent Orchestration (Phase 7)"])
def list_agent_registry():
    """Returns the central agent catalog, execution contracts, context scopes, and boundaries."""
    return AgentRegistry.list_agents()


@router.post("/workflows/interview-feedback", summary="Run Interview Feedback & Adaptive Competency Workflow", tags=["Agent Orchestration (Phase 7)"])
def trigger_interview_feedback_workflow(
    req: InterviewFeedbackWorkflowRequest,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Coordinates Agent 5 (Interview Mentor) -> Agent 2 (Adaptive Roadmap) -> Agent 6 (Competency Intelligence).
    """
    try:
        return run_interview_feedback_workflow(
            user_id=user.id,
            interview_id=req.interview_id,
            candidate_answer=req.candidate_answer,
            turn_index=req.turn_index,
            is_final=req.is_final,
            db=db,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Interview feedback workflow failed: {str(exc)}",
        )


@router.post("/workflows/scenario-evaluation", summary="Run Scenario Submission & Competency Update Workflow", tags=["Agent Orchestration (Phase 7)"])
def trigger_scenario_evaluation_workflow(
    req: ScenarioEvaluationWorkflowRequest,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Coordinates Agent 4 (Scenario Gen) -> Skill Analytics -> Agent 6 (Competency Intelligence).
    """
    try:
        return run_scenario_evaluation_workflow(
            user_id=user.id,
            scenario_id=req.scenario_id,
            solution_text=req.solution_text,
            code_submission=req.code_submission,
            db=db,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scenario evaluation workflow failed: {str(exc)}",
        )


@router.post("/workflows/diagnostic-onboarding", summary="Run Diagnostic Onboarding & Roadmap Initialization Workflow", tags=["Agent Orchestration (Phase 7)"])
def trigger_diagnostic_onboarding_workflow(
    req: DiagnosticOnboardingWorkflowRequest,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Coordinates Agent 1 (Learner Profiler) -> Agent 2 (Adaptive Learning Path).
    """
    try:
        return run_diagnostic_onboarding_workflow(
            user_id=user.id,
            target_role=req.target_role,
            target_level=req.target_level,
            skills=req.skills,
            db=db,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Onboarding workflow failed: {str(exc)}",
        )


@router.post("/workflows/project-mentor", summary="Run Project Mentorship & Competency Loop Workflow", tags=["Agent Orchestration (Phase 7)"])
def trigger_project_mentorship_workflow(
    req: ProjectMentorshipWorkflowRequest,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Coordinates Agent 5 (Project Mentor) -> Agent 6 (Competency Intelligence).
    """
    try:
        return run_project_mentorship_workflow(
            user_id=user.id,
            project_id=req.project_id,
            stage=req.stage,
            user_query=req.user_query,
            db=db,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Project mentorship workflow failed: {str(exc)}",
        )


@router.get("/metrics", summary="Get Orchestration & Agent Monitoring Metrics", tags=["Agent Orchestration (Phase 7)"])
def get_metrics_endpoint(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Returns agent execution metrics, latency, token estimation, and cost tracking."""
    return get_orchestration_monitoring_metrics(user_id=user.id, db=db)


@router.get("/workflows/{workflow_id}", summary="Inspect Workflow Execution Run", tags=["Agent Orchestration (Phase 7)"])
def get_workflow_run_endpoint(
    workflow_id: str,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Retrieves execution status, step count, and output summary for a specific workflow run."""
    run = db.query(AgentWorkflowRun).filter(
        AgentWorkflowRun.workflow_id == workflow_id,
        AgentWorkflowRun.user_id == user.id,
    ).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found.")

    return {
        "workflow_id": run.workflow_id,
        "workflow_type": run.workflow_type,
        "status": run.status,
        "steps_completed": run.steps_completed,
        "total_steps": run.total_steps,
        "result_summary": json.loads(run.result_summary) if run.result_summary else None,
        "error_details": run.error_details,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
