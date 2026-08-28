"""
Adaptive Candidate Profile Service Layer
Computes multi-factor, explainable, and deterministic Adaptive Profiles for candidates.
"""
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import re
import json

from app.db_models import (
    UserAccount,
    InterviewHistory,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
    MockInterview,
    ResumeScan
)
from app.models import (
    InterviewRequest,
    AdaptiveProfileResponse,
    ProfileStrengthItem,
    ProfileFocusAreaItem,
    ProfileOpenMistakeItem,
    ProfileRecommendedFocus,
    AdaptiveQuestionItem,
    AdaptiveGenerateResponse,
    EvaluateResponseRequest,
    ResponseEvaluationResult,
    SkillScoreItem,
    DetectedMistakeItem,
    NextQuestionRequest,
    AdaptiveNextQuestionResponse,
    AdaptiveFromMatchRequest,
    AdaptiveFromMatchResponse
)
from fastapi import HTTPException
from app.prompts import interview_prompt
from app.services import generate_ai_questions, parse_raw_questions, get_fallback_questions

# Role Importance Tiers
ROLE_IMPORTANCE_HIGH = 1.0     # Core role pillar: fatal if weak
ROLE_IMPORTANCE_MEDIUM = 0.6   # Supporting competency: important but recoverable
ROLE_IMPORTANCE_LOW = 0.3      # Peripheral / Adjacent: nice-to-have bonus


def get_candidate_adaptive_profile(user: UserAccount, db: Session) -> AdaptiveProfileResponse:
    """
    Computes a comprehensive, explainable Adaptive Candidate Profile for the authenticated candidate.
    
    Answers:
    1. What is the candidate's current interview readiness?
    2. What are the candidate's strongest skills?
    3. What are the candidate's weakest skills / focus areas?
    4. Which weaknesses are persistent?
    5. Which skills are improving?
    6. Which mistakes remain unresolved?
    7. What should the candidate focus on next?
    """
    if not user or not user.id:
        return AdaptiveProfileResponse(
            readiness_score=None,
            profile_status="insufficient_data",
            interview_count=0,
            last_interview_score=None,
            improvement_since_first_interview=None,
            strengths=[],
            focus_areas=[],
            open_mistakes=[],
            recommended_focus=None
        )

    # 1. Fetch historical mock interviews, interview history, skill analytics, and mistakes ledger
    try:
        mock_interviews = db.query(MockInterview).filter(MockInterview.user_id == user.id).order_by(MockInterview.created_at.asc()).all()
    except Exception:
        mock_interviews = []

    try:
        interview_history = db.query(InterviewHistory).filter(InterviewHistory.user_id == user.id).order_by(InterviewHistory.created_at.asc()).all()
    except Exception:
        interview_history = []

    try:
        skills_analytics = db.query(CandidateSkillAnalytics).filter(CandidateSkillAnalytics.user_id == user.id).all()
    except Exception:
        skills_analytics = []

    try:
        mistakes = db.query(CandidateMistakesLedger).filter(CandidateMistakesLedger.user_id == user.id).order_by(CandidateMistakesLedger.created_at.desc()).all()
    except Exception:
        mistakes = []

    # 2. Check for empty / new user behavior
    total_interviews = len(mock_interviews) + len(interview_history)
    has_skills_data = len(skills_analytics) > 0
    has_mock_data = len(mock_interviews) > 0
    has_mistakes_data = len(mistakes) > 0

    if total_interviews == 0 and not has_skills_data and not has_mock_data and not has_mistakes_data:
        return AdaptiveProfileResponse(
            readiness_score=None,
            profile_status="insufficient_data",
            interview_count=0,
            last_interview_score=None,
            improvement_since_first_interview=None,
            strengths=[],
            focus_areas=[],
            open_mistakes=[],
            recommended_focus=None
        )

    # 3. Calculate Interview Count, Last Score & Longitudinal Improvement
    interview_count = len(mock_interviews) if has_mock_data else len(interview_history)
    last_interview_score: Optional[float] = None
    improvement_since_first_interview: Optional[float] = None

    if has_mock_data:
        first_score = mock_interviews[0].score
        last_score = mock_interviews[-1].score
        last_interview_score = round(float(last_score), 1)
        if len(mock_interviews) >= 2:
            improvement_since_first_interview = round(float(last_score - first_score), 1)
        else:
            improvement_since_first_interview = 0.0

    # 4. Filter Open Mistakes (exclude resolved mistakes from active open_mistakes list)
    open_mistakes: List[ProfileOpenMistakeItem] = []
    mistake_counts_by_skill: Dict[str, int] = {}
    for m in mistakes:
        if m.mistake_status in ["identified", "practicing"]:
            open_mistakes.append(ProfileOpenMistakeItem(
                id=m.id,
                skill=m.skill,
                category=m.mistake_category,
                description=m.description,
                severity=m.severity,
                status=m.mistake_status,
                created_at=m.created_at.isoformat() if m.created_at else datetime.utcnow().isoformat()
            ))
            mistake_counts_by_skill[m.skill.lower().strip()] = mistake_counts_by_skill.get(m.skill.lower().strip(), 0) + 1

    # 5. Classify Strengths and Focus Areas (Weaknesses)
    strengths: List[ProfileStrengthItem] = []
    focus_areas: List[ProfileFocusAreaItem] = []

    for s in skills_analytics:
        skill_name = s.skill
        score = float(s.score)
        trend = s.trend or "flat"
        confidence = s.confidence or "LOW"
        evidence_count = int(s.evidence_count or 1)
        status = s.weakness_status or "identified"
        role_relevance = float(s.role_relevance if s.role_relevance is not None else 1.0)

        # STRENGTH CLASSIFICATION:
        # Requires: score >= 75.0, evidence_count >= 2 (sufficient evidence), status != "identified"
        if score >= 75.0 and evidence_count >= 2 and status != "identified":
            strengths.append(ProfileStrengthItem(
                skill=skill_name,
                score=round(score, 1),
                trend=trend,
                confidence=confidence,
                evidence_count=evidence_count,
                role_relevance=role_relevance
            ))
        
        # FOCUS AREA (WEAKNESS) CLASSIFICATION:
        # Non-resolved weaknesses, OR score < 75 with evidence, OR active open mistakes
        skill_key = skill_name.lower().strip()
        has_open_mistakes = mistake_counts_by_skill.get(skill_key, 0) > 0

        if status in ["identified", "practicing", "improving"] or (score < 75.0 and status != "resolved") or has_open_mistakes:
            # If status was resolved, do not show in active focus areas unless regression
            if status != "resolved":
                focus_areas.append(ProfileFocusAreaItem(
                    skill=skill_name,
                    score=round(score, 1),
                    trend=trend,
                    confidence=confidence,
                    evidence_count=evidence_count,
                    status=status,
                    role_relevance=role_relevance
                ))

    # Sort strengths descending by (score * role_relevance)
    strengths.sort(key=lambda item: item.score * (item.role_relevance or 1.0), reverse=True)

    # 6. Calculate Readiness Score
    # Considers skill scores weighted by role relevance, combined with mock performance if available
    readiness_score: Optional[float] = None
    if skills_analytics:
        total_weighted_score = sum(float(s.score) * float(s.role_relevance if s.role_relevance is not None else 1.0) for s in skills_analytics)
        total_weight = sum(float(s.role_relevance if s.role_relevance is not None else 1.0) for s in skills_analytics)
        weighted_skill_avg = total_weighted_score / total_weight if total_weight > 0 else 70.0

        if last_interview_score is not None:
            readiness_score = round(0.6 * weighted_skill_avg + 0.4 * last_interview_score, 1)
        else:
            readiness_score = round(weighted_skill_avg, 1)
    elif last_interview_score is not None:
        readiness_score = last_interview_score

    # Profile Status
    profile_status = "ready" if (readiness_score is not None or len(strengths) > 0 or len(focus_areas) > 0 or len(open_mistakes) > 0) else "insufficient_data"

    # 7. Determine ONE Primary Recommended Focus Area
    # Prioritization: role_importance * (100 - score) * trend_multiplier * confidence_multiplier + open_mistake_bonus
    recommended_focus: Optional[ProfileRecommendedFocus] = None

    if focus_areas or open_mistakes:
        candidates_pool = []
        for fa in focus_areas:
            role_rel = fa.role_relevance if fa.role_relevance is not None else 1.0
            gap = max(0.0, 100.0 - fa.score)
            
            trend_mult = 1.3 if fa.trend == "declining" else (1.1 if fa.trend == "flat" else 0.8)
            conf_mult = 1.2 if fa.confidence == "HIGH" else (1.0 if fa.confidence == "MEDIUM" else 0.8)
            
            skill_k = fa.skill.lower().strip()
            mistake_bonus = 15.0 if mistake_counts_by_skill.get(skill_k, 0) > 0 else 0.0

            priority_score = (role_rel * gap * trend_mult * conf_mult) + mistake_bonus

            # Build explainable reason
            reasons = []
            if role_rel >= 0.9:
                reasons.append("Core role requirement")
            if fa.trend == "declining":
                reasons.append("declining performance trend")
            elif fa.trend == "flat" and fa.evidence_count >= 2:
                reasons.append(f"repeated weakness across {fa.evidence_count} sessions")
            if mistake_bonus > 0:
                reasons.append("unresolved logged mistakes")
            if not reasons:
                reasons.append("targeted practice needed to reach hiring bar")

            reason_str = "; ".join(reasons).capitalize() + "."

            # Priority level
            priority_tier = "high" if priority_score >= 45.0 else ("medium" if priority_score >= 25.0 else "low")

            candidates_pool.append({
                "skill": fa.skill,
                "priority_score": priority_score,
                "reason": reason_str,
                "priority": priority_tier
            })

        if candidates_pool:
            candidates_pool.sort(key=lambda x: x["priority_score"], reverse=True)
            top = candidates_pool[0]
            recommended_focus = ProfileRecommendedFocus(
                skill=top["skill"],
                reason=top["reason"],
                priority=top["priority"]
            )
        elif open_mistakes:
            top_m = open_mistakes[0]
            recommended_focus = ProfileRecommendedFocus(
                skill=top_m.skill,
                reason="Unresolved concept mistake logged in recent session.",
                priority="high" if top_m.severity in ["high", "critical"] else "medium"
            )

    return AdaptiveProfileResponse(
        readiness_score=readiness_score,
        profile_status=profile_status,
        interview_count=interview_count,
        last_interview_score=last_interview_score,
        improvement_since_first_interview=improvement_since_first_interview,
        strengths=strengths,
        focus_areas=focus_areas,
        open_mistakes=open_mistakes,
        recommended_focus=recommended_focus
    )


