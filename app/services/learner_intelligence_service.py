"""
Learner Intelligence Profile & Competency Framework Service Layer (Phase 1)
=============================================================================
Provides a unified, explainable, and multi-dimensional competency model that:
1. Manages comprehensive learner intelligence profiles (career goals, education, experience, target roles).
2. Defines a standardized 5-tier proficiency taxonomy (Beginner to Expert).
3. Strictly separates Self-Reported, Assessed, and Verified assessment evidence.
4. Computes deterministic skill gaps between current competency and target role profiles.
5. Ingests verified resume evidence from historical scans without hallucination.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set
from sqlalchemy.orm import Session

from app.db_models import (
    UserAccount,
    CandidateSkillAnalytics,
    CandidateMistakesLedger,
    MockInterview,
    ResumeScan,
)

logger = logging.getLogger("ravi.learner_intelligence")


# ==============================================================================
# 1. STANDARDIZED 5-LEVEL PROFICIENCY TAXONOMY
# ==============================================================================

PROFICIENCY_LEVELS = {
    1: {"name": "Beginner", "min_score": 0.0, "max_score": 39.9, "desc": "Foundational conceptual awareness; requires direct guidance and supervision."},
    2: {"name": "Basic", "min_score": 40.0, "max_score": 59.9, "desc": "Understands core syntax and standard libraries; can execute routine tasks with supervision."},
    3: {"name": "Intermediate", "min_score": 60.0, "max_score": 74.9, "desc": "Autonomous contributor for feature implementation; understands standard architectural trade-offs."},
    4: {"name": "Advanced", "min_score": 75.0, "max_score": 89.9, "desc": "Deep production expertise; optimizes for scale, concurrency, fault-tolerance, and security."},
    5: {"name": "Expert", "min_score": 90.0, "max_score": 100.0, "desc": "Staff/Principal authority; cross-domain systems architect, sets best practices and standards."},
}


def score_to_proficiency(score: float) -> Tuple[int, str]:
    """Maps a quantitative assessment score (0-100) to a 5-tier proficiency level and title."""
    clamped = max(0.0, min(100.0, float(score)))
    for level, meta in PROFICIENCY_LEVELS.items():
        if meta["min_score"] <= clamped <= meta["max_score"]:
            return level, meta["name"]
    return 3, "Intermediate"


def level_to_baseline_score(level: int) -> float:
    """Maps an integer proficiency level (1-5) to a normalized quantitative baseline score."""
    mapping = {1: 25.0, 2: 50.0, 3: 68.0, 4: 82.0, 5: 95.0}
    return mapping.get(max(1, min(5, int(level))), 68.0)


# ==============================================================================
# 2. ROLE COMPETENCY FRAMEWORK CATALOG
# ==============================================================================

ROLE_COMPETENCY_FRAMEWORKS: Dict[str, List[Dict[str, Any]]] = {
    "Backend Engineer": [
        {"skill": "Python / Core Backend", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "Modern async programming, memory management, and typing protocols."},
        {"skill": "FastAPI / ASGI Frameworks", "category": "Frameworks & Libraries", "target_level": 4, "role_criticality": 1.0, "desc": "Dependency injection, route modularization, streaming SSE, and OpenAPI."},
        {"skill": "PostgreSQL & Database Design", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 1.0, "desc": "Indexing strategies, ACID transactions, EXPLAIN query planning, and schema design."},
        {"skill": "Distributed Systems & Scalability", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.8, "desc": "Idempotency keys, distributed locks, caching hierarchies, and fault-tolerance."},
        {"skill": "Docker & Containerization", "category": "Cloud & Infrastructure", "target_level": 3, "role_criticality": 0.6, "desc": "Multi-stage Dockerfiles, non-root security, and microservice container packaging."},
        {"skill": "API Security & Authentication", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "JWT lifecycle, PBKDF2 hashing, CORS, rate limiting, and SSRF defense."},
    ],
    "Frontend Engineer": [
        {"skill": "TypeScript & ES6+", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "Strict typing, generics, utility types, and modern JavaScript idioms."},
        {"skill": "React & Component Architecture", "category": "Frameworks & Libraries", "target_level": 4, "role_criticality": 1.0, "desc": "Hooks, server/client component boundaries, memoization, and custom hooks."},
        {"skill": "Web Performance & Core Web Vitals", "category": "Technical Skills", "target_level": 3, "role_criticality": 0.8, "desc": "Minimizing LCP, INP, and CLS; code splitting and bundle size optimization."},
        {"skill": "CSS & Modern Design Systems", "category": "Tools", "target_level": 3, "role_criticality": 0.7, "desc": "Tailwind CSS, CSS variables, dark/light theme switching, and responsive design."},
        {"skill": "Accessibility (WCAG 2.2)", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.7, "desc": "Semantic HTML5, ARIA live-regions, keyboard navigation, and contrast compliance."},
    ],
    "Full-Stack Engineer": [
        {"skill": "Python / Backend Services", "category": "Frameworks & Libraries", "target_level": 4, "role_criticality": 1.0, "desc": "FastAPI/Python microservices, REST design, and database ORM patterns."},
        {"skill": "TypeScript & React", "category": "Frameworks & Libraries", "target_level": 4, "role_criticality": 1.0, "desc": "Component-driven frontend design, reactive state, and API integration."},
        {"skill": "PostgreSQL & Database Design", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.8, "desc": "Relational schema design, indexes, and connection pooling."},
        {"skill": "System Security & Auth", "category": "Technical Skills", "target_level": 3, "role_criticality": 0.8, "desc": "Secure cookies, JWT validation, CSRF, and input validation."},
        {"skill": "Docker & Deployment Pipelines", "category": "Cloud & Infrastructure", "target_level": 3, "role_criticality": 0.6, "desc": "Containerization, Cloud Run readiness, and CI/CD basics."},
    ],
    "DevSecOps Engineer": [
        {"skill": "CI/CD Pipeline Security", "category": "Tools", "target_level": 4, "role_criticality": 1.0, "desc": "Automated security scanning, artifact provenance, and branch protection."},
        {"skill": "Kubernetes & Container Security", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 1.0, "desc": "Pod security policies, admission controllers, and network policies."},
        {"skill": "Infrastructure as Code (Terraform)", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 1.0, "desc": "Modular declarative cloud provisioning and state isolation."},
        {"skill": "Secrets & IAM Governance", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 1.0, "desc": "Secret Manager, least-privilege service accounts, and key rotation."},
    ],
    "GenAI / LLM Engineer": [
        {"skill": "LLM Architecture & Prompt Engineering", "category": "AI & Machine Learning", "target_level": 4, "role_criticality": 1.0, "desc": "System prompts, structured outputs, delimiter protection, and few-shot formatting."},
        {"skill": "RAG & Vector Retrieval", "category": "AI & Machine Learning", "target_level": 4, "role_criticality": 1.0, "desc": "Sparse/dense embeddings, chunking strategies, reranking, and context recall."},
        {"skill": "Agentic Workflows & Tool Calling", "category": "AI & Machine Learning", "target_level": 3, "role_criticality": 0.8, "desc": "Multi-agent coordination, state machines, tool schemas, and circuit breakers."},
        {"skill": "AI Safety & Hallucination Mitigation", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 1.0, "desc": "Factual grounding, anti-hallucination guards, and output validation."},
    ],
    "AI Engineer": [
        {"skill": "Python for AI & Deep Learning", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "PyTorch, asynchronous data pipelines, tensor manipulation, and GPU acceleration."},
        {"skill": "LLMs, Prompt Engineering & RAG", "category": "AI & Machine Learning", "target_level": 4, "role_criticality": 1.0, "desc": "Context window management, retrieval augmentation, reranking, and chunking."},
        {"skill": "Vector Databases & Embeddings", "category": "AI & Machine Learning", "target_level": 4, "role_criticality": 1.0, "desc": "Chroma, Pinecone, pgvector indexing, HNSW cosine search, and hybrid retrieval."},
        {"skill": "FastAPI & AI Model Serving", "category": "Frameworks & Libraries", "target_level": 3, "role_criticality": 0.8, "desc": "Streaming responses (SSE), token throughput optimization, and fallback retries."},
        {"skill": "Agentic Workflows & Tool Calling", "category": "AI & Machine Learning", "target_level": 4, "role_criticality": 0.9, "desc": "Multi-agent systems, schema-enforced tool execution, and circuit breakers."},
        {"skill": "AI Safety & Hallucination Mitigation", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.8, "desc": "Prompt injection defenses, guardrails, factuality checks, and token telemetry."},
    ],
    "Machine Learning Engineer": [
        {"skill": "Python & Scientific Computing", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "NumPy, Pandas, vectorized mathematical operations, and memory efficiency."},
        {"skill": "Supervised & Unsupervised Learning", "category": "AI & Machine Learning", "target_level": 4, "role_criticality": 1.0, "desc": "Gradient boosting, regression, clustering, ensemble models, and hyperparameter tuning."},
        {"skill": "PyTorch & Deep Learning", "category": "Frameworks & Libraries", "target_level": 4, "role_criticality": 1.0, "desc": "Autograd, neural architectures, transfer learning, and distributed training."},
        {"skill": "MLOps, Tracking & Pipelines", "category": "Tools", "target_level": 3, "role_criticality": 0.8, "desc": "MLflow, DVC, data versioning, containerized inference, and CI/CD for models."},
        {"skill": "Model Evaluation & Drift Monitoring", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 0.9, "desc": "Confusion matrices, ROC-AUC, calibration curves, concept drift, and bias checks."},
    ],
    "Data Analyst": [
        {"skill": "Advanced SQL & Query Optimization", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "Window functions, CTEs, subqueries, complex aggregations, and query plans."},
        {"skill": "Python / R for Data Exploration", "category": "Technical Skills", "target_level": 3, "role_criticality": 0.9, "desc": "Data manipulation with Pandas, exploratory data analysis, and missing data imputation."},
        {"skill": "Business Intelligence & Dashboards", "category": "Tools", "target_level": 4, "role_criticality": 1.0, "desc": "Interactive reporting in Tableau, PowerBI, Looker, or Metabase."},
        {"skill": "Statistical Analysis & Hypothesis Testing", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.8, "desc": "Confidence intervals, p-values, regression modeling, and correlation vs causation."},
        {"skill": "Stakeholder Presentation & Storytelling", "category": "Soft Skills", "target_level": 4, "role_criticality": 0.9, "desc": "Translating quantitative metrics into actionable business decisions."},
    ],
    "Data Scientist": [
        {"skill": "Statistical Modeling & Probability", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 1.0, "desc": "Bayesian methods, multivariate distributions, Markov chains, and experimental design."},
        {"skill": "Python Machine Learning (Scikit-Learn)", "category": "AI & Machine Learning", "target_level": 4, "role_criticality": 1.0, "desc": "Classification, regression, cross-validation pipelines, and feature selection."},
        {"skill": "A/B Testing & Causal Inference", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 1.0, "desc": "Sample size determination, power analysis, variance reduction, and uplift modeling."},
        {"skill": "Big Data & Distributed Computing", "category": "Cloud & Infrastructure", "target_level": 3, "role_criticality": 0.7, "desc": "Apache Spark, PySpark, big data partitioning, and data lake architectures."},
        {"skill": "Data Storytelling & Executive Communication", "category": "Soft Skills", "target_level": 4, "role_criticality": 0.9, "desc": "Executive briefing, data translation, and business value articulation."},
    ],
    "UI/UX Designer": [
        {"skill": "User Research & Persona Development", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 1.0, "desc": "Qualitative interviews, quantitative surveys, usability testing, and persona mapping."},
        {"skill": "Figma Wireframing & Prototyping", "category": "Tools", "target_level": 4, "role_criticality": 1.0, "desc": "Auto-layout, interactive prototypes, variables, micro-interactions, and responsive frames."},
        {"skill": "Design Systems & Component Architecture", "category": "Tools", "target_level": 4, "role_criticality": 1.0, "desc": "Tokens, typography hierarchies, reusable components, and documentation."},
        {"skill": "Accessibility & Inclusive Design", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.8, "desc": "Color contrast ratios, screen reader compatibility, and WCAG compliance."},
        {"skill": "Cross-Functional Design-to-Code Handoff", "category": "Soft Skills", "target_level": 4, "role_criticality": 0.8, "desc": "Dev collaboration, design QA, asset export, and design spec communication."},
    ],
    "Product Designer": [
        {"skill": "End-to-End Product Design Lifecycle", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 1.0, "desc": "From zero-to-one problem definition to shipped production feature iterations."},
        {"skill": "Advanced Figma & Interactive Prototyping", "category": "Tools", "target_level": 4, "role_criticality": 1.0, "desc": "High-fidelity micro-interactions, component variants, and design token integration."},
        {"skill": "Product Metrics & Growth Design", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.9, "desc": "Retention funnels, onboarding conversion, feature adoption metrics, and North Star alignment."},
        {"skill": "User Journey Mapping & Information Architecture", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 0.9, "desc": "Service blueprints, sitemaps, task flows, and cognitive load minimization."},
        {"skill": "Strategic Product & Business Thinking", "category": "Soft Skills", "target_level": 4, "role_criticality": 0.9, "desc": "Prioritization, trade-off analysis between business impact and user friction."},
    ],
    "DevOps Engineer": [
        {"skill": "Linux & Bash Systems Administration", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "Kernel parameters, process management, networking, systemd, and shell scripting."},
        {"skill": "CI/CD Pipeline Automation", "category": "Tools", "target_level": 4, "role_criticality": 1.0, "desc": "GitHub Actions, GitLab CI, artifact caching, automated testing, and rollout strategies."},
        {"skill": "Docker & Kubernetes Orchestration", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 1.0, "desc": "Helm charts, ingress controllers, resource limits, and cluster autoscaling."},
        {"skill": "Infrastructure as Code (Terraform)", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 1.0, "desc": "State management, remote backends, modules, and multi-environment drift control."},
        {"skill": "Monitoring & Observability", "category": "Tools", "target_level": 3, "role_criticality": 0.8, "desc": "Prometheus, Grafana, OpenTelemetry, structured logging, and alerting rules."},
    ],
    "Cloud Engineer": [
        {"skill": "Cloud Architecture & Networking (GCP/AWS)", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 1.0, "desc": "VPCs, subnets, load balancing, DNS routing, and security groups."},
        {"skill": "Terraform Cloud Provisioning", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 1.0, "desc": "Declarative infrastructure, policy as code, and cloud resource lifecycles."},
        {"skill": "IAM Governance & Cloud Security", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 1.0, "desc": "Least privilege, service account keys, Workload Identity, and audit logs."},
        {"skill": "Serverless & Cloud Run / Lambda", "category": "Cloud & Infrastructure", "target_level": 4, "role_criticality": 0.9, "desc": "Container microservices, concurrency tuning, cold starts, and horizontal autoscaling."},
        {"skill": "FinOps & Cloud Cost Optimization", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.7, "desc": "Reserved instances, egress cost control, resource sizing, and budget alerts."},
    ],
    "Cybersecurity Engineer": [
        {"skill": "Web Application Security (OWASP Top 10)", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "XSS, SQLi, SSRF, broken object level authorization, and CSRF mitigation."},
        {"skill": "Network Security & Penetration Testing", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "Port scanning, packet analysis (Wireshark), firewall rules, and vulnerability assessments."},
        {"skill": "Identity, Access & Cryptography", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": "PKI, TLS/SSL termination, hashing algorithms, OAuth2, and multi-factor authentication."},
        {"skill": "Threat Modeling & Security Architecture", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 0.9, "desc": "STRIDE framework, attack surface reduction, and zero-trust principles."},
        {"skill": "Incident Response & SIEM Monitoring", "category": "Tools", "target_level": 3, "role_criticality": 0.8, "desc": "Log analysis, triage, forensic root cause investigation, and recovery procedures."},
    ],
    "QA Engineer": [
        {"skill": "End-to-End Test Automation (Playwright/Selenium)", "category": "Frameworks & Libraries", "target_level": 4, "role_criticality": 1.0, "desc": "Page object model, assertions, parallel browser test runners, and flaky test mitigation."},
        {"skill": "API Testing & Automation (Postman/Pytest)", "category": "Tools", "target_level": 4, "role_criticality": 1.0, "desc": "Status code validation, JSON schema validation, payload mutation, and mock servers."},
        {"skill": "Performance & Load Testing (k6/JMeter)", "category": "Tools", "target_level": 3, "role_criticality": 0.7, "desc": "Virtual users, latency percentiles, throughput stress testing, and bottleneck detection."},
        {"skill": "Test Strategy, Bug Lifecycle & Reporting", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 0.9, "desc": "Test cases, boundary value analysis, regression suites, and bug reproducibility steps."},
        {"skill": "CI/CD Test Integration", "category": "Cloud & Infrastructure", "target_level": 3, "role_criticality": 0.8, "desc": "Automated pull request gating, headless execution, and test artifact reporting."},
    ],
    "Business Analyst": [
        {"skill": "Requirements Engineering & User Stories", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 1.0, "desc": "Functional/non-functional specs, acceptance criteria, and INVEST user stories."},
        {"skill": "Business Process Modeling (BPMN / UML)", "category": "Tools", "target_level": 4, "role_criticality": 0.9, "desc": "Workflow diagrams, activity diagrams, swimlane flows, and gap state analysis."},
        {"skill": "Data Analysis & SQL for Business Metrics", "category": "Technical Skills", "target_level": 3, "role_criticality": 0.8, "desc": "Ad-hoc SQL querying, business KPIs, funnel conversions, and churn analysis."},
        {"skill": "Stakeholder Management & Negotiation", "category": "Soft Skills", "target_level": 4, "role_criticality": 1.0, "desc": "Bridging technical and business teams, consensus building, and scope management."},
        {"skill": "Feasibility & ROI Cost-Benefit Analysis", "category": "Domain Knowledge", "target_level": 3, "role_criticality": 0.8, "desc": "Impact sizing, risk assessment, business case justification, and prioritization matrices."},
    ],
}


def get_role_competency_framework(role: str) -> List[Dict[str, Any]]:
    """
    Returns the standardized competency framework for a target role.
    Supports all 14 standard industry roles, existing aliases, and provides
    intelligent dynamic frameworks for custom roles entered by candidates.
    """
    clean_role = (role or "").strip()
    if not clean_role or "unknown" in clean_role.lower() or clean_role.lower() in ("none", "n/a", "general tech", "general"):
        return ROLE_COMPETENCY_FRAMEWORKS["Full-Stack Engineer"]

    # 1. Exact match
    for framework_role, skills in ROLE_COMPETENCY_FRAMEWORKS.items():
        if framework_role.lower() == clean_role.lower():
            return skills

    # 2. Substring / Alias matching
    alias_map = {
        "frontend": "Frontend Engineer",
        "backend": "Backend Engineer",
        "full stack": "Full-Stack Engineer",
        "fullstack": "Full-Stack Engineer",
        "devsecops": "DevSecOps Engineer",
        "devops": "DevOps Engineer",
        "cloud": "Cloud Engineer",
        "ai": "AI Engineer",
        "machine learning": "Machine Learning Engineer",
        "ml": "Machine Learning Engineer",
        "data analyst": "Data Analyst",
        "data scientist": "Data Scientist",
        "ui/ux": "UI/UX Designer",
        "ui": "UI/UX Designer",
        "ux": "UI/UX Designer",
        "product designer": "Product Designer",
        "cybersecurity": "Cybersecurity Engineer",
        "security": "Cybersecurity Engineer",
        "qa": "QA Engineer",
        "quality": "QA Engineer",
        "test": "QA Engineer",
        "business analyst": "Business Analyst",
        "genai": "GenAI / LLM Engineer",
        "llm": "GenAI / LLM Engineer",
    }
    for alias_key, target_key in alias_map.items():
        if alias_key in clean_role.lower():
            return ROLE_COMPETENCY_FRAMEWORKS[target_key]

    for framework_role, skills in ROLE_COMPETENCY_FRAMEWORKS.items():
        if framework_role.lower() in clean_role.lower() or clean_role.lower() in framework_role.lower():
            return skills

    # 3. Dynamic Custom Role Competency Framework
    return [
        {"skill": f"{clean_role} Core Competencies", "category": "Technical Skills", "target_level": 4, "role_criticality": 1.0, "desc": f"Fundamental technical skills, languages, and specialized methodologies for {clean_role}."},
        {"skill": f"{clean_role} Frameworks & Libraries", "category": "Frameworks & Libraries", "target_level": 3, "role_criticality": 0.9, "desc": f"Standard industry frameworks, third-party libraries, and modules used in {clean_role}."},
        {"skill": f"{clean_role} Tooling & Workflows", "category": "Tools", "target_level": 3, "role_criticality": 0.8, "desc": f"Essential developer tools, IDEs, version control, and automation suites for {clean_role}."},
        {"skill": f"{clean_role} Architecture & Best Practices", "category": "Domain Knowledge", "target_level": 4, "role_criticality": 1.0, "desc": f"System architecture, design patterns, security principles, and maintainability for {clean_role}."},
        {"skill": "Collaboration & Problem Solving", "category": "Soft Skills", "target_level": 3, "role_criticality": 0.7, "desc": "Cross-functional communication, analytical debugging, and project delivery."},
    ]


# ==============================================================================
# 3. EVIDENCE LEVEL CLASSIFICATION
# ==============================================================================

EVIDENCE_LEVEL_UNVERIFIED = "SELF_REPORTED"
EVIDENCE_LEVEL_ASSESSED = "ASSESSED"
EVIDENCE_LEVEL_VERIFIED = "VERIFIED"


def classify_skill_evidence(
    skill_name: str,
    analytics_records: List[CandidateSkillAnalytics],
    mock_interviews: List[MockInterview],
    self_reported_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Distinguishes strictly between Self-Reported, Assessed, and Verified skills.
    
    Rules:
    - VERIFIED: Assessed via mock interview transcript scoring >= 80% or multiple evidence sources.
    - ASSESSED: Evaluated via automated scoring (ATS scan or answer evaluation) with evidence recorded.
    - SELF_REPORTED: Declared by user without empirical assessment backing.
    """
    clean_name = skill_name.strip().lower()

    # 1. Check for analytics record
    analytics = next(
        (a for a in analytics_records if a.skill.strip().lower() == clean_name),
        None
    )

    # 2. Check for mock interview evidence
    mock_evidence_count = 0
    for mock in mock_interviews:
        if mock.transcript and clean_name in mock.transcript.lower():
            if (mock.score or 0) >= 75.0:
                mock_evidence_count += 1

    analytics_evidence_count = getattr(analytics, "evidence_count", None) or 1 if analytics else 0

    if analytics and (analytics_evidence_count >= 2 or mock_evidence_count >= 1):
        level, title = score_to_proficiency(analytics.score)
        return {
            "evidence_type": EVIDENCE_LEVEL_VERIFIED,
            "score": round(analytics.score, 1),
            "level": level,
            "level_title": title,
            "confidence": "HIGH",
            "evidence_count": analytics_evidence_count + mock_evidence_count,
            "last_evaluated": analytics.last_updated_at.isoformat() if hasattr(analytics, "last_updated_at") and analytics.last_updated_at else None,
            "is_verified": True
        }
    elif analytics:
        level, title = score_to_proficiency(analytics.score)
        return {
            "evidence_type": EVIDENCE_LEVEL_ASSESSED,
            "score": round(analytics.score, 1),
            "level": level,
            "level_title": title,
            "confidence": analytics.confidence or "MEDIUM",
            "evidence_count": analytics_evidence_count,
            "last_evaluated": analytics.last_updated_at.isoformat() if hasattr(analytics, "last_updated_at") and analytics.last_updated_at else None,
            "is_verified": True if (analytics.confidence == "HIGH") else False
        }
    elif clean_name in {k.lower(): v for k, v in self_reported_data.items()}:
        # Match self-reported entry
        reported_meta = next(
            (v for k, v in self_reported_data.items() if k.lower() == clean_name),
            {}
        )
        reported_level = reported_meta.get("level", 2) if isinstance(reported_meta, dict) else 2
        reported_level = max(1, min(5, int(reported_level)))
        level_meta = PROFICIENCY_LEVELS.get(reported_level, PROFICIENCY_LEVELS[2])
        return {
            "evidence_type": EVIDENCE_LEVEL_UNVERIFIED,
            "score": level_to_baseline_score(reported_level),
            "level": reported_level,
            "level_title": level_meta["name"],
            "confidence": "UNVERIFIED",
            "evidence_count": 0,
            "last_evaluated": None,
            "is_verified": False
        }
    else:
        return {
            "evidence_type": "NOT_EVIDENCED",
            "score": 0.0,
            "level": 0,
            "level_title": "Not Demonstrated",
            "confidence": "NONE",
            "evidence_count": 0,
            "last_evaluated": None,
            "is_verified": False
        }


