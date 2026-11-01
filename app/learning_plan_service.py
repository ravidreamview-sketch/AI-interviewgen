"""
learning_plan_service.py
========================
Contextual Personalized Learning Plan Engine for AI Interview Studio.

Analyzes candidate resume evidence against target Job Description (JD) mapping results
to identify skill gaps, experience gaps, and career progression gaps, generating a
personalized, evidence-based learning roadmap.

Key Principles:
1. Evidence-Based Classification: Matched, Partially Matched, Not Evidenced, Candidate Verified.
2. Distinct Gap Taxonomy: Keeps Skill Gaps, Experience Gaps, and Career Gaps separate.
3. Prioritized Recommendations: Critical (P1), Skills to Improve (P2), Career Growth (P3).
4. Candidate Control: The candidate selects and approves what enters their learning plan.
5. Zero Fake Credentials: Canonical, authoritative documentation and real-world project rubrics.
"""

import re
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


# Canonical Knowledge Catalog for standard tech skills (canonical docs, verified best practices)
SKILL_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "python": {
        "category": "Programming Languages",
        "what_to_learn": "Modern Python (3.11+) asynchronous programming (asyncio), type hinting, generators, memory profiling, and clean architecture patterns.",
        "why_it_matters": "Core foundational language for backend services, automation, and AI pipeline orchestration in this role.",
        "target_proficiency": "Production-Ready Senior Contributor",
        "learning_objectives": [
            "Master asyncio event loops, concurrency primitives, and async context managers.",
            "Implement strict static type safety using typing protocols and Pydantic v2.",
            "Profile execution bottlenecks and memory leaks using cProfile and tracemalloc."
        ],
        "resources": [
            {"title": "Python Official Documentation", "url": "https://docs.python.org/3/", "type": "Official Documentation"},
            {"title": "Real Python Async IO in Python", "url": "https://realpython.com/async-io-python/", "type": "Authoritative Guide"},
            {"title": "Fluent Python (Architecture Reference)", "url": "https://www.oreilly.com/library/view/fluent-python-2nd/9781492056348/", "type": "Reference Book"}
        ],
        "practical_exercises": [
            "Write an asynchronous worker pool handling 1,000 simulated HTTP requests with semaphore-based rate limiting.",
            "Refactor a legacy untyped module into fully typed Pydantic models with custom validators."
        ],
        "suggested_project": "High-throughput asynchronous data scraper and telemetry normalizer with streaming JSON output.",
        "completion_criteria": [
            "100% test coverage with pytest-asyncio.",
            "Strict mypy validation passing with zero warnings.",
            "Sub-100ms response handling under concurrent load."
        ],
        "estimated_effort": "12–16 hours (1–2 weeks)"
    },
    "fastapi": {
        "category": "Backend Architecture",
        "what_to_learn": "FastAPI ASGI lifecycle, dependency injection system, OAuth2 with JWT validation, background tasks, and streaming SSE responses.",
        "why_it_matters": "Powers high-concurrency microservices, AI inference endpoints, and web applications specified in the JD.",
        "target_proficiency": "Production API Architect",
        "learning_objectives": [
            "Design modular APIRouters with reusable dependency injection chains.",
            "Implement secure token-based authentication with HttpOnly cookies and CSRF safeguards.",
            "Deploy production ASGI servers with Uvicorn and Gunicorn worker configurations."
        ],
        "resources": [
            {"title": "FastAPI Official Documentation", "url": "https://fastapi.tiangolo.com/", "type": "Official Documentation"},
            {"title": "Starlette Core Documentation", "url": "https://www.starlette.io/", "type": "Framework Guide"},
            {"title": "Tiangolo Full-Stack FastAPI Template", "url": "https://github.com/tiangolo/full-stack-fastapi-template", "type": "Reference Architecture"}
        ],
        "practical_exercises": [
            "Create a multi-tier dependency injection hierarchy for database sessions, current user lookup, and RBAC permissions.",
            "Implement a streaming response endpoint delivering chunked AI completion tokens via Server-Sent Events."
        ],
        "suggested_project": "Production-grade RESTful API service with OpenAPI specification, rate-limiting middleware, and comprehensive integration test suite.",
        "completion_criteria": [
            "All endpoints documented in interactive Swagger UI.",
            "Automated pytest suite utilizing TestClient and HTTPX.",
            "Zero leaked database sessions under load testing."
        ],
        "estimated_effort": "14–18 hours (2 weeks)"
    },
    "postgresql": {
        "category": "Databases & Storage",
        "what_to_learn": "Relational schema design, ACID transactions, isolation levels, multi-column indexing (B-Tree, GIN), EXPLAIN ANALYZE query optimization, and connection pooling.",
        "why_it_matters": "Serves as the primary operational datastore for candidate records, telemetry, and transactional state.",
        "target_proficiency": "Database Optimization Specialist",
        "learning_objectives": [
            "Formulate efficient complex queries involving CTEs, window functions, and JSONB operators.",
            "Analyze and tune slow queries using EXPLAIN ANALYZE and appropriate index strategies.",
            "Configure SQLAlchemy / Psycopg connection pools with connection reuse and retry safeguards."
        ],
        "resources": [
            {"title": "PostgreSQL Official Documentation", "url": "https://www.postgresql.org/docs/", "type": "Official Documentation"},
            {"title": "Use The Index, Luke (SQL Indexing Guide)", "url": "https://use-the-index-luke.com/", "type": "Engineering Guide"},
            {"title": "SQLAlchemy 2.0 Unified Documentation", "url": "https://docs.sqlalchemy.org/en/20/", "type": "ORM Guide"}
        ],
        "practical_exercises": [
            "Optimize a multi-table JOIN query scanning 100,000 rows to execute in under 15ms using compound indexes.",
            "Write a database migration with Alembic managing zero-downtime column renaming and schema evolution."
        ],
        "suggested_project": "Scalable multi-tenant analytics schema with partitioned audit tables, materialized views, and automated refresh triggers.",
        "completion_criteria": [
            "Query plan demonstrates Index Scan / Bitmap Index Scan rather than Sequential Scan.",
            "Zero deadlock vulnerabilities under concurrent transaction test scripts.",
            "Automated rollback verified on simulated migration failure."
        ],
        "estimated_effort": "12–16 hours (2 weeks)"
    },
    "redis": {
        "category": "Caching & In-Memory Systems",
        "what_to_learn": "In-memory caching architectures, Redis data structures (Hashes, Sorted Sets, HyperLogLog), distributed locks, and pub/sub messaging.",
        "why_it_matters": "Required to deliver sub-millisecond caching, rate-limiting, and session management in high-scale systems.",
        "target_proficiency": "Cache & Concurrency Engineering",
        "learning_objectives": [
            "Implement cache-aside and write-through patterns with explicit TTL expiration strategies.",
            "Build distributed locks using Redlock algorithm primitives for critical section protection.",
            "Utilize Redis Streams or Pub/Sub for lightweight event decoupling."
        ],
        "resources": [
            {"title": "Redis Official University & Documentation", "url": "https://redis.io/docs/", "type": "Official Documentation"},
            {"title": "Redis Data Structures & Command Reference", "url": "https://redis.io/commands/", "type": "Specification"}
        ],
        "practical_exercises": [
            "Implement a sliding-window rate limiter in Redis enforcing 60 requests per minute per IP.",
            "Construct a cache wrapper with stale-while-revalidate semantics."
        ],
        "suggested_project": "Distributed session manager and real-time active user presence tracker for concurrent interview rooms.",
        "completion_criteria": [
            "Cache hit ratio verified above 85% during simulated traffic.",
            "Graceful fallback to primary database on Redis outage.",
            "Memory footprint constrained with maxmemory LRU eviction policy."
        ],
        "estimated_effort": "8–12 hours (1 week)"
    },
    "docker": {
        "category": "DevOps & Infrastructure",
        "what_to_learn": "Containerization fundamentals, multi-stage builds, rootless container security, container layer caching, and Docker Compose orchestration.",
        "why_it_matters": "Enables deterministic development parity and reproducible artifact deployment across staging and production clusters.",
        "target_proficiency": "Containerization & Deployment Competence",
        "learning_objectives": [
            "Write minimal, secure multi-stage Dockerfiles reducing image size by >60%.",
            "Configure Docker Compose environments modeling app, database, and cache dependencies.",
            "Apply non-root user execution and read-only filesystem security constraints."
        ],
        "resources": [
            {"title": "Docker Official Documentation", "url": "https://docs.docker.com/", "type": "Official Documentation"},
            {"title": "Dockerfile Best Practices Guide", "url": "https://docs.docker.com/develop/develop-images/dockerfile_best-practices/", "type": "Best Practices"}
        ],
        "practical_exercises": [
            "Create a multi-stage Dockerfile for a Python web app compiling binary wheels in builder stage and producing <120MB final image.",
            "Write a docker-compose.yml testing healthcheck dependency ordering between database and API."
        ],
        "suggested_project": "Containerized local development harness with automated test runner, hot reloading, and service mocks.",
        "completion_criteria": [
            "Container passes vulnerability scan (e.g. trivy) with zero critical CVEs.",
            "Clean shutdown handling SIGTERM within 10 seconds.",
            "Zero secrets or API keys embedded in image layers."
        ],
        "estimated_effort": "8–10 hours (1 week)"
    },
    "system design": {
        "category": "Architecture & Engineering Leadership",
        "what_to_learn": "Scalable distributed architecture, CAP theorem trade-offs, load balancing strategies, API gateway routing, data partitioning, and disaster recovery.",
        "why_it_matters": "Essential for senior roles to make sound trade-offs between latency, consistency, availability, and engineering cost.",
        "target_proficiency": "System Architect / Tech Lead",
        "learning_objectives": [
            "Design resilient architectures resilient to single-point-of-failure (SPOF) risks.",
            "Evaluate read-heavy vs write-heavy architectural patterns and back-of-the-envelope capacity planning.",
            "Document architecture decision records (ADRs) with clear trade-off rationale."
        ],
        "resources": [
            {"title": "The System Design Primer (Donne Martin)", "url": "https://github.com/donnemartin/system-design-primer", "type": "Comprehensive Guide"},
            {"title": "Martin Kleppmann: Designing Data-Intensive Applications", "url": "https://dataintensive.net/", "type": "Reference Book"}
        ],
        "practical_exercises": [
            "Produce an architectural blueprint for a real-time collaborative interview feedback tool scaling to 50,000 DAU.",
            "Write an Architecture Decision Record (ADR) comparing PostgreSQL vs MongoDB for structured interview telemetry."
        ],
        "suggested_project": "End-to-end distributed system design document and prototype incorporating rate-limiting, message queues, and read replicas.",
        "completion_criteria": [
            "Capacity calculations detailing bandwidth, storage, and IOPS requirements.",
            "Documented failure mode and recovery strategies for every tier.",
            "Clear component sequence diagram."
        ],
        "estimated_effort": "16–24 hours (2–3 weeks)"
    },
    "kubernetes": {
        "category": "DevOps & Infrastructure",
        "what_to_learn": "Kubernetes primitives (Deployments, StatefulSets, Services, Ingress), ConfigMaps/Secrets, resource requests/limits, and horizontal pod autoscaling (HPA).",
        "why_it_matters": "Standard deployment platform for enterprise services and modern cloud workloads referenced in the JD.",
        "target_proficiency": "Cloud-Native Deployment Engineer",
        "learning_objectives": [
            "Write declarative Kubernetes manifests following cloud-native best practices.",
            "Configure liveness, readiness, and startup probes for zero-downtime rolling updates.",
            "Set up Horizontal Pod Autoscalers responding to CPU, memory, and custom metrics."
        ],
        "resources": [
            {"title": "Kubernetes Official Documentation & Tutorials", "url": "https://kubernetes.io/docs/home/", "type": "Official Documentation"},
            {"title": "Kubernetes The Hard Way (Kelsey Hightower)", "url": "https://github.com/kelseyhightower/kubernetes-the-hard-way", "type": "Deep Dive Guide"}
        ],
        "practical_exercises": [
            "Deploy a 3-replica web application to a local Minikube/Kind cluster with Ingress routing.",
            "Configure rolling update strategies and verify zero HTTP 5xx errors during simulated redeployment."
        ],
        "suggested_project": "Complete GitOps deployment repository with Helm or Kustomize managing dev, staging, and production overlays.",
        "completion_criteria": [
            "Zero downtime during deployment rollout.",
            "Graceful termination honoring pod preStop hooks.",
            "Resource limits enforced prevent node exhaustion."
        ],
        "estimated_effort": "14–20 hours (2 weeks)"
    },
    "testing": {
        "category": "Software Quality & Reliability",
        "what_to_learn": "Test-Driven Development (TDD), unit testing with pytest, mocking external services, integration testing with ephemeral databases, and property-based testing.",
        "why_it_matters": "Ensures software correctness, prevents regression defects, and validates complex business rules.",
        "target_proficiency": "Quality-First Engineer",
        "learning_objectives": [
            "Structure clean pytest fixtures with explicit scope and dependency teardown.",
            "Mock external network dependencies (APIs, email, object storage) using respx / unittest.mock.",
            "Implement end-to-end integration tests validating multi-step user workflows."
        ],
        "resources": [
            {"title": "pytest Official Documentation", "url": "https://docs.pytest.org/", "type": "Official Documentation"},
            {"title": "Martin Fowler: Test Pyramid Patterns", "url": "https://martinfowler.com/articles/practical-test-pyramid.html", "type": "Engineering Guide"}
        ],
        "practical_exercises": [
            "Write a test suite with 100% boundary value coverage for a scoring and ranking algorithm.",
            "Build an integration test verifying transactional database rollback upon simulated mid-request failure."
        ],
        "suggested_project": "Robust automated test harness with CI execution, code coverage reporting, and regression guardrails.",
        "completion_criteria": [
            "Code coverage exceeding 90% across core domain logic.",
            "Test suite executes in under 15 seconds.",
            "Deterministic test execution with zero flaky tests."
        ],
        "estimated_effort": "10–14 hours (1–2 weeks)"
    }
}


