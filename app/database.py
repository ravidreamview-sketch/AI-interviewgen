import os
import tempfile
import logging
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

import urllib.parse
from sqlalchemy.pool import NullPool

logger = logging.getLogger("ravi.database")

# Only these established tables may be created implicitly during application
# initialization. New schema must be introduced through an explicit migration.
LEGACY_STARTUP_TABLE_NAMES = (
    "user_accounts",
    "audit_logs",
    "system_configs",
    "interview_history",
    "candidate_skill_analytics",
    "candidate_mistakes_ledger",
    "page_view_events",
    "click_events",
    "prompts",
    "prompt_versions",
    "mock_interviews",
    "resume_scans",
    "coach_sessions",
    "coach_messages",
)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def configure_sqlite_foreign_keys(target_engine):
    """Enable SQLite FK enforcement for every connection from an app engine."""
    if target_engine.dialect.name == "sqlite":
        event.listen(target_engine, "connect", _enable_sqlite_foreign_keys)


def _create_legacy_tables(target_engine):
    from app import db_models  # noqa: F401 - registers all mapped tables

    tables = [Base.metadata.tables[name] for name in LEGACY_STARTUP_TABLE_NAMES]
    Base.metadata.create_all(bind=target_engine, tables=tables)

# ---------------------------------------------------------------------------
# Stage 1: Resolve database configuration and detect runtime environment
# ---------------------------------------------------------------------------
raw_db_url = os.environ.get("DATABASE_URL")
if raw_db_url:
    raw_db_url = raw_db_url.strip().strip("'").strip('"')

is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
runtime_env = os.environ.get("ENV", "").strip().lower()
is_local_development = runtime_env in {"", "local", "dev", "development", "test"} and not is_vercel
is_production = not is_local_development

# Safe diagnostic logging (never log secrets, passwords, or full credentials)
if raw_db_url:
    try:
        parsed_url = urllib.parse.urlparse(raw_db_url)
        db_scheme = parsed_url.scheme or "unknown"
        db_host = parsed_url.hostname or "localhost"
        logger.info(f"Database configuration detected: dialect={db_scheme}, host={db_host}, serverless={is_vercel}")
    except Exception:
        logger.info(f"Database configuration detected: present (parsing sanitized), serverless={is_vercel}")
else:
    logger.info(f"Database configuration detected: none (using ephemeral storage), serverless={is_vercel}")

# ---------------------------------------------------------------------------
# Stage 2: Create SQLAlchemy engine with environment-appropriate pooling
# ---------------------------------------------------------------------------
try:
    if raw_db_url:
        # Normalize postgres:// to postgresql+psycopg2:// or postgresql://
        if raw_db_url.startswith("postgres://"):
            DATABASE_URL = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif raw_db_url.startswith("postgresql://") and "+psycopg2" not in raw_db_url:
            DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        else:
            DATABASE_URL = raw_db_url

        if "sqlite" in DATABASE_URL:
            engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
            )
            logger.info("SQLite engine created successfully")
        else:
            # PostgreSQL engine (Supabase / Neon / AWS RDS / Vercel Postgres)
            # In serverless environments, NullPool prevents stale connections and pool exhaustion
            connect_args = {
                "connect_timeout": 5,
            }
            if is_vercel:
                engine = create_engine(
                    DATABASE_URL,
                    poolclass=NullPool,
                    pool_pre_ping=True,
                    connect_args=connect_args,
                )
                logger.info("PostgreSQL engine created with NullPool (optimized for serverless cold-starts)")
            else:
                engine = create_engine(
                    DATABASE_URL,
                    pool_pre_ping=True,
                    pool_recycle=300,
                    pool_size=5,
                    max_overflow=10,
                    connect_args=connect_args,
                )
                logger.info("PostgreSQL engine created with QueuePool (pool_pre_ping=True, pool_recycle=300)")
    else:
        if is_production or is_vercel:
            # Serverless fallback when DATABASE_URL is not yet supplied in Vercel environment
            tmp_db_path = os.path.join(tempfile.gettempdir(), "interview.db")
            DATABASE_URL = f"sqlite:///{tmp_db_path}"
            engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
            )
            logger.warning("Running in serverless without DATABASE_URL; fallback ephemeral SQLite active")
        else:
            # Local development SQLite
            DATABASE_URL = "sqlite:///./interview.db"
            engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
            )
            logger.info("Local SQLite engine created with check_same_thread=False")
except Exception as engine_err:
    logger.exception("Unexpected error during database engine creation; falling back to in-memory SQLite")
    DATABASE_URL = "sqlite://"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

configure_sqlite_foreign_keys(engine)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


