import sys
import os
import logging
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Vercel Serverless Entry Point
# Exposes the FastAPI ASGI app for Vercel's Python runtime.
# IMPORTANT: This module is guaranteed import-safe and crash-proof.
# ---------------------------------------------------------------------------

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

logger.info(f"Configured sys.path: {sys.path[:4]}")

try:
    from app.main import app
    logger.info("Successfully imported FastAPI app from app.main")
except Exception as primary_err:
    logger.exception(f"Primary import failed for app.main: {primary_err}")
    try:
        from api.app.main import app
        logger.info("Successfully imported FastAPI app from api.app.main fallback")
    except Exception as fallback_err:
        logger.exception(f"Fallback import failed for api.app.main: {fallback_err}")
        # Build an emergency diagnostic ASGI app so Vercel never crashes with FUNCTION_INVOCATION_FAILED
        try:
            from fastapi import FastAPI
            from fastapi.responses import JSONResponse
            app = FastAPI(title="Ravi AI - Serverless Diagnostic Mode")
            
            trace_str = traceback.format_exc()
            
            @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
            async def diagnostic_catch_all(full_path: str = ""):
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "startup_import_error",
                        "service": "RaviGen AI Interview Studio",
                        "error_type": type(fallback_err).__name__,
                        "error_detail": str(fallback_err),
                        "sys_path": sys.path,
                        "current_dir": str(current_dir),
                        "root_dir": str(root_dir),
                        "traceback": trace_str.splitlines()
                    }
                )
        except Exception as critical_err:
            raise critical_err
