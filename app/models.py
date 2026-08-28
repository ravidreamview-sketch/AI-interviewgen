from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# ==============================================================================
# ADAPTIVE INTERVIEW ENGINE ENUMS & VERSION CONSTANTS
# ==============================================================================

DEFAULT_QUESTION_ENGINE_VERSION = "qengine-v2.0.0"
DEFAULT_EVALUATION_VERSION = "eval-v1.2.0"


class WeaknessStatusEnum(str, Enum):
    identified = "identified"
    practicing = "practicing"
    improving = "improving"
    resolved = "resolved"


class MistakeStatusEnum(str, Enum):
    identified = "identified"
    practicing = "practicing"
    resolved = "resolved"


class ConfidenceLevelEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MistakeSeverityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TrendSlopeEnum(str, Enum):
    improving = "improving"
    flat = "flat"
    declining = "declining"


class QuestionReasonEnum(str, Enum):
    role_requirement = "role_requirement"
    resume_skill = "resume_skill"
    jd_requirement = "jd_requirement"
    candidate_weakness = "candidate_weakness"
    previous_mistake = "previous_mistake"
    low_score = "low_score"
    practice_goal = "practice_goal"
    follow_up = "follow_up"


class InterviewRequest(BaseModel):
    role: str = Field(..., min_length=2)
    experience: Optional[str] = Field("Mid Level (3-5 Years)")
    skills: Optional[List[str]] = Field(default_factory=list)
    difficulty: Optional[str] = Field("Hard")
    number_of_questions: Optional[int] = Field(5, ge=1, le=50)
    company: Optional[str] = Field("General Tech", description="Target company bar (e.g. Google, Amazon, Meta, Microsoft)")
    interview_type: Optional[str] = Field("Technical & Architecture", description="Interview round format")
    custom_question: Optional[str] = Field(None, description="Optional specific focus question, case study, or seed prompt to branch related questions from")
    
    # Optional adaptive lineage and context fields (backward compatible)
    adaptive_session_id: Optional[str] = Field(None, description="Unique adaptive session identifier")
    resume_text: Optional[str] = Field(None, description="Optional raw resume text or summary")
    jd_text: Optional[str] = Field(None, description="Optional target job description")
    practice_goal: Optional[str] = Field("balanced", description="balanced | weakness_remediation | ats_gap_closer | faang_stress_drill")


# ==============================================================================
# CANDIDATE SKILL ANALYTICS & MISTAKES LEDGER SCHEMAS
# ==============================================================================

class SkillAnalyticsCreate(BaseModel):
    user_id: int
    skill: str
    score: Optional[float] = Field(70.0, ge=0.0, le=100.0)
    trend: Optional[TrendSlopeEnum] = TrendSlopeEnum.flat
    role_relevance: Optional[float] = Field(1.0, ge=0.0, le=1.0)
    evidence_count: Optional[int] = Field(1, ge=1)
    confidence: Optional[ConfidenceLevelEnum] = ConfidenceLevelEnum.LOW
    weakness_status: Optional[WeaknessStatusEnum] = WeaknessStatusEnum.identified
    adaptive_session_id: Optional[str] = None


class SkillAnalyticsUpdate(BaseModel):
    score: Optional[float] = Field(None, ge=0.0, le=100.0)
    trend: Optional[TrendSlopeEnum] = None
    role_relevance: Optional[float] = Field(None, ge=0.0, le=1.0)
    evidence_count: Optional[int] = None
    confidence: Optional[ConfidenceLevelEnum] = None
    weakness_status: Optional[WeaknessStatusEnum] = None
    adaptive_session_id: Optional[str] = None


class SkillAnalyticsResponse(BaseModel):
    id: int
    user_id: int
    skill: str
    score: float
    trend: str
    role_relevance: float
    evidence_count: int
    confidence: str
    weakness_status: str
    adaptive_session_id: Optional[str] = None
    first_detected_at: str
    last_updated_at: str


