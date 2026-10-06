import logging
import json
from typing import List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db_models import (
    CandidateMistakesLedger,
    CandidateSkillAnalytics,
    InterviewHistory,
    MockInterview,
    ResumeScan,
    UserAccount,
)
from app.dashboard_service import calculate_readiness
from app.services import generate_ai_questions, parse_raw_questions

logger = logging.getLogger("ravi.coach")


def _transcript_turns(raw_transcript: str | None) -> List[dict]:
    if not raw_transcript:
        return []
    try:
        data = json.loads(raw_transcript)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [turn for turn in data if isinstance(turn, dict)]


def _split_stored_values(raw_value: str | None) -> List[str]:
    if not raw_value:
        return []
    try:
        values = json.loads(raw_value)
    except (TypeError, ValueError):
        values = raw_value.split(",")
    if not isinstance(values, list):
        values = [values]
    return [str(value).strip() for value in values if str(value).strip()]


def build_candidate_context(db: Session, candidate: UserAccount) -> dict:
    user_id = candidate.id
    skills = (
        db.query(CandidateSkillAnalytics)
        .filter(
            CandidateSkillAnalytics.user_id == user_id,
            CandidateSkillAnalytics.weakness_status != "resolved",
        )
        .order_by(CandidateSkillAnalytics.score.asc())
        .limit(8)
        .all()
    )
    skill_score_count = (
        db.query(func.count(CandidateSkillAnalytics.id))
        .filter(
            CandidateSkillAnalytics.user_id == user_id,
            CandidateSkillAnalytics.weakness_status != "resolved",
            CandidateSkillAnalytics.score.isnot(None),
        )
        .scalar()
        or 0
    )
    average_skill_score = (
        db.query(func.avg(CandidateSkillAnalytics.score))
        .filter(
            CandidateSkillAnalytics.user_id == user_id,
            CandidateSkillAnalytics.weakness_status != "resolved",
            CandidateSkillAnalytics.score.isnot(None),
        )
        .scalar()
    )
    mistakes = (
        db.query(CandidateMistakesLedger)
        .filter(
            CandidateMistakesLedger.user_id == user_id,
            CandidateMistakesLedger.mistake_status != "resolved",
        )
        .order_by(CandidateMistakesLedger.created_at.desc())
        .limit(5)
        .all()
    )
    all_interviews = (
        db.query(InterviewHistory)
        .filter(InterviewHistory.user_id == user_id)
        .order_by(InterviewHistory.created_at.desc())
        .all()
    )
    interviews = all_interviews[:3]
    mock_interviews = (
        db.query(MockInterview)
        .filter(
            MockInterview.user_id == user_id,
            MockInterview.status == "completed",
        )
        .order_by(MockInterview.created_at.desc())
        .limit(5)
        .all()
    )
    total_mock_interviews = (
        db.query(func.count(MockInterview.id))
        .filter(MockInterview.user_id == user_id)
        .scalar()
        or 0
    )
    completed_mock_count = (
        db.query(func.count(MockInterview.id))
        .filter(
            MockInterview.user_id == user_id,
            MockInterview.status == "completed",
            MockInterview.score.isnot(None),
        )
        .scalar()
        or 0
    )
    average_completed_score = (
        db.query(func.avg(MockInterview.score))
        .filter(
            MockInterview.user_id == user_id,
            MockInterview.status == "completed",
            MockInterview.score.isnot(None),
        )
        .scalar()
    )
    latest_completed_score = (
        db.query(MockInterview.score)
        .filter(
            MockInterview.user_id == user_id,
            MockInterview.status == "completed",
            MockInterview.score.isnot(None),
        )
        .order_by(MockInterview.created_at.desc())
        .first()
    )
    resume_scan = (
        db.query(ResumeScan)
        .filter(ResumeScan.user_id == user_id)
        .order_by(ResumeScan.created_at.desc())
        .first()
    )

    mock_data = []
    for item in mock_interviews:
        turns = _transcript_turns(item.transcript)
        evaluated_turns = [
            turn for turn in turns
            if turn.get("evaluation") and turn.get("answer")
        ]
        mock_data.append({
            "role": item.role,
            "status": item.status,
            "score": round(float(item.score), 1) if item.score is not None else None,
            "technical_score": round(float(item.technical_accuracy), 1) if item.technical_accuracy is not None else None,
            "communication_score": round(float(item.communication_clarity), 1) if item.communication_clarity is not None else None,
            "star_score": round(float(item.star_depth), 1) if item.star_depth is not None else None,
            "problem_solving_score": round(float(item.confidence_score), 1) if item.confidence_score is not None else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "transcript_summary": (
                (item.transcript or "")[:700]
                if item.transcript and not turns
                else None
            ),
            "turns": [
                {
                    "question": str(turn.get("question", ""))[:500],
                    "answer": str(turn.get("answer", ""))[:700],
                    "feedback": str(turn["evaluation"].get("feedback", ""))[:400],
                    "improvements": [
                        str(value)[:200]
                        for value in turn["evaluation"].get("improvements", [])[:4]
                    ] if isinstance(turn["evaluation"].get("improvements"), list) else [],
                    "strengths": [
                        str(value)[:200]
                        for value in turn["evaluation"].get("strengths", [])[:4]
                    ] if isinstance(turn["evaluation"].get("strengths"), list) else [],
                }
                for turn in evaluated_turns[-5:]
            ],
        })

    history_data = [
        {
            "role": item.role,
            "experience": item.experience,
            "skills": _split_stored_values(item.skills),
            "difficulty": item.difficulty,
            "questions": parse_raw_questions(item.questions or "")[:10],
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in interviews
    ]
    skill_data = [
        {
            "skill": item.skill,
            "score": round(float(item.score), 1),
            "trend": item.trend,
            "status": item.weakness_status,
        }
        for item in skills
    ]
    mistake_data = [
        {
            "skill": item.skill,
            "category": item.mistake_category,
            "description": item.description[:500],
            "evidence": item.evidence[:400] if item.evidence else None,
            "severity": item.severity,
            "recommendation": item.recommendation[:400] if item.recommendation else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in mistakes
    ]
    resume_data = None
    if resume_scan:
        resume_data = {
            "target_role": resume_scan.target_role,
            "match_score": round(float(
                resume_scan.overall_match_score
                if resume_scan.overall_match_score is not None
                else resume_scan.match_score
            ), 1) if (
                resume_scan.overall_match_score is not None
                or resume_scan.match_score is not None
            ) else None,
            "matched_skills": _split_stored_values(resume_scan.matched_skills)[:20],
            "missing_skills": _split_stored_values(resume_scan.missing_skills)[:20],
            "critical_gaps": _split_stored_values(resume_scan.critical_gaps)[:20],
            "recommendations": (resume_scan.recommendations or "")[:1000] or None,
        }

    completed_mocks = [
        item for item in mock_interviews
        if (item.status or "").lower() == "completed" and item.score is not None
    ]
    resume_score = resume_data["match_score"] if resume_data else None
    readiness = None
    if completed_mock_count or skill_score_count or (resume_score is not None and resume_score > 0):
        performance_total = (
            (float(average_completed_score) * completed_mock_count if average_completed_score is not None else 0)
            + (float(average_skill_score) * skill_score_count if average_skill_score is not None else 0)
        )
        performance_count = completed_mock_count + skill_score_count
        readiness = calculate_readiness(
            questions_count=sum(len(parse_raw_questions(item.questions or "")) for item in all_interviews),
            mocks_count=completed_mock_count,
            avg_score=performance_total / performance_count if performance_count else 0,
            resume_score=resume_score,
        )

    observed_scores = [
        (item.skill, float(item.score))
        for item in skills
        if item.score is not None
    ]
    for item in completed_mocks:
        observed_scores.extend([
            (name, float(score))
            for name, score in (
                ("Technical accuracy", item.technical_accuracy),
                ("Communication clarity", item.communication_clarity),
                ("STAR depth", item.star_depth),
                ("Problem solving", item.confidence_score),
            )
            if score is not None
        ])
    observed_scores = [(name, score) for name, score in observed_scores if score > 0]
    strengths = [
        {"area": name, "score": round(score, 1)}
        for name, score in observed_scores if score >= 80
    ][:6]
    improvement_areas = [
        {"area": name, "score": round(score, 1)}
        for name, score in sorted(observed_scores, key=lambda value: value[1])
        if score < 70
    ][:6]

    all_skills = list(dict.fromkeys(
        [item["skill"] for item in skill_data]
        + [skill for item in history_data for skill in item["skills"]]
        + (resume_data["matched_skills"] if resume_data else [])
    ))
    target_role = (
        resume_data["target_role"] if resume_data and resume_data["target_role"]
        else (history_data[0]["role"] if history_data
              else (mock_data[0]["role"] if mock_data else None))
    )
    return {
        "candidate": {
            "id": candidate.id,
            "name": candidate.full_name or candidate.email.split("@")[0],
            "email": candidate.email,
            "plan_tier": candidate.plan_tier,
            "target_role": target_role,
            "experience": history_data[0]["experience"] if history_data else None,
            "skills": all_skills[:30],
        },
        "interview_stats": {
            "total_interviews": total_mock_interviews,
            "completed_interviews": completed_mock_count,
            "question_sessions": len(all_interviews),
            "questions_generated": sum(len(parse_raw_questions(item.questions or "")) for item in all_interviews),
            "average_score": round(float(average_completed_score), 1) if average_completed_score is not None else None,
            "latest_score": round(float(latest_completed_score[0]), 1) if latest_completed_score and latest_completed_score[0] is not None else None,
        },
        "readiness": {
            "score": readiness,
            "has_sufficient_data": readiness is not None,
        },
        "strengths": strengths,
        "improvement_areas": improvement_areas,
        "skill_scores": skill_data,
        "mistakes": mistake_data,
        "recent_interviews": mock_data,
        "recent_questions": [
            {
                "role": item["role"],
                "question": question,
                "created_at": item["created_at"],
            }
            for item in history_data
            for question in item["questions"]
        ][:20],
        "recent_scorecards": [
            {
                key: value for key, value in item.items()
                if key not in {"turns", "transcript_summary"}
            }
            for item in mock_data if item["status"] == "completed"
        ],
        "resume_match": resume_data,
    }


def _format_candidate_context(context: dict) -> str:
    sections = [
        "Candidate profile:\n"
        f"- Target role: {context['candidate']['target_role'] or 'Not available'}\n"
        f"- Experience level from saved question practice: {context['candidate']['experience'] or 'Not available'}\n"
        f"- Skills recorded: {', '.join(context['candidate']['skills']) or 'Not available'}",
        "Interview statistics:\n"
        f"- Completed mock interviews: {context['interview_stats']['completed_interviews']}\n"
        f"- Generated question sessions: {context['interview_stats']['question_sessions']}\n"
        f"- Average completed score: {context['interview_stats']['average_score'] if context['interview_stats']['average_score'] is not None else 'Not available'}",
    ]
    if context["skill_scores"]:
        sections.append("Recorded skill scores:\n" + "\n".join(
            f"- {item['skill']}: {item['score']}/100 ({item['trend']}, {item['status']})"
            for item in context["skill_scores"]
        ))
    if context["mistakes"]:
        sections.append("Recorded interview feedback:\n" + "\n".join(
            f"- {item['skill']} ({item['severity']}): {item['description']}"
            for item in context["mistakes"]
        ))
    if context["recent_questions"]:
        sections.append("Recently generated interview questions:\n" + "\n".join(
            f"- [{item['role']}] {item['question']}"
            for item in context["recent_questions"][:10]
        ))
    mock_turns = [
        (interview["role"], turn)
        for interview in context["recent_interviews"]
        for turn in interview["turns"]
    ]
    if mock_turns:
        sections.append("Recent evaluated answers:\n" + "\n".join(
            f"- Role: {role}; question: {turn['question']}; answer: {turn['answer']}; "
            f"feedback: {turn['feedback']}; improvement: {'; '.join(turn['improvements'])}"
            for role, turn in mock_turns[-8:]
        ))
    transcript_summaries = [
        f"- Role: {item['role']}; transcript: {item['transcript_summary']}"
        for item in context["recent_interviews"]
        if item["transcript_summary"]
    ]
    if transcript_summaries:
        sections.append("Recent recorded mock-interview transcript excerpts:\n" + "\n".join(transcript_summaries))
    if context["recent_scorecards"]:
        sections.append("Recent completed scorecards:\n" + "\n".join(
            f"- {item['role']}: overall {item['score']}/100, technical "
            f"{item['technical_score']}, communication {item['communication_score']}, "
            f"STAR {item['star_score']}, problem solving {item['problem_solving_score']}"
            for item in context["recent_scorecards"][:5]
        ))
    if context["resume_match"]:
        sections.append(
            "Latest resume/JD match:\n"
            f"- Role: {context['resume_match']['target_role']}\n"
            f"- Match score: {context['resume_match']['match_score']}\n"
            f"- Matched skills: {', '.join(context['resume_match']['matched_skills']) or 'Not recorded'}\n"
            f"- Missing skills: {', '.join(context['resume_match']['missing_skills']) or 'Not recorded'}\n"
            f"- Critical gaps: {', '.join(context['resume_match']['critical_gaps']) or 'Not recorded'}"
        )
    return "\n\n".join(sections)


def generate_coach_reply(
    db: Session,
    candidate: UserAccount,
    prior_messages: List[Tuple[str, str]],
    message: str,
) -> str:
    context = _format_candidate_context(build_candidate_context(db, candidate))
    transcript = "\n".join(
        f"{'Candidate' if role == 'user' else 'Coach'}: {content[:2000]}"
        for role, content in prior_messages
    )
    prompt = f"""You are RaviGen AI Interview Coach, a supportive and practical interview-preparation coach.
Give specific, actionable advice. Use the candidate's saved practice data when relevant, but never invent scores, experience, or mistakes. If no data is available, say so and ask a focused question when needed. Keep replies clear and appropriately concise.

Candidate: {candidate.full_name or "Candidate"}

Existing candidate practice data:
{context}

Conversation so far:
{transcript or "(This is the first message.)"}

Candidate's latest message:
{message}

Respond as the interview coach. Refer only to evidence in the saved data above. If it is absent, explicitly say you do not have that information and ask a useful follow-up. Do not infer or invent a performance score. If there is not yet any completed interview data, say: "You don't have enough completed interview data yet. Complete a mock interview and I'll analyze it here." Be supportive and specific; provide a readiness number only when the stored readiness score is available."""

    try:
        reply = generate_ai_questions(prompt)
    except Exception:
        logger.exception("Interview Coach provider request failed for user_id=%s", candidate.id)
        raise

    if not reply or not reply.strip():
        logger.error("Interview Coach provider returned an empty response for user_id=%s", candidate.id)
        raise RuntimeError("The AI Coach returned an empty response.")

    return reply.strip()
