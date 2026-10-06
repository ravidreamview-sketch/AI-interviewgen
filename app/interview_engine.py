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
from app.services import generate_ai_questions, parse_raw_questions
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
    db: Optional[Session] = None,
    experience: Optional[str] = None,
    interview_type: Optional[str] = None,
    company: Optional[str] = None,
    custom_question: Optional[str] = None,
    questions: Optional[List[str]] = None,
    question_count: int = 5,
    candidate_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Initializes a new conversational AI interview session and generates Question 1.
    """
    persona_info = get_persona_info(persona)
    skills_str = ", ".join(skills) if skills else "Core Engineering & Architecture"

    prepared_questions = [
        question.strip()[:1000]
        for question in (questions or [])
        if isinstance(question, str) and question.strip()
    ][:20]
    if not prepared_questions:
        prompt = f"""
You are {persona_info['name']}, a {persona_info['role']}.
Your interviewing style: {persona_info['tone']}

Role: {role}
Interview type: {interview_type or "Mixed interview"}
Experience: {experience or "Not provided"}
Focus skills: {skills_str}
Candidate focus topic: {custom_question or "No additional topic"}
Candidate evidence: {json.dumps(candidate_context or {}, ensure_ascii=True)[:4000]}

Write {max(1, min(question_count, 20))} distinct concise interview questions, ordered from foundational to deeper probing. Tailor them to the role, interview type, skills, and experience. Do not invent candidate history.
Output only the question, with no greeting or explanation.
"""
        try:
            generated_response = generate_ai_questions(prompt)
        except RuntimeError as exc:
            logger.warning(
                "AI provider unavailable while starting interview (%s)",
                type(exc).__name__,
            )
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:
            logger.warning(
                "Could not generate the opening interview question (%s)",
                type(exc).__name__,
            )
            raise RuntimeError("The interviewer could not generate the first question.") from exc
        generated_questions = [
            question[:1000]
            for question in parse_raw_questions(
                generated_response,
                target_count=max(1, min(question_count, 20)),
            )
        ]
        if not generated_questions:
            raise RuntimeError("The interviewer returned an invalid first question.")
        prepared_questions = generated_questions
    first_question = prepared_questions[0]

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
        "timestamp": datetime.utcnow().isoformat(),
        "session_context": {
            "experience": experience,
            "interview_type": interview_type or "Mixed interview",
            "custom_question": custom_question,
            "skills": skills[:20],
            "candidate_evidence": candidate_context or {},
            "planned_questions": prepared_questions,
            "question_count": max(1, min(question_count, 20)),
        },
    }

    if not db or user_id is None:
        raise RuntimeError("An authenticated candidate session is required.")
    try:
        mock_record = MockInterview(
            user_id=user_id,
            role=role,
            company_target=company or "Not specified",
            interviewer_persona=f"{persona_info['name']} ({persona_info['role']})",
            score=0,
            technical_accuracy=0,
            communication_clarity=0,
            star_depth=0,
            confidence_score=0,
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
        db.rollback()
        logger.exception("Could not persist mock interview session for user_id=%s", user_id)
        raise RuntimeError("The interview session could not be saved.") from db_err

    return {
        "interview_id": session_id,
        "first_question": first_question,
        "question_count": len(prepared_questions),
        "questions": prepared_questions,
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
    user_id: Optional[int] = None,
    is_final: bool = False,
    turn_index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Evaluates the candidate's turn answer and synthesizes a contextual follow-up or next question.
    """
    if not db or user_id is None or not interview_id.startswith("mock_"):
        raise ValueError("An authenticated, saved interview session is required.")
    if not answer_text.strip() or len(answer_text) > 10000:
        raise ValueError("The answer must contain 1 to 10000 characters.")
    try:
        record_id = int(interview_id.removeprefix("mock_"))
    except ValueError as exc:
        raise ValueError("The interview session ID is invalid.") from exc

    mock_record = (
        db.query(MockInterview)
        .filter(MockInterview.id == record_id, MockInterview.user_id == user_id)
        .first()
    )
    if not mock_record:
        raise LookupError("Interview session not found.")
    if mock_record.status != "in_progress":
        raise ValueError("This interview session is no longer in progress.")
    role = mock_record.role
    persona_key = "alex"
    if "Elena" in (mock_record.interviewer_persona or ""):
        persona_key = "elena"
    elif "Marcus" in (mock_record.interviewer_persona or ""):
        persona_key = "marcus"
    try:
        history = json.loads(mock_record.transcript or "[]")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("The saved interview transcript is invalid.") from exc
    if not isinstance(history, list) or not history:
        raise RuntimeError("The saved interview transcript is empty.")

    persona_info = get_persona_info(persona_key)
    pending_turn = next(
        (
            turn for turn in history
            if turn_index is not None and turn.get("turn_index") == turn_index
        ),
        None,
    ) if turn_index is not None else next(
        (turn for turn in reversed(history) if not turn.get("evaluation")),
        None,
    )
    if not pending_turn:
        raise ValueError("There is no unanswered interview question to evaluate.")
    if pending_turn.get("evaluation"):
        if pending_turn.get("answer") != answer_text.strip():
            raise ValueError("This question has already been evaluated with a different answer.")
        turn_position = history.index(pending_turn)
        next_turn = history[turn_position + 1] if turn_position + 1 < len(history) else None
        saved_evaluation = pending_turn["evaluation"]
        return {
            "evaluation": saved_evaluation,
            "next_question": next_turn.get("question") if next_turn else None,
            "follow_up_required": bool(saved_evaluation.get("follow_up_required", False)),
            "turn_index": pending_turn.get("turn_index"),
            "is_complete": bool(pending_turn.get("is_final")),
            "tts_speech": None,
        }
    if pending_turn.get("answer") and pending_turn["answer"] != answer_text.strip():
        raise ValueError("This question already has a saved answer.")
    if not pending_turn.get("answer"):
        pending_turn["answer"] = answer_text.strip()
        mock_record.transcript = json.dumps(history)
        try:
            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.exception("Could not save answer for mock_id=%s", mock_record.id)
            raise RuntimeError("The answer could not be saved.") from db_err
    current_turn_index = len([turn for turn in history if turn.get("question")])
    current_question = pending_turn.get("question", "")
    session_context = history[0].get("session_context", {})
    planned_questions = session_context.get("planned_questions", [])
    completed_answers = sum(bool(turn.get("evaluation")) for turn in history)
    question_count = max(
        1,
        min(int(session_context.get("question_count", len(planned_questions) or 5)), 20),
    )
    ending_turn = is_final or completed_answers + 1 >= question_count
    remaining_plan = planned_questions[completed_answers + 1:] if planned_questions else []
    remaining_plan_text = "\n".join(
        f"- {question}" for question in remaining_plan[:10]
    ) or "(No pre-generated questions remain.)"

    prompt = f"""
You are {persona_info['name']}, a {persona_info['role']} conducting an interview for: {role}.
Interview style: {persona_info['tone']}
Interview type: {session_context.get('interview_type', 'Mixed interview')}
Candidate experience: {session_context.get('experience') or 'Not provided'}
Focus skills: {', '.join(session_context.get('skills', [])) or 'Role core competencies'}
Additional focus topic: {session_context.get('custom_question') or 'None'}
Saved candidate evidence (use only if relevant): {json.dumps(session_context.get('candidate_evidence', {}), ensure_ascii=True)[:4000]}

Question asked: "{current_question}"
Candidate answer: \"\"\"{answer_text}\"\"\"
Planned interview questions remaining:
{remaining_plan_text}

TASK:
Evaluate the answer using criteria appropriate to the role and interview type. Scores must be evidence-based; do not invent achievements.
Identify 1-2 concrete strengths and 1-2 specific improvements.
{"This is the final answer. Do not generate another question." if ending_turn else "Generate one concise next question that adapts to the answer while staying aligned to the planned interview."}

STRICT JSON OUTPUT FORMAT:
Output ONLY valid JSON matching this schema:
{{
  "evaluation": {{
    "score": integer 0-100,
    "technical_score": integer 0-100,
    "communication_score": integer 0-100,
    "strengths": ["<strength 1>", "<strength 2>"],
    "improvements": ["<improvement 1>"],
    "star_detected": <boolean>,
    "feedback": "<1-2 sentence coaching observation>"
  }},
  {"\"next_question\": null," if ending_turn else "\"next_question\": \"<concise interview question>\","}
  "follow_up_required": <boolean>
}}
"""

    try:
        raw_res = generate_ai_questions(prompt)
        json_match = re.search(r"\{.*\}", raw_res, re.DOTALL)
        if not json_match:
            raise ValueError("The evaluator response was not valid JSON.")
        eval_result = json.loads(json_match.group(0))
    except Exception as exc:
        logger.warning(
            "Interview evaluation failed for user_id=%s (%s)",
            user_id,
            type(exc).__name__,
        )
        error_message = str(exc)
        if error_message.startswith(("AI provider is not configured.", "Configured AI provider request failed.")):
            raise RuntimeError(f"{error_message} Your answer is saved; retry after configuration.") from exc
        raise RuntimeError("The answer could not be evaluated. Your answer is saved; retry when ready.") from exc

    evaluation = eval_result.get("evaluation")
    if not isinstance(evaluation, dict):
        raise RuntimeError("The answer is saved, but the evaluator returned no evaluation. Retry shortly.")
    try:
        for key in ("score", "technical_score", "communication_score"):
            value = evaluation[key]
            if isinstance(value, bool) or not 0 <= int(value) <= 100:
                raise ValueError
            evaluation[key] = int(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("The answer is saved, but the evaluator returned invalid scores. Retry shortly.") from exc
    for key in ("strengths", "improvements"):
        values = evaluation.get(key, [])
        evaluation[key] = [str(value)[:300] for value in values[:5]] if isinstance(values, list) else []
    evaluation["feedback"] = str(evaluation.get("feedback", ""))[:1000]
    evaluation["star_detected"] = bool(evaluation.get("star_detected", False))
    evaluation["follow_up_required"] = bool(eval_result.get("follow_up_required", False))
    next_q = str(eval_result.get("next_question") or "").strip() if not ending_turn else ""
    if not ending_turn and len(next_q) < 10:
        raise RuntimeError("The answer is saved, but the interviewer did not return a valid next question. Retry shortly.")

    pending_turn["evaluation"] = evaluation
    pending_turn["answered_at"] = datetime.utcnow().isoformat()
    pending_turn["is_final"] = ending_turn
    if not ending_turn:
        history.append({
            "turn_index": current_turn_index + 1,
            "question": next_q[:1000],
            "answer": "",
            "evaluation": None,
            "timestamp": datetime.utcnow().isoformat(),
        })
    mock_record.transcript = json.dumps(history)
    scores = [
        turn["evaluation"]["score"]
        for turn in history
        if turn.get("evaluation") and "score" in turn["evaluation"]
    ]
    mock_record.score = sum(scores) / len(scores) if scores else 0
    mock_record.duration_seconds = max(
        0,
        int((datetime.utcnow() - mock_record.created_at).total_seconds())
        if mock_record.created_at else 0,
    )
    try:
        db.commit()
    except Exception as db_err:
        db.rollback()
        logger.exception("Could not persist evaluated answer for mock_id=%s", mock_record.id)
        raise RuntimeError("Your answer is saved, but its evaluation could not be persisted. Retry shortly.") from db_err

    try:
        tts_data = get_tts_provider().synthesize_speech(next_q, persona_key) if next_q else None
    except Exception as tts_err:
        logger.warning(
            "Speech synthesis unavailable for mock_id=%s (%s)",
            mock_record.id,
            type(tts_err).__name__,
        )
        tts_data = None

    return {
        "evaluation": evaluation,
        "next_question": next_q or None,
        "follow_up_required": evaluation["follow_up_required"],
        "turn_index": current_turn_index,
        "is_complete": ending_turn,
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
    if not db or user_id is None or not interview_id.startswith("mock_"):
        raise ValueError("An authenticated, saved interview session is required.")
    try:
        record_id = int(interview_id.removeprefix("mock_"))
    except ValueError as exc:
        raise ValueError("The interview session ID is invalid.") from exc
    mock_record = (
        db.query(MockInterview)
        .filter(MockInterview.id == record_id, MockInterview.user_id == user_id)
        .first()
    )
    if not mock_record:
        raise LookupError("Interview session not found.")
    role = mock_record.role
    try:
        history = json.loads(mock_record.transcript or "[]")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("The saved interview transcript is invalid.") from exc

    evaluated_turns = [t for t in history if t.get("evaluation")]
    total_turns = len(evaluated_turns)
    if not total_turns:
        raise ValueError("Complete at least one evaluated answer before ending the interview.")
    if mock_record.status == "completed":
        pass
    elif mock_record.status != "in_progress":
        raise ValueError("This interview session cannot be completed.")

    overall_score = round(sum(t["evaluation"]["score"] for t in evaluated_turns) / total_turns, 1)
    tech_values = [t["evaluation"]["technical_score"] for t in evaluated_turns]
    comm_values = [t["evaluation"]["communication_score"] for t in evaluated_turns]
    tech_score = round(sum(tech_values) / len(tech_values), 1)
    comm_score = round(sum(comm_values) / len(comm_values), 1)
    problem_solving_score = round((overall_score + tech_score) / 2, 1)
    unique_strengths = list(dict.fromkeys(
        strength
        for turn in evaluated_turns
        for strength in turn["evaluation"].get("strengths", [])
    ))[:4]
    unique_improvements = list(dict.fromkeys(
        improvement
        for turn in evaluated_turns
        for improvement in turn["evaluation"].get("improvements", [])
    ))[:4]
    recommendations = unique_improvements.copy()
    if mock_record.status != "completed":
        context = history[0].get("session_context", {}) if history else {}
        context["completed_at"] = datetime.utcnow().isoformat()
        if history:
            history[0]["session_context"] = context
        mock_record.transcript = json.dumps(history)
        mock_record.score = overall_score
        mock_record.technical_accuracy = tech_score
        mock_record.communication_clarity = comm_score
        mock_record.star_depth = None
        mock_record.confidence_score = problem_solving_score
        mock_record.status = "completed"
        mock_record.duration_seconds = max(
            mock_record.duration_seconds or 0,
            int((datetime.utcnow() - mock_record.created_at).total_seconds())
            if mock_record.created_at else 0,
        )
        try:
            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.exception("Could not complete mock interview mock_id=%s", mock_record.id)
            raise RuntimeError("The completed interview could not be saved.") from db_err

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
