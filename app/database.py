import os
import tempfile
import logging
import threading
from contextlib import contextmanager
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import timezone
import urllib.parse
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Helper: Validate that a DATABASE_URL is a proper PostgreSQL DSN for production.
# ---------------------------------------------------------------------------
def _is_valid_postgres_url(url: str) -> bool:
    """Return True if *url* looks like a PostgreSQL connection string.
    The function performs a lightweight validation without contacting the DB.
    It accepts schemes ``postgresql`` or ``postgresql+psycopg2`` and requires
    a hostname and a non‑empty path (the database name).
    """
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        if not parsed.scheme.startswith("postgresql"):
            return False
        if not parsed.hostname:
            return False
        # ``path`` includes leading '/', ensure there is a name after it
        if not parsed.path or parsed.path == "/":
            return False
        return True
    except Exception:
        return False

logger = logging.getLogger("ravi.database")

# ---------------------------------------------------------------------------
# Stage 1: Resolve database configuration and detect runtime environment
# ---------------------------------------------------------------------------
raw_db_url = os.environ.get("DATABASE_URL")
if raw_db_url:
    raw_db_url = raw_db_url.strip().strip("'").strip('"')

is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
is_production = os.environ.get("ENV") == "production" or is_vercel

def _is_production_mode() -> bool:
    """Dynamically determines if running in production or serverless deployment."""
    return (os.environ.get("ENV") == "production") or bool(os.environ.get("VERCEL")) or bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

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
            # Strip unsupported query parameters (e.g., channel_binding) that psycopg2 may reject
            from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
            parsed = urlparse(DATABASE_URL)
            allowed = [(k, v) for k, v in parse_qsl(parsed.query) if k != "channel_binding"]
            if len(allowed) != len(parse_qsl(parsed.query)):
                logger.info("Removed unsupported 'channel_binding' param from DATABASE_URL for compatibility")
            cleaned_query = urlencode(allowed)
            DATABASE_URL = urlunparse(parsed._replace(query=cleaned_query))

        # Production guards: disallow SQLite and validate PostgreSQL URL
        if is_production or is_vercel:
            if "sqlite" in DATABASE_URL:
                raise RuntimeError("Production deployment requires a PostgreSQL DATABASE_URL; SQLite URL detected.")
            if not _is_valid_postgres_url(DATABASE_URL):
                raise RuntimeError("Production deployment requires a valid PostgreSQL DATABASE_URL; provided value is malformed.")

        # Engine creation
        if "sqlite" in DATABASE_URL:
            engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
            )
            logger.info("SQLite engine created successfully")
        else:
            # PostgreSQL engine (Supabase / Neon / AWS RDS / Vercel Postgres)
            # In serverless environments, NullPool prevents stale connections and pool exhaustion
            connect_args = {"connect_timeout": 5}
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
        # No DATABASE_URL supplied; enforce production guard
        if is_production or is_vercel:
            raise RuntimeError(
                "Production deployment requires a valid PostgreSQL DATABASE_URL. No DATABASE_URL was provided."
            )
        # Local development fallback (SQLite)
        DATABASE_URL = "sqlite:///./interview.db"
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
        )
        logger.info("Local SQLite engine created with check_same_thread=False")
except Exception as engine_err:
    logger.exception("Unexpected error during database engine creation; handling according to environment")
    # In production or Vercel, re‑raise to avoid silent fallback to SQLite
    if is_production or is_vercel:
        raise
    # Development fallback: use in‑memory SQLite
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
# PostgreSQL Advisory Lock and Concurrency Control
# ---------------------------------------------------------------------------
PG_ADVISORY_LOCK_ID = 1492026841
_init_thread_lock = threading.RLock()


def _table_exists(table_name: str, conn=None) -> bool:
    """Checks whether a table exists in the current database."""
    try:
        if conn is not None and not getattr(conn, "closed", False):
            insp = inspect(conn)
        else:
            insp = inspect(engine)
        return table_name in insp.get_table_names()
    except Exception as e:
        logger.warning(f"[DB Inspect] Error checking if table '{table_name}' exists: {e}")
        return False


def _safe_execute_ddl(ddl_sql: str, conn=None) -> bool:
    """
    Executes a single DDL statement within its own isolated transaction or provided connection.
    If the statement fails, it catches the notice and does not crash startup.
    """
    try:
        if conn is not None:
            conn.execute(text(ddl_sql))
        else:
            with engine.begin() as isolated_conn:
                isolated_conn.execute(text(ddl_sql))
        return True
    except Exception as ddl_err:
        logger.warning(f"[DB Migration DDL Notice] DDL execution notice: {ddl_err}")
        return False


