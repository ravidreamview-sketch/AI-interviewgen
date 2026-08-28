import os
import tempfile
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger("ravi.database")

# ---------------------------------------------------------------------------
# Stage 1: Resolve database configuration and detect runtime environment
# ---------------------------------------------------------------------------
logger.info("Starting database module initialization")
logger.info("Resolving database configuration")

raw_db_url = os.environ.get("DATABASE_URL")
if raw_db_url:
    raw_db_url = raw_db_url.strip().strip("'").strip('"')

is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
is_production = os.environ.get("ENV") == "production" or is_vercel

# ---------------------------------------------------------------------------
# Stage 2: Create SQLAlchemy engine with environment-appropriate pooling
# ---------------------------------------------------------------------------
logger.info("Creating database engine")

try:
    if raw_db_url:
        # Normalize postgres:// to postgresql:// for SQLAlchemy 2.0+ compatibility
        if raw_db_url.startswith("postgres://"):
            DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
        else:
            DATABASE_URL = raw_db_url

        if DATABASE_URL.startswith("sqlite"):
            engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
            )
            logger.info("SQLite engine created with check_same_thread=False")
        else:
            # PostgreSQL engine (Supabase / Neon / AWS RDS / Vercel Postgres)
            # Configured appropriately for serverless with pool pre-ping and recycle
            engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=5,
                max_overflow=10,
            )
            logger.info("PostgreSQL engine created with pool_pre_ping=True and pool_recycle=300")
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
    Executes a single DDL statement within its own isolated transaction.
    If the statement fails, it rolls back automatically without corrupting
    any shared connection state or failing the entire startup.
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(ddl_sql))
        return True
    except Exception as ddl_err:
        logger.warning(f"[DB Migration DDL Notice] DDL execution notice: {ddl_err}")
        return False


# ---------------------------------------------------------------------------
# Stage 3: Database initialization — schema creation and idempotent migration
# ---------------------------------------------------------------------------
_migration_completed = False


def init_db():
    """
    Initializes database schema and runs idempotent migrations.
    Designed for serverless cold start safety:
    - Base.metadata.create_all() creates new tables safely
    - Each migration step is executed in an isolated transaction
    - No SQLite-specific SQL executes against PostgreSQL
    - Non-critical migration errors are caught and logged, never crashing import
    """
    global _migration_completed
    if _migration_completed:
        logger.info("Database schema already initialized in this worker process — skipping")
        return

    logger.info("Initializing database schema")

    # Step 3a: Create all tables from ORM models if they don't exist
    try:
        from app import db_models  # noqa: F401
        logger.info("Running Base.metadata.create_all()")
        Base.metadata.create_all(bind=engine)
        logger.info("Base.metadata.create_all() completed successfully")
    except Exception as create_err:
        logger.warning(f"[DB Init 3a] Base.metadata.create_all() notice: {create_err}")

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

            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_interview_history_user ON interview_history(user_id)")
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_interview_history_asess ON interview_history(adaptive_session_id)")
        else:
            # PostgreSQL: native idempotent ADD COLUMN IF NOT EXISTS & CREATE INDEX IF NOT EXISTS
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "created_at" TIMESTAMP')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "user_id" INTEGER')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "adaptive_session_id" VARCHAR')
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "question_engine_version" VARCHAR DEFAULT \'qengine-v1.0.0\'')
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_interview_history_user ON interview_history(user_id)')
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_interview_history_asess ON interview_history(adaptive_session_id)')
    except Exception as e:
        logger.warning(f"[DB Migration] interview_history migration notice: {e}")


def _run_migration_skill_analytics_indexes(dialect: str):
    """Migration: candidate_skill_analytics indexes."""
    try:
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_user ON candidate_skill_analytics(user_id)")
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_status ON candidate_skill_analytics(user_id, weakness_status)")
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_prof ON candidate_skill_analytics(user_id, score)")
    except Exception as e:
        logger.warning(f"[DB Migration] candidate_skill_analytics index notice: {e}")


def _run_migration_mistakes_indexes(dialect: str):
    """Migration: candidate_mistakes_ledger indexes."""
    try:
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_mistakes_user_status ON candidate_mistakes_ledger(user_id, mistake_status)")
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_mistakes_asess ON candidate_mistakes_ledger(adaptive_session_id)")
    except Exception as e:
        logger.warning(f"[DB Migration] candidate_mistakes_ledger index notice: {e}")


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
        logger.warning(f"[DB Migration] user_accounts migration notice: {e}")


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
        logger.warning(f"[DB Migration] resume_scans migration notice: {e}")


def _run_account_bootstrap():
    """Provision or rotate Super Admin and candidate accounts safely from environment variables."""
    try:
        from app.security import hash_password, verify_password
        from app import db_models

        with SessionLocal() as db:
            admin_email = os.environ.get("SUPER_ADMIN_EMAIL") or "admin@example.com"
            admin_password = os.environ.get("SUPER_ADMIN_PASSWORD") or "SuperAdminPass123!"
            clean_email = admin_email.strip().lower()
            clean_password = admin_password.strip()

            existing_super = db.query(db_models.UserAccount).filter(db_models.UserAccount.role == "super_admin").first()

            if clean_email and clean_password:
                if not existing_super:
                    super_admin = db_models.UserAccount(
                        email=clean_email,
                        password_hash=hash_password(clean_password),
                        role="super_admin",
                        plan_tier="enterprise",
                        is_active=True,
                    )
                    db.add(super_admin)
                    db.commit()
                    logger.info("Provisioned initial Super Admin account")
                else:
                    needs_update = False
                    if existing_super.email != clean_email:
                        existing_super.email = clean_email
                        needs_update = True
                    if not verify_password(clean_password, existing_super.password_hash):
                        existing_super.password_hash = hash_password(clean_password)
                        needs_update = True

                    if needs_update:
                        db.commit()
                        logger.info("Synchronized Super Admin credentials")

            # Provision default candidate account candidate@example.com if not present
            existing_candidate = db.query(db_models.UserAccount).filter(db_models.UserAccount.email == "candidate@example.com").first()
            if not existing_candidate:
                cand_user = db_models.UserAccount(
                    email="candidate@example.com",
                    full_name="Demo Candidate",
                    password_hash=hash_password("CandidatePass123!"),
                    role="candidate",
                    plan_tier="pro",
                    is_active=True,
                )
                db.add(cand_user)
                db.commit()
                logger.info("Provisioned default Candidate account")
            else:
                if not verify_password("CandidatePass123!", existing_candidate.password_hash):
                    existing_candidate.password_hash = hash_password("CandidatePass123!")
                    existing_candidate.is_active = True
                    db.commit()

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
                logger.warning(f"[DB Bootstrap] Prompt seeding notice: {seed_err}")
    except Exception as bootstrap_err:
        logger.warning(f"[DB Bootstrap] Account bootstrapping notice: {bootstrap_err}")


_db_initialized = False


def ensure_db_initialized():
    """
    Lazy initialization guard for endpoints that access the database.
    Ensures database initialization is executed once per worker process.
    """
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            logger.info("Database initialization guard completed successfully")
        except Exception as e:
            logger.warning(f"[DB Ensure Notice] {e}")
        finally:
            _db_initialized = True


def get_db():
    ensure_db_initialized()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()