def generate_adaptive_question_package(
    data: InterviewRequest,
    user: UserAccount,
    db: Session
) -> AdaptiveGenerateResponse:
    """
    Generates personalized, high-signal interview/practice questions using the candidate's
    Adaptive Profile, targeting the highest-priority weakness/mistake while preventing duplication.
    """
    # 1. Establish session lineage
    adaptive_session_id = getattr(data, "adaptive_session_id", None) or f"asess_{uuid.uuid4().hex[:12]}"
    target_count = data.number_of_questions or 5

    # 2. Retrieve candidate's Adaptive Profile
    profile = get_candidate_adaptive_profile(user, db)
    profile_status = profile.profile_status

    # 3. Determine target skill, focus skill, reason, and evidence reference
    target_skill = ""
    focus_skill = ""
    reason = "role_requirement"
    source = "adaptive_profile"
    evidence_reference = None

    if profile.recommended_focus and profile.focus_areas:
        target_skill = profile.recommended_focus.skill
        # Find matching focus area
        matched_fa = next((fa for fa in profile.focus_areas if fa.skill.lower() == target_skill.lower()), None)
        if not matched_fa and profile.focus_areas:
            matched_fa = profile.focus_areas[0]
            target_skill = matched_fa.skill

        # Check if there are open mistakes for this skill
        matched_mistake = next((m for m in profile.open_mistakes if m.skill.lower() == target_skill.lower()), None)

        if matched_mistake:
            reason = "previous_mistake"
            source = "mistakes_ledger"
            focus_skill = matched_mistake.category or "Remediation"
            evidence_reference = {
                "skill": matched_mistake.skill,
                "mistake_description": matched_mistake.description,
                "severity": matched_mistake.severity,
                "status": matched_mistake.status
            }
        elif matched_fa:
            reason = "candidate_weakness"
            focus_skill = "Core Nuance"
            evidence_reference = {
                "skill": matched_fa.skill,
                "score": matched_fa.score,
                "evidence_count": matched_fa.evidence_count,
                "confidence": matched_fa.confidence,
                "status": matched_fa.status
            }
    elif profile.open_mistakes:
        matched_mistake = profile.open_mistakes[0]
        target_skill = matched_mistake.skill
        reason = "previous_mistake"
        source = "mistakes_ledger"
        focus_skill = matched_mistake.category or "Remediation"
        evidence_reference = {
            "skill": matched_mistake.skill,
            "mistake_description": matched_mistake.description,
            "severity": matched_mistake.severity,
            "status": matched_mistake.status
        }
    else:
        # New candidate / insufficient data fallback
        profile_status = "insufficient_data"
        target_skill = (data.skills[0] if data.skills else data.role)
        focus_skill = "Core Principles"
        reason = "role_requirement"
        source = "baseline_generator"
        evidence_reference = None

    # Check custom_question / practice_goal overrides
    if getattr(data, "custom_question", None) and getattr(data, "custom_question", "").strip():
        reason = "practice_goal"
        focus_skill = data.custom_question.strip()

    # 4. Anti-Duplication: Retrieve candidate's recent questions
    recent_fingerprints = set()
    try:
        past_sittings = db.query(InterviewHistory).filter(InterviewHistory.user_id == user.id).order_by(InterviewHistory.created_at.desc()).limit(5).all()
        for sitting in past_sittings:
            if sitting.questions:
                for q_line in sitting.questions.split("\n"):
                    clean_fp = re.sub(r"[^a-zA-Z0-9]", "", q_line.lower())[:40]
                    if clean_fp:
                        recent_fingerprints.add(clean_fp)
    except Exception:
        pass

    # 5. Build Adaptive Prompt
    base_prompt = interview_prompt(data)
    adaptive_context = f"""
================================================================================
ADAPTIVE INTERVIEW CONTEXT (PERSONALIZED CANDIDATE TELEMETRY):
- Target Improvement Skill: {target_skill}
- Focus Nuance: {focus_skill}
- Trigger Driver: {reason}
- Readiness Score: {profile.readiness_score or 'Calibrating'}
- Target Company Bar: {getattr(data, 'company', 'General Tech')}
- Target Round Format: {getattr(data, 'interview_type', 'Technical & Architecture')}

ADAPTIVE GENERATION DIRECTIVES:
1. Target at least 60% of the {target_count} questions specifically to drill, probe, and test improvement in "{target_skill}".
2. Questions must be deep, practical, and explore real-world scenarios, trade-offs, and failure recovery.
3. The remaining questions should cover comprehensive role competencies for {data.role} ({data.experience}).
================================================================================
"""
    full_prompt = base_prompt + "\n" + adaptive_context

    # 6. Execute AI Generation with Multi-Tier Fallback
    raw_questions: List[str] = []
    try:
        ai_output = generate_ai_questions(full_prompt)
        raw_questions = parse_raw_questions(ai_output, target_count=target_count)
    except Exception as ai_err:
        print(f"[Adaptive Generator] LLM unavailable/fallback: {ai_err}")
        raw_questions = get_fallback_questions(
            data.role, data.skills, target_count, custom_q=target_skill
        )

    # If parsing returned insufficient questions, top up from fallback bank
    if len(raw_questions) < target_count:
        fallback = get_fallback_questions(data.role, data.skills, target_count, custom_q=target_skill)
        for q in fallback:
            if q not in raw_questions:
                raw_questions.append(q)

    # 7. Deduplicate against recent questions
    final_questions: List[str] = []
    for q in raw_questions:
        q_fp = re.sub(r"[^a-zA-Z0-9]", "", q.lower())[:40]
        if q_fp not in recent_fingerprints or len(final_questions) == 0:
            final_questions.append(q)
        else:
            # If duplicate, retrieve an alternative from fallback bank
            alt_candidates = get_fallback_questions(data.role, data.skills, target_count + 5, custom_q=target_skill)
            for alt in alt_candidates:
                alt_fp = re.sub(r"[^a-zA-Z0-9]", "", alt.lower())[:40]
                if alt_fp not in recent_fingerprints and alt not in final_questions:
                    final_questions.append(alt)
                    break
            else:
                final_questions.append(q)

    final_questions = final_questions[:target_count]

    # 8. Enrich Questions with Metadata
    enriched_questions: List[AdaptiveQuestionItem] = []
    diff = data.difficulty or "Hard"

    for i, q_text in enumerate(final_questions):
        # The first majority are weakness-targeted; the remainder are core role pillars
        q_reason = reason if i < max(1, int(target_count * 0.6)) else "role_requirement"
        q_target = target_skill if i < max(1, int(target_count * 0.6)) else (data.skills[0] if data.skills else data.role)
        q_focus = focus_skill if i < max(1, int(target_count * 0.6)) else "Role Mastery"
        q_source = source if i < max(1, int(target_count * 0.6)) else "role_matrix"
        q_evidence = evidence_reference if i < max(1, int(target_count * 0.6)) else None

        enriched_questions.append(AdaptiveQuestionItem(
            question=q_text,
            reason=q_reason,
            source=q_source,
            target_skill=q_target,
            focus_skill=q_focus,
            difficulty=diff,
            evidence_reference=q_evidence,
            question_engine_version="adaptive-qengine-v1.0.0"
        ))

    # 9. Lightweight Persistence in interview_history
    try:
        formatted_raw = "\n".join([f"{i+1}. {q.question}" for i, q in enumerate(enriched_questions)])
        history_record = InterviewHistory(
            user_id=user.id,
            adaptive_session_id=adaptive_session_id,
            role=data.role,
            experience=data.experience or "3-5 Years",
            skills=", ".join(data.skills or []),
            difficulty=data.difficulty or "Hard",
            questions=formatted_raw,
            question_engine_version="adaptive-qengine-v1.0.0",
            created_at=datetime.utcnow()
        )
        db.add(history_record)
        db.commit()
    except Exception as db_err:
        print(f"[Adaptive Persistence Warning] {db_err}")
        db.rollback()

    return AdaptiveGenerateResponse(
        adaptive_session_id=adaptive_session_id,
        profile_status=profile_status,
        recommended_focus=profile.recommended_focus,
        questions=enriched_questions
    )


