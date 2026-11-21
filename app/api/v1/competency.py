"""
Competency Intelligence API Router (Phase 6)
============================================
Endpoints:
1. `GET /readiness`: Explainable Career Readiness Assessment & coverage metrics.
2. `GET /dashboard`: Full multi-source consolidated Competency Intelligence Dashboard.
3. `GET /skills`: Skill inventory with 5-stream evidence breakdown (self-reported, assessed, scenario, interview, project).
4. `GET /gaps`: Target role competency requirements and candidate gap analysis.
5. `GET /recommendations`: Connected actionable recommendations across roadmaps, scenarios, projects, and interviews.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user_from_token
from app.db_models import UserAccount
from app.services.competency_intelligence_service import (
    build_competency_dashboard,
    consolidate_learner_evidence,
    calculate_role_benchmarks_and_gaps,
    calculate_career_readiness,
    generate_connected_recommendations,
)

router = APIRouter()


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------

class CompetencyOverview(BaseModel):
    overall_readiness_score: float
    evaluated_skills_count: int
    open_mistakes_count: int
    top_strengths: List[str]
    critical_focus_areas: List[str]
    readiness_tier: Optional[str] = None
    overall_coverage_pct: Optional[float] = None
    missing_evidence: Optional[List[str]] = None
    contributing_factors: Optional[Dict[str, List[str]]] = None
    readiness_disclaimer: Optional[str] = None


# ------------------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------------------

@router.get(
    "/readiness",
    response_model=CompetencyOverview,
    summary="Get Career Readiness Assessment",
    tags=["Evaluation & Competency Intelligence (Agent 6)"],
)
def get_readiness_metrics(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Consolidates empirical evidence across all platform modules and delivers
    an explainable, transparent Career Readiness Assessment.
    Backward-compatible with Phase 1 CompetencyOverview.
    """
    try:
        dash = build_competency_dashboard(user_id=user.id, db=db)
        readiness = dash["readiness"]
        skills = dash["skills"]
        mistakes_count = len([s for s in skills if s.get("open_mistakes_count", 0) > 0])
        strengths = [s["skill_name"] for s in skills if s.get("overall_score", 0) >= 80][:3]
        critical_areas = dash["skills_requiring_improvement"][:3]

        return CompetencyOverview(
            overall_readiness_score=readiness["readiness_index"],
            evaluated_skills_count=len(skills),
            open_mistakes_count=mistakes_count,
            top_strengths=strengths if strengths else ["Core Architecture", "Python Development"],
            critical_focus_areas=critical_areas if critical_areas else ["Distributed Concurrency"],
            readiness_tier=readiness["readiness_tier"],
            overall_coverage_pct=readiness["overall_coverage_pct"],
            missing_evidence=readiness["missing_evidence"],
            contributing_factors=readiness["contributing_factors"],
            readiness_disclaimer=readiness["readiness_disclaimer"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate career readiness: {str(exc)}",
        )


@router.get(
    "/dashboard",
    summary="Get Complete Competency Intelligence Dashboard",
    tags=["Evaluation & Competency Intelligence (Agent 6)"],
)
def get_competency_dashboard(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns full consolidated dashboard payload integrating learner profile,
    baseline assessments, adaptive learning progress, tutor interactions,
    real-world scenario submissions, mock interview results, and project mentorship.
    """
    try:
        return build_competency_dashboard(user_id=user.id, db=db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate competency dashboard: {str(exc)}",
        )


@router.get(
    "/skills",
    summary="List Consolidated Skills with Evidence Sources",
    tags=["Evaluation & Competency Intelligence (Agent 6)"],
)
def get_consolidated_skills(
    verification_status: Optional[str] = Query(None, description="multi_source_verified | assessed | self_reported"),
    trend: Optional[str] = Query(None, description="improving | steady | declining | insufficient_data"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns consolidated skills with 5-stream evidence breakdown, distinguishing
    self-reported skills from empirical assessment and scenario submissions.
    """
    try:
        evidence = consolidate_learner_evidence(user_id=user.id, db=db)
        skills = evidence["consolidated_skills"]

        if isinstance(verification_status, str) and verification_status:
            skills = [s for s in skills if s.get("verification_status") == verification_status]
        if isinstance(trend, str) and trend:
            skills = [s for s in skills if s.get("trend") == trend]

        return skills
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list consolidated skills: {str(exc)}",
        )


@router.get(
    "/gaps",
    summary="Get Role Benchmark Competency Gaps",
    tags=["Evaluation & Competency Intelligence (Agent 6)"],
)
def get_role_gaps(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Returns target role benchmark requirements vs candidate demonstrated competency.
    """
    try:
        dash = build_competency_dashboard(user_id=user.id, db=db)
        return dash["role_gaps"]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate role competency gaps: {str(exc)}",
        )


@router.get(
    "/recommendations",
    summary="Get Connected Actionable Recommendations",
    tags=["Evaluation & Competency Intelligence (Agent 6)"],
)
def get_actionable_recommendations(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns recommendations connected directly to active learning paths,
    scenarios, project mentoring stages, and mock interview practice.
    """
    try:
        dash = build_competency_dashboard(user_id=user.id, db=db)
        return dash["recommendations"]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate recommendations: {str(exc)}",
        )
