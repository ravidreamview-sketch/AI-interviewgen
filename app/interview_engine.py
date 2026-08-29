"""
Conversational AI Interview Engine

Coordinates real-time turn-taking interview loops:
1. Dynamic Opening Question synthesis based on target role & skills.
2. Contextual Candidate Answer evaluation (STAR framework, technical depth, clarity).
3. Intelligent Follow-up question branching preserving conversational memory.
4. Comprehensive multi-dimensional scorecard generation and candidate dashboard integration.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import re
import json
import uuid
import logging
from datetime import datetime

from sqlalchemy.orm import Session
from app.db_models import UserAccount, MockInterview
from app.services import generate_ai_questions
from app.tts_service import get_tts_provider
from app.avatar_service import get_avatar_provider

logger = logging.getLogger("ravi.interview_engine")


# Persona Interview Style Profiles
PERSONA_PROMPTS = {
    "alex": {
        "name": "Alex",
        "role": "Principal Technical Lead",
        "tone": "Direct, rigorous, deeply technical. Probes architecture, scale trade-offs, concurrency, and clean code.",
        "fallback_first_q": "Welcome! I'm Alex. To start off, could you walk me through the most technically challenging system or feature you've designed recently, and the key architectural trade-offs you made?"
    },
    "elena": {
        "name": "Elena",
        "role": "Principal Systems Architect",
        "tone": "Strategic, architectural, focused on scalability, high availability, failure modes, caching, and data pipelines.",
        "fallback_first_q": "Hello, I'm Elena. Let's begin by discussing high-scale system design. How do you design and partition a distributed system to handle a 10x traffic spike while maintaining strict data consistency?"
    },
    "marcus": {
        "name": "Marcus",
        "role": "VP of People & Leadership",
        "tone": "Warm, perceptive, focused on behavioral insights, STAR structure, conflict resolution, leadership, and product impact.",
        "fallback_first_q": "Hi, I'm Marcus. I'm excited to speak with you today. Tell me about a time when you strongly disagreed with a team decision or technical direction. How did you handle it and what was the outcome?"
    }
}


def get_persona_info(persona_key: str) -> Dict[str, str]:
    k = persona_key.lower().strip()
    return PERSONA_PROMPTS.get(k, PERSONA_PROMPTS["alex"])


def start_interview_session(
    role: str,
    skills: List[str],
    persona: str = "alex",
    mode: str = "video_voice",
    user_id: Optional[int] = None,
    db: Optional[Session] = None
) -> Dict[str, Any]:
    """
    Initializes a new conversational AI interview session and generates Question 1.
    """
    session_id = f"mock_{uuid.uuid4().hex[:12]}"
    persona_info = get_persona_info(persona)
    skills_str = ", ".join(skills) if skills else "Core Engineering & Architecture"

    prompt = f"""
You are {persona_info['name']}, a {persona_info['role']}.
Your interviewing style: {persona_info['tone']}

Role being interviewed for: {role}
Key skills to evaluate: {skills_str}