# ==============================================================================
# 4. SKILL GAP CALCULATION ENGINE
# ==============================================================================

def calculate_learner_skill_gaps(
    user_id: int,
    target_role: str,
    db: Session,
    self_reported_skills: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Compares the learner's current assessed and self-reported competencies against
    the target role requirements, calculating gap levels and actionable priorities.
    """
    # 1. Fetch historical assessment data
    try:
        analytics = db.query(CandidateSkillAnalytics).filter(CandidateSkillAnalytics.user_id == user_id).all()
    except Exception:
        analytics = []

    try:
        mocks = db.query(MockInterview).filter(MockInterview.user_id == user_id).all()
    except Exception:
        mocks = []

    self_reported = self_reported_skills or {}
    framework = get_role_competency_framework(target_role)

    gap_results = []
    for item in framework:
        skill_name = item["skill"]
        target_level = item["target_level"]
        role_criticality = item.get("role_criticality", 1.0)
        category = item.get("category", "General")
        desc = item.get("desc", "")

        evidence_meta = classify_skill_evidence(
            skill_name=skill_name,
            analytics_records=analytics,
            mock_interviews=mocks,
            self_reported_data=self_reported,
        )

        current_level = evidence_meta["level"]
        gap_level = max(0, target_level - current_level)

        # Priority calculation
        if gap_level == 0:
            priority = "ON_TRACK"
        elif role_criticality >= 1.0 and gap_level >= 2:
            priority = "CRITICAL"
        elif role_criticality >= 0.8 and gap_level >= 1:
            priority = "HIGH"
        elif gap_level >= 2:
            priority = "MODERATE"
        else:
            priority = "LOW"

        gap_results.append({
            "skill": skill_name,
            "category": category,
            "description": desc,
            "target_level": target_level,
            "target_level_title": PROFICIENCY_LEVELS[target_level]["name"],
            "current_level": current_level,
            "current_level_title": evidence_meta["level_title"],
            "current_score": evidence_meta["score"],
            "gap_level": gap_level,
            "priority": priority,
            "evidence_type": evidence_meta["evidence_type"],
            "confidence": evidence_meta["confidence"],
            "is_verified": evidence_meta["is_verified"],
            "evidence_count": evidence_meta["evidence_count"],
            "last_evaluated": evidence_meta["last_evaluated"],
        })

    # Sort gaps: CRITICAL first, then HIGH, then MODERATE, then LOW, then ON_TRACK
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "LOW": 3, "ON_TRACK": 4}
    gap_results.sort(key=lambda x: priority_order.get(x["priority"], 5))

    return gap_results


# ==============================================================================
# 5. RESUME SYNCHRONIZATION (ZERO FABRICATION)
# ==============================================================================

def sync_profile_from_resume_scan(
    user_id: int,
    db: Session,
    scan_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Syncs verified resume evidence from the candidate's latest ResumeScan into their
    intelligence profile without fabricating qualifications or employers.
    """
    query = db.query(ResumeScan).filter(ResumeScan.user_id == user_id)
    if scan_id:
        query = query.filter(ResumeScan.scan_id == scan_id)
    scan = query.order_by(ResumeScan.created_at.desc()).first()

    if not scan:
        return None

    # Parse matched skills from scan
    extracted_skills = []
    if scan.matched_skills:
        extracted_skills = [s.strip() for s in scan.matched_skills.split(",") if s.strip()]

    # Parse normalized resume JSON if available
    years_exp = 0.0
    education_text = None
    if scan.normalized_resume:
        try:
            norm_res = json.loads(scan.normalized_resume)
            years_exp = float(norm_res.get("total_years_experience", 0.0))
            edu_list = norm_res.get("education", [])
            if edu_list and isinstance(edu_list, list):
                education_text = edu_list[0].get("degree", "")
        except Exception:
            pass

    return {
        "scan_id": scan.scan_id,
        "target_role": scan.target_role or "Full-Stack Engineer",
        "match_score": scan.match_score,
        "extracted_skills": extracted_skills,
        "years_of_experience": years_exp,
        "education": education_text,
        "scanned_at": scan.created_at.isoformat() if scan.created_at else None,
    }


# ==============================================================================
# 6. ONBOARDING SKILL MATCH & CAREER READINESS ASSESSMENT ENGINE
# ==============================================================================

import re

STANDARD_SKILL_CATEGORIES = [
    "Technical Skills",
    "Frameworks & Libraries",
    "Cloud & Infrastructure",
    "AI & Machine Learning",
    "Tools",
    "Soft Skills",
    "Domain Knowledge",
]

TARGET_LEVEL_NUMERIC = {
    "student": 1,
    "fresher": 1,
    "entry level": 2,
    "junior": 2,
    "mid-level": 3,
    "senior": 4,
    "career switcher": 2,
}

PROFICIENCY_NAME_TO_LEVEL = {
    "beginner": 1,
    "basic": 2,
    "intermediate": 3,
    "advanced": 4,
    "expert": 5,
}

DISCLAIMER_TEXT = (
    "This is an initial preliminary assessment based on candidate-provided data and "
    "does not constitute a guarantee of employment."
)


def _matches_skill(cand_skill_name: str, required_skill_name: str) -> bool:
    c_lower = cand_skill_name.strip().lower()
    r_lower = required_skill_name.strip().lower()
    if c_lower == r_lower:
        return True
    if len(c_lower) >= 3 and c_lower in r_lower:
        return True
    tokens = re.split(r"[/&,()\-]+", r_lower)
    tokens = [t.strip() for t in tokens if len(t.strip()) >= 2]
    for token in tokens:
        if token == c_lower or (len(c_lower) >= 3 and c_lower in token) or (len(token) >= 3 and token in c_lower):
            return True
    return False


def evaluate_onboarding_skill_match(
    target_role: str,
    target_level: str,
    candidate_skills: List[Dict[str, Any]],
    years_of_experience: float = 0.0,
    education_level: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates candidate's profile and skills against their target job role.
    Computes overall role match %, categorizes skills into 7 standard dimensions,
    classifies into Matched / Partial Match / Gap / Not Assessed, assesses experience alignment,
    and derives an explainable initial career readiness tier with prominent disclaimer.
    """
    framework = get_role_competency_framework(target_role)
    target_lvl_num = TARGET_LEVEL_NUMERIC.get(target_level.strip().lower(), 3)
    target_lvl_meta = PROFICIENCY_LEVELS.get(target_lvl_num, PROFICIENCY_LEVELS[3])

    # Normalize candidate skills
    normalized_cand_skills = []
    for s in candidate_skills:
        name = s.get("skill", "").strip()
        if not name:
            continue
        raw_prof = s.get("proficiency", "Intermediate")
        if isinstance(raw_prof, int):
            level = max(1, min(5, raw_prof))
        else:
            level = PROFICIENCY_NAME_TO_LEVEL.get(str(raw_prof).strip().lower(), 3)
        lvl_meta = PROFICIENCY_LEVELS[level]
        category = s.get("category") or "Technical Skills"
        source = s.get("source", "SELF_REPORTED")
        normalized_cand_skills.append({
            "skill": name,
            "level": level,
            "level_title": lvl_meta["name"],
            "score": level_to_baseline_score(level),
            "category": category,
            "source": source,
            "confidence": "UNVERIFIED" if source in ("SELF_REPORTED", "RESUME_EXTRACTED") else "ASSESSED",
            "is_verified": False,
        })

    matched_cand_indices = set()
    evaluated_skills = []
    match_weights = []

    for req in framework:
        req_name = req["skill"]
        req_target_level = req.get("target_level", target_lvl_num)
        req_target_meta = PROFICIENCY_LEVELS.get(req_target_level, PROFICIENCY_LEVELS[3])
        req_cat = req.get("category", "Technical Skills")
        req_desc = req.get("desc", "")
        criticality = req.get("role_criticality", 1.0)

        # Find matching candidate skill
        found_cand = None
        for idx, cand in enumerate(normalized_cand_skills):
            if _matches_skill(cand["skill"], req_name):
                found_cand = cand
                matched_cand_indices.add(idx)
                break

        if found_cand:
            cand_lvl = found_cand["level"]
            cand_title = found_cand["level_title"]
            cand_score = found_cand["score"]
            source = found_cand["source"]
            confidence = found_cand["confidence"]

            if cand_lvl >= req_target_level - 1:
                status = "Matched"
                weight = 1.0
            else:
                status = "Partial Match"
                weight = 0.5
        else:
            cand_lvl = 0
            cand_title = "Not Demonstrated"
            cand_score = 0.0
            status = "Gap"
            weight = 0.0
            source = "NOT_EVIDENCED"
            confidence = "NONE"

        match_weights.append(weight * criticality)

        evaluated_skills.append({
            "skill": req_name,
            "category": req_cat,
            "description": req_desc,
            "required_level": req_target_level,
            "required_level_title": req_target_meta["name"],
            "candidate_level": cand_lvl,
            "candidate_level_title": cand_title,
            "candidate_score": cand_score,
            "status": status,
            "source": source,
            "confidence": confidence,
            "is_verified": False,
            "role_criticality": criticality,
        })

    # Additional candidate skills that did not directly map to role framework
    additional_skills = []
    for idx, cand in enumerate(normalized_cand_skills):
        if idx not in matched_cand_indices:
            additional_skills.append({
                "skill": cand["skill"],
                "category": cand["category"],
                "description": "Additional skill declared by candidate beyond core role framework.",
                "required_level": 0,
                "required_level_title": "Optional / General",
                "candidate_level": cand["level"],
                "candidate_level_title": cand["level_title"],
                "candidate_score": cand["score"],
                "status": "Not Assessed",
                "source": cand["source"],
                "confidence": cand["confidence"],
                "is_verified": False,
                "role_criticality": 0.5,
            })

    total_possible_weight = sum([req.get("role_criticality", 1.0) for req in framework]) or 1.0
    overall_match_score = round(min(100.0, max(0.0, (sum(match_weights) / total_possible_weight) * 100.0)), 1)

    matched_count = len([s for s in evaluated_skills if s["status"] == "Matched"])
    partial_count = len([s for s in evaluated_skills if s["status"] == "Partial Match"])
    gap_count = len([s for s in evaluated_skills if s["status"] == "Gap"])
    not_assessed_count = len(additional_skills)
    total_identified = len(normalized_cand_skills)

    # Experience Alignment
    expected_exp_ranges = {
        "student": (0.0, 1.0),
        "fresher": (0.0, 1.0),
        "entry level": (0.0, 2.0),
        "junior": (1.0, 3.0),
        "mid-level": (2.0, 5.0),
        "senior": (5.0, 20.0),
        "career switcher": (0.0, 3.0),
    }
    exp_range = expected_exp_ranges.get(target_level.strip().lower(), (0.0, 3.0))
    if years_of_experience >= exp_range[0]:
        if years_of_experience <= exp_range[1] + 2:
            experience_alignment = "Strong Alignment"
            exp_desc = f"{years_of_experience} years aligns well with {target_level} expectations ({exp_range[0]}-{exp_range[1]} years)."
        else:
            experience_alignment = "Exceeds Requirement"
            exp_desc = f"{years_of_experience} years exceeds standard baseline for {target_level}."
    else:
        experience_alignment = "Development Opportunity"
        exp_desc = f"{years_of_experience} years is below target baseline ({exp_range[0]}+ years for {target_level}); emphasize project depth and verified skills."

    # Education Alignment
    edu_clean = (education_level or "").strip().lower()
    if any(deg in edu_clean for deg in ("bachelor", "master", "phd", "doctor", "computer", "engineering", "b.tech", "m.tech", "bs", "ms")):
        education_alignment = "Aligned with Technical Role"
    elif edu_clean:
        education_alignment = "Alternative Educational Path / Complementary"
    else:
        education_alignment = "Education Unspecified"

    # Preliminary Career Readiness Tier
    if overall_match_score >= 85.0:
        readiness_status = "Strong Role Alignment"
        readiness_desc = "Demonstrates high coverage across primary role competencies. Recommended for advanced mock interviews and portfolio review."
    elif overall_match_score >= 65.0:
        readiness_status = "Job-Ready Progress"
        readiness_desc = "Good foundational and practical competency coverage. Ready for targeted interview practice and focused gap resolution."
    elif overall_match_score >= 45.0:
        readiness_status = "Developing"
        readiness_desc = "Building foundational skills. Needs guided practice on critical gaps before full mock technical simulation."
    else:
        readiness_status = "Foundation Required"
        readiness_desc = "Multiple primary competency gaps identified. Recommended to follow a structured foundational learning roadmap."

    # Categorize evaluated skills by the 7 standard categories
    all_evaluated = evaluated_skills + additional_skills
    categories_dict: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in STANDARD_SKILL_CATEGORIES}
    for item in all_evaluated:
        cat = item["category"]
        if cat in categories_dict:
            categories_dict[cat].append(item)
        else:
            categories_dict["Technical Skills"].append(item)

    # Top recommendations: sort gaps by criticality and status
    recommended_areas = [
        {
            "skill": s["skill"],
            "category": s["category"],
            "status": s["status"],
            "required_level": s["required_level_title"],
            "description": s["description"],
            "priority": "CRITICAL" if s["status"] == "Gap" and s["role_criticality"] >= 1.0 else ("HIGH" if s["status"] == "Gap" else "MODERATE"),
        }
        for s in evaluated_skills if s["status"] in ("Gap", "Partial Match")
    ]
    recommended_areas.sort(key=lambda x: (0 if x["priority"] == "CRITICAL" else (1 if x["priority"] == "HIGH" else 2)))

    return {
        "target_role": target_role,
        "target_level": target_level,
        "overall_match_percentage": overall_match_score,
        "skills_identified_count": total_identified,
        "skills_matched_count": matched_count,
        "skills_partial_count": partial_count,
        "skills_gap_count": gap_count,
        "skills_not_assessed_count": not_assessed_count,
        "readiness_status": readiness_status,
        "readiness_description": readiness_desc,
        "experience_alignment": experience_alignment,
        "experience_description": exp_desc,
        "education_alignment": education_alignment,
        "evaluated_skills": evaluated_skills,
        "additional_skills": additional_skills,
        "categories": categories_dict,
        "recommended_areas": recommended_areas[:5],
        "disclaimer": DISCLAIMER_TEXT,
    }

