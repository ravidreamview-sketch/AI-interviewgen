"""
AI Interview & Project Mentor Agent Service Layer (Phase 5)
===========================================================
Integrates and enhances existing AI Interview Studio capabilities:
1. Reuses existing `app.interview_engine.start_interview_session` and
   `app.interview_engine.evaluate_and_generate_next_question`.
2. Assembles context-aware preparation from:
   - LearnerProfile (target role, level, years of experience)
   - CandidateSkillAnalytics (weakest competencies to probe)
   - CandidateMistakesLedger (past failure points)
   - AdaptiveRoadmap (active module & targeted skills)
   - LearnerProjects (portfolio projects to probe)
3. Enriches interview evaluations with Phase 1 5-tier competency framework mapping.
4. Provides AI Project Mentoring across 6 technical development stages:
   - Planning, Requirements, Architecture, Debugging, Design Review, Presentation Prep.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db_models import (
    UserAccount,
    LearnerProfile,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
    MockInterview,
    AdaptiveRoadmap,
    LearnerProject,
    ProjectMentorshipTurn,
)
from app.services.learner_intelligence_service import score_to_proficiency
from app.interview_engine import (
    start_interview_session as engine_start_interview,
    evaluate_and_generate_next_question as engine_evaluate_turn,
)
from app.services import generate_ai_questions, get_ai_provider_status

logger = logging.getLogger("ravi.interview_mentor")


# ==============================================================================
# 1. CONTEXT-AWARE INTERVIEW PREPARATION
# ==============================================================================

def assemble_interview_context(
    user_id: int,
    db: Session,
    target_role: Optional[str] = None,
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Assembles rich learner context to seed the existing interview engine.
    Returns: (role, priority_skills, candidate_context_dict)
    """
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    selected_role = target_role or (profile.target_role if profile else "Full-Stack Engineer")
    years_exp = profile.years_of_experience if profile else 0.0
    target_level = profile.target_level if profile else "Mid-Level"

    # Identify weak skills from analytics
    analytics = db.query(CandidateSkillAnalytics).filter(
        CandidateSkillAnalytics.user_id == user_id
    ).order_by(CandidateSkillAnalytics.score.asc()).limit(4).all()

    priority_skills = [a.skill for a in analytics] if analytics else [
        "Distributed Systems & Architecture",
        "PostgreSQL & Database Design",
        "Python / Core Backend",
        "System Security & Auth",
    ]

    # Past mistakes
    mistakes = db.query(CandidateMistakesLedger).filter(
        CandidateMistakesLedger.user_id == user_id,
        CandidateMistakesLedger.mistake_status != "resolved"
    ).limit(3).all()

    # Active roadmap activity
    active_roadmap = db.query(AdaptiveRoadmap).filter(
        AdaptiveRoadmap.user_id == user_id,
        AdaptiveRoadmap.status == "active"
    ).order_by(AdaptiveRoadmap.created_at.desc()).first()

    roadmap_focus = None
    if active_roadmap and active_roadmap.roadmap_data:
        try:
            r_data = json.loads(active_roadmap.roadmap_data)
            for m in r_data.get("modules", []):
                if m.get("status") in ("in_progress", "available"):
                    roadmap_focus = m.get("title")
                    break
        except Exception:
            pass

    # Registered learner projects
    projects = db.query(LearnerProject).filter(LearnerProject.user_id == user_id).all()
    project_titles = [f"{p.title} ({p.domain})" for p in projects]

    candidate_context = {
        "candidate_id": user_id,
        "target_level": target_level,
        "years_of_experience": years_exp,
        "weak_competencies": priority_skills,
        "unresolved_mistakes": [m.description for m in mistakes],
        "active_curriculum_focus": roadmap_focus,
        "portfolio_projects": project_titles,
    }

    return selected_role, priority_skills, candidate_context


