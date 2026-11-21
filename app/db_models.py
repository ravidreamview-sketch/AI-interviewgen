from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float
from datetime import datetime, timezone
from app.database import Base


class UserAccount(Base):
    __tablename__ = "user_accounts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="candidate", index=True)  # super_admin, admin, candidate
    plan_tier = Column(String, nullable=False, default="free")              # free, pro, enterprise
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
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
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)
    ip_address = Column(String, nullable=True)
    request_id = Column(String, nullable=True)


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String, unique=True, index=True, nullable=False)
    config_value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


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
    questions_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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
    first_detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    last_updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False, index=True)


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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
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
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


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
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class ResumeScan(Base):
    __tablename__ = "resume_scans"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(String, unique=True, index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=True, index=True)
    matching_engine_version = Column(String, default="match-v1.1.0")
    evaluation_fingerprint = Column(String(64), index=True, nullable=True)
    resume_fingerprint = Column(String(64), index=True, nullable=True)
    jd_fingerprint = Column(String(64), index=True, nullable=True)
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
        default=datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
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
        default=datetime.now(timezone.utc),
        nullable=False,
    )

class CandidateAnswerAttempt(Base):
    __tablename__ = "candidate_answer_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    interview_id = Column(Integer, ForeignKey("interview_history.id", ondelete="CASCADE"), nullable=False, index=True)
    question_index = Column(Integer, nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    candidate_answer = Column(Text, nullable=False)
    evaluation_feedback = Column(Text, nullable=False)
    overall_score = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class UserInvitation(Base):
    __tablename__ = "user_invitations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False, default="candidate")
    plan_tier = Column(String, nullable=False, default="free")
    token_hash = Column(String, unique=True, index=True, nullable=False)
    invited_by_user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True)
    invited_by_email = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    is_revoked = Column(Boolean, default=False, nullable=False)


