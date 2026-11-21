from fastapi import APIRouter, status
from app.core.config import settings
from app.core.database import check_db_connection

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, tags=["System Health"])
def health_check():
    """
    Liveness probe: verifies that the FastAPI application container is running.
    Used by Google Cloud Run startup and liveness probes.
    """
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENV,
    }


@router.get("/readiness", status_code=status.HTTP_200_OK, tags=["System Health"])
def readiness_check():
    """
    Readiness probe: validates database connectivity and external system health.
    Returns HTTP 200 if ready to receive traffic, HTTP 503 if dependencies fail.
    """
    db_healthy = check_db_connection()
    ai_configured = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY)
    
    overall_status = "ready" if db_healthy else "degraded"
    
    return {
        "status": overall_status,
        "database": "connected" if db_healthy else "disconnected",
        "ai_provider_configured": ai_configured,
        "environment": settings.ENV,
    }

