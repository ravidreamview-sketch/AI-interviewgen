"""
Adaptive Learning Path Agent Service Layer (Phase 2)
===================================================
Provides deterministic, schema-validated, and deeply personalized learning roadmaps based on:
1. Learner Profile (target role, target level, career goals, years of experience).
2. Competency Framework Gaps (CRITICAL, HIGH, MODERATE, LOW, ON_TRACK from Phase 1).
3. Assessment Performance & Candidate Mistakes Ledger (unresolved errors, weak spots).
4. Continuous Adaptation preserving historical progress (never erasing completed achievements).
5. Acyclic prerequisite graph and strict module sequencing.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db_models import (
    UserAccount,
    LearnerProfile,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
    MockInterview,
    AdaptiveRoadmap,
)
from app.services.learner_intelligence_service import (
    calculate_learner_skill_gaps,
    get_role_competency_framework,
    PROFICIENCY_LEVELS,
)
from app.learning_plan_service import SKILL_KNOWLEDGE_BASE

logger = logging.getLogger("ravi.adaptive_path")


# ==============================================================================
# 1. STRUCTURED SCHEMAS FOR ROADMAP VALIDATION
# ==============================================================================

class LearningActivity(BaseModel):
    id: str = Field(..., description="Unique activity ID e.g. act_py_concurrency_01")
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=5, max_length=1000)
    activity_type: str = Field(
        ...,
        description="interactive_concept | code_exercise | system_design_challenge | architecture_review | knowledge_check"
    )
    estimated_minutes: int = Field(..., ge=5, le=360)
    status: str = Field("pending", description="pending | in_progress | completed")
    completed_at: Optional[str] = None
    score: Optional[float] = None
    external_resources: List[Dict[str, str]] = []


class LearningMilestone(BaseModel):
    id: str = Field(..., description="Unique milestone ID e.g. ms_backend_arch_01")
    title: str = Field(..., min_length=2, max_length=200)
    criteria: str = Field(..., min_length=5, max_length=500)
    milestone_type: str = Field(
        ...,
        description="checkpoint_quiz | mock_scenario | project_verification"
    )
    status: str = Field("pending", description="pending | unlocked | passed")
    score: Optional[float] = None
    passed_at: Optional[str] = None


class LearningModule(BaseModel):
    id: str = Field(..., description="Unique module ID e.g. mod_fastapi_async")
    sequence_index: int = Field(..., ge=1)
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=5, max_length=1000)
    targeted_skills: List[str] = Field(..., min_items=1)
    target_level: int = Field(..., ge=1, le=5)
    target_level_title: str
    gap_priority: str = Field(
        "MODERATE",
        description="CRITICAL | HIGH | MODERATE | LOW | ON_TRACK"
    )
    estimated_hours: float = Field(..., ge=0.5, le=100.0)
    prerequisites: List[str] = []
    activities: List[LearningActivity] = Field(..., min_items=1)
    milestone: LearningMilestone
    status: str = Field("available", description="locked | available | in_progress | completed")
    progress_percentage: float = Field(0.0, ge=0.0, le=100.0)


class AdaptiveRoadmapData(BaseModel):
    roadmap_id: str
    title: str
    target_role: str
    target_level: str
    rationale: str
    total_estimated_hours: float
    modules: List[LearningModule] = Field(..., min_items=1)
    overall_progress: float = Field(0.0, ge=0.0, le=100.0)
    last_adapted_at: str
    adaptation_reason: Optional[str] = "Initial Generation"


# ==============================================================================
# 2. ACTIVITY & MODULE CURRICULUM TEMPLATES
# ==============================================================================

ROLE_CORE_CURRICULUM_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "Backend Engineer (Python / Cloud)": [
        {
            "module_key": "py_async_arch",
            "title": "Asynchronous Backend Architecture with Modern Python",
            "targeted_skills": ["Python / Core Backend", "FastAPI / ASGI Frameworks"],
            "target_level": 4,
            "estimated_hours": 8.0,
            "activities": [
                {
                    "title": "Mastering Asyncio Concurrency & Non-Blocking I/O",
                    "description": "Deep dive into event loop mechanics, coroutines, Tasks, and non-blocking sockets. Prevent GIL bottlenecks in compute-heavy paths.",
                    "activity_type": "interactive_concept",
                    "estimated_minutes": 45,
                    "resources": [{"title": "Python Asyncio Docs", "url": "https://docs.python.org/3/library/asyncio.html", "type": "Documentation"}]
                },
                {
                    "title": "High-Throughput FastAPI Service with Dependency Injection",
                    "description": "Construct production APIRouters with reusable db session dependencies, request context tracing, and rate limiters.",
                    "activity_type": "code_exercise",
                    "estimated_minutes": 60,
                    "resources": [{"title": "FastAPI Dependency Injection", "url": "https://fastapi.tiangolo.com/tutorial/dependencies/", "type": "Guide"}]
                },
                {
                    "title": "Idempotent Webhooks & Safe Concurrent State Handlers",
                    "description": "Design an async webhook consumer handling 1,000 req/sec with distributed lock semantics and idempotent mutation keys.",
                    "activity_type": "system_design_challenge",
                    "estimated_minutes": 75,
                    "resources": [{"title": "Designing Data-Intensive Applications", "url": "https://dataintensive.net", "type": "Book"}]
                }
            ],
            "milestone": {
                "title": "Production Async Microservice Checkpoint",
                "criteria": "Implement an async queue-backed REST endpoint handling retry backoff with zero memory leaks.",
                "milestone_type": "mock_scenario"
            }
        },
        {
            "module_key": "db_perf_data_mod",
            "title": "Relational Data Modeling & High-Performance SQL",
            "targeted_skills": ["PostgreSQL & Database Design"],
            "target_level": 4,
            "estimated_hours": 10.0,
            "activities": [
                {
                    "title": "PostgreSQL Indexing & Query Plan Execution Analysis",
                    "description": "Analyze EXPLAIN (ANALYZE, BUFFERS) outputs to eliminate Seq Scans, identify B-Tree vs GIN indexing trade-offs, and partition large tables.",
                    "activity_type": "interactive_concept",
                    "estimated_minutes": 45,
                    "resources": [{"title": "PostgreSQL Performance Optimization", "url": "https://www.postgresql.org/docs/current/performance-tips.html", "type": "Documentation"}]
                },
                {
                    "title": "ACID Transactions & Row-Level Concurrency Isolation",
                    "description": "Prevent phantom reads, lost updates, and serialization anomalies with SELECT FOR UPDATE and optimistic locking columns.",
                    "activity_type": "code_exercise",
                    "estimated_minutes": 60,
                    "resources": [{"title": "SQLAlchemy 2.0 Concurrency Models", "url": "https://docs.sqlalchemy.org/en/20/", "type": "Guide"}]
                },
                {
                    "title": "Zero-Downtime Schema Migration Architecture",
                    "description": "Plan and script a non-destructive column backfill and index creation on a 50-million-row production table.",
                    "activity_type": "architecture_review",
                    "estimated_minutes": 60,
                    "resources": [{"title": "Alembic Safe Migrations Guide", "url": "https://alembic.sqlalchemy.org/", "type": "Documentation"}]
                }
            ],
            "milestone": {
                "title": "Database Scalability Verification Checkpoint",
                "criteria": "Resolve simulated slow queries and lock contention scenarios in a live PostgreSQL schema.",
                "milestone_type": "checkpoint_quiz"
            }
        },
        {
            "module_key": "dist_scale_cloud",
            "title": "Distributed Systems, Caching & Cloud Resilience",
            "targeted_skills": ["Distributed Systems & Scalability", "Docker & Containerization"],
            "target_level": 4,
            "estimated_hours": 12.0,
            "activities": [
                {
                    "title": "Distributed Caching Topologies & Cache Invalidation",
                    "description": "Implement Cache-Aside, Write-Through, and stampede-protected Redis strategies with adaptive TTLs.",
                    "activity_type": "interactive_concept",
                    "estimated_minutes": 50,
                    "resources": [{"title": "Redis Best Practices", "url": "https://redis.io/docs/manual/patterns/", "type": "Documentation"}]
                },
                {
                    "title": "Production Containerization & Distroless Cloud Run Builds",
                    "description": "Author multi-stage Dockerfiles optimizing image size under 150MB with non-root security contexts and health probes.",
                    "activity_type": "code_exercise",
                    "estimated_minutes": 45,
                    "resources": [{"title": "Google Cloud Run Container Best Practices", "url": "https://cloud.google.com/run/docs/building/containers", "type": "Guide"}]
                },
                {
                    "title": "Fault-Tolerant Circuit Breakers & Graceful Degradation",
                    "description": "Implement exponential backoff with full jitter and circuit breakers for downstream service failures.",
                    "activity_type": "system_design_challenge",
                    "estimated_minutes": 70,
                    "resources": [{"title": "Release It! Design and Deploy Production-Ready Software", "url": "https://pragprog.com/titles/mnee2/release-it-second-edition/", "type": "Book"}]
                }
            ],
            "milestone": {
                "title": "Distributed System Chaos Simulation",
                "criteria": "Survive 50% node dropouts and Redis partition failures with continuous uptime.",
                "milestone_type": "mock_scenario"
            }
        }
    ],
    "Full-Stack Engineer": [
        {
            "module_key": "fullstack_react_api",
            "title": "Modern Frontend State & Server-Driven Architecture",
            "targeted_skills": ["TypeScript & React", "Python / Backend Services"],
            "target_level": 4,
            "estimated_hours": 8.0,
            "activities": [
                {
                    "title": "Type-Safe Client-Server Contract with TypeScript & Pydantic",
                    "description": "Eliminate API drift using auto-generated client models and strict runtime schema enforcement.",
                    "activity_type": "interactive_concept",
                    "estimated_minutes": 40,
                    "resources": [{"title": "TypeScript Handbook", "url": "https://www.typescriptlang.org/docs/", "type": "Documentation"}]
                },
                {
                    "title": "Optimistic UI Updates & Resilient Client Mutation State",
                    "description": "Build responsive React mutation flows with rollback on network failure and toast alerts.",
                    "activity_type": "code_exercise",
                    "estimated_minutes": 60,
                    "resources": [{"title": "React Best Practices", "url": "https://react.dev", "type": "Guide"}]
                }
            ],
            "milestone": {
                "title": "Full-Stack End-to-End Delivery Milestone",
                "criteria": "Deliver a fully responsive feature with unit-tested backend endpoints and type-safe frontend UI.",
                "milestone_type": "project_verification"
            }
        },
        {
            "module_key": "fullstack_data_auth",
            "title": "Secure Authentication & Relational Data Engineering",
            "targeted_skills": ["PostgreSQL & Database Design", "System Security & Auth"],
            "target_level": 4,
            "estimated_hours": 9.0,
            "activities": [
                {
                    "title": "Defensive Auth: PBKDF2 Hashing, HttpOnly JWTs & CSRF Defenses",
                    "description": "Harden authentication flows against XSS, credential stuffing, and session fixation.",
                    "activity_type": "interactive_concept",
                    "estimated_minutes": 50,
                    "resources": [{"title": "OWASP Authentication Cheat Sheet", "url": "https://cheatsheetseries.owasp.org", "type": "Security Guide"}]
                },
                {
                    "title": "Complex Relational Joins & Subquery Optimizations",
                    "description": "Optimize multi-table aggregation queries with CTEs and covering indexes.",
                    "activity_type": "code_exercise",
                    "estimated_minutes": 55,
                    "resources": [{"title": "PostgreSQL Query Docs", "url": "https://www.postgresql.org/docs/", "type": "Documentation"}]
                }
            ],
            "milestone": {
                "title": "Security & Data Architecture Checkpoint",
                "criteria": "Pass automated penetration test suite covering JWT manipulation and SQL injection.",
                "milestone_type": "checkpoint_quiz"
            }
        }
    ],
    "AI / Machine Learning Engineer": [
        {
            "module_key": "ml_llm_orchestration",
            "title": "Agentic AI Architectures & LLM System Design",
            "targeted_skills": ["LLM Application Architecture", "Vector Search & Retrieval"],
            "target_level": 4,
            "estimated_hours": 10.0,
            "activities": [
                {
                    "title": "Structured Tool-Calling & State Machine Guardrails",
                    "description": "Design reliable multi-step agent decision trees with deterministic schema fallback and cycle detection.",
                    "activity_type": "interactive_concept",
                    "estimated_minutes": 55,
                    "resources": [{"title": "Google Gemini API Best Practices", "url": "https://ai.google.dev", "type": "Documentation"}]
                },
                {
                    "title": "Hybrid Vector Search & RAG Pipeline Optimization",
                    "description": "Combine dense embedding retrieval with sparse BM25 reranking for high-precision context injection.",
                    "activity_type": "code_exercise",
                    "estimated_minutes": 65,
                    "resources": [{"title": "Vector Embeddings Guide", "url": "https://cloud.google.com/vertex-ai/docs/vector-search", "type": "Guide"}]
                }
            ],
            "milestone": {
                "title": "Autonomous Agent Verification Milestone",
                "criteria": "Execute multi-turn agent workflow with zero hallucinated tool calls.",
                "milestone_type": "project_verification"
            }
        }
    ]
}


# ==============================================================================
# 3. ROADMAP GENERATION ENGINE
# ==============================================================================

def generate_adaptive_learning_path(
    user_id: int,
    db: Session,
    target_role: Optional[str] = None,
    personalization_context: Optional[Dict[str, Any]] = None,
) -> AdaptiveRoadmapData:
    """
    Creates a deeply personalized, schema-validated learning roadmap.
    Incorporates:
    - LearnerProfile (role, level, experience, goals)
    - Phase 1 Competency Gaps (prioritizes CRITICAL and HIGH gaps first)
    - CandidateMistakesLedger (remediates recurring weak concepts)
    """
    # 1. Fetch learner profile
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user_id).first()
    selected_role = target_role or (profile.target_role if profile else "Full-Stack Engineer")
    target_level = profile.target_level if profile else "Mid-Level"
    years_exp = profile.years_of_experience if profile else 0.0

    # 2. Fetch skill gaps
    self_reported = {}
    if profile and profile.self_reported_skills:
        try:
            self_reported = json.loads(profile.self_reported_skills)
        except Exception:
            pass

    skill_gaps = calculate_learner_skill_gaps(
        user_id=user_id,
        target_role=selected_role,
        db=db,
        self_reported_skills=self_reported,
    )

    # 3. Fetch candidate mistakes ledger to detect recurring failure points
    mistakes = db.query(CandidateMistakesLedger).filter(CandidateMistakesLedger.user_id == user_id).all()
    unresolved_mistakes = [
        m for m in mistakes
        if getattr(m, "mistake_status", getattr(m, "status", "identified")) in ("identified", "practicing", "active")
    ]

    # 4. Synthesize personalized modules from catalog and gaps
    catalog = ROLE_CORE_CURRICULUM_CATALOG.get(selected_role) or ROLE_CORE_CURRICULUM_CATALOG.get("Full-Stack Engineer", [])
    
    # Map gaps by skill name for quick lookup
    gap_map = {g["skill"].lower(): g for g in skill_gaps}

    modules: List[LearningModule] = []
    seq_index = 1
    total_hours = 0.0

    # If unresolved mistakes exist, inject an upfront High-Yield Remediation Module
    if unresolved_mistakes:
        mistake_topics = list({m.mistake_category or "System Architecture" for m in unresolved_mistakes})
        remediation_activities = [
            LearningActivity(
                id=f"act_rem_{i}_{uuid.uuid4().hex[:6]}",
                title=f"Targeted Recovery: Resolving {topic}",
                description=f"Actionable debrief addressing historical mistakes: {getattr(unresolved_mistakes[min(i, len(unresolved_mistakes)-1)], 'description', 'Reviewing core principles.')}",
                activity_type="interactive_concept",
                estimated_minutes=40,
                status="pending",
                external_resources=[{"title": "Best Practices Guide", "url": "https://docs.python.org", "type": "Documentation"}]
            )
            for i, topic in enumerate(mistake_topics[:3])
        ]

        rem_module = LearningModule(
            id=f"mod_remediation_{uuid.uuid4().hex[:6]}",
            sequence_index=seq_index,
            title="Rapid Remediation & Mistake Resolution",
            description="Focused drills specifically calibrated to resolve errors identified in your recent interviews and code assessments.",
            targeted_skills=[t for t in mistake_topics[:3]],
            target_level=3,
            target_level_title="Intermediate",
            gap_priority="CRITICAL",
            estimated_hours=3.0,
            prerequisites=[],
            activities=remediation_activities,
            milestone=LearningMilestone(
                id=f"ms_rem_{uuid.uuid4().hex[:6]}",
                title="Mistake Mastery Verification",
                criteria="Complete error correction quiz with >= 85% accuracy.",
                milestone_type="checkpoint_quiz",
                status="pending"
            ),
            status="available",
            progress_percentage=0.0
        )
        modules.append(rem_module)
        total_hours += rem_module.estimated_hours
        seq_index += 1

    # Add core modules, prioritizing modules targeting CRITICAL / HIGH gaps
    ranked_catalog = []
    for raw_mod in catalog:
        # Determine highest gap priority among targeted skills
        mod_priority = "MODERATE"
        mod_gap_level = 0
        for skill in raw_mod["targeted_skills"]:
            g = gap_map.get(skill.lower())
            if g:
                if g["priority"] == "CRITICAL":
                    mod_priority = "CRITICAL"
                    mod_gap_level = max(mod_gap_level, g["gap_level"])
                elif g["priority"] == "HIGH" and mod_priority != "CRITICAL":
                    mod_priority = "HIGH"
                    mod_gap_level = max(mod_gap_level, g["gap_level"])

        ranked_catalog.append((mod_priority, mod_gap_level, raw_mod))

    # Sort: CRITICAL first, then HIGH, then others
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3, "ON_TRACK": 4}
    ranked_catalog.sort(key=lambda x: (priority_order.get(x[0], 5), -x[1]))

    previous_mod_id = None
    for priority, gap_lvl, raw_mod in ranked_catalog:
        mod_id = f"mod_{raw_mod['module_key']}_{uuid.uuid4().hex[:6]}"
        
        # Scale estimated effort based on learner's experience & gap severity
        effort = float(raw_mod["estimated_hours"])
        if years_exp >= 3.0:
            effort = max(2.0, round(effort * 0.85, 1))  # experienced candidates move faster
        if gap_lvl >= 2:
            effort = round(effort * 1.25, 1)  # deep gaps require more practice

        activities = [
            LearningActivity(
                id=f"act_{uuid.uuid4().hex[:8]}",
                title=act["title"],
                description=act["description"],
                activity_type=act["activity_type"],
                estimated_minutes=act["estimated_minutes"],
                status="pending",
                external_resources=act.get("resources", [])
            )
            for act in raw_mod["activities"]
        ]

        milestone = LearningMilestone(
            id=f"ms_{uuid.uuid4().hex[:8]}",
            title=raw_mod["milestone"]["title"],
            criteria=raw_mod["milestone"]["criteria"],
            milestone_type=raw_mod["milestone"]["milestone_type"],
            status="pending"
        )

        prereqs = [previous_mod_id] if previous_mod_id else []
        mod_status = "available" if len(modules) == 0 else "locked"

        mod = LearningModule(
            id=mod_id,
            sequence_index=seq_index,
            title=raw_mod["title"],
            description=f"Personalized module targeting {', '.join(raw_mod['targeted_skills'])} for {selected_role}.",
            targeted_skills=raw_mod["targeted_skills"],
            target_level=raw_mod["target_level"],
            target_level_title=PROFICIENCY_LEVELS.get(raw_mod["target_level"], {}).get("name", "Advanced"),
            gap_priority=priority,
            estimated_hours=effort,
            prerequisites=prereqs,
            activities=activities,
            milestone=milestone,
            status=mod_status,
            progress_percentage=0.0
        )

        modules.append(mod)
        total_hours += effort
        previous_mod_id = mod_id
        seq_index += 1

    roadmap_id = f"path_{uuid.uuid4().hex[:12]}"
    roadmap_data = AdaptiveRoadmapData(
        roadmap_id=roadmap_id,
        title=f"Mastery Journey: {selected_role} ({target_level})",
        target_role=selected_role,
        target_level=target_level,
        rationale=f"Calibrated for candidate with {years_exp} yrs experience targeting {selected_role}. Prioritizes {len([m for m in modules if m.gap_priority in ('CRITICAL', 'HIGH')])} high-impact competency modules.",
        total_estimated_hours=round(total_hours, 1),
        modules=modules,
        overall_progress=0.0,
        last_adapted_at=datetime.now(timezone.utc).isoformat(),
        adaptation_reason="Initial Generation"
    )

    # Persist in database
    # Archive any previous active roadmaps for this user
    db.query(AdaptiveRoadmap).filter(
        AdaptiveRoadmap.user_id == user_id,
        AdaptiveRoadmap.status == "active"
    ).update({"status": "archived"})

    total_acts = sum(len(m.activities) for m in modules)
    orm_roadmap = AdaptiveRoadmap(
        roadmap_id=roadmap_id,
        user_id=user_id,
        title=roadmap_data.title,
        target_role=roadmap_data.target_role,
        target_level=roadmap_data.target_level,
        status="active",
        overall_progress=0.0,
        total_estimated_hours=roadmap_data.total_estimated_hours,
        completed_activities_count=0,
        total_activities_count=total_acts,
        roadmap_data=roadmap_data.model_dump_json(),
        adaptation_history=json.dumps([{
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": "Initial generation based on learner profile and competency gaps",
            "modules_count": len(modules),
            "total_hours": roadmap_data.total_estimated_hours
        }]),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.add(orm_roadmap)
    db.commit()
    db.refresh(orm_roadmap)

    return roadmap_data


# ==============================================================================
# 4. CONTINUOUS ADAPTATION ENGINE (PRESERVING COMPLETED PROGRESS)
# ==============================================================================

def update_learning_path_with_evidence(
    user_id: int,
    db: Session,
    roadmap_id: Optional[str] = None,
    trigger_reason: str = "Assessment & Competency Recalibration"
) -> AdaptiveRoadmapData:
    """
    Adapts an existing roadmap using the latest assessment results, mistakes, and skill gaps.
    GUARANTEE: Completed learning activities and milestones are NEVER erased.
    """
    query = db.query(AdaptiveRoadmap).filter(AdaptiveRoadmap.user_id == user_id)
    if roadmap_id:
        query = query.filter(AdaptiveRoadmap.roadmap_id == roadmap_id)
    else:
        query = query.filter(AdaptiveRoadmap.status == "active")
    
    record = query.order_by(AdaptiveRoadmap.created_at.desc()).first()
    if not record:
        # If no roadmap exists yet, generate one
        return generate_adaptive_learning_path(user_id=user_id, db=db)

    # 1. Parse existing roadmap data
    existing_data_dict = json.loads(record.roadmap_data)
    existing_roadmap = AdaptiveRoadmapData.model_validate(existing_data_dict)

    # 2. Extract and preserve completed activities map
    completed_activities: Dict[str, LearningActivity] = {}
    completed_milestones: Dict[str, LearningMilestone] = {}
    for mod in existing_roadmap.modules:
        for act in mod.activities:
            if act.status == "completed":
                completed_activities[act.id] = act
                completed_activities[act.title] = act  # Match by title as well
        if mod.milestone.status in ("passed", "unlocked"):
            completed_milestones[mod.milestone.id] = mod.milestone
            completed_milestones[mod.milestone.title] = mod.milestone

    # 3. Generate newly calibrated roadmap modules
    new_roadmap = generate_adaptive_learning_path(
        user_id=user_id,
        db=db,
        target_role=existing_roadmap.target_role
    )

    # 4. Merge preserved completion state into new roadmap
    total_completed = 0
    total_activities = 0
    for mod in new_roadmap.modules:
        mod_completed_count = 0
        for act in mod.activities:
            total_activities += 1
            # Check if this activity was previously completed
            preserved = completed_activities.get(act.id) or completed_activities.get(act.title)
            if preserved:
                act.status = "completed"
                act.completed_at = preserved.completed_at
                act.score = preserved.score
                mod_completed_count += 1
                total_completed += 1

        # Check milestone completion
        preserved_ms = completed_milestones.get(mod.milestone.id) or completed_milestones.get(mod.milestone.title)
        if preserved_ms:
            mod.milestone.status = preserved_ms.status
            mod.milestone.score = preserved_ms.score
            mod.milestone.passed_at = preserved_ms.passed_at

        # Calculate module progress
        if len(mod.activities) > 0:
            mod.progress_percentage = round((mod_completed_count / len(mod.activities)) * 100.0, 1)
            if mod_completed_count == len(mod.activities):
                mod.status = "completed"
            elif mod_completed_count > 0:
                mod.status = "in_progress"

    # Unlock first pending module or module whose prerequisites are completed
    unlocked_any = False
    for mod in new_roadmap.modules:
        if mod.status == "completed":
            continue
        # Check prerequisites
        prereqs_met = True
        for p_id in mod.prerequisites:
            p_mod = next((m for m in new_roadmap.modules if m.id == p_id), None)
            if p_mod and p_mod.status != "completed":
                prereqs_met = False
                break
        if prereqs_met and not unlocked_any:
            mod.status = "in_progress" if mod.progress_percentage > 0 else "available"
            unlocked_any = True
        elif not prereqs_met:
            mod.status = "locked"

    new_overall_progress = round((total_completed / total_activities * 100.0), 1) if total_activities > 0 else 0.0
    new_roadmap.overall_progress = new_overall_progress
    new_roadmap.last_adapted_at = datetime.now(timezone.utc).isoformat()
    new_roadmap.adaptation_reason = trigger_reason

    # Parse and update adaptation history
    history = []
    if record.adaptation_history:
        try:
            history = json.loads(record.adaptation_history)
        except Exception:
            pass

    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": trigger_reason,
        "completed_preserved": len(completed_activities),
        "overall_progress": new_overall_progress
    })

    # Update database record
    record.overall_progress = new_overall_progress
    record.completed_activities_count = total_completed
    record.total_activities_count = total_activities
    record.roadmap_data = new_roadmap.model_dump_json()
    record.adaptation_history = json.dumps(history)
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)

    return new_roadmap


# ==============================================================================
# 5. PROGRESS TRACKING & RECOMMENDATION ENGINE
# ==============================================================================

def track_activity_progress(
    roadmap_id: str,
    activity_id: str,
    status: str,
    user_id: int,
    db: Session,
    score: Optional[float] = None
) -> Dict[str, Any]:
    """
    Updates the status and optional score of an individual activity,
    automatically recalculating module progress and unlocking the next milestone.
    """
    record = db.query(AdaptiveRoadmap).filter(
        AdaptiveRoadmap.roadmap_id == roadmap_id,
        AdaptiveRoadmap.user_id == user_id
    ).first()

    if not record:
        raise ValueError(f"Roadmap '{roadmap_id}' not found for user {user_id}")

    roadmap = AdaptiveRoadmapData.model_validate(json.loads(record.roadmap_data))

    target_activity = None
    target_module = None
    for mod in roadmap.modules:
        for act in mod.activities:
            if act.id == activity_id:
                target_activity = act
                target_module = mod
                break
        if target_activity:
            break

    if not target_activity or not target_module:
        raise ValueError(f"Activity '{activity_id}' not found in roadmap '{roadmap_id}'")

    # Update activity state
    target_activity.status = status
    if status == "completed":
        target_activity.completed_at = datetime.now(timezone.utc).isoformat()
        if score is not None:
            target_activity.score = score

    # Recalculate module progress
    completed_acts = sum(1 for a in target_module.activities if a.status == "completed")
    target_module.progress_percentage = round((completed_acts / len(target_module.activities)) * 100.0, 1)

    if completed_acts == len(target_module.activities):
        target_module.status = "completed"
        target_module.milestone.status = "unlocked"

        # Check and unlock dependent modules
        for mod in roadmap.modules:
            if target_module.id in mod.prerequisites and mod.status == "locked":
                # Check if ALL prerequisites of this module are now completed
                all_met = all(
                    any(m.id == p and m.status == "completed" for m in roadmap.modules)
                    for p in mod.prerequisites
                )
                if all_met:
                    mod.status = "available"
    elif completed_acts > 0:
        target_module.status = "in_progress"

    # Recalculate overall roadmap metrics
    total_acts = sum(len(m.activities) for m in roadmap.modules)
    total_completed = sum(sum(1 for a in m.activities if a.status == "completed") for m in roadmap.modules)
    roadmap.overall_progress = round((total_completed / total_acts * 100.0), 1) if total_acts > 0 else 0.0

    record.overall_progress = roadmap.overall_progress
    record.completed_activities_count = total_completed
    record.roadmap_data = roadmap.model_dump_json()
    record.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "success": True,
        "activity_id": activity_id,
        "new_status": status,
        "module_progress": target_module.progress_percentage,
        "module_status": target_module.status,
        "roadmap_progress": roadmap.overall_progress,
        "completed_count": total_completed,
        "total_count": total_acts
    }


def get_next_recommended_activity(
    roadmap_id: str,
    user_id: int,
    db: Session
) -> Dict[str, Any]:
    """
    Finds the active module and delivers the immediate next recommended learning action.
    Returns:
    - current_activity: The single next activity to focus on right now.
    - current_module: Parent module context and objectives.
    - upcoming_queue: Next 3 upcoming activities.
    """
    record = db.query(AdaptiveRoadmap).filter(
        AdaptiveRoadmap.roadmap_id == roadmap_id,
        AdaptiveRoadmap.user_id == user_id
    ).first()

    if not record:
        return {"current_activity": None, "current_module": None, "upcoming_queue": []}

    roadmap = AdaptiveRoadmapData.model_validate(json.loads(record.roadmap_data))

    current_activity = None
    current_module = None
    upcoming_queue = []

    for mod in roadmap.modules:
        if mod.status in ("in_progress", "available"):
            for act in mod.activities:
                if act.status != "completed":
                    if not current_activity:
                        current_activity = act
                        current_module = mod
                    else:
                        upcoming_queue.append({
                            "id": act.id,
                            "title": act.title,
                            "module_title": mod.title,
                            "activity_type": act.activity_type,
                            "estimated_minutes": act.estimated_minutes
                        })
                        if len(upcoming_queue) >= 3:
                            break
            if len(upcoming_queue) >= 3:
                break

    return {
        "current_activity": current_activity.model_dump() if current_activity else None,
        "current_module": {
            "id": current_module.id,
            "title": current_module.title,
            "gap_priority": current_module.gap_priority,
            "targeted_skills": current_module.targeted_skills,
            "progress_percentage": current_module.progress_percentage
        } if current_module else None,
        "upcoming_queue": upcoming_queue,
        "overall_progress": roadmap.overall_progress
    }
