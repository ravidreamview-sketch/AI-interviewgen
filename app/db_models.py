from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float
from datetime import datetime
from app.database import Base


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="candidate", index=True)  # super_admin, admin, candidate
    plan_tier = Column(String, nullable=False, default="free")              # free, pro, enterprise
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)



class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    admin_email = Column(String, nullable=True)
    action = Column(String, nullable=False, index=True)
    resource = Column(String, nullable=False)
    previous_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    ip_address = Column(String, nullable=True)
    request_id = Column(String, nullable=True)


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String, unique=True, index=True, nullable=False)
    config_value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class InterviewHistory(Base):
    __tablename__ = "interview_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    adaptive_session_id = Column(String, nullable=True, index=True)
    role = Column(String, nullable=False)
    experience = Column(String, nullable=False)
    skills = Column(Text, nullable=False)
    difficulty = Column(String, nullable=False)
    questions = Column(Text, nullable=False)
    question_engine_version = Column(String, nullable=True, default="qengine-v1.0.0")
    created_at = Column(DateTime, default=datetime.utcnow)


class CandidateSkillAnalytics(Base):
    __tablename__ = "candidate_skill_analytics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    skill = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False, default=70.0, index=True)
    trend = Column(String, nullable=False, default="flat")           # improving | flat | declining
    role_relevance = Column(Float, nullable=False, default=1.0)      # 0.3 to 1.0
    evidence_count = Column(Integer, nullable=False, default=1)
    confidence = Column(String, nullable=False, default="LOW")       # LOW | MEDIUM | HIGH
    weakness_status = Column(String, nullable=False, default="identified", index=True) # identified | practicing | improving | resolved
    adaptive_session_id = Column(String, nullable=True, index=True)
    first_detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)


class CandidateMistakesLedger(Base):
    __tablename__ = "candidate_mistakes_ledger"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    interview_id = Column(Integer, ForeignKey("interview_history.id", ondelete="SET NULL"), nullable=True, index=True)
    adaptive_session_id = Column(String, nullable=False, index=True)
    skill = Column(String, nullable=False, index=True)
    mistake_category = Column(String, nullable=False, default="conceptual")
    description = Column(Text, nullable=False)
    evidence = Column(Text, nullable=True)
    severity = Column(String, nullable=False, default="medium")       # low | medium | high | critical
    recommendation = Column(Text, nullable=True)
    mistake_status = Column(String, nullable=False, default="identified", index=True) # identified | practicing | resolved
    evaluation_version = Column(String, nullable=False, default="eval-v1.2.0")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)


class PageViewEvent(Base):
    __tablename__ = "page_view_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    page_url = Column(String, nullable=False)
    page_title = Column(String, nullable=True)
    referrer = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    browser = Column(String, nullable=True)
    os = Column(String, nullable=True)
    device_type = Column(String, nullable=True)
    screen_resolution = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class ClickEvent(Base):
    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    page_url = Column(String, nullable=False)
    element_tag = Column(String, nullable=True)
    element_id = Column(String, nullable=True)
    element_text = Column(String, nullable=True)
    element_class = Column(String, nullable=True)
    target_role = Column(String, nullable=True)
    action_type = Column(String, nullable=True)
    browser = Column(String, nullable=True)
    os = Column(String, nullable=True)
    device_type = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


# ==============================================================================
# PROMPT MANAGEMENT MODULE MODELS
# ==============================================================================

class Prompt(Base):
    __tablename__ = "prompts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=False, index=True) # Interview Questions, Resume Scan, Code Review, Mock Feedback
    role = Column(String, nullable=True, index=True)       # e.g. Python Developer, General Tech, All Roles
    difficulty = Column(String, nullable=True)            # Warm-up, Medium, Hard, Brutal, All
    system_prompt = Column(Text, nullable=True)
    user_prompt = Column(Text, nullable=False)
    variables = Column(Text, nullable=True)               # e.g. "role,experience,skills,difficulty,count"
    model = Column(String, nullable=False, default="gemini-1.5-flash")
    temperature = Column(Float, nullable=False, default=0.7)
    max_tokens = Column(Integer, nullable=False, default=1024)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="draft", index=True) # draft, active, archived
    created_by = Column(Integer, ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, index=True)
    prompt_id = Column(Integer, ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=False)
    role = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)
    system_prompt = Column(Text, nullable=True)
    user_prompt = Column(Text, nullable=False)
    variables = Column(Text, nullable=True)
    model = Column(String, nullable=False)
    temperature = Column(Float, nullable=False)
    max_tokens = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    change_summary = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class MockInterview(Base):
    __tablename__ = "mock_interviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    role = Column(String, nullable=False)
    company_target = Column(String, default="FAANG Tier")
    interviewer_persona = Column(String, default="Alex (Tech Lead)")
    score = Column(Float, nullable=False, default=85.0)
    technical_accuracy = Column(Float, default=85.0)
    communication_clarity = Column(Float, default=85.0)
    star_depth = Column(Float, default=85.0)
    confidence_score = Column(Float, default=85.0)
    duration_seconds = Column(Integer, default=300)
    transcript = Column(Text, nullable=True)
    status = Column(String, default="completed")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ResumeScan(Base):
    __tablename__ = "resume_scans"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(String, unique=True, index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    matching_engine_version = Column(String, default="match-v1.0.0")
    candidate_name = Column(String, default="Candidate")
    target_role = Column(String, nullable=False, default="General Tech")
    match_score = Column(Float, default=80.0)
    overall_match_score = Column(Float, default=80.0)
    match_confidence = Column(String, default="MEDIUM")
    sub_scores = Column(Text, nullable=True)
    skill_matrix = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)
    skill_gaps = Column(Text, nullable=True)
    critical_gaps = Column(Text, nullable=True)
    recommendations = Column(Text, nullable=True)
    normalized_jd = Column(Text, nullable=True)
    normalized_resume = Column(Text, nullable=True)
    matched_skills = Column(Text, default="")
    missing_skills = Column(Text, default="")
    source_type = Column(String, default="paste")
    source_url = Column(String, nullable=True)
    fetched_at = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)