def evaluate_candidate_response(
    payload: EvaluateResponseRequest,
    user: UserAccount,
    db: Session
) -> ResponseEvaluationResult:
    """
    Evaluates one candidate response against question target skill, focus skill, role,
    and expected answer signals. Updates candidate_skill_analytics and candidate_mistakes_ledger.
    """
    adaptive_session_id = payload.adaptive_session_id or f"asess_{uuid.uuid4().hex[:12]}"
    target_skill = (payload.target_skill or "General Competency").strip()
    focus_skill = (payload.focus_skill or "Core Principles").strip()
    candidate_resp = (payload.candidate_response or "").strip()
    question = (payload.question or "").strip()
    role = (payload.role or "Software Engineer").strip()
    difficulty = payload.difficulty or "Hard"

    # 1. Build Evaluation Prompt for LLM
    eval_prompt = f"""
You are a Principal Bar Raiser evaluating a candidate's response to an interview question.

QUESTION:
"{question}"

CANDIDATE TARGET ROLE: {role} (Difficulty: {difficulty})
PRIMARY TARGET SKILL: {target_skill} (Nuance / Focus: {focus_skill})
EXPECTED SIGNALS: {", ".join(payload.expected_signals) if payload.expected_signals else "Practical trade-offs, correct technical reasoning, clear structure, edge cases"}

CANDIDATE'S ACTUAL RESPONSE:
\"\"\"
{candidate_resp}
\"\"\"

EVALUATION RUBRIC:
1. Relevance & Correctness (Does the answer address the question accurately?)
2. Technical Depth & Trade-offs (Are architectural decisions, scale considerations, and edge cases handled?)
3. Structure & Framing (STAR framing or logical, structured explanation)
4. Target Skill Competency ({target_skill})

OUTPUT STRICT REQUIREMENTS:
Output ONLY a valid JSON object matching this schema with NO markdown preamble:
{{
  "overall_score": <number 0-100>,
  "skill_scores": [
    {{"skill": "{target_skill}", "score": <number 0-100>, "evidence": "<exact quote or specific observation from response>", "confidence": "HIGH"}},
    {{"skill": "Technical Depth", "score": <number 0-100>, "evidence": "<observation>", "confidence": "MEDIUM"}}
  ],
  "good_signals": ["<specific positive signal 1>", "<specific positive signal 2>"],
  "missing_signals": ["<specific missing signal 1>"],
  "red_flags": ["<specific red flag or empty list>"],
  "mistakes": [
    {{
      "skill": "{target_skill}",
      "category": "<e.g. STAR_framing, edge_cases, concurrency, validation, scalability>",
      "severity": "<low|medium|high|critical>",
      "description": "<specific mistake description>",
      "recommendation": "<concrete actionable remediation>"
    }}
  ],
  "summary": "<Concise 2-sentence summary of performance and key gap>"
}}
"""

    eval_data = None
    try:
        raw_output = generate_ai_questions(eval_prompt)
        json_match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if json_match:
            eval_data = json.loads(json_match.group(0))
    except Exception as ai_err:
        print(f"[Adaptive Evaluator] LLM evaluation fallback triggered: {ai_err}")

    # Fallback heuristic evaluation if AI unavailable
    if not eval_data:
        word_count = len(candidate_resp.split())
        has_keywords = any(kw.lower() in candidate_resp.lower() for kw in target_skill.split())

        if word_count < 10:
            eval_score = 42.0
            good_signals = []
            missing_signals = ["Detailed technical explanation", "Concrete implementation steps", "Trade-off analysis"]
            red_flags = ["Superficial answer lacking substance"]
            mistakes = [
                DetectedMistakeItem(
                    skill=target_skill,
                    category="insufficient_depth",
                    severity="medium",
                    description="Response is too brief and lacks concrete architectural or implementation detail.",
                    recommendation="Elaborate on specific mechanisms, trade-offs, and measurable outcomes."
                )
            ]
            summary = "The response is overly brief and lacks required technical depth and context."
        elif word_count < 25 or not has_keywords:
            eval_score = 64.0
            good_signals = ["Attempted direct answer"]
            missing_signals = ["Structured trade-off discussion", "Failure mode considerations"]
            red_flags = []
            mistakes = [
                DetectedMistakeItem(
                    skill=target_skill,
                    category="shallow_framing",
                    severity="medium",
                    description="Answer mentions high-level concepts without probing underlying trade-offs.",
                    recommendation="Structure answer to clearly state the problem context, chosen solution, and trade-offs."
                )
            ]
            summary = f"Good initial framing, but requires deeper exploration of {target_skill} trade-offs."
        else:
            eval_score = 85.0
            good_signals = ["Thorough explanation", "Addressed core technical mechanics", "Clear logical flow"]
            missing_signals = []
            red_flags = []
            mistakes = []
            summary = f"Strong and coherent response demonstrating practical understanding of {target_skill}."

        eval_data = {
            "overall_score": eval_score,
            "skill_scores": [
                {
                    "skill": target_skill,
                    "score": eval_score,
                    "evidence": candidate_resp[:120] if candidate_resp else "No response provided",
                    "confidence": "HIGH" if word_count > 30 else "MEDIUM"
                }
            ],
            "good_signals": good_signals,
            "missing_signals": missing_signals,
            "red_flags": red_flags,
            "mistakes": [m.dict() for m in mistakes],
            "summary": summary
        }

    overall_score = float(eval_data.get("overall_score", 70.0))
    skill_scores_raw = eval_data.get("skill_scores", [])
    good_signals = eval_data.get("good_signals", [])
    missing_signals = eval_data.get("missing_signals", [])
    red_flags = eval_data.get("red_flags", [])
    mistakes_raw = eval_data.get("mistakes", [])
    summary = eval_data.get("summary", "Evaluation complete.")

    parsed_skill_scores = [
        SkillScoreItem(
            skill=s.get("skill", target_skill),
            score=float(s.get("score", overall_score)),
            evidence=str(s.get("evidence", "")),
            confidence=str(s.get("confidence", "MEDIUM"))
        )
        for s in skill_scores_raw
    ]
    if not parsed_skill_scores:
        parsed_skill_scores.append(
            SkillScoreItem(skill=target_skill, score=overall_score, evidence=candidate_resp[:100], confidence="MEDIUM")
        )

    parsed_mistakes = [
        DetectedMistakeItem(
            skill=m.get("skill", target_skill),
            category=m.get("category", "conceptual"),
            severity=m.get("severity", "medium"),
            description=m.get("description", "Identified gap in answer"),
            recommendation=m.get("recommendation", "Review core principles")
        )
        for m in mistakes_raw
    ]

    # 2. Update candidate_mistakes_ledger in DB
    try:
        for mistake_obj in parsed_mistakes:
            existing_mistake = db.query(CandidateMistakesLedger).filter(
                CandidateMistakesLedger.user_id == user.id,
                CandidateMistakesLedger.skill == mistake_obj.skill,
                CandidateMistakesLedger.mistake_status.in_(["identified", "practicing"])
            ).first()

            if existing_mistake:
                # Update existing mistake evidence and maintain practicing state
                existing_mistake.evidence = f"{existing_mistake.evidence or ''}\nRepeat observation: {mistake_obj.description}".strip()
                existing_mistake.mistake_status = "practicing"
                existing_mistake.severity = mistake_obj.severity
                existing_mistake.recommendation = mistake_obj.recommendation
            else:
                # Create new mistake record
                new_mistake = CandidateMistakesLedger(
                    user_id=user.id,
                    adaptive_session_id=adaptive_session_id,
                    skill=mistake_obj.skill,
                    mistake_category=mistake_obj.category,
                    description=mistake_obj.description,
                    evidence=mistake_obj.description,
                    severity=mistake_obj.severity,
                    recommendation=mistake_obj.recommendation,
                    mistake_status="identified",
                    evaluation_version="eval-v1.2.0",
                    created_at=datetime.utcnow()
                )
                db.add(new_mistake)

        # If candidate scored high on target_skill and produced no mistakes, resolve existing open mistakes for that skill
        if overall_score >= 80.0 and len(parsed_mistakes) == 0:
            open_m = db.query(CandidateMistakesLedger).filter(
                CandidateMistakesLedger.user_id == user.id,
                CandidateMistakesLedger.skill == target_skill,
                CandidateMistakesLedger.mistake_status.in_(["identified", "practicing"])
            ).all()
            for m in open_m:
                m.mistake_status = "resolved"
                m.resolved_at = datetime.utcnow()

        db.commit()
    except Exception as m_err:
        print(f"[Adaptive Mistake Ledger Warning] {m_err}")
        db.rollback()

    # 3. Update candidate_skill_analytics in DB
    try:
        for sk_item in parsed_skill_scores:
            existing_skill = db.query(CandidateSkillAnalytics).filter(
                CandidateSkillAnalytics.user_id == user.id,
                CandidateSkillAnalytics.skill == sk_item.skill
            ).first()

            if existing_skill:
                new_evidence_count = existing_skill.evidence_count + 1
                # Moving weighted average
                new_score = round(existing_skill.score * 0.4 + sk_item.score * 0.6, 1)

                # Trend calculation
                if new_score > existing_skill.score + 5:
                    new_trend = "improving"
                elif new_score < existing_skill.score - 5:
                    new_trend = "declining"
                else:
                    new_trend = "flat"

                # Confidence calculation
                if new_evidence_count >= 4:
                    new_confidence = "HIGH"
                elif new_evidence_count >= 2:
                    new_confidence = "MEDIUM"
                else:
                    new_confidence = "LOW"

                # Weakness lifecycle transition
                if new_score >= 80.0 and new_evidence_count >= 4:
                    new_status = "resolved"
                elif new_score >= 75.0 and new_evidence_count >= 2:
                    new_status = "improving"
                elif new_score < 70.0:
                    if existing_skill.weakness_status in ["improving", "resolved"]:
                        new_status = "practicing"
                    else:
                        new_status = "identified"
                else:
                    new_status = existing_skill.weakness_status

                existing_skill.score = new_score
                existing_skill.trend = new_trend
                existing_skill.confidence = new_confidence
                existing_skill.evidence_count = new_evidence_count
                existing_skill.weakness_status = new_status
                existing_skill.adaptive_session_id = adaptive_session_id
                existing_skill.last_updated_at = datetime.utcnow()
            else:
                new_status = "improving" if sk_item.score >= 75.0 else "identified"
                new_skill_record = CandidateSkillAnalytics(
                    user_id=user.id,
                    skill=sk_item.skill,
                    score=sk_item.score,
                    trend="flat",
                    role_relevance=ROLE_IMPORTANCE_HIGH,
                    evidence_count=1,
                    confidence="LOW",
                    weakness_status=new_status,
                    adaptive_session_id=adaptive_session_id,
                    first_detected_at=datetime.utcnow(),
                    last_updated_at=datetime.utcnow()
                )
                db.add(new_skill_record)

        db.commit()
    except Exception as s_err:
        print(f"[Adaptive Skill Analytics Warning] {s_err}")
        db.rollback()

    return ResponseEvaluationResult(
        adaptive_session_id=adaptive_session_id,
        evaluation_version="eval-v1.2.0",
        overall_score=overall_score,
        skill_scores=parsed_skill_scores,
        good_signals=good_signals,
        missing_signals=missing_signals,
        red_flags=red_flags,
        mistakes=parsed_mistakes,
        summary=summary
    )


