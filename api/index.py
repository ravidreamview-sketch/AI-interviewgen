import sys
import os
import json
import logging
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Vercel Serverless Entry Point
# Exposes FastAPI ASGI app for Vercel's Python runtime.
# Crash-proof fallback: delegates to FastAPI app or returns diagnostic JSON.
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
    handler = app
    print("✓ [Vercel Serverless] Successfully imported FastAPI app from app.main", file=sys.stderr, flush=True)
except Exception as e1:
    tb1 = traceback.format_exc()
    print(f"❌ [Vercel Serverless] Primary import failed for app.main:\n{tb1}", file=sys.stderr, flush=True)
    try:
        from api.app.main import app
        handler = app
        print("✓ [Vercel Serverless] Successfully imported FastAPI app from api.app.main fallback", file=sys.stderr, flush=True)
    except Exception as e2:
        tb2 = traceback.format_exc()
        print(f"❌ [Vercel Serverless] Fallback import failed for api.app.main:\n{tb2}", file=sys.stderr, flush=True)
        _import_error = tb2

        async def fallback_app(scope, receive, send):
            if scope["type"] == "lifespan":
                while True:
                    msg = await receive()
                    if msg["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif msg["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return

            if scope["type"] == "http":
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

        app = fallback_app
        handler = fallback_app