def _match_catalog_entry(skill_name: str) -> Optional[Dict[str, Any]]:
    """Finds best matching knowledge base entry for a given skill."""
    name_clean = (skill_name or "").lower().strip()
    # 1. Exact match
    if name_clean in SKILL_KNOWLEDGE_BASE:
        return SKILL_KNOWLEDGE_BASE[name_clean]
    # 2. Key contained in name
    for k, v in SKILL_KNOWLEDGE_BASE.items():
        if k in name_clean or name_clean in k:
            return v
    # 3. Keyword associations
    if any(w in name_clean for w in ["sql", "database", "postgres", "rdbms"]):
        return SKILL_KNOWLEDGE_BASE.get("postgresql")
    if any(w in name_clean for w in ["api", "rest", "endpoint", "microservice", "fastapi"]):
        return SKILL_KNOWLEDGE_BASE.get("fastapi")
    if any(w in name_clean for w in ["cache", "redis", "in-memory", "session"]):
        return SKILL_KNOWLEDGE_BASE.get("redis")
    if any(w in name_clean for w in ["container", "docker", "dockerfile"]):
        return SKILL_KNOWLEDGE_BASE.get("docker")
    if any(w in name_clean for w in ["k8s", "kubernetes", "cluster"]):
        return SKILL_KNOWLEDGE_BASE.get("kubernetes")
    if any(w in name_clean for w in ["architecture", "scale", "system design", "distributed"]):
        return SKILL_KNOWLEDGE_BASE.get("system design")
    if any(w in name_clean for w in ["test", "pytest", "unit test", "tdd", "qa"]):
        return SKILL_KNOWLEDGE_BASE.get("testing")
    return None