def determine_adaptive_next_question(
    payload: NextQuestionRequest,
    user: UserAccount,
    db: Session
) -> AdaptiveNextQuestionResponse:
    """
    Determines the next best question after the candidate's latest response,
    choosing strategy based on candidate performance, recurring mistakes,
    or advancing to the next priority weakness.
    """
    adaptive_session_id = payload.adaptive_session_id or f"asess_{uuid.uuid4().hex[:12]}"
    role = payload.role or "Software Engineer"
    exp = payload.experience or "3-5 Years"
    current_diff = payload.difficulty or "Hard"

    # 1. Fetch Fresh Adaptive Profile
    profile = get_candidate_adaptive_profile(user, db)

    # 2. Evaluate performance signals from latest evaluation
    latest_eval = payload.latest_evaluation
    eval_score = latest_eval.overall_score if latest_eval else 70.0
    detected_mistakes = latest_eval.mistakes if latest_eval else []

    current_target = payload.current_target_skill or (profile.recommended_focus.skill if profile.recommended_focus else (payload.skills[0] if payload.skills else role))

    strategy = "continue_probing"
    target_skill = current_target
    focus_skill = "Core Principles"
    reason = "candidate_weakness"
    source = "adaptive_profile"
    evidence_reference = None
    next_diff = current_diff

    # 3. Decision Branching
    # Case B: Recurring or newly detected mistake -> Follow-up targeted at correcting the mistake
    if detected_mistakes:
        top_mistake = detected_mistakes[0]
        strategy = "mistake_follow_up"
        target_skill = top_mistake.skill
        focus_skill = top_mistake.category
        reason = "previous_mistake"
        source = "mistakes_ledger"
        evidence_reference = {
            "skill": top_mistake.skill,
            "mistake_description": top_mistake.description,
            "severity": top_mistake.severity,
            "status": "practicing"
        }
    # Case D / E: Strong performance or target weakness resolved/improving -> Advance to recommended focus
    elif eval_score >= 80.0 and profile.recommended_focus and profile.recommended_focus.skill.lower() != current_target.lower():
        strategy = "advance_next_weakness"
        target_skill = profile.recommended_focus.skill
        focus_skill = "Nuance & Principles"
        reason = "candidate_weakness"
        source = "adaptive_profile"
        matching_fa = next((fa for fa in profile.focus_areas if fa.skill.lower() == target_skill.lower()), None)
        if matching_fa:
            evidence_reference = {
                "skill": matching_fa.skill,
                "score": matching_fa.score,
                "evidence_count": matching_fa.evidence_count,
                "confidence": matching_fa.confidence,
                "status": matching_fa.status
            }
    elif eval_score >= 82.0 and profile.focus_areas and any(fa.skill.lower() == current_target.lower() and fa.status in ["improving", "resolved"] for fa in profile.focus_areas):
        next_fa = next((fa for fa in profile.focus_areas if fa.skill.lower() != current_target.lower() and fa.status != "resolved"), None)
        if next_fa:
            strategy = "advance_next_weakness"
            target_skill = next_fa.skill
            focus_skill = "Nuance & Principles"
            reason = "candidate_weakness"
            source = "adaptive_profile"
            evidence_reference = {
                "skill": next_fa.skill,
                "score": next_fa.score,
                "evidence_count": next_fa.evidence_count,
                "confidence": next_fa.confidence,
                "status": next_fa.status
            }
        else:
            strategy = "advance_next_weakness"
            target_skill = (payload.skills[1] if payload.skills and len(payload.skills) > 1 else role)
            focus_skill = "Architecture & Systems"
            reason = "role_requirement"
            source = "role_matrix"
    # Case C: Single high score on target skill -> Scale difficulty
    elif eval_score >= 80.0:
        strategy = "scale_difficulty"
        target_skill = current_target
        focus_skill = "Complex High-Scale Scenario"
        reason = "candidate_weakness"
        source = "adaptive_profile"
        diff_progression = {"Easy": "Medium", "Medium": "Hard", "Hard": "Brutal", "Brutal": "Brutal"}
        next_diff = diff_progression.get(current_diff, "Hard")
    # Case A: Poor score (<70) on target skill -> Continue probing same weakness
    elif eval_score < 70.0:
        strategy = "continue_probing"
        target_skill = current_target
        focus_skill = "Trade-offs & Edge Cases"
        reason = "candidate_weakness"
        source = "adaptive_profile"
        matching_fa = next((fa for fa in profile.focus_areas if fa.skill.lower() == current_target.lower()), None)
        if matching_fa:
            evidence_reference = {
                "skill": matching_fa.skill,
                "score": matching_fa.score,
                "evidence_count": matching_fa.evidence_count,
                "confidence": matching_fa.confidence,
                "status": matching_fa.status
            }
    else:
        strategy = "baseline_exploration"
        target_skill = current_target
        reason = "role_requirement"
        source = "baseline_generator"

    # 4. Anti-Duplication: Retrieve previous questions
    recent_fingerprints = set()
    if payload.previous_question:
        recent_fingerprints.add(re.sub(r"[^a-zA-Z0-9]", "", payload.previous_question.lower())[:40])
    try:
        past_sittings = db.query(InterviewHistory).filter(InterviewHistory.user_id == user.id).order_by(InterviewHistory.created_at.desc()).limit(5).all()
        for sitting in past_sittings:
            if sitting.questions:
                for q_line in sitting.questions.split("\n"):
                    clean_fp = re.sub(r"[^a-zA-Z0-9]", "", q_line.lower())[:40]
                    if clean_fp:
                        recent_fingerprints.add(clean_fp)
    except Exception:
        pass

    # 5. Generate Next Question via Prompt
    question_text = ""
    next_q_prompt = f"""
You are an expert interviewer conducting an adaptive interview for a {role} ({exp}, Level: {next_diff}).

CONTEXT:
- Target Skill to Probe: {target_skill} (Focus: {focus_skill})
- Strategy: {strategy} (Driver Reason: {reason})
- Previous Question Asked: "{payload.previous_question or 'N/A'}"
- Candidate Previous Response Score: {eval_score}%
{f"- Previous Detected Mistake: {detected_mistakes[0].description}" if detected_mistakes else ""}

TASK:
Generate EXACTLY 1 new, highly focused interview question that executes this strategy ({strategy}).
CRITICAL RULES:
- Do NOT repeat or duplicate the previous question.
- If strategy is "mistake_follow_up", explicitly test whether the candidate corrects the identified mistake.
- If strategy is "scale_difficulty", present a complex, high-concurrency or ambiguous scenario.
- Return ONLY the question text on a single line with NO numbering or preamble.
"""

    try:
        raw_output = generate_ai_questions(next_q_prompt)
        parsed = parse_raw_questions(raw_output, target_count=1)
        if parsed:
            question_text = parsed[0]
    except Exception as ai_err:
        print(f"[Adaptive Next Question] LLM fallback: {ai_err}")

    # Fallback to offline question bank if AI fails
    if not question_text:
        fallback_qs = get_fallback_questions(role, [target_skill], count=3, custom_q=target_skill)
        for fb_q in fallback_qs:
            fb_fp = re.sub(r"[^a-zA-Z0-9]", "", fb_q.lower())[:40]
            if fb_fp not in recent_fingerprints:
                question_text = fb_q
                break
        if not question_text:
            question_text = f"Can you walk me through a challenging scenario involving {target_skill}, detailing your architectural trade-offs and error handling?"

    question_item = AdaptiveQuestionItem(
        question=question_text,
        reason=reason,
        source=source,
        target_skill=target_skill,
        focus_skill=focus_skill,
        difficulty=next_diff,
        evidence_reference=evidence_reference,
        question_engine_version="adaptive-qengine-v1.0.0"
    )

    # 6. Append to interview history for session lineage
    try:
        history_record = InterviewHistory(
            user_id=user.id,
            adaptive_session_id=adaptive_session_id,
            role=role,
            experience=exp,
            skills=target_skill,
            difficulty=next_diff,
            questions=f"1. {question_text}",
            question_engine_version="adaptive-qengine-v1.0.0",
            created_at=datetime.utcnow()
        )
        db.add(history_record)
        db.commit()
    except Exception as hist_err:
        print(f"[Adaptive Next Question Persistence Warning] {hist_err}")
        db.rollback()

    return AdaptiveNextQuestionResponse(
        adaptive_session_id=adaptive_session_id,
        strategy=strategy,
        question=question_item
    )