Generate the OPENING interview question for this candidate.
STRICT REQUIREMENTS:
- Speak directly in the first person ("I", "my").
- Make the question engaging, professional, and tailored specifically to the target role ({role}) and skills ({skills_str}).
- Output ONLY the question text (1-3 sentences max). Do not include any intro, pleasantries, or quotes.
"""

    first_question = persona_info["fallback_first_q"]
    try:
        raw_res = generate_ai_questions(prompt)
        cleaned = raw_res.strip().strip('"').strip("'")
        if len(cleaned) > 20:
            first_question = cleaned
    except Exception as e:
        logger.warning(f"[Interview Engine] Opening question fallback triggered: {e}")

    # Voice and Avatar metadata
    tts_provider = get_tts_provider()
    tts_data = tts_provider.synthesize_speech(first_question, persona)
    avatar_provider = get_avatar_provider()
    avatar_meta = avatar_provider.get_persona_avatar_metadata(persona)

    initial_turn = {
        "turn_index": 1,
        "question": first_question,
        "answer": "",
        "evaluation": None,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Persist in DB if available
    if db:
        try:
            mock_record = MockInterview(
                user_id=user_id,
                role=role,
                company_target="FAANG Tier",
                interviewer_persona=f"{persona_info['name']} ({persona_info['role']})",
                score=80.0,
                technical_accuracy=80.0,
                communication_clarity=80.0,
                star_depth=80.0,
                confidence_score=80.0,
                duration_seconds=0,
                transcript=json.dumps([initial_turn]),
                status="in_progress",
                interview_mode=mode,
                created_at=datetime.utcnow()
            )
            db.add(mock_record)
            db.commit()
            db.refresh(mock_record)
            session_id = f"mock_{mock_record.id}"
        except Exception as db_err:
            logger.warning(f"[Interview Engine] DB save warning during session start: {db_err}")

    return {
        "interview_id": session_id,
        "first_question": first_question,
        "persona": {
            "name": persona_info["name"],
            "role": persona_info["role"],
            "accent_color": avatar_meta.get("accent_color", "#38BDF8"),
            "theme_gradient": avatar_meta.get("theme_gradient", "")
        },
        "tts_config": tts_data.get("voice_config", {}),
        "initial_speech": tts_data,
        "mode": mode
    }


def evaluate_and_generate_next_question(
    interview_id: str,
    answer_text: str,
    db: Optional[Session] = None,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Evaluates the candidate's turn answer and synthesizes a contextual follow-up or next question.
    """
    mock_record = None
    role = "Software Engineer"
    persona_key = "alex"
    history: List[Dict[str, Any]] = []

    if db and interview_id.startswith("mock_"):
        try:
            rec_id = int(interview_id.replace("mock_", ""))
            mock_record = db.query(MockInterview).filter(MockInterview.id == rec_id).first()
            if mock_record:
                role = mock_record.role
                if "Elena" in (mock_record.interviewer_persona or ""):
                    persona_key = "elena"
                elif "Marcus" in (mock_record.interviewer_persona or ""):
                    persona_key = "marcus"
                
                if mock_record.transcript:
                    try:
                        history = json.loads(mock_record.transcript)
                    except Exception:
                        history = []
        except Exception as e:
            logger.warning(f"[Interview Engine] Record load warning: {e}")

    persona_info = get_persona_info(persona_key)
    current_turn_index = len(history)
    current_question = history[-1]["question"] if history else "Tell me about your technical background."

    # Prompt LLM for structured evaluation and intelligent follow-up
    prompt = f"""
You are {persona_info['name']}, a {persona_info['role']} conducting an interview for: {role}.
Interview style: {persona_info['tone']}

CONVERSATION CONTEXT:
Question Asked: "{current_question}"
Candidate Answer: \"\"\"{answer_text}\"\"\"

TASK:
1. Evaluate the answer thoroughly.
2. Score performance (0-100).
3. Identify 1-2 concrete strengths.
4. Identify 1-2 specific areas of improvement (e.g. missing metrics, vague implementation, lack of STAR format).
5. Generate the NEXT question or a deep-dive FOLLOW-UP question branching directly from their answer.

STRICT JSON OUTPUT FORMAT:
Output ONLY valid JSON matching this schema:
{{
  "evaluation": {{
    "score": <integer 0-100>,
    "technical_score": <integer 0-100>,
    "communication_score": <integer 0-100>,
    "strengths": ["<strength 1>", "<strength 2>"],
    "improvements": ["<improvement 1>"],
    "star_detected": <boolean>,
    "feedback": "<1-2 sentence coaching observation>"
  }},
  "next_question": "<Concise conversational follow-up or next question>",
  "follow_up_required": <boolean>
}}
"""

    eval_result = None
    try:
        raw_res = generate_ai_questions(prompt)
        json_match = re.search(r"\{.*\}", raw_res, re.DOTALL)
        if json_match:
            eval_result = json.loads(json_match.group(0))
    except Exception as e:
        logger.warning(f"[Interview Engine] LLM turn evaluation fallback: {e}")

    if not eval_result or "evaluation" not in eval_result:
        words = len(answer_text.strip().split())
        score = min(92, max(45, int(50 + (words * 0.4))))
        eval_result = {
            "evaluation": {
                "score": score,
                "technical_score": score,
                "communication_score": max(50, score - 5),
                "strengths": ["Clear communication and direct engagement with the question."],
                "improvements": ["Elaborate with measurable business metrics and architectural trade-offs."],
                "star_detected": words > 40,
                "feedback": "Solid foundation. To elevate your answer to senior level, quantify your impact."
            },
            "next_question": f"Building on that, how did your team measure the reliability and latency impact of that solution in production?",
            "follow_up_required": False
        }

    next_q = eval_result.get("next_question", "Could you walk me through the monitoring and error-handling strategy for that?")
    tts_provider = get_tts_provider()
    tts_data = tts_provider.synthesize_speech(next_q, persona_key)

    # Update history
    if history:
        history[-1]["answer"] = answer_text
        history[-1]["evaluation"] = eval_result["evaluation"]

    new_turn = {
        "turn_index": current_turn_index + 1,
        "question": next_q,
        "answer": "",
        "evaluation": None,
        "timestamp": datetime.utcnow().isoformat()
    }
    history.append(new_turn)

    # Update DB record
    if mock_record and db:
        try:
            mock_record.transcript = json.dumps(history)
            mock_record.duration_seconds = max(60, (len(history) * 60))
            scores = [t["evaluation"]["score"] for t in history if t.get("evaluation") and "score" in t["evaluation"]]
            if scores:
                mock_record.score = sum(scores) / len(scores)
            db.commit()
        except Exception as db_err:
            logger.warning(f"[Interview Engine] DB update warning: {db_err}")

    return {
        "evaluation": eval_result["evaluation"],
        "next_question": next_q,
        "follow_up_required": eval_result.get("follow_up_required", False),
        "turn_index": len(history),
        "tts_speech": tts_data
    }