def _acquire_advisory_lock(conn, dialect: str) -> bool:
    """Acquires a session-level advisory lock on PostgreSQL to serialize migrations across serverless instances."""
    if dialect != "postgresql":
        return False
    try:
        logger.info(f"Acquiring PostgreSQL advisory lock ({PG_ADVISORY_LOCK_ID})")
        conn.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": PG_ADVISORY_LOCK_ID})
        logger.info("PostgreSQL advisory lock acquired successfully")
        return True
    except Exception as e:
        logger.warning(f"Could not acquire PostgreSQL advisory lock: {e}")
        if _is_production_mode():
            logger.error(
                f"[DB Init Error] Failed to acquire PostgreSQL advisory lock in production mode: {e}. "
                "Aborting schema initialization to prevent concurrent migration corruption."
            )
            raise RuntimeError(
                f"PostgreSQL advisory lock acquisition failed in production: {e}"
            ) from e
        return False


def _release_advisory_lock(conn, dialect: str, lock_acquired: bool):
    """Releases the session-level advisory lock on PostgreSQL."""
    if not lock_acquired or dialect != "postgresql":
        return
    try:
        logger.info(f"Releasing PostgreSQL advisory lock ({PG_ADVISORY_LOCK_ID})")
        conn.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": PG_ADVISORY_LOCK_ID})
        logger.info("PostgreSQL advisory lock released successfully")
    except Exception as e:
        logger.warning(f"Could not release PostgreSQL advisory lock: {e}")


@contextmanager
def _advisory_lock_guard(conn, dialect: str):
    """Context manager ensuring PostgreSQL advisory locks are acquired and released on the same connection."""
    is_postgres = (dialect == "postgresql")
    acquired = False
    if is_postgres:
        acquired = _acquire_advisory_lock(conn, dialect)
        if not acquired and _is_production_mode():
            raise RuntimeError("PostgreSQL advisory lock could not be acquired in production mode.")
    try:
        yield acquired
    finally:
        if is_postgres and acquired:
            _release_advisory_lock(conn, dialect, acquired)


def _cleanup_orphaned_postgres_sequences(conn):
    """
    Cleans up any orphaned sequences that exist in pg_class without their corresponding table.
    This prevents 'duplicate key value violates unique constraint pg_class_relname_nsp_index'
    during Base.metadata.create_all() or table creation.
    """
    cleanup_sql = """
    DO $$
    DECLARE
        seq_record RECORD;
    BEGIN
        FOR seq_record IN
            SELECT c.relname AS seq_name,
                   regexp_replace(c.relname, '_id_seq$', '') AS tbl_name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'S'
              AND n.nspname = current_schema()
              AND c.relname IN ('user_invitations_id_seq', 'candidate_answer_attempts_id_seq')
        LOOP
            IF NOT EXISTS (
                SELECT 1 FROM pg_class tc
                JOIN pg_namespace tn ON tn.oid = tc.relnamespace
                WHERE tc.relkind = 'r'
                  AND tn.nspname = current_schema()
                  AND tc.relname = seq_record.tbl_name
            ) THEN
                EXECUTE 'DROP SEQUENCE IF EXISTS ' || quote_ident(seq_record.seq_name) || ' CASCADE';
            END IF;
        END LOOP;
    END $$;
    """
    try:
        conn.execute(text(cleanup_sql))
    except Exception as e:
        logger.warning(f"[DB Init] Orphaned sequence cleanup notice: {e}")


# ---------------------------------------------------------------------------
# Stage 3: Database initialization — schema creation and idempotent migration
# ---------------------------------------------------------------------------
_migration_completed = False


