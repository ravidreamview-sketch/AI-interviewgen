from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.learners import router as learners_router
from app.api.v1.paths import router as paths_router
from app.api.v1.tutor import router as tutor_router
from app.api.v1.scenarios import router as scenarios_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.competency import router as competency_router
from app.api.v1.orchestration import router as orchestration_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.admin import router as admin_router

api_v1_router = APIRouter()

# Register modular sub-routers with clear prefixes and tags
api_v1_router.include_router(health_router, prefix="", tags=["System Health"])
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_v1_router.include_router(learners_router, prefix="/learners", tags=["Learner Profiling (Agent 1 Foundation)"])
api_v1_router.include_router(paths_router, prefix="/paths", tags=["Adaptive Learning Paths (Agent 2 Foundation)"])
api_v1_router.include_router(tutor_router, prefix="/tutor", tags=["AI Tutor (Agent 3 Foundation)"])
api_v1_router.include_router(scenarios_router, prefix="/scenarios", tags=["Real-World Scenarios (Agent 4 Foundation)"])
api_v1_router.include_router(interviews_router, prefix="/interviews", tags=["AI Interview & Project Mentor (Agent 5 Foundation)"])
api_v1_router.include_router(competency_router, prefix="/competency", tags=["Evaluation & Competency Intelligence (Agent 6 Foundation)"])
api_v1_router.include_router(orchestration_router, prefix="/orchestrator", tags=["Agent Orchestration & Monitoring (Phase 7)"])
api_v1_router.include_router(resumes_router, prefix="/resumes", tags=["Resumes & ATS Matching"])
api_v1_router.include_router(admin_router, prefix="/admin", tags=["Administration"])