class MistakeLedgerCreate(BaseModel):
    user_id: int
    interview_id: Optional[int] = None
    adaptive_session_id: str
    skill: str
    mistake_category: Optional[str] = "conceptual"
    description: str
    evidence: Optional[str] = None
    severity: Optional[MistakeSeverityEnum] = MistakeSeverityEnum.medium
    recommendation: Optional[str] = None
    mistake_status: Optional[MistakeStatusEnum] = MistakeStatusEnum.identified
    evaluation_version: Optional[str] = DEFAULT_EVALUATION_VERSION


class MistakeLedgerUpdate(BaseModel):
    mistake_status: Optional[MistakeStatusEnum] = None
    recommendation: Optional[str] = None
    resolved_at: Optional[str] = None


class MistakeLedgerResponse(BaseModel):
    id: int
    user_id: int
    interview_id: Optional[int] = None
    adaptive_session_id: str
    skill: str
    mistake_category: str
    description: str
    evidence: Optional[str] = None
    severity: str
    recommendation: Optional[str] = None
    mistake_status: str
    evaluation_version: str
    created_at: str
    resolved_at: Optional[str] = None


class AdaptiveSessionSummary(BaseModel):
    adaptive_session_id: str
    candidate_id: int
    target_role: str
    question_engine_version: str = DEFAULT_QUESTION_ENGINE_VERSION
    evaluation_version: str = DEFAULT_EVALUATION_VERSION
    active_weaknesses_count: int = 0
    resolved_weaknesses_count: int = 0
    logged_mistakes_count: int = 0
    resolved_mistakes_count: int = 0


# ==============================================================================
# ADAPTIVE CANDIDATE PROFILE SCHEMAS
# ==============================================================================

class ProfileStrengthItem(BaseModel):
    skill: str
    score: float
    trend: str
    confidence: str
    evidence_count: int
    role_relevance: Optional[float] = 1.0


class ProfileFocusAreaItem(BaseModel):
    skill: str
    score: float
    trend: str
    confidence: str
    evidence_count: int
    status: str
    role_relevance: Optional[float] = 1.0


class ProfileOpenMistakeItem(BaseModel):
    id: int
    skill: str
    category: str
    description: str
    severity: str
    status: str
    created_at: str


class ProfileRecommendedFocus(BaseModel):
    skill: str
    reason: str
    priority: str  # "high" | "medium" | "low"


class AdaptiveProfileResponse(BaseModel):
    readiness_score: Optional[float] = None
    profile_status: str = "ready"  # "ready" | "insufficient_data"
    interview_count: int = 0
    last_interview_score: Optional[float] = None
    improvement_since_first_interview: Optional[float] = None
    strengths: List[ProfileStrengthItem] = Field(default_factory=list)
    focus_areas: List[ProfileFocusAreaItem] = Field(default_factory=list)
    open_mistakes: List[ProfileOpenMistakeItem] = Field(default_factory=list)
    recommended_focus: Optional[ProfileRecommendedFocus] = None


class AdaptiveQuestionItem(BaseModel):
    question: str
    reason: str  # role_requirement | resume_skill | jd_requirement | candidate_weakness | previous_mistake | low_score | practice_goal | follow_up
    source: str
    target_skill: str
    focus_skill: str
    difficulty: str
    evidence_reference: Optional[Dict[str, Any]] = None
    question_engine_version: str = "adaptive-qengine-v1.0.0"


class AdaptiveGenerateResponse(BaseModel):
    adaptive_session_id: str
    profile_status: str  # "ready" | "insufficient_data"
    recommended_focus: Optional[ProfileRecommendedFocus] = None
    questions: List[AdaptiveQuestionItem] = Field(default_factory=list)


class SkillScoreItem(BaseModel):
    skill: str
    score: float
    evidence: str
    confidence: str = "MEDIUM"


class DetectedMistakeItem(BaseModel):
    skill: str
    category: str
    severity: str
    description: str
    recommendation: str


class EvaluateResponseRequest(BaseModel):
    adaptive_session_id: Optional[str] = None
    question: str
    candidate_response: str
    target_skill: Optional[str] = "General Competency"
    focus_skill: Optional[str] = "Core Principles"
    difficulty: Optional[str] = "Hard"
    role: Optional[str] = "Software Engineer"
    expected_signals: Optional[List[str]] = Field(default_factory=list)
    question_engine_version: Optional[str] = "adaptive-qengine-v1.0.0"