def init_db():
    """
    Initializes database schema and runs idempotent migrations.
    Serialized across threads and processes:
    - In PostgreSQL, acquires a session-level advisory lock (PG_ADVISORY_LOCK_ID)
      so concurrent serverless cold starts never collide on DDL or sequence creation.
    - Cleans up any orphaned sequences before Base.metadata.create_all().
    - Runs dialect-specific idempotent migrations.
    - Bootstraps administrative credentials securely without exposing default demo passwords in production.
    """
    global _migration_completed
    if _migration_completed:
        logger.info("Database schema already initialized in this worker process — skipping")
        return

    with _init_thread_lock:
        if _migration_completed:
            return

        logger.info("Initializing database schema")
        dialect = engine.dialect.name
        is_postgres = (dialect == "postgresql")

        if is_postgres:
            conn_options = {"isolation_level": "AUTOCOMMIT"}
            with engine.connect().execution_options(**conn_options) as conn:
                with _advisory_lock_guard(conn, dialect):
                    # Step 3a: PostgreSQL orphaned sequence cleanup before create_all
                    _cleanup_orphaned_postgres_sequences(conn)

                    # Step 3b: Create all tables from ORM models if they don't exist
                    from app import db_models  # noqa: F401
                    logger.info("Running Base.metadata.create_all()")
                    Base.metadata.create_all(bind=conn)
                    logger.info("Base.metadata.create_all() completed successfully")

                    # Step 3c: Dialect-agnostic schema migration
                    logger.info(f"Executing dialect-agnostic schema migrations for dialect: {dialect}")
                    _run_migration_interview_history(dialect, conn=conn)
                    _run_migration_skill_analytics_indexes(dialect, conn=conn)
                    _run_migration_mistakes_indexes(dialect, conn=conn)
                    _run_migration_user_accounts(dialect, conn=conn)
                    _run_migration_resume_scans(dialect, conn=conn)
                    _run_migration_candidate_answer_attempts(dialect, conn=conn)
                    _run_migration_user_invitations(dialect, conn=conn)

                    # Step 3d: Bootstrap accounts
                    logger.info("Bootstrapping administrative and candidate accounts")
                    _run_account_bootstrap()
        else:
            # SQLite / other dialects: serialized by _init_thread_lock
            from app import db_models  # noqa: F401
            logger.info("Running Base.metadata.create_all()")
            Base.metadata.create_all(bind=engine)
            logger.info("Base.metadata.create_all() completed successfully")

            logger.info(f"Executing dialect-agnostic schema migrations for dialect: {dialect}")
            _run_migration_interview_history(dialect)
            _run_migration_skill_analytics_indexes(dialect)
            _run_migration_mistakes_indexes(dialect)
            _run_migration_user_accounts(dialect)
            _run_migration_resume_scans(dialect)
            _run_migration_candidate_answer_attempts(dialect)
            _run_migration_user_invitations(dialect)

            logger.info("Bootstrapping administrative and candidate accounts")
            _run_account_bootstrap()

        _migration_completed = True
        logger.info("Database schema initialization completed successfully")


def _run_migration_interview_history(dialect: str, conn=None):
    """Migration: interview_history table columns and indexes."""
    try:
        if dialect == "sqlite":
            insp = inspect(conn) if (conn is not None and not getattr(conn, "closed", False)) else inspect(engine)
            existing_tables = set(insp.get_table_names())
            if "interview_history" not in existing_tables:
                return
            ih_cols = {col["name"] for col in insp.get_columns("interview_history")}

            if "created_at" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN created_at DATETIME", conn=conn)
            if "user_id" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN user_id INTEGER", conn=conn)
            if "adaptive_session_id" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN adaptive_session_id VARCHAR", conn=conn)
            if "question_engine_version" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN question_engine_version VARCHAR DEFAULT 'qengine-v1.0.0'", conn=conn)
            if "questions_payload" not in ih_cols:
                _safe_execute_ddl("ALTER TABLE interview_history ADD COLUMN questions_payload TEXT", conn=conn)

            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_interview_history_user ON interview_history(user_id)", conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_interview_history_asess ON interview_history(adaptive_session_id)", conn=conn)
        else:
            # PostgreSQL: native idempotent ADD COLUMN IF NOT EXISTS & CREATE INDEX IF NOT EXISTS
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "created_at" TIMESTAMP', conn=conn)
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "user_id" INTEGER', conn=conn)
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "adaptive_session_id" VARCHAR', conn=conn)
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "question_engine_version" VARCHAR DEFAULT \'qengine-v1.0.0\'', conn=conn)
            _safe_execute_ddl('ALTER TABLE "interview_history" ADD COLUMN IF NOT EXISTS "questions_payload" TEXT', conn=conn)
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_interview_history_user ON interview_history(user_id)', conn=conn)
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_interview_history_asess ON interview_history(adaptive_session_id)', conn=conn)
    except Exception as e:
        logger.warning(f"[DB Migration] interview_history migration notice: {e}")


def _run_migration_skill_analytics_indexes(dialect: str, conn=None):
    """Migration: candidate_skill_analytics indexes."""
    try:
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_user ON candidate_skill_analytics(user_id)", conn=conn)
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_status ON candidate_skill_analytics(user_id, weakness_status)", conn=conn)
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_skill_analytics_prof ON candidate_skill_analytics(user_id, score)", conn=conn)
    except Exception as e:
        logger.warning(f"[DB Migration] candidate_skill_analytics index notice: {e}")


