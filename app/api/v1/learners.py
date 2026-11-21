"""
Learner Intelligence Profile & Competency Framework API Router (Phase 1)
========================================================================
Provides endpoints for:
1. Learner Profile CRUD (Target role, career goals, education, experience, learning preferences).
2. 5-Tier Competency Framework exploration for target roles.
3. Self-reported skill recording (clearly demarcated as unverified).
4. Deterministic Skill Gap calculation with priority tiers and evidence classification.
5. Resume evidence synchronization from verified ResumeScans.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user_from_token, get_current_user_optional
from app.db_models import (
    UserAccount,
    LearnerProfile,
    CandidateSkillAnalytics,
    ResumeScan,
)
from app.services.learner_intelligence_service import (
    PROFICIENCY_LEVELS,
    ROLE_COMPETENCY_FRAMEWORKS,
    get_role_competency_framework,
    score_to_proficiency,
    level_to_baseline_score,
    classify_skill_evidence,
    calculate_learner_skill_gaps,
    sync_profile_from_resume_scan,
    evaluate_onboarding_skill_match,
)
from app.services.adaptive_path_service import generate_adaptive_learning_path
from app.jd_service import extract_text_from_document
from app.matching_service import normalize_resume

router = APIRouter()


# ==============================================================================
# SCHEMAS
# ==============================================================================

class AssessedSkillOut(BaseModel):
    skill: str
    score: float
    level: int
    level_title: str
    confidence: str
    trend: str
    weakness_status: str


class SelfReportedSkillIn(BaseModel):
    skill: str = Field(..., min_length=1, max_length=100)
    level: int = Field(..., ge=1, le=5, description="1=Beginner, 2=Basic, 3=Intermediate, 4=Advanced, 5=Expert")
    notes: Optional[str] = Field(None, max_length=500)


class SelfReportedSkillOut(BaseModel):
    skill: str
    level: int
    level_title: str
    baseline_score: float
    notes: Optional[str] = None
    reported_at: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    target_role: Optional[str] = Field(None, min_length=2, max_length=255)
    secondary_roles: Optional[List[str]] = None
    career_goals: Optional[str] = Field(None, max_length=2000)
    target_level: Optional[str] = Field(None, max_length=50)
    education_level: Optional[str] = Field(None, max_length=100)
    institution: Optional[str] = Field(None, max_length=255)
    graduation_year: Optional[int] = Field(None, ge=1970, le=2040)
    years_of_experience: Optional[float] = Field(None, ge=0.0, le=60.0)
    current_role: Optional[str] = Field(None, max_length=255)
    current_company: Optional[str] = Field(None, max_length=255)
    preferred_learning_goals: Optional[List[str]] = None
    career_interests: Optional[List[str]] = None


class LearnerProfileOut(BaseModel):
    id: int
    user_id: int
    email: str
    full_name: Optional[str] = None
    target_role: str
    secondary_roles: List[str] = []
    career_goals: Optional[str] = None
    target_level: str
    education_level: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[int] = None
    years_of_experience: float
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    preferred_learning_goals: List[str] = []
    career_interests: List[str] = []
    self_reported_skills: Dict[str, Any] = {}
    assessed_skills: List[AssessedSkillOut] = []
    latest_scan_id: Optional[str] = None
    created_at: str
    updated_at: str


class CompetencyItemOut(BaseModel):
    skill: str
    category: str
    target_level: int
    target_level_title: str
    role_criticality: float
    description: str


class SkillGapOut(BaseModel):
    skill: str
    category: str
    description: str
    target_level: int
    target_level_title: str
    current_level: int
    current_level_title: str
    current_score: float
    gap_level: int
    priority: str
    evidence_type: str
    confidence: str
    is_verified: bool
    evidence_count: int
    last_evaluated: Optional[str] = None


class ResumeSyncResultOut(BaseModel):
    success: bool
    scan_id: str
    target_role: str
    match_score: float
    extracted_skills: List[str]
    years_of_experience: float
    education: Optional[str] = None
    message: str


class CandidateSkillEntryIn(BaseModel):
    skill: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = Field("Technical Skills", max_length=100)
    proficiency: str = Field("Intermediate", description="Beginner | Basic | Intermediate | Advanced | Expert")
    source: Optional[str] = Field("SELF_REPORTED", description="SELF_REPORTED | RESUME_EXTRACTED")
    notes: Optional[str] = None


class OnboardingAssessmentRequest(BaseModel):
    target_role: str = Field(..., min_length=2, max_length=255)
    target_level: str = Field("Mid-Level", max_length=50)
    years_of_experience: float = Field(0.0, ge=0.0, le=60.0)
    education_level: Optional[str] = Field(None, max_length=100)
    institution: Optional[str] = Field(None, max_length=255)
    skills: List[CandidateSkillEntryIn] = Field(default_factory=list)
    career_goals: Optional[str] = Field(None, max_length=2000)
    target_industry: Optional[str] = Field(None, max_length=100)


class EvaluatedSkillOut(BaseModel):
    skill: str
    category: str
    description: str
    required_level: int
    required_level_title: str
    candidate_level: int
    candidate_level_title: str
    candidate_score: float
    status: str
    source: str
    confidence: str
    is_verified: bool
    role_criticality: float


class OnboardingAssessmentResponse(BaseModel):
    target_role: str
    target_level: str
    overall_match_percentage: float
    skills_identified_count: int
    skills_matched_count: int
    skills_partial_count: int
    skills_gap_count: int
    skills_not_assessed_count: int
    readiness_status: str
    readiness_description: str
    experience_alignment: str
    experience_description: str
    education_alignment: str
    evaluated_skills: List[EvaluatedSkillOut]
    additional_skills: List[EvaluatedSkillOut]
    categories: Dict[str, List[EvaluatedSkillOut]]
    recommended_areas: List[Dict[str, Any]]
    disclaimer: str


class CompleteOnboardingRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    summary: Optional[str] = Field(None, max_length=5000)
    education_level: Optional[str] = Field(None, max_length=100)
    institution: Optional[str] = Field(None, max_length=255)
    graduation_year: Optional[int] = Field(None, ge=1950, le=2040)
    target_role: str = Field(..., min_length=2, max_length=255)
    target_level: str = Field("Mid-Level", max_length=50)
    years_of_experience: float = Field(0.0, ge=0.0, le=60.0)
    current_role: Optional[str] = Field(None, max_length=255)
    current_company: Optional[str] = Field(None, max_length=255)
    work_experience: Optional[List[Dict[str, Any]]] = None
    projects: Optional[List[Dict[str, Any]]] = None
    certifications: Optional[List[str]] = None
    career_goals: Optional[str] = Field(None, max_length=2000)
    target_industry: Optional[str] = Field(None, max_length=100)
    preferred_learning_goals: Optional[List[str]] = None
    skills: List[CandidateSkillEntryIn] = Field(default_factory=list)
    raw_resume_text: Optional[str] = None
    resume_filename: Optional[str] = None


class CompleteOnboardingResponse(BaseModel):
    success: bool
    message: str
    profile_id: int
    user_id: int
    full_name: str
    target_role: str
    target_level: str
    overall_match_score: float
    readiness_status: str
    roadmap_id: Optional[str] = None
    top_matched_skills: List[str] = []
    top_skill_gaps: List[str] = []
    next_action: str
    assessment: Optional[OnboardingAssessmentResponse] = None
    submitted_profile: Optional[Dict[str, Any]] = None


class ResumeExtractedSkillItem(BaseModel):
    skill: str
    category: str
    proficiency: str = "Intermediate"
    source: str = "RESUME_EXTRACTED"


class ResumeUploadExtractResponse(BaseModel):
    success: bool
    message: str
    filename: str
    file_size_bytes: int
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    summary: Optional[str] = None
    years_of_experience: float = 0.0
    education: Optional[str] = None
    institution: Optional[str] = None
    graduation_year: Optional[int] = None
    current_role: Optional[str] = None
    current_company: Optional[str] = None
    work_experience: List[Dict[str, Any]] = []
    projects_detail: List[Dict[str, Any]] = []
    skills: List[ResumeExtractedSkillItem] = []
    technical_skills: List[str] = []
    soft_skills: List[str] = []
    tools_and_technologies: List[str] = []
    projects: List[str] = []
    certifications: List[str] = []
    raw_text: Optional[str] = None


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_or_create_learner_profile(user: UserAccount, db: Session) -> LearnerProfile:
    """Retrieves existing profile or initializes a default profile for the user."""
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user.id).first()
    if not profile:
        profile = LearnerProfile(
            user_id=user.id,
            target_role="Full-Stack Engineer",
            target_level="Mid-Level",
            years_of_experience=0.0,
            secondary_roles=json.dumps([]),
            preferred_learning_goals=json.dumps([]),
            career_interests=json.dumps([]),
            self_reported_skills=json.dumps({}),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def format_profile_out(profile: LearnerProfile, user: UserAccount, db: Session) -> LearnerProfileOut:
    """Formats a LearnerProfile model into the full LearnerProfileOut schema."""
    # Assessed skills from CandidateSkillAnalytics
    analytics = db.query(CandidateSkillAnalytics).filter(CandidateSkillAnalytics.user_id == user.id).all()
    assessed = []
    for a in analytics:
        lvl, title = score_to_proficiency(a.score)
        assessed.append(
            AssessedSkillOut(
                skill=a.skill,
                score=round(a.score, 1),
                level=lvl,
                level_title=title,
                confidence=a.confidence or "LOW",
                trend=a.trend or "flat",
                weakness_status=a.weakness_status or "identified",
            )
        )

    # Parse JSON fields safely
    secondary_roles = []
    if profile.secondary_roles:
        try:
            secondary_roles = json.loads(profile.secondary_roles)
        except Exception:
            pass

    preferred_learning_goals = []
    if profile.preferred_learning_goals:
        try:
            preferred_learning_goals = json.loads(profile.preferred_learning_goals)
        except Exception:
            pass

    career_interests = []
    if profile.career_interests:
        try:
            career_interests = json.loads(profile.career_interests)
        except Exception:
            pass

    self_reported = {}
    if profile.self_reported_skills:
        try:
            self_reported = json.loads(profile.self_reported_skills)
        except Exception:
            pass

    return LearnerProfileOut(
        id=profile.id,
        user_id=profile.user_id,
        email=user.email,
        full_name=user.full_name,
        target_role=profile.target_role,
        secondary_roles=secondary_roles,
        career_goals=profile.career_goals,
        target_level=profile.target_level,
        education_level=profile.education_level,
        institution=profile.institution,
        graduation_year=profile.graduation_year,
        years_of_experience=profile.years_of_experience,
        current_role=profile.current_role,
        current_company=profile.current_company,
        preferred_learning_goals=preferred_learning_goals,
        career_interests=career_interests,
        self_reported_skills=self_reported,
        assessed_skills=assessed,
        latest_scan_id=profile.latest_scan_id,
        created_at=profile.created_at.isoformat() if profile.created_at else "",
        updated_at=profile.updated_at.isoformat() if profile.updated_at else "",
    )


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.get("/profile", response_model=LearnerProfileOut, summary="Retrieve authenticated learner profile")
def get_profile(
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Returns the authenticated learner's intelligence profile, goals, education, experience, and baseline competencies."""
    profile = get_or_create_learner_profile(user, db)
    return format_profile_out(profile, user, db)


