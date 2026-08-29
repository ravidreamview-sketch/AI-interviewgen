"""
Candidate Dashboard Aggregation Service (Phase 6A)

Provides real-time, deterministic performance metrics, streak tracking,
competency breakdowns, resume scan insights, and activity timelines
strictly isolated for the authenticated candidate.
"""

from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Set, Any
import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db_models import (
    UserAccount,
    InterviewHistory,
    MockInterview,
    ResumeScan,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
)
from app.models import (
    CandidateUserSummary,
    CandidateCompetencyScores,
    CandidateDashboardResumeSummary,
    CandidateRecommendedFocusItem,
    CandidateRecentActivityItem,
    CandidateDashboardResponse,
)

logger = logging.getLogger("ravi.dashboard")


# ==============================================================================
# DETERMINISTIC HELPER FUNCTIONS
# ==============================================================================

def parse_questions_count(questions_raw: Optional[str]) -> int:
    """
    Parses stored question representation (JSON array or newline-separated strings)
    and returns the integer count of questions.
    """
    if not questions_raw or not str(questions_raw).strip():
        return 0
    
    raw = str(questions_raw).strip()
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return len(parsed)
        except Exception:
            pass
            
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    return len(lines) if lines else 1


def calculate_streak(active_dates: Set[date], today: Optional[date] = None) -> int:
    """
    Calculates consecutive active days streak in UTC.
    Counts backwards from today (or yesterday if candidate has not been active yet today).
    Duplicate activities on the same day are naturally deduplicated by the set.
    """
    if not active_dates:
        return 0
    
    if today is None:
        today = datetime.now(timezone.utc).date()
        
    start_date = None
    if today in active_dates:
        start_date = today
    elif (today - timedelta(days=1)) in active_dates:
        start_date = today - timedelta(days=1)
    else:
        return 0
        
    streak = 0
    check_day = start_date
    while check_day in active_dates:
        streak += 1
        check_day = check_day - timedelta(days=1)
        
    return streak


def calculate_readiness(
    questions_count: int,
    mocks_count: int,
    avg_score: float,
    resume_score: Optional[float]
) -> int:
    """
    Calculates overall interview preparation readiness on a transparent 0-100 scale:
    - Practice Activity Factor (25%): Target of 30+ practiced questions
    - Mock Interview Factor (25%): Target of 3+ mock interviews
    - Average Evaluation Score Factor (30%): Evaluation & mock performance
    - Resume/JD Match Factor (20%): Latest resume match score (if available)

    If no activity exists (brand new candidate), returns 0.
    """
    if questions_count == 0 and mocks_count == 0 and avg_score == 0.0 and (resume_score is None or resume_score == 0.0):
        return 0

    practice_factor = min(100.0, (questions_count / 30.0) * 100.0)
    mock_factor = min(100.0, (mocks_count / 3.0) * 100.0)
    score_factor = avg_score if avg_score > 0 else (0.5 * practice_factor + 0.5 * mock_factor)

    if resume_score is not None and resume_score > 0:
        readiness = (
            0.25 * practice_factor +
            0.25 * mock_factor +
            0.30 * score_factor +
            0.20 * resume_score
        )
    else:
        # Re-distribute the 20% resume weight proportionally across the other three factors
        readiness = (
            (0.25 / 0.80) * practice_factor +
            (0.25 / 0.80) * mock_factor +
            (0.30 / 0.80) * score_factor
        )

    return max(0, min(100, int(round(readiness))))