class ResponseEvaluationResult(BaseModel):
    adaptive_session_id: str
    evaluation_version: str = "eval-v1.2.0"
    overall_score: float
    skill_scores: List[SkillScoreItem] = Field(default_factory=list)
    good_signals: List[str] = Field(default_factory=list)
    missing_signals: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    mistakes: List[DetectedMistakeItem] = Field(default_factory=list)
    summary: str


class NextQuestionRequest(BaseModel):
    adaptive_session_id: Optional[str] = None
    current_target_skill: Optional[str] = None
    previous_question: Optional[str] = None
    previous_response: Optional[str] = None
    latest_evaluation: Optional[ResponseEvaluationResult] = None
    role: Optional[str] = "Software Engineer"
    experience: Optional[str] = "3-5 Years"
    difficulty: Optional[str] = "Hard"
    interview_type: Optional[str] = "Technical & Architecture"
    company: Optional[str] = "General Tech"
    practice_goal: Optional[str] = "weakness_remediation"
    skills: Optional[List[str]] = Field(default_factory=list)


class AdaptiveNextQuestionResponse(BaseModel):
    adaptive_session_id: str
    strategy: str  # continue_probing | mistake_follow_up | scale_difficulty | advance_next_weakness | baseline_exploration
    question: AdaptiveQuestionItem


class PageViewPayload(BaseModel):
    session_id: str
    page_url: str
    page_title: Optional[str] = None
    referrer: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    device_type: Optional[str] = None
    screen_resolution: Optional[str] = None


class ClickEventPayload(BaseModel):
    session_id: str
    page_url: str
    element_tag: Optional[str] = None
    element_id: Optional[str] = None
    element_text: Optional[str] = None
    element_class: Optional[str] = None
    target_role: Optional[str] = None
    action_type: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    device_type: Optional[str] = None


# ==============================================================================
# ADMIN AUTH & RBAC MODELS
# ==============================================================================

class AdminLoginRequest(BaseModel):
    email: Optional[str] = "admin@example.com"
    password: Optional[str] = "SuperAdminPass123!"


class CandidateLoginRequest(BaseModel):
    email: Optional[str] = "candidate@example.com"
    password: Optional[str] = "CandidatePass123!"


class UserCreateRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = Field(None, description="Candidate or User Full Name")
    role: Optional[str] = Field("candidate", description="super_admin | admin | candidate")
    plan_tier: Optional[str] = Field("free", description="free | pro | enterprise")
    is_active: Optional[bool] = True


class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)
    role: Optional[str] = Field(None, description="super_admin | admin | candidate")
    plan_tier: Optional[str] = Field(None, description="free | pro | enterprise")
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    plan_tier: str
    is_active: bool
    created_at: str
    last_login: Optional[str] = None


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    admin_email: Optional[str] = None
    action: str
    resource: str
    previous_value: Optional[str] = None
    new_value: Optional[str] = None
    timestamp: str
    ip_address: Optional[str] = None
    request_id: Optional[str] = None


class RoleDefinitionResponse(BaseModel):
    role: str
    title: str
    description: str
    permissions: List[str]


class SystemConfigItem(BaseModel):
    config_key: str
    config_value: str
    updated_at: str


# ==============================================================================
# PROMPT MANAGEMENT MODULE SCHEMAS
# ==============================================================================

class PromptCreateRequest(BaseModel):
    name: str = Field(..., min_length=2)
    description: Optional[str] = None
    category: str = Field("Interview Questions")
    role: Optional[str] = "General Tech"
    difficulty: Optional[str] = "Hard"
    system_prompt: Optional[str] = None
    user_prompt: str = Field(..., min_length=5)
    variables: Optional[str] = None
    model: Optional[str] = "gemini-1.5-flash"
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(1024, ge=64, le=8192)
    status: Optional[str] = Field("draft", description="draft | active | archived")
    change_summary: Optional[str] = "Initial prompt creation"


class PromptUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    role: Optional[str] = None
    difficulty: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    variables: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=64, le=8192)
    status: Optional[str] = Field(None, description="draft | active | archived")
    change_summary: Optional[str] = None


class PromptTestRequest(BaseModel):
    test_variables: Optional[dict] = Field(default_factory=dict)


class PromptResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category: str
    role: Optional[str] = None
    difficulty: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt: str
    variables: Optional[str] = None
    model: str
    temperature: float
    max_tokens: int
    version: int
    status: str
    created_at: str
    updated_at: str
    is_active: bool


class PromptVersionResponse(BaseModel):
    id: int
    prompt_id: int
    version: int
    name: str
    description: Optional[str] = None
    category: str
    role: Optional[str] = None
    difficulty: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt: str
    variables: Optional[str] = None
    model: str
    temperature: float
    max_tokens: int
    status: str
    change_summary: Optional[str] = None
    changed_by_email: Optional[str] = None
    created_at: str


# ==============================================================================
# PHASE 5A: JOB DESCRIPTION EXTRACTION & NORMALIZATION SCHEMAS
# ==============================================================================

class NormalizedJobDescription(BaseModel):
    job_title: Optional[str] = Field(None, description="Extracted job role or title")
    company: Optional[str] = Field(None, description="Hiring company or organization name")
    location: Optional[str] = Field(None, description="Job location or remote status")
    experience_required: Optional[str] = Field(None, description="Required years of experience or seniority level")
    employment_type: Optional[str] = Field(None, description="Full-time, Contract, Part-time, Internship")
    responsibilities: List[str] = Field(default_factory=list, description="Core responsibilities and duties")
    required_skills: List[str] = Field(default_factory=list, description="Must-have technical and foundational skills")
    preferred_skills: List[str] = Field(default_factory=list, description="Nice-to-have or preferred skills")
    domain_requirements: List[str] = Field(default_factory=list, description="Industry or domain requirements")
    tools: List[str] = Field(default_factory=list, description="Specific developer tools, platforms, or utilities")
    technical_requirements: List[str] = Field(default_factory=list, description="Architecture, protocols, or engineering standards")
    soft_skills: List[str] = Field(default_factory=list, description="Interpersonal and leadership competencies")
    education_requirements: Optional[str] = Field(None, description="Degree or educational prerequisite")
    source_type: str = Field("manual_paste", description="public_url | document_upload | manual_paste")
    source_url: Optional[str] = Field(None, description="Original job URL if fetched from web")
    fetched_at: Optional[str] = Field(None, description="ISO timestamp of when the JD was extracted")


class JobURLExtractRequest(BaseModel):
    url: str = Field(..., min_length=4, description="Public HTTP/HTTPS job posting URL")


class JobURLExtractResponse(BaseModel):
    success: bool
    status: str = Field(..., description="extracted | fallback_required")
    fallback_required: bool = Field(False, description="True if automated extraction failed gracefully and candidate should paste JD text")
    message: Optional[str] = None
    raw_jd: Optional[str] = None
    normalized_jd: Optional[NormalizedJobDescription] = None


class JobUploadExtractResponse(BaseModel):
    success: bool
    status: str = Field(..., description="extracted | fallback_required")
    fallback_required: bool = Field(False, description="True if automated extraction failed and candidate should paste JD text")
    message: Optional[str] = None
    filename: Optional[str] = None
    raw_jd: Optional[str] = None
    normalized_jd: Optional[NormalizedJobDescription] = None


# ==============================================================================
# PHASE 5B: RESUME ↔ JD MULTI-DIMENSIONAL MATCHING SCHEMAS
# ==============================================================================

class ResumeWorkExperience(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    duration_years: Optional[float] = None
    description: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)


class ResumeProject(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)


class NormalizedResume(BaseModel):
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    summary: Optional[str] = None
    total_years_experience: Optional[float] = None
    skills: List[str] = Field(default_factory=list)
    work_experience: List[ResumeWorkExperience] = Field(default_factory=list)
    projects: List[ResumeProject] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    raw_text: Optional[str] = None


