import sys
import os
import json
import logging
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Vercel Serverless Entry Point
# Exposes ASGI app for Vercel's Python runtime.
# Crash-proof ASGI wrapper: delegates to FastAPI app or returns diagnostic JSON.
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ravi.serverless")

# Configure sys.path early
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent

for candidate_path in [str(root_dir), str(current_dir), "/var/task", "/var/task/api", os.getcwd()]:
    if candidate_path and candidate_path not in sys.path:
        sys.path.insert(0, candidate_path)

_real_app = None
_import_error = None

try:
    from app.main import app as _fastapi_app
    _real_app = _fastapi_app
    logger.info("Successfully imported FastAPI app from app.main")
except Exception as e1:
    logger.exception(f"Primary import failed: {e1}")
    try:
        from api.app.main import app as _fallback_app
        _real_app = _fallback_app
        logger.info("Successfully imported FastAPI app from api.app.main fallback")
    except Exception as e2:
        logger.exception(f"Fallback import failed: {e2}")
        _import_error = traceback.format_exc()


async def app(scope, receive, send):
    """
    Standard ASGI 3.0 interface callable.
    Guaranteed never to throw unhandled exceptions during invocation.
    """
    if scope["type"] == "lifespan":
        if _real_app is not None:
            try:
                return await _real_app(scope, receive, send)
            except Exception as lifespan_err:
                logger.warning(f"[Lifespan Notice] {lifespan_err}")
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] == "http":
        if _real_app is not None:
            return await _real_app(scope, receive, send)

        # Diagnostic response when import fails
        error_payload = {
            "status": "serverless_import_error",
            "service": "RaviGen AI Interview Studio",
            "message": "The application could not be loaded during serverless import.",
            "sys_path": sys.path,
            "traceback": _import_error.splitlines() if _import_error else "No traceback available"
        }
        body_bytes = json.dumps(error_payload, indent=2).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body_bytes)).encode("utf-8")),
            ]
        })
        await send({
            "type": "http.response.body",
            "body": body_bytes,
        })
