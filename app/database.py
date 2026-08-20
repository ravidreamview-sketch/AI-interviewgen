from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

import os
import tempfile

if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DATABASE_URL = f"sqlite:///{tempfile.gettempdir()}/interview.db"
else:
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
            if columns and "created_at" not in columns:
                conn.execute(text("ALTER TABLE interview_history ADD COLUMN created_at DATETIME"))
                conn.commit()
        except Exception as e:
            print(f"[DB] Migration check notice: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()