class SkillMatrixItem(BaseModel):
    skill: str
    importance: str = Field("HIGH", description="HIGH | MEDIUM | LOW")
    jd_requirement: str = Field("", description="Requirement context from JD")
    resume_evidence: Optional[str] = Field(None, description="Exact textual evidence from resume, or null")
    evidence_level: int = Field(6, ge=1, le=6, description="Level 1 to 6")
    evidence_strength: str = Field("NONE", description="HIGH | MEDIUM | LOW | NONE")
    match_score: float = Field(0.0, ge=0.0, le=100.0, description="Match score for this competency (0-100)")
    gap_status: str = Field("gap", description="matched | partial | gap")


class SubScores(BaseModel):
    required_skills: float = Field(0.0, ge=0.0, le=100.0)
    experience: float = Field(0.0, ge=0.0, le=100.0)
    domain: float = Field(0.0, ge=0.0, le=100.0)
    responsibilities: float = Field(0.0, ge=0.0, le=100.0)
    preferred_skills: float = Field(0.0, ge=0.0, le=100.0)
    tools_technology: Optional[float] = Field(None, ge=0.0, le=100.0)
    education: Optional[float] = Field(None, ge=0.0, le=100.0)


class ResumeJDMatchResult(BaseModel):
    overall_match_score: float = Field(..., ge=0.0, le=100.0)
    match_confidence: str = Field(..., description="HIGH | MEDIUM | LOW")
    sub_scores: SubScores
    skill_matrix: List[SkillMatrixItem] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)
    critical_gaps: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


# ==============================================================================
# PHASE 5C: MATCH PERSISTENCE & API SCHEMAS
# ==============================================================================

class ResumeJDMatchRequest(BaseModel):
    resume_text: Optional[str] = Field(None, description="Raw plain text resume content")
    jd_text: Optional[str] = Field(None, description="Raw job description text")
    jd_url: Optional[str] = Field(None, description="Public job posting URL")
    normalized_resume: Optional[NormalizedResume] = Field(None, description="Pre-normalized resume model")
    normalized_jd: Optional[NormalizedJobDescription] = Field(None, description="Pre-normalized JD model")
    source_type: Optional[str] = Field("paste", description="paste | upload | public_url")
    source_url: Optional[str] = Field(None, description="Original job URL if applicable")
    candidate_name: Optional[str] = Field(None, description="Optional override candidate name")
    target_role: Optional[str] = Field(None, description="Optional override target role")


class ResumeJDMatchResponse(BaseModel):
    scan_id: str = Field(..., description="Secure unique server-generated scan identifier")
    matching_engine_version: str = Field("match-v1.0.0", description="Algorithm version")
    overall_match_score: float = Field(..., ge=0.0, le=100.0)
    match_confidence: str = Field(..., description="HIGH | MEDIUM | LOW")
    sub_scores: SubScores
    skill_matrix: List[SkillMatrixItem] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)
    critical_gaps: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    target_role: str
    candidate_name: Optional[str] = None
    source_type: str = "paste"
    source_url: Optional[str] = None
    created_at: str


class ResumeJDMatchSummaryItem(BaseModel):
    scan_id: str
    target_role: str
    overall_match_score: float
    match_confidence: str
    matching_engine_version: str
    source_type: str
    created_at: str


# ==============================================================================
# PHASE 5D: RESUME/JD MATCH → ADAPTIVE INTERVIEW INTEGRATION SCHEMAS
# ==============================================================================

class AdaptiveFromMatchRequest(BaseModel):
    scan_id: str = Field(..., description="Secure server-generated scan identifier")
    number_of_questions: Optional[int] = Field(5, ge=1, le=20, description="Desired number of adaptive questions")


class AdaptiveFromMatchResponse(BaseModel):
    adaptive_session_id: str = Field(..., description="Unique adaptive session ID")
    scan_id: str = Field(..., description="Associated scan reference ID")
    profile_status: str = Field(..., description="profile_status from candidate profile")
    recommended_focus: Optional[ProfileRecommendedFocus] = Field(None, description="Recommended focus area")
    questions: List[AdaptiveQuestionItem] = Field(default_factory=list, description="Targeted adaptive questions")