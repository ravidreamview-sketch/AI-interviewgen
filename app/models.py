from pydantic import BaseModel, Field
from typing import List, Optional

class InterviewRequest(BaseModel):
    role: str = Field(..., min_length=2)
    experience: Optional[str] = Field("Mid Level (3-5 Years)")
    skills: Optional[List[str]] = Field(default_factory=list)
    difficulty: Optional[str] = Field("Hard")
    number_of_questions: Optional[int] = Field(5, ge=1, le=50)
    company: Optional[str] = Field("General Tech", description="Target company bar (e.g. Google, Amazon, Meta, Microsoft)")
    interview_type: Optional[str] = Field("Technical & Architecture", description="Interview round format")
    custom_question: Optional[str] = Field(None, description="Optional specific focus question, case study, or seed prompt to branch related questions from")


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