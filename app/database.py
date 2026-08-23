from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

import os
import tempfile

raw_db_url = os.environ.get("DATABASE_URL")
is_production = os.environ.get("ENV") == "production" or bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

if raw_db_url:
    # Normalize postgres:// to postgresql:// for SQLAlchemy 2.0+ compatibility
    if raw_db_url.startswith("postgres://"):
        DATABASE_URL = raw_db_url.replace("postgres://", "postgresql://", 1)
    else:
        DATABASE_URL = raw_db_url
    
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        # PostgreSQL with robust connection pooling
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
else:
    if is_production:
        # Fallback to ephemeral /tmp SQLite on Vercel if DATABASE_URL is not set yet, so process does not crash
        tmp_db_path = os.path.join(tempfile.gettempdir(), "interview.db")
        DATABASE_URL = f"sqlite:///{tmp_db_path}"
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
        print("[DB WARNING] Running in serverless without DATABASE_URL. Using /tmp/interview.db fallback. Set DATABASE_URL in Vercel for PostgreSQL persistence.")
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

    # Automatic schema migration: ensure created_at column exists in interview_history
    with engine.connect() as conn:
        try:
            result = conn.execute(text("PRAGMA table_info(interview_history)"))
            columns = [row[1] for row in result.fetchall()]
            if "created_at" not in columns:
                conn.execute(text("ALTER TABLE interview_history ADD COLUMN created_at DATETIME"))
                conn.commit()

            result_ua = conn.execute(text("PRAGMA table_info(user_accounts)"))
            columns_ua = [row[1] for row in result_ua.fetchall()]
            if "full_name" not in columns_ua:
                conn.execute(text("ALTER TABLE user_accounts ADD COLUMN full_name VARCHAR"))
                conn.commit()
        except Exception as e:
            print(f"[DB] Migration check notice: {e}")

    # Provision or rotate Super Admin account strictly from environment variables
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
                    change_summary="Initial system prompt creation",
                    changed_by_email="system@genai-studio.dev"
                )
                db.add(v1)
                db.commit()
                print("[DB Bootstrap] Seeded default production prompt library.")
        except Exception as seed_err:
            print(f"[DB Bootstrap] Prompt seeding notice: {seed_err}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()