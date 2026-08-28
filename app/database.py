import os
import tempfile
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger("ravi.database")

raw_db_url = os.environ.get("DATABASE_URL")
is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
is_production = os.environ.get("ENV") == "production" or is_vercel

if raw_db_url:
    # Normalize postgres:// to postgresql:// for SQLAlchemy 2.0+ compatibility
    if raw_db_url.startswith("postgres://"):
        DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
    else:
        DATABASE_URL = raw_db_url
    
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        # PostgreSQL / Supabase with serverless connection pooling & recycling
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=10
        )
        logger.info("[DB Engine] Initialized production PostgreSQL engine with serverless pre-ping & recycle.")
else:
    if is_production or is_vercel:
        # Serverless fallback when DATABASE_URL is not yet supplied in Vercel environment
        tmp_db_path = os.path.join(tempfile.gettempdir(), "interview.db")
        DATABASE_URL = f"sqlite:///{tmp_db_path}"
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
        logger.warning("[DB Engine] Running in serverless without DATABASE_URL. Ephemeral SQLite (/tmp/interview.db) active. Configure PostgreSQL DATABASE_URL in Vercel for persistence.")
    else:
        # Local development SQLite
        DATABASE_URL = "sqlite:///./interview.db"
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False}
        )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def init_db():
    from app import db_models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Dialect-agnostic schema migration for SQLite and PostgreSQL
    dialect = engine.dialect.name
    try:
        with engine.connect() as conn:
            insp = inspect(conn)
            existing_tables = set(insp.get_table_names())

            # 1. interview_history migrations
            if "interview_history" in existing_tables:
                ih_cols = {col["name"] for col in insp.get_columns("interview_history")}
                if "created_at" not in ih_cols:
                    col_type = "DATETIME" if dialect == "sqlite" else "TIMESTAMP"
                    conn.execute(text(f"ALTER TABLE interview_history ADD COLUMN created_at {col_type}"))
                if "user_id" not in ih_cols:
                    conn.execute(text("ALTER TABLE interview_history ADD COLUMN user_id INTEGER"))
                if "adaptive_session_id" not in ih_cols:
                    conn.execute(text("ALTER TABLE interview_history ADD COLUMN adaptive_session_id VARCHAR"))
                if "question_engine_version" not in ih_cols:
                    conn.execute(text("ALTER TABLE interview_history ADD COLUMN question_engine_version VARCHAR DEFAULT 'qengine-v1.0.0'"))
                conn.commit()

                # Indexes
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_interview_history_user ON interview_history(user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_interview_history_asess ON interview_history(adaptive_session_id)"))
                conn.commit()

            # 2. candidate_skill_analytics & mistakes indexes
            if "candidate_skill_analytics" in existing_tables:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_skill_analytics_user ON candidate_skill_analytics(user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_skill_analytics_status ON candidate_skill_analytics(user_id, weakness_status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_skill_analytics_prof ON candidate_skill_analytics(user_id, score)"))
                conn.commit()

            if "candidate_mistakes_ledger" in existing_tables:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mistakes_user_status ON candidate_mistakes_ledger(user_id, mistake_status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mistakes_asess ON candidate_mistakes_ledger(adaptive_session_id)"))
                conn.commit()

            # 3. user_accounts migrations
            if "user_accounts" in existing_tables:
                ua_cols = {col["name"] for col in insp.get_columns("user_accounts")}
                if "full_name" not in ua_cols:
                    conn.execute(text("ALTER TABLE user_accounts ADD COLUMN full_name VARCHAR"))
                    conn.commit()

            # 4. resume_scans migrations (Phase 5C)
            if "resume_scans" in existing_tables:
                rs_cols = {col["name"] for col in insp.get_columns("resume_scans")}
                dt_type = "DATETIME" if dialect == "sqlite" else "TIMESTAMP"
                text_type = "TEXT"
                
                columns_to_add = [
                    ("scan_id", "VARCHAR"),
                    ("matching_engine_version", "VARCHAR DEFAULT 'match-v1.0.0'"),
                    ("overall_match_score", "FLOAT"),
                    ("match_confidence", "VARCHAR DEFAULT 'MEDIUM'"),
                    ("sub_scores", text_type),
                    ("skill_matrix", text_type),
                    ("strengths", text_type),
                    ("skill_gaps", text_type),
                    ("critical_gaps", text_type),
                    ("recommendations", text_type),
                    ("normalized_jd", text_type),
                    ("normalized_resume", text_type),
                    ("source_type", "VARCHAR DEFAULT 'paste'"),
                    ("source_url", "VARCHAR"),
                    ("fetched_at", "VARCHAR"),
                    ("updated_at", dt_type),
                ]
                for col_name, col_def in columns_to_add:
                    if col_name not in rs_cols:
                        conn.execute(text(f"ALTER TABLE resume_scans ADD COLUMN {col_name} {col_def}"))
                conn.commit()

                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_resume_scans_scan_id ON resume_scans(scan_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_resume_scans_user_created ON resume_scans(user_id, created_at)"))
                conn.commit()
    except Exception as e:
        logger.warning(f"[DB Migration Notice] Schema check: {e}")

    # Provision or rotate Super Admin and candidate accounts strictly from environment variables
    try:
        from app.security import hash_password, verify_password
        with SessionLocal() as db:
            admin_email = os.environ.get("SUPER_ADMIN_EMAIL") or "admin@example.com"
            admin_password = os.environ.get("SUPER_ADMIN_PASSWORD") or "SuperAdminPass123!"
            clean_email = admin_email.strip().lower()
            clean_password = admin_password.strip()

            existing_super = db.query(db_models.UserAccount).filter(db_models.UserAccount.role == "super_admin").first()

            if admin_email and admin_password and admin_password.strip():
                clean_email = admin_email.strip().lower()
                clean_password = admin_password.strip()

                if not existing_super:
                    super_admin = db_models.UserAccount(
                        email=clean_email,
                        password_hash=hash_password(clean_password),
                        role="super_admin",
                        plan_tier="enterprise",
                        is_active=True
                    )
                    db.add(super_admin)
                    db.commit()
                    print(f"[DB Bootstrap] Provisioned initial Super Admin from environment variables.")
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
                        print(f"[DB Bootstrap] Synchronized Super Admin credentials from environment variables.")

            # Provision default candidate account candidate@example.com if not present
            existing_candidate = db.query(db_models.UserAccount).filter(db_models.UserAccount.email == "candidate@example.com").first()
            if not existing_candidate:
                cand_user = db_models.UserAccount(
                    email="candidate@example.com",
                    full_name="Demo Candidate",
                    password_hash=hash_password("CandidatePass123!"),
                    role="candidate",
                    plan_tier="pro",
                    is_active=True
                )
                db.add(cand_user)
                db.commit()
                print("[DB Bootstrap] Provisioned default Candidate account (candidate@example.com / CandidatePass123!).")
            else:
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
                        is_active=True
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
                        change_summary="Initial system prompt creation"
                    )
                    db.add(v1)
                    db.commit()
                    print("[DB Bootstrap] Seeded default production prompt library.")
            except Exception as seed_err:
                print(f"[DB Bootstrap] Prompt seeding notice: {seed_err}")
    except Exception as bootstrap_err:
        print(f"[DB Bootstrap] Account bootstrapping notice: {bootstrap_err}")


_db_initialized = False


def ensure_db_initialized():
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
        except Exception as e:
            print(f"[DB Ensure Notice] {e}")


def get_db():
    ensure_db_initialized()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