def _run_migration_mistakes_indexes(dialect: str, conn=None):
    """Migration: candidate_mistakes_ledger indexes."""
    try:
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_mistakes_user_status ON candidate_mistakes_ledger(user_id, mistake_status)", conn=conn)
        _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_mistakes_asess ON candidate_mistakes_ledger(adaptive_session_id)", conn=conn)
    except Exception as e:
        logger.warning(f"[DB Migration] candidate_mistakes_ledger index notice: {e}")


def _run_migration_user_accounts(dialect: str, conn=None):
    """Migration: user_accounts table columns."""
    try:
        if dialect == "sqlite":
            insp = inspect(conn) if (conn is not None and not getattr(conn, "closed", False)) else inspect(engine)
            existing_tables = set(insp.get_table_names())
            if "user_accounts" not in existing_tables:
                return
            ua_cols = {col["name"] for col in insp.get_columns("user_accounts")}

            if "full_name" not in ua_cols:
                _safe_execute_ddl("ALTER TABLE user_accounts ADD COLUMN full_name VARCHAR", conn=conn)
        else:
            _safe_execute_ddl('ALTER TABLE "user_accounts" ADD COLUMN IF NOT EXISTS "full_name" VARCHAR', conn=conn)
    except Exception as e:
        logger.warning(f"[DB Migration] user_accounts migration notice: {e}")


