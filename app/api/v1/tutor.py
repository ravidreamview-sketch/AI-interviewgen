"""
AI Tutor Agent API Router (Phase 3)
===================================
Provides endpoints for:
1. Interactive context-aware Socratic tutoring queries (`POST /query`).
2. Conversation session history and turn retrieval (`GET /sessions`, `GET /sessions/{session_id}/messages`).
3. Guided pedagogical strategies (explain, demonstrate, hint, challenge, solution).
4. Coding assistance and error analysis (static review without untrusted code execution).
5. Strict prompt injection and tenant isolation boundaries.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user_from_token
from app.db_models import UserAccount, TutorSession, TutorMessage
from app.services.ai_tutor_service import execute_tutor_interaction

router = APIRouter()


# ==============================================================================
# SCHEMAS
# ==============================================================================

class TutorQueryRequest(BaseModel):
    concept: str = Field(..., min_length=2, max_length=150, description="Target technical concept e.g. 'Asyncio Event Loop'")
    query: str = Field(..., min_length=2, max_length=2000, description="Candidate question or inquiry")
    code_context: Optional[str] = Field(None, max_length=5000, description="Optional code snippet for review or debugging")
    session_id: Optional[str] = Field(None, description="Optional existing session ID to continue dialogue")
    activity_id: Optional[str] = Field(None, description="Optional associated roadmap activity ID")
    roadmap_id: Optional[str] = Field(None, description="Optional associated adaptive roadmap ID")
    teaching_mode: str = Field("explain", pattern=r"^(explain|demonstrate|hint|challenge|solution)$")
    complexity_level: str = Field("standard", pattern=r"^(simple|standard|deep_dive)$")


class TutorResponseOut(BaseModel):
    session_id: str
    concept: str
    teaching_mode: str
    complexity_level: str
    message: str
    pedagogical_intent: str
    activity_id: Optional[str] = None
    created_at: str


class TutorMessageItemOut(BaseModel):
    id: int
    role: str
    content: str
    code_snippet: Optional[str] = None
    pedagogical_intent: Optional[str] = None
    created_at: str


class TutorSessionItemOut(BaseModel):
    session_id: str
    concept: str
    teaching_mode: str
    complexity_level: str
    activity_id: Optional[str] = None
    roadmap_id: Optional[str] = None
    title: Optional[str] = None
    message_count: int
    created_at: str
    updated_at: str


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.post("/query", response_model=TutorResponseOut, summary="Submit Socratic query to AI Tutor")
def query_ai_tutor(
    req: TutorQueryRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Interacts with the AI Tutor Agent using context-aware Socratic mentoring.
    Incorporates candidate profile, active roadmap activity, and mistakes ledger.
    Strictly forbids untrusted code execution.
    """
    try:
        result = execute_tutor_interaction(
            user=user,
            db=db,
            concept=req.concept,
            query=req.query,
            session_id=req.session_id,
            activity_id=req.activity_id,
            roadmap_id=req.roadmap_id,
            code_context=req.code_context,
            teaching_mode=req.teaching_mode,
            complexity_level=req.complexity_level,
        )
        return TutorResponseOut(**result)
    except ValueError as e:
        msg = str(e)
        if "Rate limit" in msg:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get("/sessions", response_model=List[TutorSessionItemOut], summary="List candidate tutor sessions")
def list_tutor_sessions(
    activity_id: Optional[str] = Query(None, description="Filter by activity ID"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Returns all active and past tutoring dialogue sessions for the authenticated learner."""
    query = db.query(TutorSession).filter(TutorSession.user_id == user.id)
    if isinstance(activity_id, str) and activity_id:
        query = query.filter(TutorSession.activity_id == activity_id)

    sessions = query.order_by(TutorSession.updated_at.desc()).all()
    results = []
    for s in sessions:
        msg_count = db.query(TutorMessage).filter(TutorMessage.session_id == s.id).count()
        results.append(
            TutorSessionItemOut(
                session_id=s.session_id,
                concept=s.concept,
                teaching_mode=s.teaching_mode,
                complexity_level=s.complexity_level,
                activity_id=s.activity_id,
                roadmap_id=s.roadmap_id,
                title=s.title,
                message_count=msg_count,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
            )
        )
    return results


@router.get("/sessions/{session_id}/messages", response_model=List[TutorMessageItemOut], summary="Retrieve session message history")
def get_session_messages(
    session_id: str,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Fetches chronological message history for a specific tutoring session.
    Strictly verifies ownership to prevent cross-tenant data leaks.
    """
    session = db.query(TutorSession).filter(
        TutorSession.session_id == session_id,
        TutorSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tutoring session not found or access denied.")

    messages = db.query(TutorMessage).filter(
        TutorMessage.session_id == session.id
    ).order_by(TutorMessage.created_at.asc()).all()

    return [
        TutorMessageItemOut(
            id=m.id,
            role=m.role,
            content=m.content,
            code_snippet=m.code_snippet,
            pedagogical_intent=m.pedagogical_intent,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.delete("/sessions/{session_id}", summary="Delete a tutoring dialogue session")
def delete_tutor_session(
    session_id: str,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Deletes a tutoring conversation session and associated turns."""
    session = db.query(TutorSession).filter(
        TutorSession.session_id == session_id,
        TutorSession.user_id == user.id
    ).first()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tutoring session not found.")

    db.delete(session)
    db.commit()
    return {"success": True, "message": f"Tutor session '{session_id}' successfully removed."}
