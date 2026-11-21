"""
AI Interview & Project Mentor API Router (Phase 5)
==================================================
Provides endpoints for:
1. Context-Aware Mock Interview Initialization (`POST /start`).
2. Adaptive Turn Evaluation & Follow-up Generation (`POST /{interview_id}/turn`).
3. Candidate Interview History & Scorecards (`GET /history`, `GET /{interview_id}/scorecard`).
4. Learner Project Registration (`POST /projects`, `GET /projects`).
5. AI Project Mentoring Interactions across 6 stages (`POST /projects/{project_id}/mentor`).
6. Project Mentoring Transcript History (`GET /projects/{project_id}/history`).
7. Strict Session and Project Ownership boundaries.
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
    MockInterview,
    LearnerProject,
    ProjectMentorshipTurn,
)
from app.services.interview_mentor_service import (
    start_context_aware_interview,
    process_context_aware_interview_turn,
    mentor_project_interaction,
)

router = APIRouter()


# ==============================================================================
# SCHEMAS
# ==============================================================================

class StartInterviewRequest(BaseModel):
    role: Optional[str] = Field(None, min_length=2, max_length=100)
    persona: str = Field("alex", pattern=r"^(alex|elena|marcus)$")
    interview_type: str = Field(
        "technical",
        pattern=r"^(technical|behavioral|hr|coding|role_specific|project_based|system_design)$"
    )
    mode: str = Field("voice", pattern=r"^(voice|video_voice|text)$")
    question_count: int = Field(5, ge=1, le=20)
    custom_question: Optional[str] = Field(None, max_length=1000)


class InterviewTurnRequest(BaseModel):
    turn_index: int = Field(..., ge=1)
    candidate_answer: str = Field(..., min_length=2, max_length=10000)
    is_final: bool = False


class ProjectCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    target_role: str = Field(..., min_length=2, max_length=255)
    domain: str = Field("Full-Stack Web Systems", max_length=100)
    description: str = Field(..., min_length=10, max_length=5000)
    architecture_overview: Optional[str] = Field(None, max_length=5000)
    tech_stack: List[str] = Field(..., min_items=1)


class ProjectMentorRequest(BaseModel):
    stage: str = Field(
        ...,
        pattern=r"^(planning|requirements|architecture|debugging|design_review|presentation_prep)$"
    )
    user_query: str = Field(..., min_length=5, max_length=3000)


class ProjectOut(BaseModel):
    project_id: str
    title: str
    target_role: str
    domain: str
    description: str
    architecture_overview: Optional[str] = None
    tech_stack: List[str]
    status: str
    created_at: str
    updated_at: str


class ProjectMentorshipTurnOut(BaseModel):
    id: int
    project_id: str
    mentorship_stage: str
    user_query: str
    mentor_guidance: str
    action_items: List[str]
    created_at: str


# ==============================================================================
# INTERVIEW ENGINE ENDPOINTS (REUSING EXISTING ENGINE)
# ==============================================================================

@router.post("/start", summary="Start context-aware mock interview")
def start_interview_endpoint(
    req: StartInterviewRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Initializes a new interactive interview session.
    Reuses existing interview_engine while seeding it with Phase 1 competency gaps,
    profile goals, and active learning curriculum focus.
    """
    try:
        return start_context_aware_interview(
            user_id=user.id,
            db=db,
            target_role=req.role,
            persona=req.persona,
            interview_type=req.interview_type,
            mode=req.mode,
            question_count=req.question_count,
            custom_question=req.custom_question,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{interview_id}/turn", summary="Process candidate answer turn")
def process_turn_endpoint(
    interview_id: str,
    req: InterviewTurnRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Evaluates candidate turn answer, checks STAR depth & accuracy, and branches to follow-up.
    Reuses existing interview_engine and maps outcomes to the 5-tier competency framework.
    """
    try:
        return process_context_aware_interview_turn(
            interview_id=interview_id,
            answer_text=req.candidate_answer,
            user_id=user.id,
            db=db,
            is_final=req.is_final,
            turn_index=req.turn_index,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/history", summary="List candidate mock interview history")
def list_interview_history(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Fetches candidate's mock interview history with scores and statuses."""
    interviews = db.query(MockInterview).filter(
        MockInterview.user_id == user.id
    ).order_by(MockInterview.created_at.desc()).all()

    return [
        {
            "interview_id": f"mock_{i.id}",
            "role": i.role,
            "company_target": i.company_target,
            "interviewer_persona": i.interviewer_persona,
            "score": i.score,
            "technical_accuracy": i.technical_accuracy,
            "communication_clarity": i.communication_clarity,
            "star_depth": i.star_depth,
            "status": i.status,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in interviews
    ]


@router.get("/{interview_id}/scorecard", summary="Retrieve final scorecard and transcript")
def get_interview_scorecard(
    interview_id: str,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Retrieves full transcript and final scorecard for a completed interview."""
    if not interview_id.startswith("mock_"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid interview ID format.")

    try:
        rec_id = int(interview_id.removeprefix("mock_"))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid interview ID.")

    interview = db.query(MockInterview).filter(
        MockInterview.id == rec_id,
        MockInterview.user_id == user.id
    ).first()

    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found or access denied.")

    history = []
    if interview.transcript:
        try:
            history = json.loads(interview.transcript)
        except Exception:
            pass

    return {
        "interview_id": interview_id,
        "role": interview.role,
        "persona": interview.interviewer_persona,
        "status": interview.status,
        "score": interview.score,
        "technical_accuracy": interview.technical_accuracy,
        "communication_clarity": interview.communication_clarity,
        "star_depth": interview.star_depth,
        "turns": history,
        "created_at": interview.created_at.isoformat() if interview.created_at else None,
    }


# ==============================================================================
# PROJECT MENTOR ENDPOINTS
# ==============================================================================

@router.post("/projects", response_model=ProjectOut, summary="Register project for mentoring")
def create_project(
    req: ProjectCreateRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Registers a learner portfolio project for AI technical mentoring."""
    project_id = f"proj_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    project = LearnerProject(
        project_id=project_id,
        user_id=user.id,
        title=req.title,
        target_role=req.target_role,
        domain=req.domain,
        description=req.description,
        architecture_overview=req.architecture_overview,
        tech_stack=json.dumps(req.tech_stack),
        status="planning",
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return ProjectOut(
        project_id=project.project_id,
        title=project.title,
        target_role=project.target_role,
        domain=project.domain,
        description=project.description,
        architecture_overview=project.architecture_overview,
        tech_stack=json.loads(project.tech_stack),
        status=project.status,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.get("/projects", response_model=List[ProjectOut], summary="List candidate projects")
def list_projects(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Lists all registered portfolio projects for the authenticated candidate."""
    projects = db.query(LearnerProject).filter(
        LearnerProject.user_id == user.id
    ).order_by(LearnerProject.updated_at.desc()).all()

    return [
        ProjectOut(
            project_id=p.project_id,
            title=p.title,
            target_role=p.target_role,
            domain=p.domain,
            description=p.description,
            architecture_overview=p.architecture_overview,
            tech_stack=json.loads(p.tech_stack) if p.tech_stack else [],
            status=p.status,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        )
        for p in projects
    ]


@router.post("/projects/{project_id}/mentor", summary="Request AI Project Mentorship guidance")
def mentor_project_endpoint(
    project_id: str,
    req: ProjectMentorRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Delivers Socratic technical mentorship for a project across 6 stages:
    planning, requirements, architecture, debugging, design_review, presentation_prep.
    Enforces ownership boundaries.
    """
    try:
        return mentor_project_interaction(
            user=user,
            db=db,
            project_id=project_id,
            stage=req.stage,
            user_query=req.user_query,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/projects/{project_id}/history", response_model=List[ProjectMentorshipTurnOut], summary="List mentorship turns")
def list_project_mentorship_history(
    project_id: str,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Fetches chronological mentorship transcript for a project."""
    # Ownership verification
    project = db.query(LearnerProject).filter(
        LearnerProject.project_id == project_id,
        LearnerProject.user_id == user.id
    ).first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found or access denied.")

    turns = db.query(ProjectMentorshipTurn).filter(
        ProjectMentorshipTurn.project_id == project_id,
        ProjectMentorshipTurn.user_id == user.id
    ).order_by(ProjectMentorshipTurn.created_at.asc()).all()

    return [
        ProjectMentorshipTurnOut(
            id=t.id,
            project_id=t.project_id,
            mentorship_stage=t.mentorship_stage,
            user_query=t.user_query,
            mentor_guidance=t.mentor_guidance,
            action_items=json.loads(t.action_items) if t.action_items else [],
            created_at=t.created_at.isoformat(),
        )
        for t in turns
    ]
