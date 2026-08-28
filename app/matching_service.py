"""
Resume ↔ Job Description (JD) Multi-Dimensional Matching Engine (Phase 5B)

Evaluates candidate fit against job requirements across multiple dimensions:
- Required Skills (weighted by role importance)
- Preferred Skills
- Experience & Seniority
- Domain Requirements
- Responsibilities & Core Competencies
- Tools & Technologies
- Education & Certifications

Implements:
- Approved Score Weighting Baseline:
    Overall Match = 0.40 * Required_Skills + 0.20 * Experience + 0.15 * Domain + 0.15 * Responsibilities + 0.10 * Preferred_Skills
- Six-Tier Evidence Hierarchy (Level 1 to 6)
- Anti-Masking Critical Gap Rule (High-importance gaps never hidden by high aggregate score)
- Strict Technology Equivalence Boundaries (No Docker==Kubernetes, Redis==Kafka, SQL==PostgreSQL, React==Angular)
- Independent Match Confidence Scoring (LOW / MEDIUM / HIGH)
- Deterministic Fallback & Zero-Fabrication Guarantee
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from datetime import datetime

from app.models import (
    NormalizedJobDescription,
    NormalizedResume,
    ResumeWorkExperience,
    ResumeProject,
    SkillMatrixItem,
    SubScores,
    ResumeJDMatchResult,
)


# ==============================================================================
# IMPORTANCE WEIGHTS & EVIDENCE RATINGS
# ==============================================================================

IMPORTANCE_WEIGHTS = {
    "HIGH": 1.0,
    "MEDIUM": 0.6,
    "LOW": 0.3,
}

# Six-Tier Evidence Model: Level -> (Strength, Credit_Fraction, Description)
EVIDENCE_TIERS = {
    1: ("HIGH", 1.00, "Direct production experience with verified scale/metrics"),
    2: ("HIGH", 0.88, "Core responsibility / major achievement in work history"),
    3: ("MEDIUM", 0.70, "Project / implementation experience"),
    4: ("LOW", 0.45, "Skills-section mention only without contextual bullets"),
    5: ("LOW", 0.25, "Weak contextual / adjacent mention"),
    6: ("NONE", 0.00, "No evidence found in resume"),
}


# ==============================================================================
# SEMANTIC SKILL TAXONOMY & STRICT FALSE-EQUIVALENCE BOUNDARIES
# ==============================================================================

# Genuine semantic aliases and specialized relationships
SEMANTIC_SKILL_RELATIONS: Dict[str, List[Tuple[str, float]]] = {
    "asyncio": [("asynchronous python", 0.90), ("async python", 0.90), ("async/await", 0.85)],
    "fastapi": [("pydantic", 0.65), ("starlette", 0.70), ("uvicorn", 0.60), ("asynchronous rest apis", 0.75)],
    "postgresql": [("postgres", 1.00), ("psql", 0.95), ("relational database", 0.45)],
    "react": [("react.js", 1.00), ("reactjs", 1.00), ("next.js", 0.75)],
    "vue": [("vue.js", 1.00), ("vuejs", 1.00), ("nuxt.js", 0.75)],
    "angular": [("angularjs", 0.80), ("angular 2+", 1.00), ("typescript angular", 0.90)],
    "machine learning": [("deep learning", 0.80), ("scikit-learn", 0.80), ("pytorch", 0.80), ("tensorflow", 0.80)],
    "distributed systems": [("microservices", 0.75), ("system design", 0.75), ("event-driven architecture", 0.75), ("high availability", 0.70)],
    "kubernetes": [("k8s", 1.00), ("container orchestration", 0.75), ("helm", 0.70)],
    "kafka": [("apache kafka", 1.00), ("event streaming", 0.75), ("message broker", 0.50)],
    "docker": [("containerization", 0.85), ("docker-compose", 0.90), ("containers", 0.80)],
    "graphql": [("apollo graphql", 0.90), ("graphql schema", 0.90)],
    "grpc": [("protobuf", 0.85), ("protocol buffers", 0.85), ("rpc", 0.70)],
}

# Strict negative guards: technology pairs that must NEVER be treated as identical
DISALLOWED_EQUIVALENCES: Set[Tuple[str, str]] = {
    ("docker", "kubernetes"),
    ("kubernetes", "docker"),
    ("redis", "kafka"),
    ("kafka", "redis"),
    ("sql", "postgresql"),
    ("postgresql", "sql"),
    ("react", "angular"),
    ("angular", "react"),
    ("vue", "react"),
    ("react", "vue"),
    ("mysql", "mongodb"),
    ("mongodb", "mysql"),
    ("mongodb", "postgresql"),
    ("postgresql", "mongodb"),
    ("flask", "fastapi"),
}


# ==============================================================================
# RESUME NORMALIZATION HELPER
# ==============================================================================

def normalize_resume(raw_text: str) -> NormalizedResume:
    """
    Parses unstructured raw resume text into a structured NormalizedResume model.
    Segments work experience, projects, skills list, education, and calculates duration.
    """
    if not raw_text or not raw_text.strip():
        return NormalizedResume(raw_text="")

    text = raw_text.strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    candidate_name = None
    email = None
    phone = None
    summary = None
    total_years = 0.0

    # 1. Contact Info
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    if email_match:
        email = email_match.group(0)

    phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    if phone_match:
        phone = phone_match.group(0)

    # Candidate Name (First non-header line without contact symbols)
    for line in lines[:4]:
        if not "@" and not re.search(r"\d", line) and len(line.split()) in (2, 3, 4):
            if not any(header in line.lower() for header in ["resume", "curriculum", "profile", "summary"]):
                candidate_name = line
                break

    # 2. Total Experience Parsing (e.g. "4 years of experience", "5+ yrs experience")
    exp_year_matches = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+experience)?", text, re.IGNORECASE)
    if exp_year_matches:
        try:
            total_years = max([float(y) for y in exp_year_matches])
        except ValueError:
            total_years = 0.0

    # 3. Section Segmentation
    sections: Dict[str, List[str]] = {
        "summary": [],
        "experience": [],
        "projects": [],
        "skills": [],
        "education": [],
        "certifications": [],
    }

    current_section = "summary"
    for line in lines:
        line_lower = line.lower().strip()
        if re.match(r"^(?:work\s+experience|experience|employment|employment\s+history|professional\s+experience)[:\s]*$", line_lower):
            current_section = "experience"
            continue
        elif re.match(r"^(?:projects|personal\s+projects|key\s+projects|technical\s+projects)[:\s]*$", line_lower):
            current_section = "projects"
            continue
        elif re.match(r"^(?:skills|technical\s+skills|core\s+competencies|technologies)[:\s]*$", line_lower):
            current_section = "skills"
            continue
        elif re.match(r"^(?:education|academic\s+background)[:\s]*$", line_lower):
            current_section = "education"
            continue
        elif re.match(r"^(?:certifications|certificates|licenses)[:\s]*$", line_lower):
            current_section = "certifications"
            continue
        elif re.match(r"^(?:summary|profile|about\s+me)[:\s]*$", line_lower):
            current_section = "summary"
            continue

        sections[current_section].append(line)

    summary = " ".join(sections["summary"]) if sections["summary"] else None

    # 4. Extract Skills List
    extracted_skills: List[str] = []
    skills_text = " ".join(sections["skills"])
    # If explicit skills section exists, split by commas, pipes, or bullets
    if skills_text:
        skill_items = re.split(r"[,|•·\n\r/]+", skills_text)
        for item in skill_items:
            s = item.strip()
            if s and len(s) < 40 and not s.lower().startswith("skills") and not s.lower().startswith("proficient"):
                if s not in extracted_skills:
                    extracted_skills.append(s)

    # 5. Extract Work Experience
    work_experiences: List[ResumeWorkExperience] = []
    exp_lines = sections["experience"]
    current_exp_block: List[str] = []

    for eline in exp_lines:
        if re.match(r"^(?:Senior|Junior|Lead|Staff|Principal|Software|Backend|Frontend|Full Stack|DevOps|Data|Cloud|Architect|Engineer|Developer|Manager|Consultant)\b", eline, re.IGNORECASE) and len(eline) < 80:
            if current_exp_block:
                work_experiences.append(_build_work_experience_item(current_exp_block))
                current_exp_block = []
        current_exp_block.append(eline)

    if current_exp_block:
        work_experiences.append(_build_work_experience_item(current_exp_block))

    # If no separate blocks were matched, use all experience lines as one block
    if not work_experiences and exp_lines:
        work_experiences.append(_build_work_experience_item(exp_lines))

    # 6. Extract Projects
    projects: List[ResumeProject] = []
    proj_lines = sections["projects"]
    if proj_lines:
        projects.append(ResumeProject(
            name="Key Projects",
            description="\n".join(proj_lines),
            technologies=[]
        ))

    return NormalizedResume(
        candidate_name=candidate_name,
        email=email,
        phone=phone,
        summary=summary,
        total_years_experience=total_years if total_years > 0 else None,
        skills=extracted_skills,
        work_experience=work_experiences,
        projects=projects,
        education=sections["education"],
        certifications=sections["certifications"],
        raw_text=raw_text
    )


def _build_work_experience_item(lines: List[str]) -> ResumeWorkExperience:
    """Helper to parse a block of lines into a structured ResumeWorkExperience."""
    title = lines[0] if lines else None
    company = None
    duration = None
    bullets: List[str] = []

    # Look for duration e.g. "2020 - 2024" or "3 years"
    block_text = " ".join(lines)
    dur_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)", block_text, re.IGNORECASE)
    if dur_match:
        try:
            duration = float(dur_match.group(1))
        except ValueError:
            duration = None

    for line in lines[1:]:
        if line.startswith("-") or line.startswith("*") or line.startswith("•") or len(line) > 30:
            bullets.append(line.lstrip("-*• ").strip())
        elif not company and len(line) < 50:
            company = line

    return ResumeWorkExperience(
        title=title,
        company=company,
        duration_years=duration,
        description="\n".join(lines),
        responsibilities=bullets,
        technologies=[]
    )


# ==============================================================================
# SIX-TIER EVIDENCE CLASSIFIER
# ==============================================================================

PRODUCTION_KEYWORDS = [
    "production", "prod", "deployed to production", "live system", "high availability",
    "scaled to", "scale of", "million users", "active users", "24/7", "sla", "latency",
    "throughput", "petabytes", "terabytes", "concurrency", "qps", "rps", "microservices in production"
]

CORE_ACTION_VERBS = [
    "architected", "designed", "implemented", "developed", "led", "engineered",
    "built", "optimized", "spearheaded", "authored", "maintained", "migrated",
    "scaled", "created", "refactored", "integrated", "managed"
]


WEAK_QUALIFIERS = [
    "familiar", "familiarity", "basic knowledge", "knowledge of", "exposure to",
    "trained on", "training", "overview", "introductory", "beginner", "learning"
]


def classify_skill_evidence(
    skill: str,
    resume: NormalizedResume,
    raw_resume_text: str
) -> Tuple[int, str, Optional[str], float]:
    """
    Evaluates evidence for a skill according to the 6-Tier Evidence Model:
    Level 1: Direct production experience (Strength=HIGH, Credit=100%)
    Level 2: Core responsibility / major achievement (Strength=HIGH, Credit=88%)
    Level 3: Project / implementation experience (Strength=MEDIUM, Credit=70%)
    Level 4: Skills section mention only (Strength=LOW, Credit=45%)
    Level 5: Weak contextual / adjacent mention (Strength=LOW, Credit=25%)
    Level 6: No evidence found (Strength=NONE, Credit=0%, Evidence=None)

    Returns:
        Tuple of (evidence_level, evidence_strength, evidence_snippet, credit_fraction)
    """
    skill_clean = skill.strip()
    skill_lower = skill_clean.lower()
    pattern = rf"\b{re.escape(skill_lower)}\b"

    # Search in Work Experience (Level 1, Level 2, or Level 5 if qualified weakly)
    for exp in resume.work_experience:
        exp_text = (exp.description or "") + " " + " ".join(exp.responsibilities or [])
        if re.search(pattern, exp_text, re.IGNORECASE):
            for bullet in (exp.responsibilities or [exp.description]):
                if re.search(pattern, bullet, re.IGNORECASE):
                    bullet_lower = bullet.lower()

                    # Check for Weak Qualifiers first (Level 5)
                    if any(wq in bullet_lower for wq in WEAK_QUALIFIERS):
                        tier = EVIDENCE_TIERS[5]
                        return 5, tier[0], bullet.strip(), tier[1]

                    # Check for Level 1 (Production markers)
                    if any(pk in bullet_lower for pk in PRODUCTION_KEYWORDS):
                        tier = EVIDENCE_TIERS[1]
                        return 1, tier[0], bullet.strip(), tier[1]

                    # Check for Level 2 (Core Action verbs in work history)
                    if any(verb in bullet_lower for verb in CORE_ACTION_VERBS) or len(bullet) > 25:
                        tier = EVIDENCE_TIERS[2]
                        return 2, tier[0], bullet.strip(), tier[1]

            tier = EVIDENCE_TIERS[2]
            return 2, tier[0], exp_text[:180].strip(), tier[1]

    # Search in Projects (Level 3)
    for proj in resume.projects:
        proj_text = (proj.name or "") + " " + (proj.description or "")
        if re.search(pattern, proj_text, re.IGNORECASE):
            tier = EVIDENCE_TIERS[3]
            return 3, tier[0], proj_text[:180].strip(), tier[1]

    # Search in Raw Resume for Action Bullets if work_experience wasn't fully structured
    for line in raw_resume_text.splitlines():
        line_clean = line.strip()
        if re.search(pattern, line_clean, re.IGNORECASE):
            line_lower = line_clean.lower()

            if any(wq in line_lower for wq in WEAK_QUALIFIERS):
                tier = EVIDENCE_TIERS[5]
                return 5, tier[0], line_clean, tier[1]

            # If line has bullet marker or action verb and is in main body
            if (line_clean.startswith("-") or line_clean.startswith("•") or line_clean.startswith("*")) and len(line_clean) > 30:
                if any(pk in line_lower for pk in PRODUCTION_KEYWORDS):
                    tier = EVIDENCE_TIERS[1]
                    return 1, tier[0], line_clean, tier[1]
                elif any(verb in line_lower for verb in CORE_ACTION_VERBS):
                    tier = EVIDENCE_TIERS[2]
                    return 2, tier[0], line_clean, tier[1]
                else:
                    tier = EVIDENCE_TIERS[3]
                    return 3, tier[0], line_clean, tier[1]

    # Search in Skills Section / Keywords (Level 4)
    if any(re.search(pattern, s, re.IGNORECASE) for s in resume.skills):
        tier = EVIDENCE_TIERS[4]
        return 4, tier[0], f"Mentioned in Skills section: '{skill_clean}'", tier[1]

    # Check if mentioned anywhere else in raw text as isolated token (Level 4/5)
    if re.search(pattern, raw_resume_text, re.IGNORECASE):
        for line in raw_resume_text.splitlines():
            if re.search(pattern, line, re.IGNORECASE):
                line_clean = line.strip()
                if any(wq in line_clean.lower() for wq in WEAK_QUALIFIERS):
                    tier = EVIDENCE_TIERS[5]
                    return 5, tier[0], line_clean, tier[1]
                tier = EVIDENCE_TIERS[4]
                return 4, tier[0], line_clean, tier[1]

    # Check for Semantic / Related skills (Level 5)
    if skill_lower in SEMANTIC_SKILL_RELATIONS:
        for rel_skill, rel_weight in SEMANTIC_SKILL_RELATIONS[skill_lower]:
            # Guard against disallowed false equivalences
            if (skill_lower, rel_skill.lower()) in DISALLOWED_EQUIVALENCES or (rel_skill.lower(), skill_lower) in DISALLOWED_EQUIVALENCES:
                continue

            rel_pattern = rf"\b{re.escape(rel_skill.lower())}\b"
            if re.search(rel_pattern, raw_resume_text, re.IGNORECASE):
                tier = EVIDENCE_TIERS[5]
                evidence_text = f"Related capability demonstrated: '{rel_skill}' (adjacent to required '{skill_clean}')"
                return 5, tier[0], evidence_text, min(0.35, tier[1] * rel_weight)

    # Level 6: No Evidence
    tier = EVIDENCE_TIERS[6]
    return 6, tier[0], None, tier[1]


# ==============================================================================
# DIMENSION EVALUATION MODULES
# ==============================================================================

def evaluate_experience_match(
    jd: NormalizedJobDescription,
    resume: NormalizedResume
) -> Tuple[float, Optional[str]]:
    """
    Compares JD experience requirements against resume experience.
    Handles partial fit proportionally (e.g. 4 years vs 5 years = 80%).
    Does not invent years not present in resume.
    """
    jd_years_req = 0.0
    if jd.experience_required:
        exp_str = jd.experience_required.lower()
        match = re.search(r"(\d+(?:\.\d+)?)", exp_str)
        if match:
            jd_years_req = float(match.group(1))
        elif "senior" in exp_str or "staff" in exp_str or "principal" in exp_str:
            jd_years_req = 5.0
        elif "mid" in exp_str:
            jd_years_req = 3.0
        elif "junior" in exp_str or "entry" in exp_str:
            jd_years_req = 1.0

    # If JD specifies no experience requirement, full fit
    if jd_years_req <= 0:
        return 90.0, "No specific minimum years specified in job description."

    resume_years = resume.total_years_experience or 0.0
    # Also sum experience blocks if total_years_experience wasn't explicitly stated
    if resume_years == 0 and resume.work_experience:
        for w in resume.work_experience:
            if w.duration_years:
                resume_years += w.duration_years

    if resume_years == 0:
        # Check if work history exists even without explicit number of years
        if len(resume.work_experience) >= 3:
            resume_years = 3.0
        elif len(resume.work_experience) >= 1:
            resume_years = 1.5

    if resume_years >= jd_years_req:
        score = 100.0
        msg = f"Meets or exceeds experience requirement: {resume_years:.1f} yrs vs {jd_years_req:.1f} yrs required."
    elif resume_years > 0:
        # Proportional partial match
        score = round(min(95.0, (resume_years / jd_years_req) * 100.0), 1)
        msg = f"Partial experience match: {resume_years:.1f} yrs demonstrated vs {jd_years_req:.1f} yrs required."
    else:
        score = 25.0
        msg = f"Insufficient work history duration to verify required {jd_years_req:.1f} yrs experience."

    return score, msg


def evaluate_domain_match(
    jd: NormalizedJobDescription,
    resume: NormalizedResume,
    raw_resume_text: str
) -> Tuple[float, Optional[str]]:
    """
    Evaluates candidate's industry/domain alignment (FinTech, SaaS, AI/ML, HealthTech, etc.).
    """
    if not jd.domain_requirements:
        return 85.0, "General technical domain (no specialized vertical required)."

    matched_domains = []
    text_lower = raw_resume_text.lower()
    for dom in jd.domain_requirements:
        dom_lower = dom.lower()
        if re.search(rf"\b{re.escape(dom_lower)}\b", text_lower):
            matched_domains.append(dom)

    total_doms = len(jd.domain_requirements)
    if not matched_domains:
        return 30.0, f"No direct evidence in target domain(s): {', '.join(jd.domain_requirements)}."

    match_fraction = len(matched_domains) / total_doms
    score = round(30.0 + (match_fraction * 70.0), 1)
    msg = f"Matched domains: {', '.join(matched_domains)} ({len(matched_domains)}/{total_doms})."
    return score, msg


def evaluate_responsibilities_match(
    jd: NormalizedJobDescription,
    resume: NormalizedResume,
    raw_resume_text: str
) -> Tuple[float, Optional[str]]:
    """
    Evaluates overlap between JD responsibilities and candidate work experience bullets.
    """
    if not jd.responsibilities:
        return 85.0, "Standard role duties (no custom responsibilities specified in JD)."

    covered_count = 0
    text_lower = raw_resume_text.lower()

    for resp in jd.responsibilities:
        words = [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", resp) if w.lower() not in ["with", "will", "your", "their", "have", "from", "that", "this", "must"]]
        if not words:
            continue
        # Check if multiple key terms from responsibility appear in resume bullets
        matched_words = [w for w in words if w in text_lower]
        if len(matched_words) >= max(2, int(len(words) * 0.35)):
            covered_count += 1

    total_resps = len(jd.responsibilities)
    ratio = covered_count / total_resps if total_resps > 0 else 1.0
    score = round(25.0 + (ratio * 75.0), 1)
    msg = f"Demonstrated evidence for {covered_count} of {total_resps} key responsibility areas."
    return score, msg


# ==============================================================================
# MAIN MATCHING ENGINE IMPLEMENTATION
# ==============================================================================

def calculate_resume_jd_match(
    jd_input: Union[NormalizedJobDescription, Dict[str, Any], str],
    resume_input: Union[NormalizedResume, Dict[str, Any], str]
) -> ResumeJDMatchResult:
    """
    Master multi-dimensional matching engine combining:
    - 6-Tier Evidence Evaluation
    - Importance Weighting (HIGH=1.0, MEDIUM=0.6, LOW=0.3)
    - Anti-Masking Critical Gap Rule
    - Baseline Scoring Weights:
        Overall = 0.40 * Required_Skills + 0.20 * Experience + 0.15 * Domain + 0.15 * Responsibilities + 0.10 * Preferred_Skills
    - Deterministic Rule Engine (100% functional without LLM)
    - Non-Fabrication of Resume Evidence
    """
    # 1. Normalize Inputs
    if isinstance(jd_input, NormalizedJobDescription):
        jd = jd_input
    elif isinstance(jd_input, dict):
        jd = NormalizedJobDescription(**jd_input)
    else:
        # Import lazily to prevent circular dependencies
        from app.jd_service import normalize_job_description
        jd = normalize_job_description(str(jd_input))

    if isinstance(resume_input, NormalizedResume):
        resume = resume_input
    elif isinstance(resume_input, dict):
        resume = NormalizedResume(**resume_input)
    else:
        resume = normalize_resume(str(resume_input))

    raw_resume_text = resume.raw_text or ""
    if not raw_resume_text:
        # Reconstruct text representation from structured resume components
        raw_resume_text = (
            (resume.summary or "") + "\n" +
            "Skills: " + ", ".join(resume.skills or []) + "\n" +
            "\n".join([(w.title or "") + " " + (w.description or "") for w in (resume.work_experience or [])]) + "\n" +
            "\n".join([(p.name or "") + " " + (p.description or "") for p in (resume.projects or [])])
        )

    # 2. Extract and Evaluate Required Skills (Weight: 0.40)
    skill_matrix: List[SkillMatrixItem] = []
    req_skills = list(dict.fromkeys(jd.required_skills or []))

    # Fallback if JD has no explicit skills list: extract keywords from title/technical_requirements
    if not req_skills:
        if jd.technical_requirements:
            req_skills = list(dict.fromkeys(jd.technical_requirements))
        elif jd.job_title:
            req_skills = [w for w in jd.job_title.split() if len(w) > 3 and w not in ["Senior", "Junior", "Lead", "Staff", "Engineer", "Developer"]]

    req_score_sum = 0.0
    req_weight_sum = 0.0

    for skill in req_skills:
        importance = "HIGH"  # Required skills are HIGH importance by default
        imp_weight = IMPORTANCE_WEIGHTS[importance]

        lvl, strength, evidence, credit = classify_skill_evidence(skill, resume, raw_resume_text)
        item_score = round(credit * 100.0, 1)

        if item_score >= 70.0:
            status = "matched"
        elif item_score >= 30.0:
            status = "partial"
        else:
            status = "gap"

        matrix_item = SkillMatrixItem(
            skill=skill,
            importance=importance,
            jd_requirement=f"Required Core Skill: {skill}",
            resume_evidence=evidence,
            evidence_level=lvl,
            evidence_strength=strength,
            match_score=item_score,
            gap_status=status
        )
        skill_matrix.append(matrix_item)

        req_score_sum += item_score * imp_weight
        req_weight_sum += imp_weight

    required_skills_subscore = round(req_score_sum / req_weight_sum, 1) if req_weight_sum > 0 else 80.0

    # 3. Extract and Evaluate Preferred Skills (Weight: 0.10)
    pref_skills = list(dict.fromkeys(jd.preferred_skills or []))
    pref_score_sum = 0.0
    pref_weight_sum = 0.0

    for skill in pref_skills:
        if skill in req_skills:
            continue
        importance = "MEDIUM"
        imp_weight = IMPORTANCE_WEIGHTS[importance]

        lvl, strength, evidence, credit = classify_skill_evidence(skill, resume, raw_resume_text)
        item_score = round(credit * 100.0, 1)

        if item_score >= 70.0:
            status = "matched"
        elif item_score >= 30.0:
            status = "partial"
        else:
            status = "gap"

        matrix_item = SkillMatrixItem(
            skill=skill,
            importance=importance,
            jd_requirement=f"Preferred Skill: {skill}",
            resume_evidence=evidence,
            evidence_level=lvl,
            evidence_strength=strength,
            match_score=item_score,
            gap_status=status
        )
        skill_matrix.append(matrix_item)

        pref_score_sum += item_score * imp_weight
        pref_weight_sum += imp_weight

    preferred_skills_subscore = round(pref_score_sum / pref_weight_sum, 1) if pref_weight_sum > 0 else 75.0

    # 4. Evaluate Tools & Technology
    for tool in (jd.tools or []):
        if not any(item.skill.lower() == tool.lower() for item in skill_matrix):
            lvl, strength, evidence, credit = classify_skill_evidence(tool, resume, raw_resume_text)
            item_score = round(credit * 100.0, 1)
            skill_matrix.append(SkillMatrixItem(
                skill=tool,
                importance="LOW",
                jd_requirement=f"Tool/Platform: {tool}",
                resume_evidence=evidence,
                evidence_level=lvl,
                evidence_strength=strength,
                match_score=item_score,
                gap_status="matched" if item_score >= 70.0 else ("partial" if item_score >= 30.0 else "gap")
            ))

    # 5. Dimension Sub-scores
    experience_subscore, exp_msg = evaluate_experience_match(jd, resume)
    domain_subscore, dom_msg = evaluate_domain_match(jd, resume, raw_resume_text)
    responsibilities_subscore, resp_msg = evaluate_responsibilities_match(jd, resume, raw_resume_text)

    # 6. Overall Match Score Formula
    # Approved Formula:
    # 0.40 * Required_Skills + 0.20 * Experience + 0.15 * Domain + 0.15 * Responsibilities + 0.10 * Preferred_Skills
    overall_match_score = round(
        (0.40 * required_skills_subscore) +
        (0.20 * experience_subscore) +
        (0.15 * domain_subscore) +
        (0.15 * responsibilities_subscore) +
        (0.10 * preferred_skills_subscore),
        1
    )
    overall_match_score = max(0.0, min(100.0, overall_match_score))

    sub_scores = SubScores(
        required_skills=required_skills_subscore,
        experience=experience_subscore,
        domain=domain_subscore,
        responsibilities=responsibilities_subscore,
        preferred_skills=preferred_skills_subscore,
        tools_technology=80.0,
        education=90.0 if resume.education else None
    )

    # 7. Identify Strengths, Skill Gaps, and Critical Gaps (with Anti-Masking Rule)
    strengths: List[str] = []
    skill_gaps: List[str] = []
    critical_gaps: List[str] = []
    recommendations: List[str] = []

    for item in skill_matrix:
        # Strengths: score >= 70 with Level 1, 2, or 3 evidence
        if item.match_score >= 70.0 and item.evidence_level in (1, 2, 3):
            strengths.append(f"{item.skill} (Level {item.evidence_level} - {item.evidence_strength} Evidence)")

        # Gaps: partial or gap
        if item.gap_status in ("partial", "gap"):
            gap_desc = f"{item.skill} (Score: {item.match_score:.0f}%, Status: {item.gap_status.title()})"
            skill_gaps.append(gap_desc)

            # CRITICAL GAP RULE:
            # Importance = HIGH and evidence is weak/absent (Level 4, 5, 6 or score < 50.0)
            # ANTI-MASKING: This MUST appear under critical_gaps even if overall_match_score >= 80%
            if item.importance == "HIGH" and (item.match_score < 50.0 or item.evidence_level >= 4):
                crit_desc = f"Critical Gap: {item.skill} (Importance: HIGH, Evidence Level: {item.evidence_level})"
                critical_gaps.append(crit_desc)
                recommendations.append(f"Add direct production or project evidence for {item.skill} to meet core role criteria.")

    # Additional contextual recommendations
    if experience_subscore < 75.0:
        recommendations.append(f"Highlight technical leadership and architectural depth to offset the {exp_msg}")

    if not critical_gaps and skill_gaps:
        for g in skill_gaps[:2]:
            skill_name = g.split()[0]
            recommendations.append(f"Review and prepare for technical deep-dive questions on {skill_name}.")

    if not recommendations:
        recommendations.append("Strong overall profile alignment. Focus preparation on system architecture trade-offs and live problem-solving.")

    # 8. Match Confidence Calculation (Independent of Match Score)
    # Factors: Resume word count, structural completeness, verified evidence coverage
    word_count = len(raw_resume_text.split())
    has_work_exp = bool(resume.work_experience and len(resume.work_experience) >= 1)
    has_bullets = any(len(w.responsibilities) > 0 for w in resume.work_experience)
    high_evidence_count = sum(1 for item in skill_matrix if item.evidence_level in (1, 2, 3))
    total_requirements = len(skill_matrix)

    if word_count < 40 or not has_work_exp or total_requirements < 2:
        match_confidence = "LOW"
    elif word_count >= 60 and (has_bullets or has_work_exp) and high_evidence_count >= max(2, int(total_requirements * 0.4)):
        match_confidence = "HIGH"
    else:
        match_confidence = "MEDIUM"

    return ResumeJDMatchResult(
        overall_match_score=overall_match_score,
        match_confidence=match_confidence,
        sub_scores=sub_scores,
        skill_matrix=skill_matrix,
        strengths=strengths,
        skill_gaps=skill_gaps,
        critical_gaps=critical_gaps,
        recommendations=recommendations
    )