def _synthesize_dynamic_recommendation(
    skill_name: str,
    importance: str,
    jd_requirement: str,
    target_role: str
) -> Dict[str, Any]:
    """
    Contextually synthesizes a realistic, high-quality recommendation module
    for domain or niche skills not in the static catalog.
    """
    clean_name = skill_name.strip().title()
    role_title = target_role or "Technical Specialist"

    return {
        "category": "Domain & Specialized Competencies",
        "what_to_learn": f"Core paradigms, design patterns, and production implementation strategies for {clean_name}.",
        "why_it_matters": f"Directly required by the employer for the {role_title} position: '{jd_requirement or clean_name}'.",
        "target_proficiency": "Production-Ready Implementation",
        "learning_objectives": [
            f"Understand the architectural role and best practices of {clean_name} in modern applications.",
            f"Implement hands-on code or configuration satisfying real-world {clean_name} requirements.",
            f"Diagnose common pitfalls, edge cases, and performance considerations with {clean_name}."
        ],
        "resources": [
            {
                "title": f"{clean_name} Official Documentation & Developer Guides",
                "url": f"https://www.google.com/search?q={clean_name.replace(' ', '+')}+official+documentation",
                "type": "Authoritative Reference"
            },
            {
                "title": f"Best Practices & Design Patterns for {clean_name}",
                "url": f"https://www.google.com/search?q={clean_name.replace(' ', '+')}+best+practices+guide",
                "type": "Engineering Guide"
            }
        ],
        "practical_exercises": [
            f"Configure a standalone proof-of-concept demonstrating {clean_name} integration.",
            f"Write unit or integration tests verifying expected behavior and error handling for {clean_name}."
        ],
        "suggested_project": f"Production-oriented module showcasing {clean_name} solving a core business challenge for the {role_title} domain.",
        "completion_criteria": [
            f"Functional implementation running with zero runtime errors.",
            "Documented README detailing setup, architectural decisions, and usage instructions.",
            "Demonstrated error handling for network or payload edge cases."
        ],
        "estimated_effort": "8–12 hours (1–2 weeks)"
    }



