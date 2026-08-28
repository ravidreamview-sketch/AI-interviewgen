import sys
import os
import logging
from pathlib import Path

# Add project root, api directory, /var/task, and current working dir to sys.path
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent

for candidate_path in [str(root_dir), str(current_dir), "/var/task", "/var/task/api", os.getcwd()]:
    if candidate_path and candidate_path not in sys.path:
        sys.path.insert(0, candidate_path)

logger = logging.getLogger("ravi.serverless")

try:
    from app.main import app
    logger.info("[Vercel Serverless] Successfully loaded app.main:app entrypoint.")
except Exception as e:
    logger.exception(f"[Vercel Serverless Entry Failure] Error loading app: {e}")
    try:
        from api.app.main import app
        logger.info("[Vercel Serverless] Successfully loaded api.app.main:app entrypoint fallback.")
    except Exception as fallback_err:
        import traceback
        traceback.print_exc()
        raise fallback_err