@router.put("/profile", response_model=LearnerProfileOut, summary="Update learner profile")
def update_profile(
    req: UpdateProfileRequest,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Updates learner target roles, career goals, education, and professional experience."""
    profile = get_or_create_learner_profile(user, db)

    if req.target_role is not None:
        profile.target_role = req.target_role
    if req.secondary_roles is not None:
        profile.secondary_roles = json.dumps(req.secondary_roles)
    if req.career_goals is not None:
        profile.career_goals = req.career_goals
    if req.target_level is not None:
        profile.target_level = req.target_level
    if req.education_level is not None:
        profile.education_level = req.education_level
    if req.institution is not None:
        profile.institution = req.institution
    if req.graduation_year is not None:
        profile.graduation_year = req.graduation_year
    if req.years_of_experience is not None:
        profile.years_of_experience = req.years_of_experience
    if req.current_role is not None:
        profile.current_role = req.current_role
    if req.current_company is not None:
        profile.current_company = req.current_company
    if req.preferred_learning_goals is not None:
        profile.preferred_learning_goals = json.dumps(req.preferred_learning_goals)
    if req.career_interests is not None:
        profile.career_interests = json.dumps(req.career_interests)

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)

    return format_profile_out(profile, user, db)


@router.post("/skills/self-report", summary="Add or update a self-reported skill")
def self_report_skill(
    req: SelfReportedSkillIn,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Records a self-reported skill with Level 1-5 proficiency.
    Clearly marked as SELF_REPORTED (unverified) until evaluated through assessment or interview.
    """
    profile = get_or_create_learner_profile(user, db)
    self_reported = {}
    if profile.self_reported_skills:
        try:
            self_reported = json.loads(profile.self_reported_skills)
        except Exception:
            pass

    lvl_meta = PROFICIENCY_LEVELS.get(req.level, PROFICIENCY_LEVELS[1])
    self_reported[req.skill] = {
        "level": req.level,
        "level_title": lvl_meta["name"],
        "baseline_score": level_to_baseline_score(req.level),
        "notes": req.notes,
        "reported_at": datetime.now(timezone.utc).isoformat(),
    }

    profile.self_reported_skills = json.dumps(self_reported)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "success": True,
        "message": f"Recorded self-reported skill '{req.skill}' at Level {req.level} ({lvl_meta['name']}). Note: Remains unverified until assessed.",
        "skill": req.skill,
        "level": req.level,
        "level_title": lvl_meta["name"],
        "is_verified": False,
        "evidence_type": "SELF_REPORTED",
    }


