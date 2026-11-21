import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from app.api.v1.auth import get_current_user_from_token
from app.db_models import UserAccount
from app.matching_service import calculate_resume_jd_match
from app.models import ResumeJDMatchRequest, ResumeJDMatchResponse

router = APIRouter()


@router.post("/match", response_model=ResumeJDMatchResponse, tags=["Resumes & ATS Matching"])
def analyze_resume_jd_match(
    payload: ResumeJDMatchRequest,
    user: UserAccount = Depends(get_current_user_from_token)
):
    """
    Preserves verified match-v1.1.0 multi-dimensional scoring engine.
    Calculates weighted fit, critical gaps, and skill matrices with zero fabrication.
    """
    if not payload.resume_text or not payload.jd_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both resume_text and jd_text are required for match analysis"
        )

    result = calculate_resume_jd_match(
        jd_text=payload.jd_text,
        resume_text=payload.resume_text,
        target_role=payload.target_role,
        source_type=payload.source_type
    )

    scan_id = f"scan_{uuid.uuid4().hex[:16]}"
    target_role = payload.target_role or "Target Role"
    created_at = datetime.now(timezone.utc).isoformat()

    return ResumeJDMatchResponse(
        scan_id=scan_id,
        target_role=target_role,
        source_type=payload.source_type or "paste",
        created_at=created_at,
        **result.model_dump()
    )