def complete_interview_session(
    interview_id: str,
    db: Optional[Session] = None,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Finalizes the interview session, calculates holistic metrics, and returns the final scorecard.
    """
    mock_record = None
    role = "Software Engineer"
    history: List[Dict[str, Any]] = []

    if db and interview_id.startswith("mock_"):
        try:
            rec_id = int(interview_id.replace("mock_", ""))
            mock_record = db.query(MockInterview).filter(MockInterview.id == rec_id).first()
            if mock_record:
                role = mock_record.role
                if mock_record.transcript:
                    try:
                        history = json.loads(mock_record.transcript)
                    except Exception:
                        history = []
        except Exception as e:
            logger.warning(f"[Interview Engine] Load error on completion: {e}")

    evaluated_turns = [t for t in history if t.get("evaluation")]
    total_turns = len(evaluated_turns)

    if total_turns > 0:
        overall_score = round(sum(t["evaluation"].get("score", 80) for t in evaluated_turns) / total_turns, 1)
        tech_score = round(sum(t["evaluation"].get("technical_score", overall_score) for t in evaluated_turns) / total_turns, 1)
        comm_score = round(sum(t["evaluation"].get("communication_score", overall_score) for t in evaluated_turns) / total_turns, 1)
        problem_solving_score = round((overall_score * 0.6 + tech_score * 0.4), 1)

        all_strengths = []
        all_improvements = []
        for t in evaluated_turns:
            all_strengths.extend(t["evaluation"].get("strengths", []))
            all_improvements.extend(t["evaluation"].get("improvements", []))
        
        unique_strengths = list(dict.fromkeys(all_strengths))[:4] or ["Strong clarity and structured responses."]
        unique_improvements = list(dict.fromkeys(all_improvements))[:4] or ["Deepen coverage of edge cases and scale trade-offs."]
    else:
        overall_score = 85.0
        tech_score = 86.0
        comm_score = 84.0
        problem_solving_score = 85.0
        unique_strengths = ["Excellent articulation of concepts.", "Clear structured delivery."]
        unique_improvements = ["Incorporate quantitative metrics into answers."]

    recommendations = [
        f"Continue practicing high-complexity scenarios for {role}.",
        "Frame architectural decisions using the STAR framework with explicit trade-off analyses.",
        "Emphasize latency, availability SLAs, and rollback mitigation strategies."
    ]

    if mock_record and db:
        try:
            mock_record.score = overall_score
            mock_record.technical_accuracy = tech_score
            mock_record.communication_clarity = comm_score
            mock_record.star_depth = comm_score
            mock_record.confidence_score = problem_solving_score
            mock_record.status = "completed"
            db.commit()
            logger.info("Mock interview completed and persisted", extra={"mock_id": mock_record.id, "score": overall_score})
        except Exception as db_err:
            logger.warning(f"[Interview Engine] DB finalization warning: {db_err}")

    return {
        "overall_score": overall_score,
        "technical_score": tech_score,
        "communication_score": comm_score,
        "problem_solving_score": problem_solving_score,
        "strengths": unique_strengths,
        "improvements": unique_improvements,
        "recommendations": recommendations,
        "total_turns": total_turns,
        "role": role,
        "status": "completed"
    }