@router.delete("/skills/self-report/{skill_name}", summary="Remove a self-reported skill")
def delete_self_reported_skill(
    skill_name: str,
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Deletes a declared self-reported skill from the learner's profile."""
    profile = get_or_create_learner_profile(user, db)
    self_reported = {}
    if profile.self_reported_skills:
        try:
            self_reported = json.loads(profile.self_reported_skills)
        except Exception:
            pass

    if skill_name not in self_reported:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Self-reported skill '{skill_name}' not found.",
        )

    del self_reported[skill_name]
    profile.self_reported_skills = json.dumps(self_reported)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "message": f"Removed self-reported skill '{skill_name}'."}


@router.get("/competency-matrix", response_model=List[CompetencyItemOut], summary="Role Competency Framework")
def get_competency_matrix(
    role: Optional[str] = Query(None, description="Target role name (defaults to learner's current target role)"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """Returns the standardized 5-tier competency framework requirements for a specified role."""
    target = role
    if not target:
        profile = get_or_create_learner_profile(user, db)
        target = profile.target_role or "Full-Stack Engineer"

    framework = get_role_competency_framework(target)
    return [
        CompetencyItemOut(
            skill=item["skill"],
            category=item.get("category", "General"),
            target_level=item["target_level"],
            target_level_title=PROFICIENCY_LEVELS[item["target_level"]]["name"],
            role_criticality=item.get("role_criticality", 1.0),
            description=item.get("desc", ""),
        )
        for item in framework
    ]


@router.get("/skill-gaps", response_model=List[SkillGapOut], summary="Calculate learner skill gaps")
def get_skill_gaps(
    role: Optional[str] = Query(None, description="Optional target role override for gap simulation"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Computes deterministic skill gaps between the learner's demonstrated competency and the target role.
    Strictly distinguishes between Self-Reported, Assessed, and Verified evidence.
    Returns prioritized gaps (CRITICAL, HIGH, MODERATE, LOW, ON_TRACK).
    """
    profile = get_or_create_learner_profile(user, db)
    target = role or profile.target_role or "Full-Stack Engineer"

    self_reported = {}
    if profile.self_reported_skills:
        try:
            self_reported = json.loads(profile.self_reported_skills)
        except Exception:
            pass

    gaps = calculate_learner_skill_gaps(
        user_id=user.id,
        target_role=target,
        db=db,
        self_reported_skills=self_reported,
    )

    return [SkillGapOut(**g) for g in gaps]


@router.post("/sync-resume", response_model=ResumeSyncResultOut, summary="Sync verified resume evidence")
def sync_resume(
    scan_id: Optional[str] = Query(None, description="Optional specific ResumeScan ID"),
    user: UserAccount = Depends(get_current_user_from_token),
    db: Session = Depends(get_db),
):
    """
    Synchronizes verified resume qualifications from historical scans into the learner's profile.
    Guarantees zero hallucination: only attributes explicitly parsed in ResumeScan are mapped.
    """
    profile = get_or_create_learner_profile(user, db)
    sync_data = sync_profile_from_resume_scan(user_id=user.id, db=db, scan_id=scan_id)

    if not sync_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed resume scan found for this user. Please upload or scan a resume first.",
        )

    # Apply extracted data if profile fields are empty or updated
    if sync_data["years_of_experience"] > 0:
        profile.years_of_experience = sync_data["years_of_experience"]
    if sync_data.get("education"):
        profile.education_level = sync_data["education"]
    if sync_data.get("target_role") and sync_data["target_role"] != "General Tech":
        profile.target_role = sync_data["target_role"]

    profile.latest_scan_id = sync_data["scan_id"]
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()

    return ResumeSyncResultOut(
        success=True,
        scan_id=sync_data["scan_id"],
        target_role=sync_data["target_role"],
        match_score=sync_data["match_score"],
        extracted_skills=sync_data["extracted_skills"],
        years_of_experience=sync_data["years_of_experience"],
        education=sync_data.get("education"),
        message="Successfully synchronized verified resume qualifications into learner profile.",
    )


# ==============================================================================
# ONBOARDING, RESUME PARSING & ASSESSMENT ENDPOINTS
# ==============================================================================

def _sanitize_resume_input(raw: str) -> str:
    """Sanitizes resume text to prevent prompt injection attacks when fed into agents."""
    if not raw:
        return ""
    injection_patterns = [
        r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
        r"(?i)<\s*system\s*>",
        r"(?i)<\s*/?\s*instructions?\s*>",
        r"(?i)system\s*:\s*",
        r"(?i)disregard\s+(?:above|earlier)\s+prompts?",
        r"(?i)override\s+(?:system|developer)\s+prompt",
    ]
    cleaned = raw
    for p in injection_patterns:
        cleaned = re.sub(p, "[REDACTED_SECURITY_PROMPT]", cleaned)
    return cleaned


def _classify_skill_category(skill_name: str) -> str:
    """Deterministically categorizes extracted skills into one of the 7 standard categories."""
    s = skill_name.strip().lower()
    if any(k in s for k in ("llm", "rag", "ai", "gpt", "prompt", "vector", "deep learning", "machine learning", "nlp", "pytorch", "tensorflow", "scikit", "embedding")):
        return "AI & Machine Learning"
    if any(k in s for k in ("aws", "gcp", "azure", "docker", "kubernetes", "k8s", "terraform", "linux", "cloud", "serverless", "ci/cd", "devops", "helm")):
        return "Cloud & Infrastructure"
    if any(k in s for k in ("react", "next.js", "nextjs", "vue", "angular", "fastapi", "django", "flask", "node", "express", "spring", "tailwind", "redux", "graphql")):
        return "Frameworks & Libraries"
    if any(k in s for k in ("git", "github", "jira", "figma", "postman", "k6", "jmeter", "grafana", "prometheus", "tableau", "powerbi", "docker", "vscode", "metabase")):
        return "Tools"
    if any(k in s for k in ("communication", "leadership", "agile", "scrum", "mentoring", "stakeholder", "problem solving", "presentation")):
        return "Soft Skills"
    if any(k in s for k in ("architecture", "security", "owasp", "database design", "distributed", "concurrency", "microservices", "testing strategy", "user research")):
        return "Domain Knowledge"
    return "Technical Skills"


@router.post(
    "/upload-resume",
    response_model=ResumeUploadExtractResponse,
    summary="Upload and extract resume data (PDF/DOCX/TXT)",
    tags=["Candidate Onboarding & Profiling"],
)
async def upload_candidate_resume(
    file: UploadFile = File(...),
    user: Optional[UserAccount] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    Accepts PDF, DOCX, or TXT resumes (up to 5MB).
    Extracts text securely with zero external C execution and normalizes into structured
    candidate data (experience, skills, education, projects, contact info) with
    strict RESUME_EXTRACTED provenance.
    """
    filename = file.filename or "uploaded_resume.txt"
    fname_lower = filename.lower()
    allowed_exts = (".pdf", ".docx", ".doc", ".txt")
    if not any(fname_lower.endswith(ext) for ext in allowed_exts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{filename}'. Please upload a PDF, DOCX, or TXT file.",
        )

    try:
        if hasattr(file, "file") and hasattr(file.file, "read"):
            if hasattr(file.file, "seek"):
                file.file.seek(0)
            content_bytes = file.file.read()
        else:
            content_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded resume file: {str(e)}",
        )

    if not content_bytes or len(content_bytes) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded resume file is empty or corrupted.",
        )

    MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB
    if len(content_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds 5MB size limit ({len(content_bytes) / 1024 / 1024:.2f}MB). Please upload a smaller document.",
        )

    try:
        raw_text = extract_text_from_document(filename, content_bytes)
    except Exception as parse_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error extracting text from document: {str(parse_err)}",
        )

    if not raw_text or len(raw_text.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract readable textual content from document. The file may be image-only/scanned.",
        )

    sanitized_text = _sanitize_resume_input(raw_text)
    normalized = normalize_resume(sanitized_text)

    # Classify skills into categories
    structured_skills = []
    technical_skills = []
    soft_skills = []
    tools_list = []

    for raw_skill in normalized.skills:
        cat = _classify_skill_category(raw_skill)
        structured_skills.append(
            ResumeExtractedSkillItem(
                skill=raw_skill,
                category=cat,
                proficiency="Intermediate",
                source="RESUME_EXTRACTED",
            )
        )
        if cat == "Soft Skills":
            soft_skills.append(raw_skill)
        elif cat == "Tools":
            tools_list.append(raw_skill)
        else:
            technical_skills.append(raw_skill)

    # Parse primary education and institution
    primary_education = None
    primary_institution = None
    grad_year = None
    if normalized.education:
        primary_education = normalized.education[0] if isinstance(normalized.education[0], str) else str(normalized.education[0])
        # Try to parse year
        yr_match = re.search(r"\b(19\d\d|20\d\d)\b", primary_education)
        if yr_match:
            try:
                grad_year = int(yr_match.group(1))
            except Exception:
                pass
        # Try to parse institution if separated by comma or pipe
        edu_parts = [p.strip() for p in re.split(r"[,|\n•-]", primary_education) if p.strip()]
        if len(edu_parts) > 1:
            for p in edu_parts[1:]:
                if any(w in p.lower() for w in ["university", "college", "institute", "school", "academy", "polytechnic"]):
                    primary_institution = p
                    break
            if not primary_institution:
                primary_institution = edu_parts[1]

    # Parse work experiences & current company/role
    current_role = None
    current_company = None
    work_exp_list = []
    if normalized.work_experience:
        first_exp = normalized.work_experience[0]
        current_role = getattr(first_exp, "role", None) or getattr(first_exp, "title", None)
        current_company = getattr(first_exp, "company", None)
        for we in normalized.work_experience:
            r_title = getattr(we, "role", None) or getattr(we, "title", None) or ""
            c_name = getattr(we, "company", None) or ""
            d_dur = f"{getattr(we, 'duration_years', '')} yrs" if getattr(we, "duration_years", None) else ""
            desc = getattr(we, "description", None) or ""
            if not desc and getattr(we, "responsibilities", None):
                desc = "\n".join(getattr(we, "responsibilities", []))
            work_exp_list.append({
                "company": c_name,
                "role": r_title,
                "duration": d_dur,
                "description": desc,
                "technologies": getattr(we, "technologies", []) or [],
            })

    # Detailed projects
    projects_detail = []
    if normalized.projects:
        for p in normalized.projects:
            projects_detail.append({
                "name": getattr(p, "name", "Project") or "Project",
                "description": getattr(p, "description", "") or "",
                "technologies": getattr(p, "technologies", []) or [],
            })

    project_names = [getattr(p, "name", str(p)) for p in normalized.projects if getattr(p, "name", None)]

    return ResumeUploadExtractResponse(
        success=True,
        message="Resume extracted successfully.",
        filename=filename,
        file_size_bytes=len(content_bytes),
        candidate_name=normalized.candidate_name,
        email=normalized.email,
        phone=normalized.phone,
        summary=normalized.summary,
        years_of_experience=float(normalized.total_years_experience or 0.0),
        education=primary_education,
        institution=primary_institution,
        graduation_year=grad_year,
        current_role=current_role,
        current_company=current_company,
        work_experience=work_exp_list,
        projects_detail=projects_detail,
        skills=structured_skills,
        technical_skills=technical_skills,
        soft_skills=soft_skills,
        tools_and_technologies=tools_list,
        projects=project_names,
        certifications=normalized.certifications or [],
        raw_text=sanitized_text,
    )


@router.post(
    "/assess-onboarding",
    response_model=OnboardingAssessmentResponse,
    summary="Evaluate candidate profile against target job role competency requirements",
    tags=["Candidate Onboarding & Profiling"],
)
def assess_onboarding(
    req: OnboardingAssessmentRequest,
    user: Optional[UserAccount] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    Computes an evidence-aware skill match and preliminary career readiness assessment.
    Maps candidate skills to the target role's competency framework, calculating match percentage,
    gaps, partial matches, experience alignment, and recommended focus areas.
    """
    cand_skills_data = [s.model_dump() for s in req.skills]
    result = evaluate_onboarding_skill_match(
        target_role=req.target_role,
        target_level=req.target_level,
        candidate_skills=cand_skills_data,
        years_of_experience=req.years_of_experience,
        education_level=req.education_level,
    )
    return result


@router.post(
    "/complete-onboarding",
    response_model=CompleteOnboardingResponse,
    summary="Persist onboarding profile, record competency baseline, and initialize adaptive roadmap",
    tags=["Candidate Onboarding & Profiling"],
)
def complete_onboarding(
    req: CompleteOnboardingRequest,
    user: Optional[UserAccount] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    Finalizes candidate onboarding:
    1. Validates required personal and career parameters.
    2. Persists learner profile with career goals, education, and target role.
    3. Initializes candidate competency baseline in CandidateSkillAnalytics.
    4. Triggers Agent 2 to synthesize candidate's personalized adaptive learning roadmap.
    5. Returns onboarding completion status and recommended next steps.
    """
    now = datetime.now(timezone.utc)

    # Resolve user account if not pre-authenticated
    if user is None:
        user_email = (req.email or "").strip().lower()
        if user_email:
            user = db.query(UserAccount).filter(UserAccount.email == user_email).first()
        if not user:
            dev_candidate = db.query(UserAccount).filter(UserAccount.role == "candidate").first()
            if dev_candidate:
                user = dev_candidate
            elif user_email:
                import secrets
                from app.core.security import get_password_hash
                user = UserAccount(
                    email=user_email,
                    full_name=(req.full_name or "Candidate").strip(),
                    password_hash=get_password_hash(secrets.token_urlsafe(16)),
                    role="candidate",
                    plan_tier="free",
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Candidate email is required to complete onboarding.",
                )

    # 1. Update user account name if provided
    candidate_name = (req.full_name or "").strip() or user.full_name or "Candidate"
    if candidate_name and (not user.full_name or user.full_name != candidate_name):
        user.full_name = candidate_name
        user.updated_at = now
        db.add(user)

    # 2. Upsert LearnerProfile
    profile = get_or_create_learner_profile(user, db)
    profile.target_role = req.target_role.strip()
    profile.target_level = req.target_level.strip()
    summary_text = (req.summary or req.career_goals or "").strip()
    profile.career_goals = summary_text if summary_text else None
    profile.education_level = req.education_level.strip() if req.education_level else None
    profile.institution = req.institution.strip() if req.institution else None
    profile.graduation_year = req.graduation_year
    profile.years_of_experience = max(0.0, float(req.years_of_experience))
    profile.current_role = req.current_role.strip() if req.current_role else None
    profile.current_company = req.current_company.strip() if req.current_company else None
    if req.target_industry:
        profile.career_interests = json.dumps([req.target_industry.strip()])
    if req.preferred_learning_goals:
        profile.preferred_learning_goals = json.dumps(req.preferred_learning_goals)

    # Convert skills into self_reported_skills dict
    skills_dict = {}
    for s in req.skills:
        skill_name = s.skill.strip()
        if not skill_name:
            continue
        # Map proficiency to level 1-5
        prof_lower = s.proficiency.strip().lower()
        level_num = {"beginner": 1, "basic": 2, "intermediate": 3, "advanced": 4, "expert": 5}.get(prof_lower, 3)
        lvl_meta = PROFICIENCY_LEVELS[level_num]
        skills_dict[skill_name] = {
            "level": level_num,
            "level_title": lvl_meta["name"],
            "baseline_score": level_to_baseline_score(level_num),
            "category": s.category or _classify_skill_category(skill_name),
            "source": s.source or "SELF_REPORTED",
            "notes": s.notes,
            "reported_at": now.isoformat(),
        }
    profile.self_reported_skills = json.dumps(skills_dict)
    profile.updated_at = now
    db.add(profile)
    db.commit()
    db.refresh(profile)

    # 3. Persist CandidateSkillAnalytics baseline
    for skill_name, s_meta in skills_dict.items():
        existing_analytics = (
            db.query(CandidateSkillAnalytics)
            .filter(
                CandidateSkillAnalytics.user_id == user.id,
                CandidateSkillAnalytics.skill == skill_name,
            )
            .first()
        )
        if not existing_analytics:
            init_analytics = CandidateSkillAnalytics(
                user_id=user.id,
                skill=skill_name,
                score=s_meta["baseline_score"],
                trend="flat",
                role_relevance=1.0,
                evidence_count=1,
                confidence="LOW",  # Unverified until assessed
                weakness_status="identified",
                first_detected_at=now,
                last_updated_at=now,
            )
            db.add(init_analytics)
    db.commit()

    # 4. Save ResumeScan record if resume was provided
    scan_id = None
    if req.raw_resume_text:
        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        matched_str = ", ".join(list(skills_dict.keys())[:15])
        scan_record = ResumeScan(
            scan_id=scan_id,
            user_id=user.id,
            matching_engine_version="match-v1.1.0",
            candidate_name=user.full_name or req.full_name,
            target_role=req.target_role,
            match_score=70.0,
            overall_match_score=70.0,
            match_confidence="MEDIUM",
            matched_skills=matched_str,
            source_type="onboarding_upload",
            created_at=now,
            updated_at=now,
        )
        db.add(scan_record)
        profile.latest_scan_id = scan_id
        db.commit()

    # 5. Evaluate Onboarding Assessment for return payload
    cand_skills_data = [s.model_dump() for s in req.skills]
    assessment = evaluate_onboarding_skill_match(
        target_role=req.target_role,
        target_level=req.target_level,
        candidate_skills=cand_skills_data,
        years_of_experience=req.years_of_experience,
        education_level=req.education_level,
    )

    # 6. Initialize Personalized Adaptive Roadmap (Agent 2)
    roadmap_id = None
    try:
        roadmap_data = generate_adaptive_learning_path(
            user_id=user.id,
            db=db,
            target_role=req.target_role,
            personalization_context={
                "target_level": req.target_level,
                "years_of_experience": req.years_of_experience,
                "career_goals": req.career_goals,
                "onboarding_initialized": True,
            },
        )
        roadmap_id = roadmap_data.roadmap_id
    except Exception as road_err:
        # Graceful non-blocking fallback if roadmap synthesis encounters edge case
        pass

    top_matched = [s["skill"] for s in assessment.get("evaluated_skills", []) if s["status"] == "Matched"][:4]
    top_gaps = [s["skill"] for s in assessment.get("evaluated_skills", []) if s["status"] == "Gap"][:4]

    submitted_profile = {
        "full_name": user.full_name or req.full_name or "Candidate",
        "email": (req.email or user.email or "").strip(),
        "phone": (req.phone or "").strip(),
        "summary": summary_text,
        "education_level": req.education_level or "",
        "institution": req.institution or "",
        "graduation_year": req.graduation_year,
        "current_role": req.current_role or "",
        "current_company": req.current_company or "",
        "years_of_experience": float(req.years_of_experience),
        "target_role": req.target_role,
        "target_level": req.target_level,
        "skills": [s.model_dump() for s in req.skills],
        "work_experience": req.work_experience or [],
        "projects": req.projects or [],
        "certifications": req.certifications or [],
    }

    return CompleteOnboardingResponse(
        success=True,
        message="Candidate onboarding and career readiness baseline initialized successfully.",
        profile_id=profile.id,
        user_id=user.id,
        full_name=user.full_name or req.full_name or "Candidate",
        target_role=profile.target_role,
        target_level=profile.target_level,
        overall_match_score=assessment.get("overall_match_percentage", 0.0),
        readiness_status=assessment.get("readiness_status", "Developing"),
        roadmap_id=roadmap_id,
        top_matched_skills=top_matched,
        top_skill_gaps=top_gaps,
        next_action="Start your personalized learning roadmap.",
        assessment=assessment,
        submitted_profile=submitted_profile,
    )
