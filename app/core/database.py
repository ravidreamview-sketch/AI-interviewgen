import logging
from typing import Generator
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal, Base, get_db, ensure_db_initialized

logger = logging.getLogger("ravi.core.database")


def check_db_connection() -> bool:
    """
    Verifies that the database connection is healthy and responsive.
    Executes a lightweight ping (SELECT 1).
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as err:
        logger.error(f"Database health check failed: {err}")
        return False