def _run_migration_resume_scans(dialect: str, conn=None):
    """Migration: resume_scans table columns and indexes (Phase 5C)."""
    try:
        columns_to_add = [
            ("scan_id", "VARCHAR"),
            ("matching_engine_version", "VARCHAR DEFAULT 'match-v1.1.0'"),
            ("evaluation_fingerprint", "VARCHAR"),
            ("resume_fingerprint", "VARCHAR"),
            ("jd_fingerprint", "VARCHAR"),
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
            ("updated_at", "DATETIME" if dialect == "sqlite" else "TIMESTAMP"),
        ]

        if dialect == "sqlite":
            insp = inspect(conn) if (conn is not None and not getattr(conn, "closed", False)) else inspect(engine)
            existing_tables = set(insp.get_table_names())
            if "resume_scans" not in existing_tables:
                return
            rs_cols = {col["name"] for col in insp.get_columns("resume_scans")}

            for col_name, col_def in columns_to_add:
                if col_name not in rs_cols:
                    _safe_execute_ddl(f"ALTER TABLE resume_scans ADD COLUMN {col_name} {col_def}", conn=conn)

            _safe_execute_ddl("CREATE UNIQUE INDEX IF NOT EXISTS idx_resume_scans_scan_id ON resume_scans(scan_id)", conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_resume_scans_user_created ON resume_scans(user_id, created_at)", conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_resume_scans_eval_fingerprint ON resume_scans(user_id, evaluation_fingerprint)", conn=conn)
        else:
            # PostgreSQL: native idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS
            for col_name, col_def in columns_to_add:
                _safe_execute_ddl(f'ALTER TABLE "resume_scans" ADD COLUMN IF NOT EXISTS "{col_name}" {col_def}', conn=conn)

            _safe_execute_ddl("CREATE UNIQUE INDEX IF NOT EXISTS idx_resume_scans_scan_id ON resume_scans(scan_id)", conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_resume_scans_user_created ON resume_scans(user_id, created_at)", conn=conn)
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_resume_scans_eval_fingerprint ON "resume_scans"("user_id", "evaluation_fingerprint")', conn=conn)
    except Exception as e:
        logger.warning(f"[DB Migration] resume_scans migration notice: {e}")


def _run_account_bootstrap():
    """Provision or rotate Super Admin and candidate accounts safely from environment variables."""
    try:
        from app.security import hash_password, verify_password
        from app import db_models

        with SessionLocal() as db:
            existing_super = db.query(db_models.UserAccount).filter(db_models.UserAccount.role == "super_admin").first()

            if _is_production_mode():
                # In production:
                # 1. Require explicit environment variables; NEVER fall back to hardcoded demo credentials.
                # 2. Never overwrite existing super admin credentials.
                # 3. Disable candidate demo provisioning entirely.
                env_email = os.environ.get("SUPER_ADMIN_EMAIL") or os.environ.get("INITIAL_ADMIN_EMAIL")
                env_password = os.environ.get("SUPER_ADMIN_PASSWORD") or os.environ.get("INITIAL_ADMIN_PASSWORD")

                if not existing_super:
                    if env_email and env_password:
                        clean_email = env_email.strip().lower()
                        clean_password = env_password.strip()
                        super_admin = db_models.UserAccount(
                            email=clean_email,
                            password_hash=hash_password(clean_password),
                            role="super_admin",
                            plan_tier="enterprise",
                            is_active=True,
                        )
                        db.add(super_admin)
                        db.commit()
                        logger.info("Provisioned initial Super Admin account from environment configuration")
                    else:
                        logger.warning("Production mode: SUPER_ADMIN_EMAIL / SUPER_ADMIN_PASSWORD not set. Skipping initial Super Admin account creation.")
                else:
                    if env_email and env_password:
                        clean_email = env_email.strip().lower()
                        clean_password = env_password.strip()
                        if existing_super.email.lower() == clean_email:
                            if not verify_password(clean_password, existing_super.password_hash):
                                existing_super.password_hash = hash_password(clean_password)
                                db.commit()
                                logger.info("Synchronized Super Admin password from environment configuration")
                    logger.info("Super Admin account verified in production.")

                logger.info("Production mode: Demo candidate account provisioning is disabled.")
            else:
                # Development & test mode:
                # Allow fallback demo credentials for seamless local testing
                admin_email = os.environ.get("SUPER_ADMIN_EMAIL") or "admin@example.com"
                admin_password = os.environ.get("SUPER_ADMIN_PASSWORD") or "SuperAdminPass123!"
                clean_email = admin_email.strip().lower()
                clean_password = admin_password.strip()

                admin_user = db.query(db_models.UserAccount).filter(db_models.UserAccount.email == clean_email).first()
                if not admin_user:
                    super_admin = db_models.UserAccount(
                        email=clean_email,
                        full_name="Super Administrator",
                        password_hash=hash_password(clean_password),
                        role="super_admin",
                        plan_tier="enterprise",
                        is_active=True,
                    )
                    db.add(super_admin)
                    db.commit()
                    logger.info("Provisioned initial Super Admin account (development fallback)")
                else:
                    admin_user.role = "super_admin"
                    admin_user.is_active = True
                    if not verify_password(clean_password, admin_user.password_hash):
                        admin_user.password_hash = hash_password(clean_password)
                        db.commit()

                # Provision default candidate account candidate@example.com if not present in dev
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
                    logger.info("Provisioned default Candidate account for development")

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
    Never marks _db_initialized = True if an initialization error occurs.
    """
    global _db_initialized
    if not _db_initialized:
        with _init_thread_lock:
            if not _db_initialized:
                try:
                    init_db()
                    _db_initialized = True
                    logger.info("Database initialization guard completed successfully")
                except Exception as e:
                    logger.error(f"[DB Ensure Error] Database initialization failed: {e}")
                    raise


def get_db():
    ensure_db_initialized()
    try:
        db = SessionLocal()
    except Exception as session_err:
        logger.warning(f"[DB Session Fallback] Failed creating session from primary engine: {session_err}")
        fallback_url = f"sqlite:///{os.path.join(tempfile.gettempdir(), 'interview_fallback.db')}"
        fallback_engine = create_engine(fallback_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=fallback_engine)
        FallbackSession = sessionmaker(autocommit=False, autoflush=False, bind=fallback_engine)
        db = FallbackSession()

    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


def _run_migration_candidate_answer_attempts(dialect: str, conn=None):
    """Migration: candidate_answer_attempts table and indexes."""
    try:
        has_table = _table_exists("candidate_answer_attempts", conn=conn)

        if dialect == "sqlite":
            if not has_table:
                _safe_execute_ddl("""
                CREATE TABLE IF NOT EXISTS candidate_answer_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
                    interview_id INTEGER NOT NULL REFERENCES interview_history(id) ON DELETE CASCADE,
                    question_index INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    candidate_answer TEXT NOT NULL,
                    evaluation_feedback TEXT NOT NULL,
                    overall_score INTEGER,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """, conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_attempt_user ON candidate_answer_attempts(user_id)", conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_attempt_interview ON candidate_answer_attempts(interview_id)", conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_attempt_user_interview ON candidate_answer_attempts(user_id, interview_id)", conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_attempt_q ON candidate_answer_attempts(interview_id, question_index)", conn=conn)
        else:
            # PostgreSQL
            if not has_table:
                _safe_execute_ddl("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relkind = 'S' AND c.relname = 'candidate_answer_attempts_id_seq'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relkind = 'r' AND c.relname = 'candidate_answer_attempts'
                    ) THEN
                        DROP SEQUENCE IF EXISTS candidate_answer_attempts_id_seq CASCADE;
                    END IF;
                END $$;
                """, conn=conn)

                _safe_execute_ddl("""
                CREATE TABLE IF NOT EXISTS "candidate_answer_attempts" (
                    "id" SERIAL PRIMARY KEY,
                    "user_id" INTEGER NOT NULL REFERENCES "user_accounts"("id") ON DELETE CASCADE,
                    "interview_id" INTEGER NOT NULL REFERENCES "interview_history"("id") ON DELETE CASCADE,
                    "question_index" INTEGER NOT NULL,
                    "question_text" TEXT NOT NULL,
                    "candidate_answer" TEXT NOT NULL,
                    "evaluation_feedback" TEXT NOT NULL,
                    "overall_score" INTEGER,
                    "created_at" TIMESTAMP DEFAULT NOW(),
                    "updated_at" TIMESTAMP DEFAULT NOW()
                )
                """, conn=conn)

            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_attempt_user ON candidate_answer_attempts(user_id)', conn=conn)
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_attempt_interview ON candidate_answer_attempts(interview_id)', conn=conn)
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_attempt_user_interview ON candidate_answer_attempts(user_id, interview_id)', conn=conn)
            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_attempt_q ON candidate_answer_attempts(interview_id, question_index)', conn=conn)
    except Exception as e:
        logger.warning(f"[DB Migration] candidate_answer_attempts migration notice: {e}")


