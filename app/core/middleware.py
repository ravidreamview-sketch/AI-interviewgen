import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("ravi.core.middleware")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects enterprise security headers to protect against clickjacking,
    MIME sniffing, cross-site scripting, and insecure protocol downgrades.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        return response


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """
    Attaches a unique Request ID (X-Request-ID) to incoming requests for
    end-to-end distributed tracing across Google Cloud Logging.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        
        start_time = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        
        # Log structured request details without sensitive data (no tokens or passwords)
        logger.info(
            f"method={request.method} path={request.url.path} "
            f"status={response.status_code} duration={duration_ms}ms "
            f"request_id={request_id}"
        )
        return response