# ==============================================================================
# PHASE 5D: ADAPTIVE PRACTICE FROM RESUME ↔ JD MATCH
# ==============================================================================

def _safe_json_loads(val: Optional[str], default_val: Any) -> Any:
    if not val:
        return default_val
    try:
        return json.loads(val)
    except Exception:
        return default_val


def generate_adaptive_from_match_service(
    scan_id: str,
    number_of_questions: Optional[int],
    user: UserAccount,
    db: Session
) -> AdaptiveFromMatchResponse:
    """
    Generates personalized, high-signal adaptive interview practice directly from a
    persisted server-side Resume/JD scan result.
    
    Security Guarantee:
    - Never trusts browser for critical gaps, skills, match scores, or evidence.
    - Loads verified scan data directly from database using authenticated user.id.
    - Preserves session lineage and versioning.
    - 60% targeted to highest-priority JD gap; 40% broader role pillars.
    """
    # 1. Authenticate and verify scan ownership
    if not scan_id or not scan_id.strip():
        raise HTTPException(
            status_code=400,
            detail="scan_id is required to start adaptive practice from a match."
        )

    scan = (
        db.query(ResumeScan)
        .filter(ResumeScan.scan_id == scan_id, ResumeScan.user_id == user.id)
        .first()
    )

    if not scan:
        raise HTTPException(
            status_code=404,
            detail="Match result not found or access denied."
        )

    # 2. Parse persisted server-side data with safe fallbacks
    normalized_jd = _safe_json_loads(scan.normalized_jd, {})
    normalized_resume = _safe_json_loads(scan.normalized_resume, {})
    skill_matrix = _safe_json_loads(scan.skill_matrix, [])
    critical_gaps = _safe_json_loads(scan.critical_gaps, [])
    strengths = _safe_json_loads(scan.strengths, [])
    recommendations = _safe_json_loads(scan.recommendations, [])

    target_role = scan.target_role or normalized_jd.get("job_title") or "Software Engineer"
    experience_req = normalized_jd.get("experience_required") or "3-5 Years"
    company_context = normalized_jd.get("company") or "Target Company"
    overall_match_score = scan.overall_match_score if scan.overall_match_score is not None else (scan.match_score or 75.0)
    match_confidence = scan.match_confidence or "MEDIUM"
    matching_engine_version = scan.matching_engine_version or "match-v1.0.0"

    # 3. Retrieve Candidate's Longitudinal Adaptive Profile
    profile = get_candidate_adaptive_profile(user, db)

    # 4. Multi-Factor Prioritization for Target Skill
    scored_gaps = []
    for item in skill_matrix:
        skill_name = item.get("skill", "")
        if not skill_name:
            continue
        importance = item.get("importance", "HIGH")
        match_score = float(item.get("match_score", 0.0))
        ev_level = int(item.get("evidence_level", 6))
        gap_status = item.get("gap_status", "gap")

        if gap_status in ("gap", "partial") or match_score < 70.0:
            imp_weight = 1.0 if importance == "HIGH" else (0.6 if importance == "MEDIUM" else 0.3)
            # Prioritization formula:
            # Importance weight * 100 + Score deficit + Evidence weakness tier
            p_score = (imp_weight * 100.0) + (100.0 - match_score) + ((ev_level - 1) * 10.0)

            # Boost if candidate has historical weakness or mistake in this competency
            if any(fa.skill.lower() == skill_name.lower() for fa in profile.focus_areas):
                p_score += 35.0
            if any(m.skill.lower() == skill_name.lower() for m in profile.open_mistakes):
                p_score += 45.0

            scored_gaps.append({
                "skill": skill_name,
                "importance": importance,
                "match_score": match_score,
                "evidence_level": ev_level,
                "priority_score": p_score,
                "item": item
            })

    scored_gaps.sort(key=lambda x: x["priority_score"], reverse=True)

    if scored_gaps:
        top_gap = scored_gaps[0]
        target_skill = top_gap["skill"]
        top_importance = top_gap["importance"]
        top_match_score = top_gap["match_score"]
        focus_skill = f"Practical {target_skill} Implementation & Architectural Trade-offs"
        reason = "jd_requirement"
        source = "resume_jd_match"
        evidence_reference = {
            "source": "resume_jd_match",
            "scan_id": scan.scan_id,
            "skill": target_skill,
            "jd_importance": top_importance,
            "match_score": top_match_score,
            "match_confidence": match_confidence,
            "matching_engine_version": matching_engine_version
        }
        recommended_focus = ProfileRecommendedFocus(
            skill=target_skill,
            reason=f"High-priority JD requirement gap ({top_importance} importance, {top_match_score:.0f}% match score)",
            priority="high" if top_importance == "HIGH" else "medium"
        )
    else:
        # Fallback if candidate has 100% match or empty matrix
        req_skills = normalized_jd.get("required_skills") or [target_role]
        target_skill = req_skills[0] if req_skills else target_role
        top_importance = "HIGH"
        top_match_score = 90.0
        focus_skill = "System Design & Core Principles"
        reason = "role_requirement"
        source = "resume_jd_match"
        evidence_reference = {
            "source": "resume_jd_match",
            "scan_id": scan.scan_id,
            "skill": target_skill,
            "jd_importance": top_importance,
            "match_score": 100.0,
            "match_confidence": match_confidence,
            "matching_engine_version": matching_engine_version
        }
        recommended_focus = ProfileRecommendedFocus(
            skill=target_skill,
            reason=f"Core role requirement verification for {target_role}",
            priority="medium"
        )

    # 5. Question Distribution (60% Targeted Gap / 40% Broader Role Competency)
    target_count = max(1, min(20, number_of_questions or 5))
    gap_count = max(1, int(target_count * 0.6))
    broader_count = target_count - gap_count

    # 6. Anti-Duplication: Retrieve candidate's recent questions
    recent_fingerprints = set()
    try:
        past_sittings = (
            db.query(InterviewHistory)
            .filter(InterviewHistory.user_id == user.id)
            .order_by(InterviewHistory.created_at.desc())
            .limit(5)
            .all()
        )
        for sitting in past_sittings:
            if sitting.questions:
                for q_line in sitting.questions.split("\n"):
                    clean_fp = re.sub(r"[^a-zA-Z0-9]", "", q_line.lower())[:40]
                    if clean_fp:
                        recent_fingerprints.add(clean_fp)
    except Exception:
        pass

    # 7. Build JD-Match Adaptive Context & Prompt
    other_gaps_summary = ", ".join([g["skill"] for g in scored_gaps[1:4]]) if len(scored_gaps) > 1 else "None"
    strengths_summary = ", ".join(strengths[:4]) if strengths else "Strong engineering fundamentals"

    adaptive_jd_context = f"""
================================================================================
ADAPTIVE JOB MATCH CONTEXT:
- Target Role: {target_role}
- Experience Requirement: {experience_req}
- Hiring Company: {company_context}
- Overall Match Score: {overall_match_score}%
- Match Confidence: {match_confidence}
- Target Improvement Skill (Critical JD Gap): {target_skill} (Importance: {top_importance}, Match: {top_match_score:.0f}%)
- Other Critical / Partial Gaps: {other_gaps_summary}
- Candidate Strengths: {strengths_summary}
- Trigger Driver: jd_requirement

ADAPTIVE GENERATION DIRECTIVES:
1. Target exactly {gap_count} of the {target_count} questions specifically to drill, probe, and test deep understanding, architectural trade-offs, and failure recovery in "{target_skill}".
2. The remaining {broader_count} questions should evaluate broad role competencies for {target_role} ({experience_req}).
3. Questions must be challenging, scenario-based, and probe practical real-world design decisions.
================================================================================
"""
    skills_list = normalized_jd.get("required_skills") or [target_skill]
    dummy_req = InterviewRequest(
        role=target_role,
        experience=experience_req,
        difficulty="Hard",
        skills=skills_list,
        number_of_questions=target_count,
        company=company_context,
        interview_type="Technical & Architecture"
    )
    base_prompt = interview_prompt(dummy_req)
    full_prompt = base_prompt + "\n" + adaptive_jd_context

    # 8. Execute AI Generation with Fallback
    raw_questions: List[str] = []
    try:
        ai_output = generate_ai_questions(full_prompt)
        raw_questions = parse_raw_questions(ai_output, target_count=target_count)
    except Exception as ai_err:
        print(f"[Adaptive Generator from Match] LLM fallback: {ai_err}")
        raw_questions = get_fallback_questions(
            target_role, skills_list, target_count, custom_q=target_skill
        )

    if len(raw_questions) < target_count:
        fallback = get_fallback_questions(target_role, skills_list, target_count, custom_q=target_skill)
        for q in fallback:
            if q not in raw_questions:
                raw_questions.append(q)

    # 9. Deduplicate against recent questions
    final_questions: List[str] = []
    for q in raw_questions:
        q_fp = re.sub(r"[^a-zA-Z0-9]", "", q.lower())[:40]
        if q_fp not in recent_fingerprints or len(final_questions) == 0:
            final_questions.append(q)
        else:
            alt_candidates = get_fallback_questions(target_role, skills_list, target_count + 5, custom_q=target_skill)
            for alt in alt_candidates:
                alt_fp = re.sub(r"[^a-zA-Z0-9]", "", alt.lower())[:40]
                if alt_fp not in recent_fingerprints and alt not in final_questions:
                    final_questions.append(alt)
                    break
            else:
                final_questions.append(q)

    final_questions = final_questions[:target_count]

    # 10. Enrich Questions with Metadata
    enriched_questions: List[AdaptiveQuestionItem] = []
    adaptive_session_id = f"asess_{uuid.uuid4().hex[:12]}"

    for i, q_text in enumerate(final_questions):
        if i < gap_count:
            q_reason = "jd_requirement"
            q_target = target_skill
            q_focus = focus_skill
            q_source = "resume_jd_match"
            q_evidence = evidence_reference
        else:
            q_reason = "role_requirement"
            q_target = skills_list[i % len(skills_list)] if skills_list else target_role
            q_focus = "Role Competency"
            q_source = "role_matrix"
            q_evidence = None

        enriched_questions.append(AdaptiveQuestionItem(
            question=q_text,
            reason=q_reason,
            source=q_source,
            target_skill=q_target,
            focus_skill=q_focus,
            difficulty="Hard",
            evidence_reference=q_evidence,
            question_engine_version="adaptive-qengine-v1.0.0"
        ))

    # 11. Record Session in InterviewHistory
    try:
        formatted_raw = "\n".join([f"{i+1}. {q.question}" for i, q in enumerate(enriched_questions)])
        history_record = InterviewHistory(
            user_id=user.id,
            adaptive_session_id=adaptive_session_id,
            role=target_role,
            experience=experience_req,
            skills=", ".join(skills_list),
            difficulty="Hard",
            questions=formatted_raw,
            question_engine_version="adaptive-qengine-v1.0.0",
            created_at=datetime.utcnow()
        )
        db.add(history_record)
        db.commit()
    except Exception as db_err:
        print(f"[Adaptive from Match Persistence Warning] {db_err}")
        db.rollback()

    return AdaptiveFromMatchResponse(
        adaptive_session_id=adaptive_session_id,
        scan_id=scan.scan_id,
        profile_status=profile.profile_status,
        recommended_focus=recommended_focus,
        questions=enriched_questions
    )