def extract_competencies(
    skills_analytics: List[CandidateSkillAnalytics],
    mocks: List[MockInterview]
) -> CandidateCompetencyScores:
    """
    Extracts real competency scores mapped from skill analytics and mock sub-scores:
    - Technical Skills: Tech/coding skills & mock technical_accuracy
    - System / Architecture: Architecture/system design skills & confidence/architecture
    - Product Thinking: Product/UX/design/strategy skills & communication_clarity
    - Behavioral: Leadership/STAR/behavioral skills & star_depth
    """
    tech_scores: List[float] = []
    arch_scores: List[float] = []
    prod_scores: List[float] = []
    behav_scores: List[float] = []

    # Map from Skill Analytics
    for item in skills_analytics:
        skill_name = (item.skill or "").lower()
        score = float(item.score or 0.0)
        if not score:
            continue
            
        if any(k in skill_name for k in ["arch", "system", "distribut", "scalab", "cloud", "infra", "database", "sql"]):
            arch_scores.append(score)
        elif any(k in skill_name for k in ["product", "design", "ux", "ui", "research", "figma", "strategy", "roadmap"]):
            prod_scores.append(score)
        elif any(k in skill_name for k in ["behavior", "lead", "communicat", "team", "star", "conflict", "manag"]):
            behav_scores.append(score)
        else:
            tech_scores.append(score)

    # Map from Mock Interviews
    for m in mocks:
        if m.technical_accuracy and m.technical_accuracy > 0:
            tech_scores.append(float(m.technical_accuracy))
        if m.confidence_score and m.confidence_score > 0:
            arch_scores.append(float(m.confidence_score))
        if m.communication_clarity and m.communication_clarity > 0:
            prod_scores.append(float(m.communication_clarity))
        if m.star_depth and m.star_depth > 0:
            behav_scores.append(float(m.star_depth))

    def avg_or_none(scores: List[float]) -> Optional[float]:
        return round(sum(scores) / len(scores), 1) if scores else None

    return CandidateCompetencyScores(
        technical_skills=avg_or_none(tech_scores),
        system_architecture=avg_or_none(arch_scores),
        product_thinking=avg_or_none(prod_scores),
        behavioral=avg_or_none(behav_scores),
    )


def generate_recommended_focus(
    mistakes: List[CandidateMistakesLedger],
    skills: List[CandidateSkillAnalytics],
    latest_scan: Optional[ResumeScan]
) -> List[CandidateRecommendedFocusItem]:
    """
    Generates deterministic, prioritized recommendations without LLM overhead based on:
    1. Active critical/high severity mistakes
    2. Identified weaknesses or declining skill trends
    3. Critical gaps from the candidate's latest resume scan
    """
    recommendations: List[CandidateRecommendedFocusItem] = []
    seen_skills: Set[str] = set()

    # 1. Critical & High Mistakes
    for m in mistakes:
        if m.mistake_status != "resolved":
            skill_clean = (m.skill or "Core Competency").strip()
            if skill_clean.lower() not in seen_skills:
                seen_skills.add(skill_clean.lower())
                priority = "HIGH" if (m.severity or "").lower() in ["critical", "high"] else "MEDIUM"
                reason = m.recommendation or m.description or f"Weakness identified in {skill_clean} evaluation"
                recommendations.append(CandidateRecommendedFocusItem(
                    skill=skill_clean,
                    priority=priority,
                    reason=reason
                ))

    # 2. Latest Resume Scan Gaps
    if latest_scan:
        # Critical gaps
        crit_raw = latest_scan.critical_gaps or "[]"
        try:
            crit_list = json.loads(crit_raw) if crit_raw.startswith("[") else [g.strip() for g in crit_raw.split(",") if g.strip()]
        except Exception:
            crit_list = []
            
        for g in crit_list:
            if g and g.lower() not in seen_skills:
                seen_skills.add(g.lower())
                recommendations.append(CandidateRecommendedFocusItem(
                    skill=g,
                    priority="HIGH",
                    reason=f"Critical gap detected for target role {latest_scan.target_role}"
                ))

        # Skill gaps
        gap_raw = latest_scan.skill_gaps or "[]"
        try:
            gap_list = json.loads(gap_raw) if gap_raw.startswith("[") else [g.strip() for g in gap_raw.split(",") if g.strip()]
        except Exception:
            gap_list = []
            
        for g in gap_list:
            if g and g.lower() not in seen_skills:
                seen_skills.add(g.lower())
                recommendations.append(CandidateRecommendedFocusItem(
                    skill=g,
                    priority="MEDIUM",
                    reason=f"Skill gap identified in resume match against {latest_scan.target_role}"
                ))

    # 3. Weak Skill Analytics
    for s in skills:
        if s.weakness_status in ["identified", "practicing"] or (s.score and s.score < 75.0) or s.trend == "declining":
            skill_clean = (s.skill or "").strip()
            if skill_clean and skill_clean.lower() not in seen_skills:
                seen_skills.add(skill_clean.lower())
                priority = "HIGH" if s.score < 65.0 or s.trend == "declining" else "MEDIUM"
                recommendations.append(CandidateRecommendedFocusItem(
                    skill=skill_clean,
                    priority=priority,
                    reason=f"Current skill score {round(s.score, 1)}% indicates practice needed for target mastery"
                ))

    return recommendations[:5]