def start_context_aware_interview(
    user_id: int,
    db: Session,
    target_role: Optional[str] = None,
    persona: str = "alex",
    interview_type: str = "technical",
    mode: str = "voice",
    question_count: int = 5,
    custom_question: Optional[str] = None,
    questions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Directly invokes the existing interview engine with context-aware candidate parameters.
    """
    role, skills, candidate_context = assemble_interview_context(
        user_id=user_id,
        db=db,
        target_role=target_role,
    )

    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    experience_str = f"{profile.years_of_experience} years ({profile.target_level})" if profile else "Mid-Level"

    # Reuse existing start_interview_session
    return engine_start_interview(
        role=role,
        skills=skills,
        persona=persona,
        mode=mode,
        user_id=user_id,
        db=db,
        experience=experience_str,
        interview_type=interview_type,
        company=None,
        custom_question=custom_question,
        questions=questions,
        question_count=question_count,
        candidate_context=candidate_context,
    )


def process_context_aware_interview_turn(
    interview_id: str,
    answer_text: str,
    user_id: int,
    db: Session,
    is_final: bool = False,
    turn_index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Directly invokes existing engine_evaluate_turn and enriches the evaluation
    with Phase 1 5-tier competency framework mapping.
    """
    result = engine_evaluate_turn(
        interview_id=interview_id,
        answer_text=answer_text,
        db=db,
        user_id=user_id,
        is_final=is_final,
        turn_index=turn_index,
    )

    # Enrich evaluation with 5-tier taxonomy
    eval_data = result.get("evaluation")
    if eval_data and isinstance(eval_data, dict):
        raw_score = float(eval_data.get("overall_score") or eval_data.get("score") or 75.0)
        lvl, lvl_title = score_to_proficiency(raw_score)
        eval_data["competency_tier"] = {
            "level": lvl,
            "title": lvl_title,
            "score": raw_score,
            "evidence_source": "MOCK_INTERVIEW_TURN",
        }

    return result


# ==============================================================================
# 2. AI PROJECT MENTOR SERVICE
# ==============================================================================

PROJECT_MENTOR_STAGE_PROMPTS = {
    "planning": "Focus on problem statement clarity, target user persona, MVP feature scoping, and realistic delivery phases.",
    "requirements": "Focus on non-functional requirements (throughput, latency, availability), edge-case failure modes, and API payload contracts.",
    "architecture": "Focus on database selection, distributed caching, concurrency boundaries, message brokers, and security barriers.",
    "debugging": "Focus on static error analysis, profiling memory/CPU bottlenecks, and race condition prevention without executing code.",
    "design_review": "Focus on clean code idioms, static type safety, separation of concerns, and dependency injection.",
    "presentation_prep": "Focus on explaining architectural trade-offs to senior interviewers, handling 'why this over that' questions, and STAR framing."
}


def generate_socratic_project_guidance(
    project_title: str,
    stage: str,
    user_query: str,
    tech_stack: List[str],
) -> Tuple[str, List[str]]:
    """
    Deterministic Socratic project mentoring fallback when external AI provider is offline.
    """
    stack_str = ", ".join(tech_stack) if tech_stack else "Python, FastAPI, PostgreSQL"

    if stage == "architecture":
        guidance = (
            f"### 🏗️ Architecture Guidance: {project_title}\n\n"
            f"For your stack ({stack_str}), let's analyze the critical architectural boundaries:\n\n"
            f"1. **State & Concurrency:** Ensure that any mutation to state is protected by atomic database transactions or idempotency keys.\n"
            f"2. **Decoupling Asynchronous Tasks:** If background tasks (e.g. notifications, processing) exceed 50ms, decouple them into a background worker queue.\n"
            f"3. **Data Access Layers:** Avoid leaking database models into client response schemas—enforce strict DTO contracts with Pydantic.\n\n"
            f"> **Socratic Question:** *If 100 users trigger this action simultaneously, where will the first bottleneck occur: the connection pool, memory, or CPU?*"
        )
        actions = [
            "Document your transactional boundaries and rollback strategy",
            "Define connection pool limits for PostgreSQL",
            "Add rate limiting at the API gateway layer"
        ]
    elif stage == "planning":
        guidance = (
            f"### 📋 Project Scoping & Planning: {project_title}\n\n"
            f"To make this project stand out in Staff/Principal technical interviews:\n\n"
            f"1. **Core Problem:** Clearly articulate what business or systems problem this solves that standard libraries don't.\n"
            f"2. **MVP Scope:** Keep the initial deliverable scoped to 2-3 high-impact workflows with 100% test coverage.\n"
            f"3. **Quantifiable Metric:** Define how success is measured (e.g., latency < 50ms, zero duplicate writes)."
        )
        actions = [
            "Write a 1-page Problem Definition RFC",
            "List 3 core user stories with acceptance criteria",
            "Establish automated CI test suite skeleton"
        ]
    elif stage == "presentation_prep":
        guidance = (
            f"### 🎙️ Technical Interview Presentation Prep: {project_title}\n\n"
            f"Interviewers will probe your deepest engineering trade-offs. Frame your pitch using the STAR method:\n\n"
            f"1. **Situation & Task:** Frame the real-world scale or concurrency challenge.\n"
            f"2. **Alternative Considered:** Name at least one alternative technology you rejected and explain *why*.\n"
            f"3. **Result:** Cite specific latency, reliability, or test coverage numbers."
        )
        actions = [
            "Prepare your 2-minute project architectural pitch",
            "Document 3 trade-offs: why you chose this stack over alternatives",
            "Practice walking through a simulated system failure and how your design recovers"
        ]
    else:
        guidance = (
            f"### 💡 Technical Mentorship ({stage.replace('_', ' ').title()}): {project_title}\n\n"
            f"Reviewing your inquiry regarding `{stage}` with tech stack ({stack_str}):\n\n"
            f"Your approach demonstrates good software engineering discipline. Ensure that all assumptions are validated with automated tests and that error boundaries prevent cascading failures.\n\n"
            f"> **Guiding Direction:** *Focus on making the system self-documenting and observable through structured telemetry.*"
        )
        actions = [
            "Review error handling boundaries",
            "Add structured logging with request correlation IDs",
            "Verify edge-case unit test coverage"
        ]

    return guidance, actions


def mentor_project_interaction(
    user: UserAccount,
    db: Session,
    project_id: str,
    stage: str,
    user_query: str,
) -> Dict[str, Any]:
    """
    Executes an AI Project Mentoring interaction:
    1. Verifies project ownership.
    2. Builds Socratic mentoring prompt.
    3. Invokes AI provider or deterministic fallback.
    4. Persists mentorship turn.
    """
    project = db.query(LearnerProject).filter(
        LearnerProject.project_id == project_id,
        LearnerProject.user_id == user.id
    ).first()

    if not project:
        raise ValueError(f"Project '{project_id}' not found or access denied.")

    tech_stack = json.loads(project.tech_stack) if project.tech_stack else []
    stage_directive = PROJECT_MENTOR_STAGE_PROMPTS.get(stage, "Provide expert technical mentorship.")

    provider_name, is_configured = get_ai_provider_status()
    guidance_text = ""
    action_items = []

    if is_configured:
        prompt = f"""You are the RaviGen AI Senior Project Mentor and Staff Engineer.
You are mentoring a software engineer building: {project.title}
Domain: {project.domain}
Target Role: {project.target_role}
Tech Stack: {', '.join(tech_stack)}

Mentorship Stage: {stage.upper()}
Stage Directive: {stage_directive}

CANDIDATE INQUIRY:
{user_query}

CRITICAL RULES:
- Provide Socratic, constructive architectural guidance. Do not write the entire project for the candidate.
- Conclude with 2-3 specific, actionable next steps.
"""
        try:
            ai_reply = generate_ai_questions(prompt, temperature=0.6)
            if ai_reply and ai_reply.strip():
                guidance_text = ai_reply
                action_items = [
                    f"Implement recommended {stage} pattern",
                    "Add automated verification tests",
                    "Document architectural trade-offs"
                ]
        except Exception as e:
            logger.warning("AI provider unavailable for project mentoring: %s", e)

    if not guidance_text:
        guidance_text, action_items = generate_socratic_project_guidance(
            project_title=project.title,
            stage=stage,
            user_query=user_query,
            tech_stack=tech_stack,
        )

    # Persist mentorship turn
    turn = ProjectMentorshipTurn(
        project_id=project.project_id,
        user_id=user.id,
        mentorship_stage=stage,
        user_query=user_query,
        mentor_guidance=guidance_text,
        action_items=json.dumps(action_items),
        created_at=datetime.now(timezone.utc),
    )
    db.add(turn)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(turn)

    return {
        "project_id": project.project_id,
        "stage": stage,
        "mentor_guidance": guidance_text,
        "action_items": action_items,
        "created_at": turn.created_at.isoformat(),
    }
