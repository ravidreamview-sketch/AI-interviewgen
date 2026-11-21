"""
Adaptive Learning Paths API Router (Phase 2)
============================================
Provides endpoints for:
1. Fetching active personalized learning roadmap (`GET /active`).
2. Generating a fresh personalized roadmap based on profile & skill gaps (`POST /generate`).
3. Continuous adaptation based on recent assessments and mistakes (`POST /adapt`).
4. Activity progress tracking (`POST /activities/{activity_id}/progress`).
5. Real-time next activity recommendations (`GET /next-recommendation`).
6. Adaptation audit history (`GET /history`).
"""

from __future__ import annotations

import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user_from_token
from app.db_models import UserAccount, AdaptiveRoadmap
from app.services.adaptive_path_service import (
    AdaptiveRoadmapData,
    generate_adaptive_learning_path,
    update_learning_path_with_evidence,
    track_activity_progress,
    get_next_recommended_activity,
)

router = APIRouter()


# ==============================================================================
# SCHEMAS
# ==============================================================================

class GeneratePathRequest(BaseModel):
    target_role: Optional[str] = Field(None, min_length=2, max_length=255)
    focus_areas: Optional[List[str]] = None


class AdaptPathRequest(BaseModel):
    roadmap_id: Optional[str] = None
    trigger_reason: str = Field("Manual Learner Calibration", min_length=2, max_length=255)


class UpdateActivityProgressRequest(BaseModel):
    roadmap_id: str
    status: str = Field(..., pattern=r"^(in_progress|completed|pending)$")
    score: Optional[float] = Field(None, ge=0.0, le=100.0)


class ActivityProgressResponse(BaseModel):
    success: bool
    activity_id: str
    new_status: str
    module_progress: float
    module_status: str
    roadmap_progress: float
    completed_count: int
    total_count: int


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.get("/active", response_model=AdaptiveRoadmapData, summary="Retrieve active adaptive learning roadmap")
def get_active_roadmap(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Returns the currently active, personalized learning roadmap for the authenticated learner.
    If no active roadmap exists, one is synthesized automatically from the learner profile & skill gaps.
    """
    record = db.query(AdaptiveRoadmap).filter(
        AdaptiveRoadmap.user_id == user.id,
        AdaptiveRoadmap.status == "active"
    ).order_by(AdaptiveRoadmap.created_at.desc()).first()

    if not record:
        return generate_adaptive_learning_path(user_id=user.id, db=db)

    try:
        data = json.loads(record.roadmap_data)
        return AdaptiveRoadmapData.model_validate(data)
    except Exception as e:
        # If stored JSON is somehow corrupted, regenerate clean roadmap
        return generate_adaptive_learning_path(user_id=user.id, db=db)


@router.post("/generate", response_model=AdaptiveRoadmapData, summary="Generate fresh personalized learning path")
def generate_roadmap_endpoint(
    req: GeneratePathRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Generates a new personalized roadmap calibrated to the candidate's target role,
    assessed competency gaps, and experience level.
    """
    return generate_adaptive_learning_path(
        user_id=user.id,
        db=db,
        target_role=req.target_role,
        personalization_context={"focus_areas": req.focus_areas} if req.focus_areas else None,
    )


@router.post("/adapt", response_model=AdaptiveRoadmapData, summary="Adapt roadmap with new assessment evidence")
def adapt_roadmap_endpoint(
    req: AdaptPathRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Recalibrates the candidate's learning roadmap using latest assessment scores and mistakes.
    STRICT GUARANTEE: Completed learning activities and milestones are preserved and never erased.
    """
    return update_learning_path_with_evidence(
        user_id=user.id,
        db=db,
        roadmap_id=req.roadmap_id,
        trigger_reason=req.trigger_reason,
    )


@router.post("/activities/{activity_id}/progress", response_model=ActivityProgressResponse, summary="Update activity progress")
def update_activity_progress_endpoint(
    activity_id: str,
    req: UpdateActivityProgressRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Records progress on a learning activity (in_progress, completed).
    Automatically recalculates module progress and unlocks dependent modules upon prerequisite satisfaction.
    """
    try:
        res = track_activity_progress(
            roadmap_id=req.roadmap_id,
            activity_id=activity_id,
            status=req.status,
            user_id=user.id,
            db=db,
            score=req.score,
        )
        return ActivityProgressResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/next-recommendation", summary="Get immediate next recommended learning action")
def get_next_recommendation_endpoint(
    roadmap_id: Optional[str] = Query(None, description="Optional roadmap ID"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Delivers the immediate next high-impact learning activity based on current module progress,
    along with the upcoming activity queue.
    """
    target_id = roadmap_id if isinstance(roadmap_id, str) else None
    if not target_id:
        active = db.query(AdaptiveRoadmap).filter(
            AdaptiveRoadmap.user_id == user.id,
            AdaptiveRoadmap.status == "active"
        ).order_by(AdaptiveRoadmap.created_at.desc()).first()
        if not active:
            # Generate one if none exists
            gen = generate_adaptive_learning_path(user_id=user.id, db=db)
            target_id = gen.roadmap_id
        else:
            target_id = active.roadmap_id

    return get_next_recommended_activity(roadmap_id=target_id, user_id=user.id, db=db)


@router.get("/history", summary="Roadmap adaptation history logs")
def get_roadmap_history_endpoint(
    roadmap_id: Optional[str] = Query(None, description="Optional specific roadmap ID"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Returns the continuous adaptation audit logs for the learner's roadmaps."""
    query = db.query(AdaptiveRoadmap).filter(AdaptiveRoadmap.user_id == user.id)
    if isinstance(roadmap_id, str) and roadmap_id:
        query = query.filter(AdaptiveRoadmap.roadmap_id == roadmap_id)
    records = query.order_by(AdaptiveRoadmap.created_at.desc()).all()

    history_list = []
    for r in records:
        logs = []
        if r.adaptation_history:
            try:
                logs = json.loads(r.adaptation_history)
            except Exception:
                pass
        history_list.append({
            "roadmap_id": r.roadmap_id,
            "title": r.title,
            "target_role": r.target_role,
            "status": r.status,
            "overall_progress": r.overall_progress,
            "completed_activities_count": r.completed_activities_count,
            "total_activities_count": r.total_activities_count,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
            "adaptations": logs,
        })

    return history_list