# ---------------------------------------------------------------------------
# Helper: Atomic and isolated DDL execution
# ---------------------------------------------------------------------------
def _safe_execute_ddl(ddl_sql: str) -> bool:
    """
    Executes one required legacy DDL statement transactionally where supported.
    Failures propagate so startup stays incomplete and can be retried safely.
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(ddl_sql))
        return True
    except Exception as ddl_err:
        logger.error("Required startup DDL failed (%s)", type(ddl_err).__name__)
        raise RuntimeError("Required database initialization DDL failed") from ddl_err


# ---------------------------------------------------------------------------
# Stage 3: Database initialization — schema creation and idempotent migration
# ---------------------------------------------------------------------------
_migration_completed = False


def init_db():
    """
    Initializes database schema and runs idempotent migrations.
    Designed for serverless cold start safety:
    - Only the explicit legacy startup table allowlist is created implicitly
    - Each migration step is executed in an isolated transaction
    - No SQLite-specific SQL executes against PostgreSQL
    - Any failed required operation is surfaced and initialization remains retryable
    """
    global _migration_completed
    if _migration_completed:
        logger.info("Database schema already initialized in this worker process — skipping")
        return

    logger.info("Initializing database schema")

    # Step 3a: Create only established legacy tables. Subscription tables are
    # intentionally excluded and can be created only by scripts.migrate.
    try:
        logger.info("Creating allowlisted legacy tables")
        _create_legacy_tables(engine)
        logger.info("Allowlisted legacy table creation completed successfully")
    except Exception as create_err:
        logger.error("Legacy table initialization failed (%s)", type(create_err).__name__)
        raise RuntimeError("Legacy database schema initialization failed") from create_err

    # Step 3b: Dialect-agnostic schema migration
    dialect = engine.dialect.name
    logger.info(f"Executing dialect-agnostic schema migrations for dialect: {dialect}")

    _run_migration_interview_history(dialect)
    _run_migration_skill_analytics_indexes(dialect)
    _run_migration_mistakes_indexes(dialect)
    _run_migration_user_accounts(dialect)
    _run_migration_resume_scans(dialect)

    # Step 3c: Bootstrap accounts
    logger.info("Bootstrapping administrative and candidate accounts")
    _run_account_bootstrap()

    _migration_completed = True
    logger.info("Database schema initialization completed successfully")


def _run_migration_interview_history(dialect: str):
    """Migration: interview_history table columns and indexes."""
    try:
        if dialect == "sqlite":
            with engine.connect() as conn:
                insp = inspect(conn)
                existing_tables = set(insp.get_table_names())
                if "interview_history" not in existing_tables:
                    return
                ih_cols = {col["name"] for col in insp.get_columns("interview_history")}

            if "created_at" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN created_at DATETIME")
            if "user_id" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN user_id INTEGER")
            if "adaptive_session_id" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN adaptive_session_id VARCHAR")
            if "question_engine_version" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN question_engine_version VARCHAR DEFAULT 'qengine-v1.0.0'")
            if "interview_type" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN interview_type VARCHAR")
            if "company" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN company VARCHAR")
            if "requested_question_count" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN requested_question_count INTEGER")

            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_interview_history_user ON interview_history(user_id)")
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_interview_history_asess ON interview_history(adaptive_session_id)")
        else:
            # PostgreSQL: native idempotent ADD COLUMN IF NOT EXISTS & CREATE INDEX IF NOT EXISTS
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "created_at" TIMESTAMP')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "user_id" INTEGER')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "adaptive_session_id" VARCHAR')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "question_engine_version" VARCHAR DEFAULT \'qengine-v1.0.0\'')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "interview_type" VARCHAR')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "company" VARCHAR')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "requested_question_count" INTEGER')
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_interview_history_user ON interview_history(user_id)')
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_interview_history_asess ON interview_history(adaptive_session_id)')
    except Exception as e:
        logger.error("interview_history startup migration failed (%s)", type(e).__name__)
        raise


def _run_migration_skill_analytics_indexes(dialect: str):
    """Migration: candidate_skill_analytics indexes."""
    try:
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_user ON candidate_skill_analytics(user_id)")
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_status ON candidate_skill_analytics(user_id, weakness_status)")
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_prof ON candidate_skill_analytics(user_id, score)")
    except Exception as e:
        logger.error("candidate_skill_analytics index migration failed (%s)", type(e).__name__)
        raise


def _run_migration_mistakes_indexes(dialect: str):
    """Migration: candidate_mistakes_ledger indexes."""
    try:
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_mistakes_user_status ON candidate_mistakes_ledger(user_id, mistake_status)")
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_mistakes_asess ON candidate_mistakes_ledger(adaptive_session_id)")
    except Exception as e:
        logger.error("candidate_mistakes_ledger index migration failed (%s)", type(e).__name__)
        raise


def _run_migration_user_accounts(dialect: str):
    """Migration: user_accounts table columns."""
    try:
        if dialect == "sqlite":
            with engine.connect() as conn:
                insp = inspect(conn)
                existing_tables = set(insp.get_table_names())
                if "user_accounts" not in existing_tables:
                    return
                ua_cols = {col["name"] for col in insp.get_columns("user_accounts")}

            if "full_name" not in ua_cols:
                _safe_execute_ddl("ALTER TABLE user_accounts ADD COLUMN full_name VARCHAR")
        else:
            _safe_execute_ddl('ALTER TABLE "user_accounts" ADD COLUMN IF NOT EXISTS "full_name" VARCHAR')
    except Exception as e:
        logger.error("user_accounts startup migration failed (%s)", type(e).__name__)
        raise


def _run_migration_resume_scans(dialect: str):
    """Migration: resume_scans table columns and indexes (Phase 5C)."""
    try:
        if dialect == "sqlite":
            with engine.connect() as conn:
                insp = inspect(conn)
                existing_tables = set(insp.get_table_names())
                if "resume_scans" not in existing_tables:
                    return
                rs_cols = {col["name"] for col in insp.get_columns("resume_scans")}

            columns_to_add = [
                ("scan_id", "VARCHAR"),
                ("matching_engine_version", "VARCHAR DEFAULT 'match-v1.0.0'"),
                ("overall_match_score", "FLOAT"),
                ("match_confidence", "VARCHAR DEFAULT 'MEDIUM'"),
                ("sub_scores", "TEXT"),
                ("skill_matrix", "TEXT"),
                ("strengths", "TEXT"),
                ("skill_gaps", "TEXT"),
                ("critical_gaps", "TEXT"),
                ("recommendations", "TEXT"),
                ("normalized_jd", "TEXT"),
                ("normalized_resume", "TEXT"),
                ("source_type", "VARCHAR DEFAULT 'paste'"),
                ("source_url", "VARCHAR"),
                ("fetched_at", "VARCHAR"),
                ("updated_at", "DATETIME"),
            ]

            for col_name, col_def in columns_to_add:
                if col_name not in rs_cols:
                    _safe_execute_ddl(f"ALTER TABLE resume_scans ADD COLUMN {col_name} {col_def}")

            _safe_execute_ddl("CREATE UNIQUE INDEX IF NOT EXISTS idx_resume_scans_scan_id ON resume_scans(scan_id)")
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_resume_scans_user_created ON resume_scans(user_id, created_at)")
        else:
            # PostgreSQL: native idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS
            columns_to_add = [
                ("scan_id", "VARCHAR"),
                ("matching_engine_version", "VARCHAR DEFAULT 'match-v1.0.0'"),
                ("overall_match_score", "FLOAT"),
                ("match_confidence", "VARCHAR DEFAULT 'MEDIUM'"),
                ("sub_scores", "TEXT"),
                ("skill_matrix", "TEXT"),
                ("strengths", "TEXT"),
                ("skill_gaps", "TEXT"),
                ("critical_gaps", "TEXT"),
                ("recommendations", "TEXT"),
                ("normalized_jd", "TEXT"),
                ("normalized_resume", "TEXT"),
                ("source_type", "VARCHAR DEFAULT 'paste'"),
                ("source_url", "VARCHAR"),
                ("fetched_at", "VARCHAR"),
                ("updated_at", "TIMESTAMP"),
            ]

            for col_name, col_def in columns_to_add:
                _safe_execute_ddl(f'ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "{col_name}" {col_def}')

            _safe_execute_ddl("CREATE UNIQUE INDEX IF NOT EXISTS idx_resume_scans_scan_id ON resume_scans(scan_id)")
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_resume_scans_user_created ON resume_scans(user_id, created_at)")
    except Exception as e:
        logger.error("resume_scans startup migration failed (%s)", type(e).__name__)
        raise


def _ensure_local_demo_candidate(db) -> bool:
    """Create or restore only the known demo account in local SQLite development."""
    if not is_local_development or db.get_bind().dialect.name != "sqlite":
        return False

    from app.security import hash_password, verify_password
    from app.db_models import UserAccount
    from sqlalchemy import func

    email = "candidate@example.com"
    password = "CandidatePass123!"
    candidate = db.query(UserAccount).filter(func.lower(UserAccount.email) == email).first()
    if candidate is None:
        db.add(UserAccount(
            email=email,
            full_name="Local Demo Candidate",
            password_hash=hash_password(password),
            role="candidate",
            plan_tier="free",
            is_active=True,
        ))
        db.commit()
        logger.info("Provisioned local SQLite demo candidate")
        return True

    # Restore only the known legacy demo record, never a similarly named registered user.
    is_known_demo = (
        candidate.role == "candidate"
        and candidate.full_name in {"Demo Candidate", "Local Demo Candidate"}
        and verify_password(password, candidate.password_hash)
    )
    if is_known_demo and (not candidate.is_active or candidate.plan_tier != "free"):
        candidate.is_active = True
        candidate.plan_tier = "free"
        db.commit()
        logger.info("Restored local SQLite demo candidate")
        return True

    # Preserve every existing account with a different password, name, or role.
    return False


def _run_account_bootstrap():
    """Provision or rotate the Super Admin only when explicit credentials are configured."""
    try:
        from app.security import hash_password, verify_password
        from app import db_models

        with SessionLocal() as db:
            admin_email = os.environ.get("SUPER_ADMIN_EMAIL", "").strip().lower()
            admin_password = os.environ.get("SUPER_ADMIN_PASSWORD", "").strip()

            existing_super = db.query(db_models.UserAccount).filter(db_models.UserAccount.role == "super_admin").first()

            if admin_email and admin_password:
                if not existing_super:
                    super_admin = db_models.UserAccount(
                        email=admin_email,
                        password_hash=hash_password(admin_password),
                        role="super_admin",
                        plan_tier="enterprise",
                        is_active=True,
                    )
                    db.add(super_admin)
                    db.commit()
                    logger.info("Provisioned initial Super Admin account")
                else:
                    needs_update = False
                    if existing_super.email != admin_email:
                        existing_super.email = admin_email
                        needs_update = True
                    if not verify_password(admin_password, existing_super.password_hash):
                        existing_super.password_hash = hash_password(admin_password)
                        needs_update = True

                    if needs_update:
                        db.commit()
                        logger.info("Synchronized Super Admin credentials")
            else:
                logger.warning("Super Admin bootstrap skipped: set SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD explicitly")

            _ensure_local_demo_candidate(db)

            # Seed initial production prompts if table is empty
            try:
                prompt_count = db.query(db_models.Prompt).count()
                if prompt_count == 0:
                    default_prompt = db_models.Prompt(
                        name="Technical Question Generator v1",
                        description="Core system prompt for generating role-specific technical interview questions",
                        category="Interview Questions",
                        role="General Tech",
                        difficulty="Hard",
                        system_prompt="You are an expert technical interviewer at a top tech company. Generate rigorous, practical interview questions.",
                        user_prompt="Role: {{role}}\nExperience: {{experience}}\nSkills: {{skills}}\nDifficulty: {{difficulty}}\nQuestions Count: {{number_of_questions}}\n\nGenerate high-signal interview questions with evaluation criteria.",
                        variables="role,experience,skills,difficulty,number_of_questions",
                        model="gemini-1.5-flash",
                        temperature=0.7,
                        max_tokens=1024,
                        version=1,
                        status="active",
                        is_active=True,
                    )
                    db.add(default_prompt)
                    db.commit()
                    db.refresh(default_prompt)

                    v1 = db_models.PromptVersion(
                        prompt_id=default_prompt.id,
                        version=1,
                        name=default_prompt.name,
                        description=default_prompt.description,
                        category=default_prompt.category,
                        role=default_prompt.role,
                        difficulty=default_prompt.difficulty,
                        system_prompt=default_prompt.system_prompt,
                        user_prompt=default_prompt.user_prompt,
                        variables=default_prompt.variables,
                        model=default_prompt.model,
                        temperature=default_prompt.temperature,
                        max_tokens=default_prompt.max_tokens,
                        status="active",
                        change_summary="Initial system prompt creation",
                    )
                    db.add(v1)
                    db.commit()
                    logger.info("Seeded default production prompt library")
            except Exception as seed_err:
                logger.error("Prompt bootstrap failed (%s)", type(seed_err).__name__)
                raise
    except Exception as bootstrap_err:
        logger.error("Account/bootstrap initialization failed (%s)", type(bootstrap_err).__name__)
        raise RuntimeError("Database bootstrap failed") from bootstrap_err


_db_initialized = False


def ensure_db_initialized():
    """
    Lazy initialization guard for endpoints that access the database.
    Ensures database initialization is executed once per worker process.
    """
    global _db_initialized
    if not _db_initialized:
        init_db()
        if _migration_completed:
            _db_initialized = True
            logger.info("Database initialization guard completed successfully")


def get_db():
    ensure_db_initialized()
    try:
        db = SessionLocal()
    except Exception as session_err:
        logger.warning(
            "[DB Session Fallback] Primary session creation failed (%s)",
            type(session_err).__name__,
        )
        fallback_url = f"sqlite:///{os.path.join(tempfile.gettempdir(), 'interview_fallback.db')}"
        fallback_engine = create_engine(fallback_url, connect_args={"check_same_thread": False})
        configure_sqlite_foreign_keys(fallback_engine)
        _create_legacy_tables(fallback_engine)
        FallbackSession = sessionmaker(autocommit=False, autoflush=False, bind=fallback_engine)
        db = FallbackSession()

    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