def get_recent_activity(user_id: int, db: Session, limit: int = 10) -> List[CandidateRecentActivityItem]:
    """
    Compiles chronological candidate timeline strictly scoped to user_id.
    Excludes private raw text; includes type, title, detail, score, and ISO timestamp.
    """
    activities: List[Dict[str, Any]] = []

    # 1. Resume Scans
    scans = (
        db.query(ResumeScan)
        .filter(ResumeScan.user_id == user_id)
        .order_by(desc(ResumeScan.created_at))
        .limit(limit)
        .all()
    )
    for s in scans:
        if s.created_at:
            activities.append({
                "type": "resume_match",
                "title": f"Resume Match ({s.target_role})",
                "detail": f"Matched with {s.target_role} — {s.match_confidence or 'MEDIUM'} fit",
                "score": round(float(s.overall_match_score or s.match_score or 0.0), 1),
                "created_at_dt": s.created_at,
                "created_at": s.created_at.isoformat()
            })

    # 2. Mock Interviews
    mocks = (
        db.query(MockInterview)
        .filter(MockInterview.user_id == user_id)
        .order_by(desc(MockInterview.created_at))
        .limit(limit)
        .all()
    )
    for m in mocks:
        if m.created_at:
            activities.append({
                "type": "mock_interview",
                "title": f"AI Mock Interview ({m.role})",
                "detail": f"{m.interviewer_persona or 'Technical Lead'} · {m.company_target or 'Target Tech'}",
                "score": round(float(m.score or 0.0), 1),
                "created_at_dt": m.created_at,
                "created_at": m.created_at.isoformat()
            })

    # 3. Question Practice Sessions
    history = (
        db.query(InterviewHistory)
        .filter(InterviewHistory.user_id == user_id)
        .order_by(desc(InterviewHistory.created_at))
        .limit(limit)
        .all()
    )
    for h in history:
        if h.created_at:
            q_count = parse_questions_count(h.questions)
            activities.append({
                "type": "question_practice",
                "title": f"Question Practice ({h.role})",
                "detail": f"{h.difficulty or 'Hard'} · {q_count} questions synthesized",
                "score": None,
                "created_at_dt": h.created_at,
                "created_at": h.created_at.isoformat()
            })

    # 4. Mistakes / Evaluations
    mistakes = (
        db.query(CandidateMistakesLedger)
        .filter(CandidateMistakesLedger.user_id == user_id)
        .order_by(desc(CandidateMistakesLedger.created_at))
        .limit(limit)
        .all()
    )
    for mk in mistakes:
        if mk.created_at:
            activities.append({
                "type": "evaluation",
                "title": f"Answer Evaluated ({mk.skill})",
                "detail": mk.description[:90] + ("..." if len(mk.description) > 90 else "") if mk.description else "Answer evaluation recorded",
                "score": None,
                "created_at_dt": mk.created_at,
                "created_at": mk.created_at.isoformat()
            })

    # Sort merged activities descending by timestamp
    activities.sort(key=lambda x: x["created_at_dt"], reverse=True)
    
    return [
        CandidateRecentActivityItem(
            type=item["type"],
            title=item["title"],
            detail=item.get("detail"),
            score=item.get("score"),
            created_at=item["created_at"]
        )
        for item in activities[:limit]
    ]


# ==============================================================================
# MAIN DASHBOARD AGGREGATOR
# ==============================================================================

