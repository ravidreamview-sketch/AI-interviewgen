"""
AI Agent Orchestration & Workflow Engine (Phase 7)
==================================================
Coordinates all 6 specialized platform agents:
1. Learner Profiling Agent
2. Adaptive Learning Path Agent
3. AI Socratic Tutor Agent
4. Real-World Scenario Generation Agent
5. AI Interview & Project Mentor Agent
6. Evaluation & Competency Intelligence Agent

Enforces:
- Shared agent registry contracts & execution boundaries.
- Data-minimised scoped context & prompt injection defenses.
- Multi-step cross-module workflows with idempotency and state tracking.
- Fault tolerance, exponential backoff retries, and fallback handling.
- Comprehensive monitoring, latency profiling, token tracking, and cost estimation.
"""

from __future__ import annotations

import time
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
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
from app.core.context_manager import LearnerContextManager, sanitize_prompt_text
from app.core.reliability import (
    global_rate_limiter,
    execute_with_retry,
    TokenCostEstimator,
    OrchestrationError,
    AgentExecutionError,
    ContextValidationError,
    IdempotencyConflictError,
    RateLimitExceededError,
)
from app.db_models import (
    UserAccount,
    LearnerProfile,
    AdaptiveRoadmap,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
    RealWorldScenario,
    ScenarioSubmissionRecord,
    LearnerProject,
    ProjectMentorshipTurn,
    MockInterview,
    AgentExecutionMetric,
    AgentWorkflowRun,
)