def _run_migration_user_invitations(dialect: str, conn=None):
    """Migration: user_invitations table and indexes."""
    try:
        has_table = _table_exists("user_invitations", conn=conn)

        if dialect == "sqlite":
            if not has_table:
                _safe_execute_ddl("""
                CREATE TABLE IF NOT EXISTS user_invitations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'candidate',
                    plan_tier TEXT NOT NULL DEFAULT 'free',
                    token_hash TEXT NOT NULL UNIQUE,
                    invited_by_user_id INTEGER REFERENCES user_accounts(id) ON DELETE SET NULL,
                    invited_by_email TEXT,
                    created_at DATETIME NOT NULL,
                    expires_at DATETIME NOT NULL,
                    accepted_at DATETIME,
                    is_revoked BOOLEAN NOT NULL DEFAULT 0
                )
                """, conn=conn)
            _safe_execute_ddl("CREATE INDEX IF NOT EXISTS idx_invitation_email ON user_invitations(email)", conn=conn)
            _safe_execute_ddl("CREATE UNIQUE INDEX IF NOT EXISTS idx_invitation_token_hash ON user_invitations(token_hash)", conn=conn)
        else:
            # PostgreSQL
            if not has_table:
                _safe_execute_ddl("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relkind = 'S' AND c.relname = 'user_invitations_id_seq'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relkind = 'r' AND c.relname = 'user_invitations'
                    ) THEN
                        DROP SEQUENCE IF EXISTS user_invitations_id_seq CASCADE;
                    END IF;
                END $$;
                """, conn=conn)

                _safe_execute_ddl("""
                CREATE TABLE IF NOT EXISTS "user_invitations" (
                    "id" SERIAL PRIMARY KEY,
                    "email" VARCHAR NOT NULL,
                    "role" VARCHAR NOT NULL DEFAULT 'candidate',
                    "plan_tier" VARCHAR NOT NULL DEFAULT 'free',
                    "token_hash" VARCHAR NOT NULL UNIQUE,
                    "invited_by_user_id" INTEGER REFERENCES "user_accounts"("id") ON DELETE SET NULL,
                    "invited_by_email" VARCHAR,
                    "created_at" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    "expires_at" TIMESTAMP WITH TIME ZONE NOT NULL,
                    "accepted_at" TIMESTAMP WITH TIME ZONE,
                    "is_revoked" BOOLEAN NOT NULL DEFAULT FALSE
                )
                """, conn=conn)

            _safe_execute_ddl('CREATE INDEX IF NOT EXISTS idx_invitation_email ON "user_invitations"(email)', conn=conn)
            _safe_execute_ddl('CREATE UNIQUE INDEX IF NOT EXISTS idx_invitation_token_hash ON "user_invitations"(token_hash)', conn=conn)
    except Exception as e:
        logger.warning(f"[DB Migration] user_invitations migration notice: {e}")