def _get_val(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def generate_career_improvement_plan(
    match_result: Any,
    normalized_jd: Optional[Any] = None,
    normalized_resume: Optional[Any] = None,
    target_role: Optional[str] = None
) -> Dict[str, Any]:
    """
    Core engine function: Analyzes match metrics, skill matrix, and normalized documents
    to produce the comprehensive 'Your Career Improvement Plan' response payload.
    """
    norm_jd = normalized_jd or _get_val(match_result, "normalized_jd")
    norm_resume = normalized_resume or _get_val(match_result, "normalized_resume")

    role_name = (
        target_role or
        _get_val(match_result, "target_role") or
        (_get_val(norm_jd, "job_title") if norm_jd else None) or
        "Target Role"
    )

    skill_matrix = _get_val(match_result, "skill_matrix", []) or []
    sub_scores = _get_val(match_result, "sub_scores")
    overall_score = float(_get_val(match_result, "overall_match_score", 0.0) or 0.0)
    strengths_list = [str(s).lower() for s in (_get_val(match_result, "strengths", []) or [])]
    critical_gaps_list = [str(s).lower() for s in (_get_val(match_result, "critical_gaps", []) or [])]
    skill_gaps_list = [str(s).lower() for s in (_get_val(match_result, "skill_gaps", []) or [])]

    # 1. Evidence-Based Skill Classification
    matched_skills = []
    partially_matched_skills = []
    not_evidenced_skills = []
    all_recommendation_items = []

    seen_skills = set()

    for item in skill_matrix:
        s_name = str(_get_val(item, "skill", "")).strip()
        if not s_name or s_name.lower() in seen_skills:
            continue
        seen_skills.add(s_name.lower())

        m_score = float(_get_val(item, "match_score", 0.0) or 0.0)
        gap_status = str(_get_val(item, "gap_status", "")).lower()
        ev_level = _get_val(item, "evidence_level", None)
        importance = str(_get_val(item, "importance", "HIGH")).upper()
        jd_req = _get_val(item, "jd_requirement", "") or f"Requirement for {s_name}"
        res_ev = _get_val(item, "resume_evidence", "")
        s_lower = s_name.lower()

        is_in_strengths = s_lower in strengths_list
        is_in_critical = s_lower in critical_gaps_list
        is_in_gaps = s_lower in skill_gaps_list

        # Evidence taxonomy classification
        if (gap_status == "matched" or m_score >= 80 or is_in_strengths) and (ev_level is None or ev_level <= 3 or m_score >= 75):
            evidence_status = "MATCHED"
            matched_skills.append(s_name)
        elif (gap_status == "partial" or (40 <= m_score < 80)) or (ev_level in [3, 4]):
            evidence_status = "PARTIALLY_MATCHED"
            partially_matched_skills.append(s_name)
        else:
            evidence_status = "NOT_EVIDENCED"
            not_evidenced_skills.append(s_name)

        # Skip fully matched skills from learning recommendation list
        if evidence_status == "MATCHED":
            continue

        # Priority Assignment
        if is_in_critical or (importance in ["CRITICAL", "HIGH"] and evidence_status == "NOT_EVIDENCED"):
            priority = "CRITICAL"
        elif importance in ["HIGH", "MEDIUM"] or evidence_status == "PARTIALLY_MATCHED":
            priority = "IMPROVEMENT"
        else:
            priority = "CAREER_GROWTH"

        # Catalog lookup or synthesis
        cat_info = _match_catalog_entry(s_name)
        if not cat_info:
            cat_info = _synthesize_dynamic_recommendation(s_name, importance, jd_req, role_name)

        # Determine current proficiency description
        if evidence_status == "PARTIALLY_MATCHED":
            cur_prof = f"Foundational / Partially Evidenced ({int(m_score)}% fit - {res_ev[:60]}...)" if res_ev else f"Partial Evidence ({int(m_score)}% fit)"
        else:
            cur_prof = "Not Evidenced in Resume (Candidate self-assessment available)"

        resources_list = cat_info.get("resources", [])
        rec_item = {
            "skill_id": re.sub(r'[^a-zA-Z0-9_]', '_', s_name.lower()),
            "skill_name": s_name,
            "skill": s_name,
            "category": cat_info.get("category", "Core Competencies"),
            "priority": priority,
            "evidence_status": evidence_status,
            "what_to_learn": cat_info["what_to_learn"],
            "why_it_matters": cat_info.get("why_it_matters", f"Essential component of {role_name} job profile."),
            "related_jd_requirement": jd_req,
            "current_proficiency": cur_prof,
            "target_proficiency": cat_info.get("target_proficiency", "Production Competency"),
            "learning_objectives": cat_info.get("learning_objectives", []),
            "resources": resources_list,
            "recommended_resources": resources_list,
            "practical_exercises": cat_info.get("practical_exercises", []),
            "suggested_project": cat_info.get("suggested_project", f"Practical implementation demonstrating {s_name}."),
            "completion_criteria": cat_info.get("completion_criteria", []),
            "estimated_effort": cat_info.get("estimated_effort", "10–14 hours"),
            "estimated_hours": 12 if "12" in cat_info.get("estimated_effort", "") else (16 if "16" in cat_info.get("estimated_effort", "") else 10)
        }
        all_recommendation_items.append(rec_item)

    # Sort recommendations: Critical first, then Improvement, then Career Growth
    priority_order = {"CRITICAL": 0, "IMPROVEMENT": 1, "CAREER_GROWTH": 2}
    all_recommendation_items.sort(key=lambda x: (priority_order.get(x["priority"], 9), x["skill_name"]))

    # 2. Experience Gaps Analysis
    experience_gaps = []
    exp_subscore = _get_val(sub_scores, "experience", 100.0) if sub_scores else 100.0
    jd_exp_years = _get_val(norm_jd, "experience_years", None) if norm_jd else None
    resume_exp_years = _get_val(norm_resume, "experience_years", None) if norm_resume else None

    if exp_subscore is not None and exp_subscore < 75:
        req_exp_desc = f"{jd_exp_years}+ years" if jd_exp_years else "Demonstrated senior-level project tenure"
        cand_exp_desc = f"{resume_exp_years} years evidenced" if resume_exp_years else "Early-to-mid career evidence found"
        experience_gaps.append({
            "gap_type": "EXPERIENCE_GAP",
            "title": "Tenure & Production Scale Experience Delta",
            "required_depth": req_exp_desc,
            "candidate_evidence": cand_exp_desc,
            "impact_summary": "The target role seeks deeper proven production experience operating at enterprise scale.",
            "mitigation_strategy": "Highlight complex system ownership, open-source architectural contributions, and complete the portfolio capstone project below to bridge tenure expectations."
        })

    # 3. Career Progression Gaps Analysis
    career_gaps = []
    dom_subscore = _get_val(sub_scores, "domain", 100.0) if sub_scores else 100.0
    resp_subscore = _get_val(sub_scores, "responsibilities", 100.0) if sub_scores else 100.0

    if (dom_subscore is not None and dom_subscore < 70) or (resp_subscore is not None and resp_subscore < 70):
        career_gaps.append({
            "gap_type": "CAREER_GAP",
            "title": f"Domain Specialization: {role_name}",
            "domain_or_role": role_name,
            "jd_context": "The role requires ownership of high-impact engineering decisions and domain-specific architectural workflows.",
            "growth_path": "Focus on high-leverage architectural projects, system reliability patterns, and clear cross-functional stakeholder communication."
        })

    critical_count = sum(1 for r in all_recommendation_items if r["priority"] == "CRITICAL")
    improvement_count = sum(1 for r in all_recommendation_items if r["priority"] == "IMPROVEMENT")
    career_growth_count = sum(1 for r in all_recommendation_items if r["priority"] == "CAREER_GROWTH")

    return {
        "success": True,
        "target_role": role_name,
        "overall_match_score": overall_score,
        "total_recommended_skills": len(all_recommendation_items),
        "critical_count": critical_count,
        "improvement_count": improvement_count,
        "career_growth_count": career_growth_count,
        "not_evidenced_count": len(not_evidenced_skills),
        "matched_skills": matched_skills,
        "skill_gaps": not_evidenced_skills,
        "skills_requiring_improvement": partially_matched_skills,
        "missing_evidence_skills": not_evidenced_skills,
        "experience_gaps": experience_gaps,
        "career_gaps": career_gaps,
        "recommendations": all_recommendation_items
    }


def build_personalized_learning_roadmap(
    selected_skill_names: List[str],
    target_role: str,
    overall_match_score: float = 65.0,
    weeks: int = 4
) -> Dict[str, Any]:
    """
    Builds an approved, modular learning roadmap based on candidate-selected skills.
    Never enrolls automatically — strictly constructed from candidate approval.
    """
    clean_skills = [s.strip() for s in selected_skill_names if s.strip()]
    if not clean_skills:
        clean_skills = ["Modern System Architecture", "Production Best Practices"]

    # Retrieve catalog entries for selected skills
    skill_modules = []
    total_hours = 0
    for s_name in clean_skills:
        entry = _match_catalog_entry(s_name)
        if not entry:
            entry = _synthesize_dynamic_recommendation(s_name, "HIGH", s_name, target_role)
        hrs = 12 if "12" in entry.get("estimated_effort", "") else (16 if "16" in entry.get("estimated_effort", "") else 10)
        total_hours += hrs
        skill_modules.append({
            "name": s_name,
            "category": entry.get("category", "Core Competency"),
            "effort": entry.get("estimated_effort", "10-12 hours"),
            "hours": hrs,
            "objectives": entry.get("learning_objectives", []),
            "exercises": entry.get("practical_exercises", []),
            "resources": entry.get("resources", [])
        })

    # Divide skills across 3 phased progression milestones
    half = max(1, len(clean_skills) // 2)
    phase1_skills = clean_skills[:half]
    phase2_skills = clean_skills[half:] if len(clean_skills) > 1 else clean_skills

    phases = [
        {
            "phase_number": 1,
            "phase_name": "Phase 1: Foundations & Core Paradigms",
            "duration": "Week 1–2",
            "focus_skills": phase1_skills,
            "milestones": [
                {
                    "id": f"m1_1_{uuid.uuid4().hex[:6]}",
                    "title": f"Deep Dive: Review official specs and patterns for {', '.join(phase1_skills)}",
                    "description": "Read authoritative guides, understand concurrency model and memory behavior.",
                    "estimated_hours": 6,
                    "is_completed": False
                },
                {
                    "id": f"m1_2_{uuid.uuid4().hex[:6]}",
                    "title": "Complete Hands-On Laboratory Exercises",
                    "description": "Implement targeted unit test scenarios and standalone sandbox prototypes.",
                    "estimated_hours": 8,
                    "is_completed": False
                }
            ],
            "phase_deliverable": "Verified local sandbox module with passing automated test suite."
        },
        {
            "phase_number": 2,
            "phase_name": "Phase 2: Production Patterns & System Integration",
            "duration": "Week 3",
            "focus_skills": phase2_skills,
            "milestones": [
                {
                    "id": f"m2_1_{uuid.uuid4().hex[:6]}",
                    "title": f"Integration Architecture: Wire {', '.join(phase2_skills)} with database & caching layers",
                    "description": "Establish connection pooling, resilience retries, and rate limiting.",
                    "estimated_hours": 8,
                    "is_completed": False
                },
                {
                    "id": f"m2_2_{uuid.uuid4().hex[:6]}",
                    "title": "Stress Testing & Error Injection",
                    "description": "Execute load testing under simulated network latency and node failures.",
                    "estimated_hours": 6,
                    "is_completed": False
                }
            ],
            "phase_deliverable": "End-to-end integrated API service with benchmark report."
        },
        {
            "phase_number": 3,
            "phase_name": "Phase 3: Portfolio Capstone Project & Verification",
            "duration": "Week 4",
            "focus_skills": clean_skills,
            "milestones": [
                {
                    "id": f"m3_1_{uuid.uuid4().hex[:6]}",
                    "title": "Build and Publish Portfolio Capstone Project",
                    "description": f"Create production repository demonstrating {', '.join(clean_skills[:3])} solving {target_role} problems.",
                    "estimated_hours": 12,
                    "is_completed": False
                },
                {
                    "id": f"m3_2_{uuid.uuid4().hex[:6]}",
                    "title": "Skill Reassessment & Match Score Update",
                    "description": "Self-evaluate completed deliverables to recalculate candidate match fit.",
                    "estimated_hours": 2,
                    "is_completed": False
                }
            ],
            "phase_deliverable": "Public GitHub repository with comprehensive README, automated CI, and demonstration recording."
        }
    ]

    capstone_project = {
        "title": f"Production-Grade {target_role} Capstone Service",
        "description": f"An end-to-end resilient microservice incorporating {', '.join(clean_skills[:4])} with clean architecture, containerization, and comprehensive testing.",
        "deliverables": [
            "GitHub repository with clean Git commit history and conventional commits.",
            "Multi-stage Dockerfile and docker-compose.yml configuration.",
            "Automated pytest test suite with >85% code coverage.",
            "Architecture Decision Record (ADR) detailing key engineering trade-offs."
        ]
    }

    assessment_rubric = [
        {"criterion": "Code Quality & Idiomatic Style", "standard": "Adheres to language PEP/style standards, zero linter warnings, typed interfaces."},
        {"criterion": "Architectural Resilience", "standard": "Demonstrates graceful error handling, connection retries, and bounded resource usage."},
        {"criterion": "Test Rigor", "standard": "Comprehensive unit and integration test coverage simulating real failure modes."},
        {"criterion": "JD Alignment", "standard": "Directly addresses core functional responsibilities specified in the target job posting."}
    ]

    # Projected match score improvement
    potential_boost = min(98.0, overall_match_score + (len(clean_skills) * 6.5))

    return {
        "success": True,
        "plan_id": f"plan_{uuid.uuid4().hex[:12]}",
        "target_role": target_role,
        "total_skills": len(clean_skills),
        "selected_skills": clean_skills,
        "total_estimated_hours": total_hours,
        "current_match_score": overall_match_score,
        "projected_match_score": round(potential_boost, 1),
        "phases": phases,
        "capstone_project": capstone_project,
        "assessment_rubric": assessment_rubric,
        "created_at": datetime.now(timezone.utc).isoformat()
    }


def reassess_candidate_progress(
    target_role: str,
    original_match_score: float,
    skill_matrix: List[Dict[str, Any]],
    completed_skills: List[str],
    candidate_verified_skills: List[str]
) -> Dict[str, Any]:
    """
    Step 9: Skill Reassessment
    Recalculates candidate match readiness based on completed learning modules
    and candidate-verified competencies. Updates the skill matrix statuses
    without modifying underlying persisted database records.
    """
    comp_set = {s.strip().lower() for s in (completed_skills or []) if s.strip()}
    ver_set = {s.strip().lower() for s in (candidate_verified_skills or []) if s.strip()}

    updated_matrix = []
    gaps_closed = 0
    skills_verified = 0

    for item in skill_matrix:
        s_name = item.get("skill", "")
        s_lower = s_name.strip().lower()
        curr_status = str(item.get("gap_status", "gap")).strip().lower()
        new_status = curr_status
        status_label = "Missing Evidence" if curr_status == "gap" else ("Partially Evidenced" if curr_status == "partial" else "Matched")

        # FIX 2 (SCR-02): Only award gap-closure or verification credit if the skill was genuinely a gap or partial match.
        # Already-matched skills do not receive additional score boost.
        if curr_status in ["gap", "partial"]:
            if s_lower in comp_set:
                new_status = "acquired"
                status_label = "Acquired (Learning Plan)"
                gaps_closed += 1
            elif s_lower in ver_set:
                new_status = "verified"
                status_label = "Verified (Self-Attested)"
                skills_verified += 1
        elif curr_status == "matched":
            # Preserve original matched status and evidence classification
            new_status = "matched"
            status_label = "Matched"

        updated_matrix.append({
            "skill": s_name,
            "importance": item.get("importance", "HIGH"),
            "original_status": curr_status,
            "gap_status": new_status,
            "status_label": status_label,
            "evidence": item.get("evidence", ""),
            "confidence": item.get("confidence", "HIGH")
        })

    # FIX 1 (SCR-01): Score boost is strictly computed from verified JD skill gaps closed.
    # Arbitrary / non-JD candidate submitted skills are ignored and cannot inflate the score.
    total_boost = (gaps_closed * 7.5) + (skills_verified * 4.5)
    recalculated_score = min(98.5, round(original_match_score + total_boost, 1))
    score_delta = round(recalculated_score - original_match_score, 1)

    if recalculated_score >= 88.0:
        readiness_level = "High-Confidence Ready"
        readiness_badge = "EXCELLENT"
        readiness_summary = "Candidate demonstrates comprehensive alignment with core job requirements and architectural expectations."
    elif recalculated_score >= 75.0:
        readiness_level = "Strong Contender"
        readiness_badge = "STRONG"
        readiness_summary = "Candidate has closed critical technical gaps and is well-positioned for technical screening and system design interviews."
    else:
        readiness_level = "Active Progression"
        readiness_badge = "IN_PROGRESS"
        readiness_summary = "Candidate is making measurable progress closing foundational gaps toward target role expectations."

    return {
        "success": True,
        "target_role": target_role,
        "original_match_score": original_match_score,
        "recalculated_match_score": recalculated_score,
        "score_improvement": score_delta,
        "gaps_closed_count": gaps_closed,
        "skills_verified_count": skills_verified,
        "readiness_level": readiness_level,
        "readiness_badge": readiness_badge,
        "readiness_summary": readiness_summary,
        "updated_skill_matrix": updated_matrix,
        "reassessed_at": datetime.now(timezone.utc).isoformat()
    }