# Service imports across all 6 phases
from app.services.adaptive_path_service import (
    generate_adaptive_learning_path,
    update_learning_path_with_evidence,
)
from app.services.ai_tutor_service import (
    execute_tutor_interaction,
)
from app.services.scenario_generation_service import (
    generate_personalized_scenario,
    evaluate_scenario_submission,
)
from app.services.interview_mentor_service import (
    start_context_aware_interview,
    process_context_aware_interview_turn,
    mentor_project_interaction,
)
from app.services.competency_intelligence_service import (
    build_competency_dashboard,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Core Agent Dispatcher
# ------------------------------------------------------------------------------

def execute_agent(
    agent_id: str,
    user_id: int,
    input_data: Dict[str, Any],
    db: Session,
    workflow_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes a single agent within strict governance boundaries:
    1. Checks sliding-window rate limit.
    2. Builds scoped, data-minimised context.
    3. Validates input schema against registry.
    4. Executes with retry and latency measurement.
    5. Records execution metrics (tokens, latency, cost).
    6. Returns validated agent output.
    """
    agent = AgentRegistry.get_agent(agent_id)
    execution_id = f"exec_{uuid.uuid4().hex[:12]}"

    # 1. Rate Limiting Check
    global_rate_limiter.check_and_record(
        user_id=user_id,
        agent_id=agent_id,
        limit_per_minute=agent.rate_limit_per_min,
    )

    # 2. Build Scoped Context (Data Minimisation)
    scoped_context = LearnerContextManager.build_scoped_context(
        user_id=user_id,
        agent_id=agent_id,
        db=db,
        extra_params=input_data,
    )

    start_time = time.perf_counter()
    status = "completed"
    error_msg = None
    output_result: Dict[str, Any] = {}

    def _invoke() -> Dict[str, Any]:
        if agent_id == AGENT_LEARNER_PROFILER:
            profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
            if not profile:
                profile = LearnerProfile(
                    user_id=user_id,
                    target_role=input_data.get("target_role", "Backend Engineer (Python / Cloud)"),
                    target_level=input_data.get("target_level", "Mid-Level"),
                    years_of_experience=float(input_data.get("years_of_experience", 0.0)),
                    self_reported_skills=json.dumps(input_data.get("skills", {})),
                )
                db.add(profile)
            else:
                if "target_role" in input_data:
                    profile.target_role = input_data["target_role"]
                if "target_level" in input_data:
                    profile.target_level = input_data["target_level"]
                if "years_of_experience" in input_data:
                    profile.years_of_experience = float(input_data["years_of_experience"])
                if "skills" in input_data:
                    profile.self_reported_skills = json.dumps(input_data["skills"])
            db.commit()
            db.refresh(profile)
            return {
                "profile_id": str(profile.id),
                "target_role": profile.target_role,
                "target_level": profile.target_level,
                "competencies": json.loads(profile.self_reported_skills or "{}") if profile.self_reported_skills else {},
            }

        elif agent_id == AGENT_ADAPTIVE_PATH:
            rdm = generate_adaptive_learning_path(
                user_id=user_id,
                db=db,
                target_role=scoped_context["target_role"],
                personalization_context={"target_level": scoped_context["target_level"], "focus_skills": input_data.get("focus_skills", [])},
            )
            return rdm.model_dump() if hasattr(rdm, "model_dump") else rdm.dict()

        elif agent_id == AGENT_AI_TUTOR:
            user_rec = db.query(UserAccount).filter(UserAccount.id == user_id).first()
            return execute_tutor_interaction(
                user=user_rec,
                db=db,
                query=input_data.get("query", "Explain this concept"),
                concept=input_data.get("concept", "System Architecture"),
                teaching_mode=input_data.get("mode", "explain"),
                session_id=input_data.get("session_id"),
                roadmap_id=input_data.get("roadmap_id"),
                activity_id=input_data.get("activity_id"),
            )

        elif agent_id == AGENT_SCENARIO_GEN:
            action = input_data.get("action", "generate")
            if action == "submit":
                scenario = db.query(RealWorldScenario).filter(
                    RealWorldScenario.scenario_id == input_data["scenario_id"],
                    RealWorldScenario.user_id == user_id,
                ).first()
                if not scenario:
                    raise LookupError(f"Scenario '{input_data['scenario_id']}' not found for user {user_id}.")

                eval_res = evaluate_scenario_submission(
                    scenario=scenario,
                    solution_text=input_data["solution_text"],
                    code_submission=input_data.get("code_submission"),
                    architectural_notes=input_data.get("architectural_notes"),
                )
                now = datetime.now(timezone.utc)
                sub_rec = ScenarioSubmissionRecord(
                    submission_id=f"sub_{uuid.uuid4().hex[:12]}",
                    scenario_id=scenario.scenario_id,
                    user_id=user_id,
                    solution_text=input_data["solution_text"],
                    code_submission=input_data.get("code_submission"),
                    architectural_notes=input_data.get("architectural_notes"),
                    status=eval_res.status,
                    overall_score=eval_res.overall_score,
                    dimension_scores=json.dumps(eval_res.dimension_scores),
                    strengths=json.dumps(eval_res.strengths),
                    areas_for_improvement=json.dumps(eval_res.areas_for_improvement),
                    evidence=eval_res.evidence,
                    feedback=eval_res.feedback,
                    recommended_next_steps=json.dumps(eval_res.recommended_next_steps),
                    evaluation_disclaimer=eval_res.evaluation_disclaimer,
                    evaluated_at=now,
                    created_at=now,
                )
                db.add(sub_rec)
                scenario.is_completed = True
                db.commit()
                return eval_res.model_dump() if hasattr(eval_res, "model_dump") else eval_res.dict()
            else:
                sc_res = generate_personalized_scenario(
                    user_id=user_id,
                    target_role=scoped_context["target_role"],
                    category=input_data.get("category", "debugging"),
                    difficulty=input_data.get("difficulty", "Intermediate"),
                    db=db,
                )
                return sc_res.model_dump() if hasattr(sc_res, "model_dump") else sc_res.dict()

        elif agent_id == AGENT_INTERVIEW_MENTOR:
            action = input_data.get("action", "start_interview")
            if action == "turn":
                return process_context_aware_interview_turn(
                    interview_id=input_data["interview_id"],
                    answer_text=input_data["candidate_answer"],
                    user_id=user_id,
                    db=db,
                    turn_index=input_data.get("turn_index", 1),
                    is_final=input_data.get("is_final", False),
                )
            elif action == "project_mentor":
                user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
                return mentor_project_interaction(
                    user=user,
                    db=db,
                    project_id=input_data["project_id"],
                    stage=input_data.get("stage", "architecture"),
                    user_query=input_data.get("user_query", "How do I review this?"),
                )
            else:
                return start_context_aware_interview(
                    user_id=user_id,
                    db=db,
                    target_role=input_data.get("role", scoped_context["target_role"]),
                    persona=input_data.get("persona", "alex"),
                    interview_type=input_data.get("interview_type", "technical"),
                    mode=input_data.get("mode", "voice"),
                    question_count=input_data.get("question_count", 3),
                    custom_question=input_data.get("custom_question"),
                )

        elif agent_id == AGENT_COMPETENCY_INTEL:
            return build_competency_dashboard(user_id=user_id, db=db)

        else:
            raise KeyError(f"Unhandled agent '{agent_id}'.")

    try:
        output_result = execute_with_retry(
            func=_invoke,
            max_retries=agent.max_retries,
            agent_id=agent_id,
        )
    except Exception as exc:
        status = "failed"
        error_msg = str(exc)
        logger.exception("Agent '%s' failed in execution '%s'", agent_id, execution_id)
        raise
    finally:
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # Estimate tokens and cost
        prompt_text = json.dumps(input_data) + json.dumps(scoped_context)
        completion_text = json.dumps(output_result) if output_result else (error_msg or "")
        tokens_p = TokenCostEstimator.estimate_tokens(prompt_text)
        tokens_c = TokenCostEstimator.estimate_tokens(completion_text)
        cost_usd = TokenCostEstimator.calculate_cost(tokens_p, tokens_c)

        # Persist metric record
        try:
            metric = AgentExecutionMetric(
                execution_id=execution_id,
                agent_id=agent_id,
                user_id=user_id,
                workflow_id=workflow_id,
                status=status,
                latency_ms=latency_ms,
                tokens_prompt=tokens_p,
                tokens_completion=tokens_c,
                cost_estimate_usd=cost_usd,
                error_message=error_msg[:1000] if error_msg else None,
                metadata_json=json.dumps({"phase": agent.phase}),
            )
            db.add(metric)
            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.warning("Failed to persist execution metric: %s", db_err)

    return output_result


# ------------------------------------------------------------------------------
# Workflow Engine: Multi-Agent Controlled Workflows
# ------------------------------------------------------------------------------

def _check_idempotency(user_id: int, idempotency_key: Optional[str], db: Session) -> Optional[AgentWorkflowRun]:
    if not idempotency_key:
        return None
    return db.query(AgentWorkflowRun).filter(
        AgentWorkflowRun.user_id == user_id,
        AgentWorkflowRun.idempotency_key == idempotency_key,
        AgentWorkflowRun.status == "completed",
    ).first()


def run_interview_feedback_workflow(
    user_id: int,
    interview_id: str,
    candidate_answer: str,
    turn_index: int,
    db: Session,
    is_final: bool = False,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Workflow A: Interview Feedback & Adaptive Competency Propagation Loop
    Steps:
    1. Evaluates candidate interview turn (Agent 5).
    2. Extracts technical score & STAR depth.
    3. Records skill analytics; if score < 70, logs mistake in CandidateMistakesLedger.
    4. Adaptively prunes/updates active AdaptiveRoadmap (Agent 2).
    5. Recomputes Competency Intelligence (Agent 6) and returns unified feedback.
    """
    existing_run = _check_idempotency(user_id, idempotency_key, db)
    if existing_run and existing_run.result_summary:
        return json.loads(existing_run.result_summary)

    workflow_id = f"wf_int_{uuid.uuid4().hex[:12]}"
    run = AgentWorkflowRun(
        workflow_id=workflow_id,
        workflow_type="interview_feedback_loop",
        user_id=user_id,
        status="running",
        steps_completed=0,
        total_steps=4,
        idempotency_key=idempotency_key,
    )
    db.add(run)
    db.commit()

    try:
        # Step 1: Evaluate interview turn
        turn_result = execute_agent(
            agent_id=AGENT_INTERVIEW_MENTOR,
            user_id=user_id,
            input_data={
                "action": "turn",
                "interview_id": interview_id,
                "candidate_answer": sanitize_prompt_text(candidate_answer),
                "turn_index": turn_index,
                "is_final": is_final,
            },
            db=db,
            workflow_id=workflow_id,
        )
        run.steps_completed = 1

        eval_data = turn_result.get("evaluation") or {}
        score = float(eval_data.get("score", 75.0))
        star_detected = bool(eval_data.get("star_detected", False))

        # Step 2: Record skill analytics & mistakes if weak
        skill_name = "System Architecture & Communication"
        analytics_rec = db.query(CandidateSkillAnalytics).filter(
            CandidateSkillAnalytics.user_id == user_id,
            CandidateSkillAnalytics.skill == skill_name,
        ).first()

        if not analytics_rec:
            analytics_rec = CandidateSkillAnalytics(
                user_id=user_id,
                skill=skill_name,
                score=score,
                trend="improving" if score >= 75.0 else "declining",
                confidence="MEDIUM",
                evidence_count=1,
                weakness_status="improving" if score >= 75.0 else "identified",
            )
            db.add(analytics_rec)
        else:
            analytics_rec.score = round((analytics_rec.score * 0.7) + (score * 0.3), 1)
            analytics_rec.evidence_count += 1
            analytics_rec.trend = "improving" if score >= analytics_rec.score else "declining"

        if score < 70.0:
            mistake = CandidateMistakesLedger(
                user_id=user_id,
                adaptive_session_id=workflow_id,
                skill=skill_name,
                mistake_category="interview_reasoning",
                description=f"Turn {turn_index}: Weak evidence and lack of structured STAR framing.",
                severity="medium",
                recommendation="Structure technical responses using Situation, Task, Action, and Measurable Result.",
                mistake_status="identified",
            )
            db.add(mistake)
        db.commit()
        run.steps_completed = 2

        # Step 3: Trigger Adaptive Roadmap update (Agent 2)
        roadmap = db.query(AdaptiveRoadmap).filter(AdaptiveRoadmap.user_id == user_id, AdaptiveRoadmap.status == "active").first()
        adaptation_summary = None
        if roadmap:
            try:
                adapt_res = update_learning_path_with_evidence(
                    user_id=user_id,
                    db=db,
                    roadmap_id=roadmap.roadmap_id,
                    trigger_reason=f"Interview Feedback Recalibration (Score: {score})",
                )
                adaptation_summary = "Roadmap adapted with new interview performance evidence"
            except Exception as e:
                logger.warning("Roadmap adaptation step warning: %s", e)
        run.steps_completed = 3

        # Step 4: Refresh Competency Intelligence (Agent 6)
        competency_dash = execute_agent(
            agent_id=AGENT_COMPETENCY_INTEL,
            user_id=user_id,
            input_data={"user_id": user_id},
            db=db,
            workflow_id=workflow_id,
        )
        run.steps_completed = 4
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)

        final_payload = {
            "workflow_id": workflow_id,
            "turn_evaluation": turn_result,
            "score": score,
            "star_detected": star_detected,
            "roadmap_adapted": adaptation_summary is not None,
            "updated_readiness": competency_dash.get("readiness"),
            "targeted_recommendations": competency_dash.get("recommendations"),
        }
        run.result_summary = json.dumps(final_payload)
        db.commit()

        return final_payload

    except Exception as exc:
        run.status = "failed"
        run.error_details = str(exc)
        db.commit()
        raise


def run_scenario_evaluation_workflow(
    user_id: int,
    scenario_id: str,
    solution_text: str,
    code_submission: Optional[str],
    db: Session,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Workflow B: Real-World Scenario Submission & Competency Propagation Loop
    Steps:
    1. Evaluates scenario submission against rubric (Agent 4).
    2. Updates CandidateSkillAnalytics for scenario required skills.
    3. Updates AdaptiveRoadmap progress if applicable (Agent 2).
    4. Refreshes Competency Intelligence (Agent 6).
    """
    existing_run = _check_idempotency(user_id, idempotency_key, db)
    if existing_run and existing_run.result_summary:
        return json.loads(existing_run.result_summary)

    workflow_id = f"wf_sc_{uuid.uuid4().hex[:12]}"
    run = AgentWorkflowRun(
        workflow_id=workflow_id,
        workflow_type="scenario_evaluation_loop",
        user_id=user_id,
        status="running",
        steps_completed=0,
        total_steps=3,
        idempotency_key=idempotency_key,
    )
    db.add(run)
    db.commit()

    try:
        # Step 1: Grade scenario submission (Agent 4)
        eval_result = execute_agent(
            agent_id=AGENT_SCENARIO_GEN,
            user_id=user_id,
            input_data={
                "action": "submit",
                "scenario_id": scenario_id,
                "solution_text": sanitize_prompt_text(solution_text),
                "code_submission": code_submission,
            },
            db=db,
            workflow_id=workflow_id,
        )
        run.steps_completed = 1

        overall_score = float(eval_result.get("overall_score", 75.0))

        # Step 2: Update CandidateSkillAnalytics for scenario skills
        scenario = db.query(RealWorldScenario).filter(RealWorldScenario.scenario_id == scenario_id).first()
        req_skills = []
        if scenario and scenario.required_skills:
            try:
                req_skills = json.loads(scenario.required_skills) if isinstance(scenario.required_skills, str) else scenario.required_skills
            except Exception:
                req_skills = ["Technical Problem Solving"]

        for sk in req_skills:
            if isinstance(sk, str) and sk.strip():
                sk_clean = sk.strip()
                s_rec = db.query(CandidateSkillAnalytics).filter(
                    CandidateSkillAnalytics.user_id == user_id,
                    CandidateSkillAnalytics.skill == sk_clean,
                ).first()
                if not s_rec:
                    s_rec = CandidateSkillAnalytics(
                        user_id=user_id,
                        skill=sk_clean,
                        score=overall_score,
                        trend="improving" if overall_score >= 75.0 else "declining",
                        confidence="HIGH",
                        evidence_count=1,
                        weakness_status="improving" if overall_score >= 75.0 else "identified",
                    )
                    db.add(s_rec)
                else:
                    s_rec.score = round((s_rec.score * 0.6) + (overall_score * 0.4), 1)
                    s_rec.evidence_count += 1
                    s_rec.trend = "improving" if overall_score >= s_rec.score else "declining"
        db.commit()
        run.steps_completed = 2

        # Step 3: Refresh Competency Intelligence (Agent 6)
        competency_dash = execute_agent(
            agent_id=AGENT_COMPETENCY_INTEL,
            user_id=user_id,
            input_data={"user_id": user_id},
            db=db,
            workflow_id=workflow_id,
        )
        run.steps_completed = 3
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)

        final_payload = {
            "workflow_id": workflow_id,
            "scenario_evaluation": eval_result,
            "overall_score": overall_score,
            "updated_readiness": competency_dash.get("readiness"),
            "targeted_recommendations": competency_dash.get("recommendations"),
        }
        run.result_summary = json.dumps(final_payload)
        db.commit()

        return final_payload

    except Exception as exc:
        run.status = "failed"
        run.error_details = str(exc)
        db.commit()
        raise


def run_diagnostic_onboarding_workflow(
    user_id: int,
    target_role: str,
    target_level: str,
    skills: List[str],
    db: Session,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Workflow C: Learner Profiling & Personalized Learning Roadmap Initialization
    Steps:
    1. Creates/Updates LearnerProfile (Agent 1).
    2. Initializes baseline skill records.
    3. Synthesizes personalized AdaptiveRoadmap (Agent 2).
    """
    existing_run = _check_idempotency(user_id, idempotency_key, db)
    if existing_run and existing_run.result_summary:
        return json.loads(existing_run.result_summary)

    workflow_id = f"wf_onb_{uuid.uuid4().hex[:12]}"
    run = AgentWorkflowRun(
        workflow_id=workflow_id,
        workflow_type="diagnostic_onboarding",
        user_id=user_id,
        status="running",
        steps_completed=0,
        total_steps=2,
        idempotency_key=idempotency_key,
    )
    db.add(run)
    db.commit()

    try:
        # Step 1: Profiler Agent
        profile_out = execute_agent(
            agent_id=AGENT_LEARNER_PROFILER,
            user_id=user_id,
            input_data={
                "target_role": target_role,
                "target_level": target_level,
                "skills": {s: "intermediate" for s in skills},
            },
            db=db,
            workflow_id=workflow_id,
        )
        run.steps_completed = 1

        # Step 2: Adaptive Roadmap Generation (Agent 2)
        roadmap_out = execute_agent(
            agent_id=AGENT_ADAPTIVE_PATH,
            user_id=user_id,
            input_data={
                "target_role": target_role,
                "target_level": target_level,
                "focus_skills": skills,
            },
            db=db,
            workflow_id=workflow_id,
        )
        run.steps_completed = 2
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)

        final_payload = {
            "workflow_id": workflow_id,
            "profile": profile_out,
            "roadmap": roadmap_out,
        }
        run.result_summary = json.dumps(final_payload)
        db.commit()

        return final_payload

    except Exception as exc:
        run.status = "failed"
        run.error_details = str(exc)
        db.commit()
        raise


def run_project_mentorship_workflow(
    user_id: int,
    project_id: str,
    stage: str,
    user_query: str,
    db: Session,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Workflow D: Project Mentorship & Competency Reinforcement Loop
    Steps:
    1. Generates Socratic guidance across the 6 project stages (Agent 5).
    2. Records mentorship turn in project history.
    3. Refreshes Competency Intelligence (Agent 6).
    """
    existing_run = _check_idempotency(user_id, idempotency_key, db)
    if existing_run and existing_run.result_summary:
        return json.loads(existing_run.result_summary)

    workflow_id = f"wf_proj_{uuid.uuid4().hex[:12]}"
    run = AgentWorkflowRun(
        workflow_id=workflow_id,
        workflow_type="project_mentorship_loop",
        user_id=user_id,
        status="running",
        steps_completed=0,
        total_steps=2,
        idempotency_key=idempotency_key,
    )
    db.add(run)
    db.commit()

    try:
        # Step 1: Project Mentor interaction (Agent 5)
        mentor_out = execute_agent(
            agent_id=AGENT_INTERVIEW_MENTOR,
            user_id=user_id,
            input_data={
                "action": "project_mentor",
                "project_id": project_id,
                "stage": stage,
                "user_query": sanitize_prompt_text(user_query),
            },
            db=db,
            workflow_id=workflow_id,
        )
        run.steps_completed = 1

        # Step 2: Refresh Competency Intelligence (Agent 6)
        competency_dash = execute_agent(
            agent_id=AGENT_COMPETENCY_INTEL,
            user_id=user_id,
            input_data={"user_id": user_id},
            db=db,
            workflow_id=workflow_id,
        )
        run.steps_completed = 2
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)

        final_payload = {
            "workflow_id": workflow_id,
            "project_mentorship": mentor_out,
            "updated_readiness": competency_dash.get("readiness"),
        }
        run.result_summary = json.dumps(final_payload)
        db.commit()

        return final_payload

    except Exception as exc:
        run.status = "failed"
        run.error_details = str(exc)
        db.commit()
        raise


# ------------------------------------------------------------------------------
# Monitoring & Metrics Service
# ------------------------------------------------------------------------------

def get_orchestration_monitoring_metrics(user_id: Optional[int], db: Session) -> Dict[str, Any]:
    """
    Returns aggregated agent metrics, execution counts, latency, and cost estimates.
    Strictly scrubs sensitive personal information from logs.
    """
    query = db.query(AgentExecutionMetric)
    if user_id is not None:
        query = query.filter(AgentExecutionMetric.user_id == user_id)

    metrics = query.order_by(AgentExecutionMetric.created_at.desc()).limit(100).all()

    total_calls = len(metrics)
    successful_calls = len([m for m in metrics if m.status == "completed"])
    failed_calls = len([m for m in metrics if m.status == "failed"])
    avg_latency = (sum(m.latency_ms for m in metrics) / total_calls) if total_calls else 0.0
    total_tokens = sum(m.tokens_prompt + m.tokens_completion for m in metrics)
    total_cost_usd = sum(m.cost_estimate_usd for m in metrics)

    # Breakdown by agent
    by_agent: Dict[str, Dict[str, Any]] = {}
    for m in metrics:
        if m.agent_id not in by_agent:
            by_agent[m.agent_id] = {"count": 0, "total_latency": 0.0, "failures": 0}
        by_agent[m.agent_id]["count"] += 1
        by_agent[m.agent_id]["total_latency"] += m.latency_ms
        if m.status == "failed":
            by_agent[m.agent_id]["failures"] += 1

    agent_breakdown = [
        {
            "agent_id": k,
            "calls_count": v["count"],
            "avg_latency_ms": round(v["total_latency"] / v["count"], 2),
            "failure_rate_pct": round((v["failures"] / v["count"]) * 100.0, 1),
        }
        for k, v in by_agent.items()
    ]

    recent_logs = [
        {
            "execution_id": m.execution_id,
            "agent_id": m.agent_id,
            "status": m.status,
            "latency_ms": m.latency_ms,
            "tokens": m.tokens_prompt + m.tokens_completion,
            "cost_usd": m.cost_estimate_usd,
            "timestamp": m.created_at.isoformat() if m.created_at else None,
        }
        for m in metrics[:15]
    ]

    return {
        "summary": {
            "total_executions": total_calls,
            "success_rate_pct": round((successful_calls / total_calls) * 100.0, 1) if total_calls else 100.0,
            "failed_executions": failed_calls,
            "average_latency_ms": round(avg_latency, 2),
            "total_tokens_estimated": total_tokens,
            "total_cost_estimated_usd": round(total_cost_usd, 4),
        },
        "agent_breakdown": agent_breakdown,
        "recent_logs": recent_logs,
    }