class RebuiltResume(Base):
    __tablename__ = "rebuilt_resumes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    rebuild_id = Column(String(64), unique=True, index=True, nullable=False)
    scan_id = Column(String(64), index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, default=1, nullable=False)
    target_role = Column(String(255), nullable=False, default="General Tech")
    original_resume_snippet = Column(Text, nullable=True)
    rebuilt_resume_text = Column(Text, nullable=False)
    rebuilt_structured_json = Column(Text, nullable=True)
    tailored_skills = Column(Text, nullable=True)
    improvements_summary = Column(Text, nullable=True)
    ats_projected_score = Column(Float, nullable=True)
    status = Column(String(50), default="active", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ==============================================================================
# PHASE 1: LEARNER INTELLIGENCE PROFILE
# ==============================================================================

class LearnerProfile(Base):
    __tablename__ = "learner_profiles"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    target_role = Column(String(255), nullable=False, default="Full-Stack Engineer")
    secondary_roles = Column(Text, nullable=True)  # JSON list
    career_goals = Column(Text, nullable=True)
    target_level = Column(String(50), nullable=False, default="Mid-Level")
    education_level = Column(String(100), nullable=True)
    institution = Column(String(255), nullable=True)
    graduation_year = Column(Integer, nullable=True)
    years_of_experience = Column(Float, nullable=False, default=0.0)
    current_role = Column(String(255), nullable=True)
    current_company = Column(String(255), nullable=True)
    preferred_learning_goals = Column(Text, nullable=True)  # JSON list
    career_interests = Column(Text, nullable=True)          # JSON list
    self_reported_skills = Column(Text, nullable=True)      # JSON dict
    latest_scan_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ==============================================================================
# PHASE 2: ADAPTIVE LEARNING PATH
# ==============================================================================

class AdaptiveRoadmap(Base):
    __tablename__ = "adaptive_roadmaps"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    roadmap_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    target_role = Column(String(255), nullable=False)
    target_level = Column(String(50), nullable=False, default="Mid-Level")
    status = Column(String(50), nullable=False, default="active")  # active, archived, completed
    overall_progress = Column(Float, nullable=False, default=0.0)
    total_estimated_hours = Column(Float, nullable=False, default=0.0)
    completed_activities_count = Column(Integer, nullable=False, default=0)
    total_activities_count = Column(Integer, nullable=False, default=0)
    roadmap_data = Column(Text, nullable=False)
    adaptation_history = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ==============================================================================
# PHASE 3: AI SOCRATIC TUTOR
# ==============================================================================

class TutorSession(Base):
    __tablename__ = "tutor_sessions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    roadmap_id = Column(String(64), nullable=True, index=True)
    activity_id = Column(String(64), nullable=True, index=True)
    concept = Column(String(255), nullable=False)
    teaching_mode = Column(String(50), nullable=False, default="explain")
    complexity_level = Column(String(50), nullable=False, default="standard")
    skill_level = Column(Integer, nullable=False, default=3)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TutorMessage(Base):
    __tablename__ = "tutor_messages"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("tutor_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    code_snippet = Column(Text, nullable=True)
    pedagogical_intent = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# ==============================================================================
# PHASE 4: REAL-WORLD SCENARIO GENERATION & EVALUATION
# ==============================================================================

class RealWorldScenario(Base):
    __tablename__ = "real_world_scenarios"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)
    domain = Column(String(100), nullable=False)
    target_role = Column(String(255), nullable=False)
    difficulty = Column(String(50), nullable=False, default="Intermediate")
    difficulty_level = Column(Integer, nullable=False, default=3)
    context = Column(Text, nullable=False)
    problem_statement = Column(Text, nullable=False)
    required_skills = Column(Text, nullable=False)  # JSON list
    objectives = Column(Text, nullable=False)       # JSON list
    instructions = Column(Text, nullable=False)     # JSON list
    constraints = Column(Text, nullable=False)      # JSON list
    deliverables = Column(Text, nullable=False)     # JSON list
    rubric = Column(Text, nullable=False)           # JSON dict with criteria dimensions
    success_criteria = Column(Text, nullable=False) # JSON list
    hints = Column(Text, nullable=True)             # JSON list
    is_completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ScenarioSubmissionRecord(Base):
    __tablename__ = "scenario_submissions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(String(64), unique=True, index=True, nullable=False)
    scenario_id = Column(
        String(64),
        ForeignKey("real_world_scenarios.scenario_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    solution_text = Column(Text, nullable=False)
    code_submission = Column(Text, nullable=True)
    architectural_notes = Column(Text, nullable=True)
    status = Column(String(50), default="evaluated", nullable=False)
    overall_score = Column(Float, nullable=True)
    dimension_scores = Column(Text, nullable=True)       # JSON dict
    strengths = Column(Text, nullable=True)              # JSON list
    areas_for_improvement = Column(Text, nullable=True)  # JSON list
    evidence = Column(Text, nullable=True)
    feedback = Column(Text, nullable=True)
    recommended_next_steps = Column(Text, nullable=True) # JSON list
    evaluation_disclaimer = Column(Text, nullable=True)
    evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# ==============================================================================
# PHASE 5: AI PROJECT MENTORING
# ==============================================================================

class LearnerProject(Base):
    __tablename__ = "learner_projects"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    target_role = Column(String(255), nullable=False)
    domain = Column(String(100), nullable=False, default="Full-Stack Web Systems")
    description = Column(Text, nullable=False)
    architecture_overview = Column(Text, nullable=True)
    tech_stack = Column(Text, nullable=False)  # JSON list
    status = Column(String(50), default="planning", nullable=False)  # planning, in_development, review_ready, completed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ProjectMentorshipTurn(Base):
    __tablename__ = "project_mentorship_turns"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        String(64),
        ForeignKey("learner_projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mentorship_stage = Column(String(50), nullable=False)  # planning, requirements, architecture, debugging, design_review, presentation_prep
    user_query = Column(Text, nullable=False)
    mentor_guidance = Column(Text, nullable=False)
    action_items = Column(Text, nullable=False)  # JSON list
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# ==============================================================================
# PHASE 7: AGENT ORCHESTRATION & MONITORING
# ==============================================================================

class AgentExecutionMetric(Base):
    __tablename__ = "agent_execution_metrics"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(String(64), unique=True, index=True, nullable=False)
    agent_id = Column(String(64), index=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id = Column(String(64), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="completed")  # started, completed, failed, fallback_used
    latency_ms = Column(Float, nullable=False, default=0.0)
    tokens_prompt = Column(Integer, nullable=False, default=0)
    tokens_completion = Column(Integer, nullable=False, default=0)
    cost_estimate_usd = Column(Float, nullable=False, default=0.0)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)  # sanitized metadata JSON
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


class AgentWorkflowRun(Base):
    __tablename__ = "agent_workflow_runs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(String(64), unique=True, index=True, nullable=False)
    workflow_type = Column(String(64), index=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(50), nullable=False, default="pending")  # pending, running, completed, failed, partially_completed
    steps_completed = Column(Integer, nullable=False, default=0)
    total_steps = Column(Integer, nullable=False, default=1)
    result_summary = Column(Text, nullable=True)
    error_details = Column(Text, nullable=True)
    idempotency_key = Column(String(128), index=True, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)



