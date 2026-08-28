import sys
import os
import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Vercel Serverless Entry Point
# Exposes the FastAPI ASGI app for Vercel's Python runtime.
# IMPORTANT: This module is import-safe — no database queries,
# no network calls, no unhandled exceptions during module load.
# ---------------------------------------------------------------------------

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ravi.serverless")

logger.info("Starting application initialization")

# Add project root, api directory, /var/task, and current working dir to sys.path
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent

for candidate_path in [str(root_dir), str(current_dir), "/var/task", "/var/task/api", os.getcwd()]:
    if candidate_path and candidate_path not in sys.path:
        sys.path.insert(0, candidate_path)

logger.info("Configured sys.path for serverless runtime. Importing FastAPI app...")

try:
    from app.main import app
    logger.info("Successfully imported FastAPI app from app.main")
except Exception as e:
    logger.exception(f"Primary import failed for app.main: {e}")
    try:
        from api.app.main import app
        logger.info("Successfully imported FastAPI app from api.app.main fallback")
    except Exception as fallback_err:
        logger.exception(f"Fallback import failed for api.app.main: {fallback_err}")
        raise fallback_err