def compute_candidate_dashboard(user: UserAccount, db: Session) -> CandidateDashboardResponse:
    """
    Computes complete, real-time candidate dashboard payload.
    Guarantees strict tenant isolation: all DB queries filter on user.id.
    """
    user_id = user.id

    # 1. Interview History & Questions Practiced
    user_history = db.query(InterviewHistory).filter(InterviewHistory.user_id == user_id).all()
    total_questions = sum(parse_questions_count(h.questions) for h in user_history)

    # 2. Mock Interviews
    user_mocks = db.query(MockInterview).filter(MockInterview.user_id == user_id).all()
    total_mocks = len(user_mocks)

    # 3. Average Score Calculation
    mock_scores = [float(m.score) for m in user_mocks if m.score is not None and m.score > 0]
    user_skills = db.query(CandidateSkillAnalytics).filter(CandidateSkillAnalytics.user_id == user_id).all()
    skill_scores = [float(s.score) for s in user_skills if s.score is not None and s.score > 0]
    
    all_scores = mock_scores + skill_scores
    average_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0

    # 4. Preparation Streak
    active_dates: Set[date] = set()
    for h in user_history:
        if h.created_at:
            active_dates.add(h.created_at.date() if isinstance(h.created_at, datetime) else h.created_at)
    for m in user_mocks:
        if m.created_at:
            active_dates.add(m.created_at.date() if isinstance(m.created_at, datetime) else m.created_at)

    user_scans = db.query(ResumeScan).filter(ResumeScan.user_id == user_id).order_by(desc(ResumeScan.created_at)).all()
    for s in user_scans:
        if s.created_at:
            active_dates.add(s.created_at.date() if isinstance(s.created_at, datetime) else s.created_at)

    user_mistakes = db.query(CandidateMistakesLedger).filter(CandidateMistakesLedger.user_id == user_id).all()
    for mk in user_mistakes:
        if mk.created_at:
            active_dates.add(mk.created_at.date() if isinstance(mk.created_at, datetime) else mk.created_at)

    streak_days = calculate_streak(active_dates)

    # 5. Latest Resume Scan Integration
    latest_scan = user_scans[0] if user_scans else None
    resume_summary: Optional[CandidateDashboardResumeSummary] = None
    latest_resume_score: Optional[float] = None
    target_role: Optional[str] = None

    if latest_scan:
        latest_resume_score = float(latest_scan.overall_match_score or latest_scan.match_score or 0.0)
        target_role = latest_scan.target_role

        # Parse skill gaps safely
        gaps_raw = latest_scan.skill_gaps or "[]"
        try:
            top_gaps = json.loads(gaps_raw) if gaps_raw.startswith("[") else [g.strip() for g in gaps_raw.split(",") if g.strip()]
        except Exception:
            top_gaps = []

        crit_raw = latest_scan.critical_gaps or "[]"
        try:
            crit_gaps = json.loads(crit_raw) if crit_raw.startswith("[") else [g.strip() for g in crit_raw.split(",") if g.strip()]
        except Exception:
            crit_gaps = []

        resume_summary = CandidateDashboardResumeSummary(
            latest_scan_id=latest_scan.scan_id or f"scan_{latest_scan.id}",
            target_role=latest_scan.target_role,
            overall_match_score=round(latest_resume_score, 1),
            match_confidence=latest_scan.match_confidence or "MEDIUM",
            top_skill_gaps=top_gaps,
            critical_gaps=crit_gaps
        )
    elif user_history:
        target_role = user_history[0].role
    elif user_mocks:
        target_role = user_mocks[0].role

    # 6. Overall Preparation Readiness
    readiness = calculate_readiness(
        questions_count=total_questions,
        mocks_count=total_mocks,
        avg_score=average_score,
        resume_score=latest_resume_score
    )

    # 7. Competency Scores
    competencies = extract_competencies(user_skills, user_mocks)

    # 8. Deterministic Recommended Focus
    recommended_focus = generate_recommended_focus(user_mistakes, user_skills, latest_scan)

    # 9. Recent Activity Timeline
    recent_activity = get_recent_activity(user_id=user_id, db=db, limit=10)

    # 10. User Summary
    user_summary = CandidateUserSummary(
        id=user.id,
        email=user.email,
        name=user.full_name or (user.email.split("@")[0].replace(".", " ").title() if "@" in user.email else "Candidate"),
        role=user.role or "candidate",
        plan_tier=user.plan_tier or "free",
        target_role=target_role
    )

    return CandidateDashboardResponse(
        user=user_summary,
        preparation_readiness=readiness,
        questions_practiced=total_questions,
        mock_interviews=total_mocks,
        average_score=average_score,
        preparation_streak=streak_days,
        competency_scores=competencies,
        resume_match=resume_summary,
        recommended_focus=recommended_focus,
        recent_activity=recent_activity
    )
