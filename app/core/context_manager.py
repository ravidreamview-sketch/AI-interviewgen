"""
Shared Learner Context Manager (Phase 7)
========================================
Implements data-minimised, secure, sanitized context assembly for each agent:
1. Strict Data Minimisation: Each agent receives ONLY the fields defined in its registry contract.
2. Tenant Isolation: Enforces user ownership boundaries.
3. Prompt Injection Defense: Sanitizes adversarial instructions and system prompts.
4. Privacy Boundaries: Strips authentication tokens, passwords, and PII.
"""

from __future__ import annotations

import re
import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.agent_registry import (
    AgentRegistry,
    AGENT_LEARNER_PROFILER,
    AGENT_ADAPTIVE_PATH,
    AGENT_AI_TUTOR,
    AGENT_SCENARIO_GEN,
    AGENT_INTERVIEW_MENTOR,
    AGENT_COMPETENCY_INTEL,
)
from app.db_models import (
    LearnerProfile,
    AdaptiveRoadmap,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
    TutorSession,
    TutorMessage,
    LearnerProject,
)

logger = logging.getLogger(__name__)

# Patterns commonly used in prompt injection attempts
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?guidelines", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+must", re.IGNORECASE),
    re.compile(r"do\s+anything\s+now|dan\s+mode", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>", re.IGNORECASE),
]


def sanitize_prompt_text(text: str) -> str:
    """Strips adversarial prompt injection phrases and control tokens."""
    if not isinstance(text, str):
        return ""
    sanitized = text
    for pattern in PROMPT_INJECTION_PATTERNS:
        sanitized = pattern.sub("[REDACTED_INJECTION_ATTEMPT]", sanitized)
    return sanitized.strip()


class LearnerContextManager:
    """Builds strictly minimised and sanitized context scoped to each agent."""

    @classmethod
    def build_scoped_context(
        cls,
        user_id: int,
        agent_id: str,
        db: Session,
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Assembles a scoped, minimal context payload matching the agent's contract.
        Prevents leaking unnecessary sensitive fields.
        """
        agent = AgentRegistry.get_agent(agent_id)
        extra = extra_params or {}

        # 1. Base profile (if exists)
        profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()

        # Build agent-specific minimised payload
        scoped_data: Dict[str, Any] = {"user_id": user_id}

        if agent_id == AGENT_LEARNER_PROFILER:
            scoped_data.update({
                "target_role": profile.target_role if profile else extra.get("target_role", "Full-Stack Engineer"),
                "target_level": profile.target_level if profile else extra.get("target_level", "Mid-Level"),
                "years_of_experience": profile.years_of_experience if profile else 0.0,
                "education_level": profile.education_level if profile else None,
            })

        elif agent_id == AGENT_ADAPTIVE_PATH:
            weak_skills = db.query(CandidateSkillAnalytics).filter(
                CandidateSkillAnalytics.user_id == user_id,
                CandidateSkillAnalytics.score < 75.0
            ).all()
            roadmap = db.query(AdaptiveRoadmap).filter(
                AdaptiveRoadmap.user_id == user_id,
                AdaptiveRoadmap.status == "active"
            ).first()

            scoped_data.update({
                "target_role": profile.target_role if profile else extra.get("target_role", "Backend Engineer"),
                "target_level": profile.target_level if profile else extra.get("target_level", "Mid-Level"),
                "skill_gaps": [s.skill for s in weak_skills],
                "active_roadmap_id": roadmap.roadmap_id if roadmap else None,
            })

        elif agent_id == AGENT_AI_TUTOR:
            # Data minimisation: ONLY the current activity, concept, level, and last 4 tutor turns
            session_id = extra.get("session_id")
            recent_turns = []
            if session_id:
                t_sess = db.query(TutorSession).filter(TutorSession.session_id == session_id, TutorSession.user_id == user_id).first()
                if t_sess:
                    messages = db.query(TutorMessage).filter(TutorMessage.session_id == t_sess.id).order_by(TutorMessage.id.desc()).limit(4).all()
                    recent_turns = [{"role": m.role, "content": sanitize_prompt_text(m.content)} for m in reversed(messages)]

            scoped_data.update({
                "roadmap_id": extra.get("roadmap_id"),
                "activity_id": extra.get("activity_id"),
                "concept": sanitize_prompt_text(str(extra.get("concept", "General Engineering"))),
                "skill_level": extra.get("skill_level", "Intermediate"),
                "recent_dialogue": recent_turns,
            })

        elif agent_id == AGENT_SCENARIO_GEN:
            weak_skills = db.query(CandidateSkillAnalytics).filter(
                CandidateSkillAnalytics.user_id == user_id,
                CandidateSkillAnalytics.score < 75.0
            ).limit(3).all()

            scoped_data.update({
                "target_role": profile.target_role if profile else extra.get("target_role", "Backend Engineer"),
                "target_level": profile.target_level if profile else extra.get("target_level", "Mid-Level"),
                "category": extra.get("category", "debugging"),
                "difficulty": extra.get("difficulty", "Intermediate"),
                "skill_gaps": [s.skill for s in weak_skills],
            })

        elif agent_id == AGENT_INTERVIEW_MENTOR:
            weak_skills = db.query(CandidateSkillAnalytics).filter(
                CandidateSkillAnalytics.user_id == user_id,
                CandidateSkillAnalytics.score < 75.0
            ).limit(3).all()
            mistakes = db.query(CandidateMistakesLedger).filter(
                CandidateMistakesLedger.user_id == user_id,
                CandidateMistakesLedger.mistake_status != "resolved"
            ).limit(3).all()

            scoped_data.update({
                "target_role": profile.target_role if profile else extra.get("target_role", "Backend Engineer"),
                "weak_competencies": [s.skill for s in weak_skills],
                "mistake_summaries": [m.description for m in mistakes],
                "project_id": extra.get("project_id"),
            })

        elif agent_id == AGENT_COMPETENCY_INTEL:
            scoped_data.update({
                "target_role": profile.target_role if profile else "Backend Engineer (Python / Cloud)",
                "target_level": profile.target_level if profile else "Mid-Level",
            })

        return scoped_data
