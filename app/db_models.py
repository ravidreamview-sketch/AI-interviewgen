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
    role = Column(String, nullable=False)
    experience = Column(String, nullable=False)
    skills = Column(Text, nullable=False)
    difficulty = Column(String, nullable=False)
    questions = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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
    changed_by = Column(Integer, ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    changed_by_email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)