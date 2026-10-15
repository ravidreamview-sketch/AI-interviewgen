from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator
from datetime import datetime, timezone
from app.database import Base


class UTCDateTime(TypeDecorator):
    """Persist timezone-aware UTC datetimes consistently on SQLite and PostgreSQL."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _currency_checks(column_name):
    """Return portable currency checks plus dialect-specific ASCII-letter checks."""
    return (
        CheckConstraint(
            f"length({column_name}) = 3 AND {column_name} = upper({column_name})",
            name=f"ck_{column_name}_uppercase_3",
        ),
        CheckConstraint(
            f"{column_name} GLOB '[A-Z][A-Z][A-Z]'",
            name=f"ck_{column_name}_sqlite_ascii_currency",
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            f"{column_name} ~ '^[A-Z]{{3}}$'",
            name=f"ck_{column_name}_postgres_ascii_currency",
        ).ddl_if(dialect="postgresql"),
    )


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

    subscriptions = relationship(
        "Subscription",
        back_populates="user",
        foreign_keys="Subscription.user_id",
        passive_deletes=True,
    )


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True)
    code = Column(String(80), nullable=False, unique=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=True)
    duration_days = Column(Integer, nullable=False)
    price_minor = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    features_json = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime(), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    subscriptions = relationship("Subscription", back_populates="plan", passive_deletes=True)

    __table_args__ = (
        CheckConstraint("duration_days > 0", name="ck_subscription_plans_duration_positive"),
        CheckConstraint("price_minor > 0", name="ck_subscription_plans_price_positive"),
        *_currency_checks("currency"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="RESTRICT"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    starts_at = Column(UTCDateTime(), nullable=False)
    ends_at = Column(UTCDateTime(), nullable=False)
    plan_code_snapshot = Column(String(80), nullable=False)
    plan_name_snapshot = Column(String(160), nullable=False)
    amount_minor_snapshot = Column(Integer, nullable=False)
    currency_snapshot = Column(String(3), nullable=False)
    auto_renew = Column(Boolean, nullable=False, default=False)
    renewal_of_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="RESTRICT"), nullable=True)
    approved_at = Column(UTCDateTime(), nullable=True)
    suspended_at = Column(UTCDateTime(), nullable=True)
    suspended_by_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="RESTRICT"), nullable=True)
    suspension_reason = Column(Text, nullable=True)
    revoked_at = Column(UTCDateTime(), nullable=True)
    revoked_by_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="RESTRICT"), nullable=True)
    revocation_reason = Column(Text, nullable=True)
    created_at = Column(UTCDateTime(), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("UserAccount", back_populates="subscriptions", foreign_keys=[user_id])
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    payment_verification = relationship(
        "PaymentVerification", back_populates="subscription", uselist=False, passive_deletes=True
    )
    renewal_of = relationship("Subscription", remote_side=[id], foreign_keys=[renewal_of_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'revoked', 'expired')",
            name="ck_subscriptions_status",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_subscriptions_date_order"),
        CheckConstraint("amount_minor_snapshot > 0", name="ck_subscriptions_snapshot_price_positive"),
        CheckConstraint("auto_renew = false", name="ck_subscriptions_auto_renew_disabled"),
        CheckConstraint(
            "(approved_by_id IS NULL AND approved_at IS NULL) OR "
            "(approved_by_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_subscriptions_approval_metadata_pair",
        ),
        CheckConstraint(
            "status <> 'active' OR (approved_by_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_subscriptions_active_requires_approval",
        ),
        CheckConstraint(
            "status <> 'suspended' OR (suspended_at IS NOT NULL AND suspended_by_id IS NOT NULL "
            "AND suspension_reason IS NOT NULL AND length(trim(suspension_reason)) > 0)",
            name="ck_subscriptions_suspended_requires_metadata",
        ),
        CheckConstraint(
            "(status = 'revoked' AND revoked_at IS NOT NULL AND revoked_by_id IS NOT NULL "
            "AND revocation_reason IS NOT NULL AND length(trim(revocation_reason)) > 0) OR "
            "(status <> 'revoked' AND revoked_at IS NULL AND revoked_by_id IS NULL "
            "AND revocation_reason IS NULL)",
            name="ck_subscriptions_revoked_requires_metadata",
        ),
        *_currency_checks("currency_snapshot"),
        UniqueConstraint("renewal_of_id", name="uq_subscriptions_direct_renewal"),
        Index("ix_subscriptions_user_status_period", "user_id", "status", "starts_at", "ends_at"),
        Index("ix_subscriptions_plan_id", "plan_id"),
    )


class PaymentVerification(Base):
    __tablename__ = "payment_verifications"

    id = Column(Integer, primary_key=True)
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    provider = Column(String(80), nullable=False)
    provider_reference = Column(String(255), nullable=False)
    amount_minor = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    recorded_by_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="RESTRICT"), nullable=True)
    verified_by_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="RESTRICT"), nullable=True)
    verified_at = Column(UTCDateTime(), nullable=True)
    status_changed_by_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="RESTRICT"), nullable=True)
    status_changed_at = Column(UTCDateTime(), nullable=True)
    status_reason = Column(Text, nullable=True)
    created_at = Column(UTCDateTime(), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    subscription = relationship("Subscription", back_populates="payment_verification")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'verified', 'disputed', 'rejected', 'refunded', 'chargeback', 'reversed')",
            name="ck_payment_verifications_status",
        ),
        CheckConstraint("amount_minor > 0", name="ck_payment_verifications_amount_positive"),
        CheckConstraint(
            "(verified_by_id IS NULL AND verified_at IS NULL) OR "
            "(verified_by_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_payment_verifications_verification_metadata_pair",
        ),
        CheckConstraint(
            "status <> 'verified' OR (verified_by_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_payment_verifications_verified_requires_metadata",
        ),
        CheckConstraint(
            "(status = 'pending' AND status_changed_by_id IS NULL AND status_changed_at IS NULL "
            "AND status_reason IS NULL) OR "
            "(status <> 'pending' AND status_changed_by_id IS NOT NULL AND status_changed_at IS NOT NULL "
            "AND status_reason IS NOT NULL AND length(trim(status_reason)) > 0)",
            name="ck_payment_verifications_status_change_metadata",
        ),
        *_currency_checks("currency"),
        UniqueConstraint("provider", "provider_reference", name="uq_payment_verifications_provider_reference"),
        Index("ix_payment_verifications_status", "status"),
    )



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
    interview_type = Column(String, nullable=True)
    company = Column(String, nullable=True)
    requested_question_count = Column(Integer, nullable=True)
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
    interview_mode = Column(String, default="voice", nullable=True)
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

class CoachSession(Base):
    __tablename__ = "coach_sessions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class CoachMessage(Base):
    __tablename__ = "coach_messages"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(
        Integer,
        ForeignKey("coach_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role = Column(String(20), nullable=False)

    content = Column(Text, nullable=False)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
