import os
import uuid
import json
import logging
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union, Set
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, desc, text
from sqlalchemy.orm import Session

logger = logging.getLogger("ravi.main")

BASE_DIR = Path(__file__).resolve().parent.parent

from app.models import (
    InterviewRequest,
    PageViewPayload,
    ClickEventPayload,
    AdaptiveProfileResponse,
    AdaptiveGenerateResponse,
    EvaluateResponseRequest,
    ResponseEvaluationResult,
    NextQuestionRequest,
    AdaptiveNextQuestionResponse,
    JobURLExtractRequest,
    JobURLExtractResponse,
    JobUploadExtractResponse,
    ResumeUploadExtractResponse,
    NormalizedJobDescription,
    NormalizedResume,
    SkillMatrixItem,
    SubScores,
    ResumeJDMatchResult,
    ResumeJDMatchRequest,
    ResumeJDMatchResponse,
    ResumeJDMatchSummaryItem,
    AdaptiveFromMatchRequest,
    AdaptiveFromMatchResponse,
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewAnswerRequest,
    InterviewAnswerResponse,
    InterviewCompleteResponse,
    AnswerEvaluationRequest,
    AnswerEvaluationResponse,
    EvaluatorPresetsResponse,
    CoachChatRequest,
)
from app.interview_engine import (
    start_interview_session,
    evaluate_and_generate_next_question,
    complete_interview_session
)
from app.evaluator_service import evaluate_candidate_answer, get_curated_presets
from app.speech_service import get_stt_provider
from app.tts_service import get_tts_provider
from app.avatar_service import get_avatar_provider
from app.prompts import interview_prompt
from app.services import (
    generate_ai_questions,
    get_ai_provider_status,
    parse_raw_questions,
    get_fallback_questions,
)
from app.coach_service import build_candidate_context, generate_coach_reply
from app.adaptive_service import (
    get_candidate_adaptive_profile,
    generate_adaptive_question_package,
    evaluate_candidate_response,
    determine_adaptive_next_question,
    generate_adaptive_from_match_service
)
from app.jd_service import (
    safe_fetch_job_url,
    extract_text_from_document,
    normalize_job_description
)
from app.matching_service import (
    calculate_resume_jd_match,
    normalize_resume
)
from app.database import get_db, init_db
from app.db_models import (
    UserAccount,
    InterviewHistory,
    PageViewEvent,
    ClickEvent,
    ResumeScan,
    MockInterview,
    CoachSession,
    CoachMessage,
)
from app.admin_routes import admin_router, candidate_router
from app.auth_deps import (
    get_current_user,
    get_current_user_optional,
    is_development_auth_bypass_enabled,
)

_ai_provider, _ai_provider_configured = get_ai_provider_status()
if _ai_provider_configured:
    logger.info("AI provider: %s; API key configured: YES", _ai_provider)
else:
    logger.warning("AI provider: %s; API key configured: NO", _ai_provider)


# Configure trusted CORS origins for local dev and production
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://ai-interviewgen.vercel.app"
]

env_origins = os.environ.get("ADMIN_ALLOWED_ORIGINS", "")
if env_origins:
    custom_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    ALLOWED_ORIGINS = list(set(DEFAULT_ALLOWED_ORIGINS + custom_origins))
else:
    ALLOWED_ORIGINS = DEFAULT_ALLOWED_ORIGINS

app = FastAPI(
    title="Ravi — AI Interview Question Generator API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/api/health")
@app.get("/health")
@app.get("/api/index.py/api/health", include_in_schema=False)
@app.get("/api/index.py/health", include_in_schema=False)
def health_check():
    """Lightweight health probe — does not touch the database."""
    return {"status": "ok", "service": "RaviGen AI Interview Studio"}


@app.get("/api/debug-status", include_in_schema=False)
@app.get("/debug-status", include_in_schema=False)
def debug_status(request: Request, db: Session = Depends(get_db)):
    db_ok = False
    db_error = None
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_error = str(e)
        
    routes = [getattr(r, 'path', str(r)) for r in app.routes if hasattr(r, 'path')]
    headers = dict(request.headers)
    scope_path = request.scope.get("path")
    
    return {
        "status": "online",
        "db_ok": db_ok,
        "db_error": db_error,
        "scope_path": scope_path,
        "x_matched_path": headers.get("x-matched-path"),
        "x_forwarded_path": headers.get("x-forwarded-path"),
        "total_routes": len(routes),
        "sample_routes": routes[:20]
    }

@app.middleware("http")
async def fix_vercel_path_middleware(request: Request, call_next):
    matched_path = request.headers.get("x-matched-path")
    forwarded_path = request.headers.get("x-forwarded-path")
    override_path = request.query_params.get("__path")

    if override_path:
        request.scope["path"] = override_path
    elif matched_path and not matched_path.startswith("/api/index.py") and not matched_path.startswith("/index.py"):
        request.scope["path"] = matched_path
    elif forwarded_path and not forwarded_path.startswith("/api/index.py") and not forwarded_path.startswith("/index.py"):
        request.scope["path"] = forwarded_path
    else:
        path = request.scope.get("path", "")
        if path.startswith("/api/index.py"):
            clean = path[len("/api/index.py"):]
            request.scope["path"] = clean if clean else "/"
        elif path.startswith("/index.py"):
            clean = path[len("/index.py"):]
            request.scope["path"] = clean if clean else "/"

    return await call_next(request)

@app.exception_handler(Exception)
async def global_production_exception_handler(request: Request, exc: Exception):
    exc_type = exc.__class__.__name__
    exc_msg = str(exc)
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    
    logger.error(
        f"[Production Unhandled Exception] method={request.method} path={request.url.path} "
        f"class={exc_type} message={exc_msg}\nTraceback:\n{tb_str}"
    )
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Mount Super Admin & Candidate API routers with dual prefix support for Vercel serverless compatibility
app.include_router(admin_router, prefix="/api/admin")
app.include_router(admin_router, prefix="/admin/api")

app.include_router(candidate_router, prefix="/api")
app.include_router(candidate_router, prefix="")

from fastapi import Response
from app.admin_routes import candidate_login, admin_login
from app.models import CandidateLoginRequest, AdminLoginRequest

@app.post("/candidate/login/action", include_in_schema=False)
@app.post("/api/candidate/login", include_in_schema=False)
@app.post("/candidate/login", include_in_schema=False)
@app.post("/api/login", include_in_schema=False)
@app.post("/login", include_in_schema=False)
@app.post("/api/index.py/candidate/login", include_in_schema=False)
@app.post("/api/index.py/login", include_in_schema=False)
def direct_candidate_login(
    payload: CandidateLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    return candidate_login(payload, request, response, db)

@app.post("/api/admin/login", include_in_schema=False)
@app.post("/admin/login", include_in_schema=False)
@app.post("/admin/api/login", include_in_schema=False)
def direct_admin_login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    return admin_login(payload, request, response, db)

from app.admin_routes import candidate_logout, get_public_menus, is_candidate_menu_enabled, update_menu
from app.auth_deps import get_current_user
from app.db_models import UserAccount

@app.post("/api/candidate/logout", include_in_schema=False)
@app.post("/candidate/logout", include_in_schema=False)
@app.post("/logout", include_in_schema=False)
@app.post("/api/logout", include_in_schema=False)
def direct_candidate_logout(
    request: Request,
    response: Response
):
    return candidate_logout(request, response)

@app.get("/api/public/menus", include_in_schema=False)
@app.get("/public/menus", include_in_schema=False)
@app.get("/api/public-menus", include_in_schema=False)
@app.get("/public-menus", include_in_schema=False)
def direct_get_public_menus(db: Session = Depends(get_db)):
    return get_public_menus(db)

@app.patch("/api/admin/menus/{menu_id}", include_in_schema=False)
@app.patch("/admin/api/menus/{menu_id}", include_in_schema=False)
@app.patch("/api/menus/{menu_id}", include_in_schema=False)
@app.post("/api/admin/menus/{menu_id}", include_in_schema=False)
@app.post("/admin/api/menus/{menu_id}", include_in_schema=False)
@app.put("/api/admin/menus/{menu_id}", include_in_schema=False)
@app.put("/admin/api/menus/{menu_id}", include_in_schema=False)
def direct_update_menu(
    menu_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user)
):
    return update_menu(menu_id, payload, request, db, current_user)

def check_menu_access_or_block(menu_key: str, db: Session):
    try:
        if not is_candidate_menu_enabled(menu_key, db):
            content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Feature Disabled — Ravi GenAI Studio</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0F172A; color: #F8FAFC; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; text-align: center; }}
    .box {{ background: #1E293B; border: 1px solid #334155; border-radius: 16px; padding: 40px 30px; max-width: 480px; width: 100%; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }}
    h1 {{ font-size: 24px; color: #EF4444; margin-bottom: 12px; font-weight: 700; }}
    p {{ color: #94A3B8; font-size: 15px; line-height: 1.6; margin-bottom: 24px; }}
    a {{ display: inline-block; background: #4F46E5; color: #FFFFFF; padding: 12px 24px; border-radius: 8px; font-weight: 600; text-decoration: none; transition: background 0.2s; }}
    a:hover {{ background: #4338CA; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>🚫 Feature Temporarily Disabled</h1>
    <p>The <strong>{menu_key}</strong> module is currently disabled by the Super Admin in Menu Management.</p>
    <a href="/">Return to Home</a>
  </div>
</body>
</html>"""
            res = HTMLResponse(content=content, status_code=403)
            res.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return res
    except Exception as e:
        print(f"[Menu Check Warning] {e}")
    return None


def format_interview_response(interview: InterviewHistory) -> dict:
    skills_list = [s.strip() for s in (interview.skills or "").split(",") if s.strip()]
    parsed_qs = parse_raw_questions(interview.questions or "")

    # If parsing somehow yielded nothing, fall back to non-empty split lines
    if not parsed_qs and interview.questions:
        parsed_qs = [q.strip() for q in interview.questions.split("\n") if q.strip()]

    return {
        "id": interview.id,
        "role": interview.role,
        "experience": interview.experience,
        "skills": skills_list,
        "difficulty": interview.difficulty,
        "questions": parsed_qs,
        "raw_questions": interview.questions,
        "count": len(parsed_qs),
        "user_id": getattr(interview, "user_id", None),
        "adaptive_session_id": getattr(interview, "adaptive_session_id", None),
        "question_engine_version": getattr(interview, "question_engine_version", None) or "qengine-v1.0.0",
        "created_at": interview.created_at.isoformat() if getattr(interview, "created_at", None) else None
    }


from app.admin_routes import _get_stored_menus

def check_feature_enabled(feature_key: str, db: Session):
    """
    Backend Security Guard: Verifies if a feature/route is currently enabled in database Menu Management.
    If disabled by Super Admin, raises HTTP 403 Forbidden.
    """
    try:
        menus = _get_stored_menus(db)
        key_raw = (feature_key or "").lower().replace("%20", " ")
        key_clean = key_raw.replace(".html", "").strip().split("/")[-1].replace("-", " ")
        
        for m in menus:
            m_route_raw = (m.get("route") or "").lower()
            m_route_clean = m_route_raw.replace(".html", "").strip().split("/")[-1].replace("-", " ")
            m_name_raw = (m.get("name") or "").lower()
            m_name_clean = m_name_raw.replace("-", " ")
            m_id = (m.get("id") or "").lower()
            
            is_match = (
                m_id == key_raw or
                key_raw in m_route_raw or
                m_route_raw in key_raw or
                key_raw in m_name_raw or
                (m_route_clean and (m_route_clean == key_clean or m_route_clean in key_clean or key_clean in m_route_clean)) or
                (m_name_clean and (m_name_clean == key_clean or m_name_clean in key_clean or key_clean in m_name_clean))
            )
            
            if is_match:
                if (m.get("status") or "").lower() == "disabled":
                    raise HTTPException(
                        status_code=403,
                        detail=f"Feature '{m.get('name')}' is currently disabled by administrator."
                    )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Feature Guard Warning] {e}")


@app.post("/generate")
@app.post("/api/generate")
def generate_questions(
    data: InterviewRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    check_feature_enabled("Interview-studio.html", db)
    target_count = data.number_of_questions or 5
    try:
        custom_q = getattr(data, "custom_question", None) or ""
        try:
            prompt = interview_prompt(data)
            raw_output = generate_ai_questions(prompt)
            clean_questions = parse_raw_questions(raw_output, target_count=target_count)
        except Exception as ai_err:
            print(f"[AI Generator] LLM unavailable/fallback: {ai_err}")
            clean_questions = get_fallback_questions(
                data.role, data.skills, target_count, custom_q
            )

        # Strictly enforce target count
        if len(clean_questions) < target_count:
            fallback = get_fallback_questions(data.role, data.skills, target_count, custom_q)
            for q in fallback:
                if q not in clean_questions:
                    clean_questions.append(q)
                if len(clean_questions) >= target_count:
                    break

        if len(clean_questions) > target_count:
            clean_questions = clean_questions[:target_count]

        # Format questions consistently as numbered lines
        formatted_raw = "\n".join([f"{i+1}. {q}" for i, q in enumerate(clean_questions)])

        interview = InterviewHistory(
            role=data.role,
            experience=data.experience,
            skills=", ".join(data.skills),
            difficulty=data.difficulty,
            questions=formatted_raw,
            user_id=getattr(current_user, "id", None) if current_user else None,
            adaptive_session_id=getattr(data, "adaptive_session_id", None),
            question_engine_version="qengine-v1.0.0",
            created_at=datetime.utcnow()
        )

        db.add(interview)
        db.commit()
        db.refresh(interview)

        res = format_interview_response(interview)
        res["company"] = getattr(data, "company", "General Tech")
        res["interview_type"] = getattr(data, "interview_type", "Technical & Architecture")
        res["questions_details"] = [
            {
                "id": i + 1,
                "question": q,
                "category": getattr(data, "interview_type", "Technical & Architecture"),
                "difficulty": data.difficulty,
                "source_type": "AI_generated",
                "source_title": f"AI Synthesis ({data.role})",
                "source_url": None,
                "source_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "confidence": 0.91,
                "model_answer": f"Evaluates depth in {', '.join(data.skills[:3]) if data.skills else data.role} with clear trade-offs."
            }
            for i, q in enumerate(clean_questions)
        ]
        res["message"] = "Interview questions generated and saved successfully"
        return res

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate interview questions: {str(e)}"
        )


@app.get("/history")
@app.get("/api/history")
def get_history(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_candidate_account(current_user)
    check_feature_enabled("Interview history.html", db)
    try:
        interviews = (
            db.query(InterviewHistory)
            .filter(InterviewHistory.user_id == current_user.id)
            .order_by(InterviewHistory.id.desc())
            .all()
        )
        return [format_interview_response(item) for item in interviews]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve interview history: {str(e)}"
        )


@app.get("/history/{interview_id}")
@app.get("/api/history/{interview_id}")
def get_interview_detail(
    interview_id: int,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_candidate_account(current_user)
    interview = (
        db.query(InterviewHistory)
        .filter(
            InterviewHistory.id == interview_id,
            InterviewHistory.user_id == current_user.id,
        )
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview sitting not found")
    return format_interview_response(interview)


@app.delete("/history/{interview_id}")
@app.delete("/api/history/{interview_id}")
def delete_interview(
    interview_id: int,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_candidate_account(current_user)
    interview = (
        db.query(InterviewHistory)
        .filter(
            InterviewHistory.id == interview_id,
            InterviewHistory.user_id == current_user.id,
        )
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview sitting not found")

    db.delete(interview)
    db.commit()
    return {"message": "Interview deleted successfully", "id": interview_id}


# ---------- ADAPTIVE INTERVIEW QUESTION ENGINE APIS ----------

@app.get("/api/adaptive/profile", response_model=AdaptiveProfileResponse)
def get_adaptive_profile(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns the authenticated candidate's real-time Adaptive Profile.
    Evaluates interview readiness, persistent weaknesses, confirmed strengths,
    open mistakes, and deterministic recommended focus areas.
    """
    try:
        return get_candidate_adaptive_profile(current_user, db)
    except Exception as e:
        print(f"[Adaptive Profile Warning] Error calculating profile: {e}")
        # Safe fallback: return baseline insufficient data state without HTTP 500
        return AdaptiveProfileResponse(
            readiness_score=None,
            profile_status="insufficient_data",
            interview_count=0,
            last_interview_score=None,
            improvement_since_first_interview=None,
            strengths=[],
            focus_areas=[],
            open_mistakes=[],
            recommended_focus=None
        )


@app.post("/api/adaptive/generate", response_model=AdaptiveGenerateResponse)
def generate_adaptive_questions(
    data: InterviewRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates personalized interview/practice questions using the candidate's Adaptive Profile.
    Addresses highest-priority improvement opportunities (weaknesses/mistakes) with full metadata
    and anti-duplication protection.
    """
    check_feature_enabled("Interview-studio.html", db)
    return generate_adaptive_question_package(data, current_user, db)


@app.post("/api/adaptive/evaluate-response", response_model=ResponseEvaluationResult)
def evaluate_response_endpoint(
    payload: EvaluateResponseRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Evaluates one candidate response against question target skill, focus skill, role,
    and expected answer signals. Updates candidate_skill_analytics and candidate_mistakes_ledger.
    """
    return evaluate_candidate_response(payload, current_user, db)


@app.post("/api/adaptive/next-question", response_model=AdaptiveNextQuestionResponse)
def next_question_endpoint(
    payload: NextQuestionRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Determines the next best question after the candidate's latest response,
    choosing strategy based on candidate performance, recurring mistakes,
    or advancing to the next priority weakness.
    """
    return determine_adaptive_next_question(payload, current_user, db)


@app.post("/api/adaptive/from-match", response_model=AdaptiveFromMatchResponse)
@app.post("/adaptive/from-match", response_model=AdaptiveFromMatchResponse)
def adaptive_from_match_endpoint(
    payload: AdaptiveFromMatchRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Phase 5D: Starts personalized adaptive interview practice targeting verified
    server-side JD gaps loaded securely using scan_id.
    """
    return generate_adaptive_from_match_service(
        scan_id=payload.scan_id,
        number_of_questions=payload.number_of_questions,
        user=current_user,
        db=db
    )


# ---------- PHASE 5A: JOB DESCRIPTION EXTRACTION & SSRF-SAFE INGESTION APIS ----------

@app.post("/api/candidate/jd/extract-url", response_model=JobURLExtractResponse)
@app.post("/candidate/jd/extract-url", response_model=JobURLExtractResponse)
def extract_jd_from_url(
    payload: JobURLExtractRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Phase 5A: Safely fetches public job description webpage with multi-layered SSRF defenses,
    Content-Type checks, timeout enforcement, streaming size limits, and text normalization.
    """
    success, status, text_or_err, final_url = safe_fetch_job_url(payload.url)
    if not success:
        return JobURLExtractResponse(
            success=False,
            status=status,
            fallback_required=True,
            message=text_or_err,
            raw_jd=None,
            normalized_jd=None
        )
    
    normalized = normalize_job_description(
        raw_text=text_or_err,
        source_type="public_url",
        source_url=final_url
    )
    return JobURLExtractResponse(
        success=True,
        status="extracted",
        fallback_required=False,
        message="Job description extracted successfully.",
        raw_jd=text_or_err,
        normalized_jd=normalized
    )


@app.post("/api/candidate/jd/upload", response_model=JobUploadExtractResponse)
@app.post("/candidate/jd/upload", response_model=JobUploadExtractResponse)
async def upload_jd_document(
    file: UploadFile = File(...),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Phase 5A: Extracts and normalizes job description text from uploaded document (PDF, DOCX, TXT).
    """
    filename = file.filename or "uploaded_jd.txt"
    fname_lower = filename.lower()
    if not (fname_lower.endswith(".pdf") or fname_lower.endswith(".docx") or fname_lower.endswith(".doc") or fname_lower.endswith(".txt")):
        return JobUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message="Unsupported document format. Please upload a PDF, DOCX, or TXT file, or paste the JD text directly.",
            raw_jd=None,
            normalized_jd=None
        )
        
    try:
        content_bytes = await file.read()
    except Exception as e:
        return JobUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message=f"Failed to read uploaded file: {str(e)}. Please paste the JD text directly.",
            raw_jd=None,
            normalized_jd=None
        )
        
    if not content_bytes or len(content_bytes) < 10:
        return JobUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message="Uploaded document is empty. Please paste the JD text directly.",
            raw_jd=None,
            normalized_jd=None
        )
        
    # Enforce 5MB limit for uploaded files
    if len(content_bytes) > 5 * 1024 * 1024:
        return JobUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message="Uploaded file exceeds 5MB limit. Please upload a smaller file or paste the JD text directly.",
            raw_jd=None,
            normalized_jd=None
        )

    try:
        raw_text = extract_text_from_document(filename, content_bytes)
    except Exception as parse_err:
        return JobUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message=f"Error extracting text from document: {str(parse_err)}. Please paste the JD text directly.",
            raw_jd=None,
            normalized_jd=None
        )
        
    if not raw_text or len(raw_text.strip()) < 10:
        return JobUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message="Could not extract readable text from document. Please copy and paste the JD text directly.",
            raw_jd=None,
            normalized_jd=None
        )
        
    normalized = normalize_job_description(
        raw_text=raw_text,
        source_type="document_upload",
        source_url=None
    )
    return JobUploadExtractResponse(
        success=True,
        status="extracted",
        fallback_required=False,
        filename=filename,
        message="Job description extracted from document successfully.",
        raw_jd=raw_text,
        normalized_jd=normalized
    )


@app.post("/api/candidate/resume/upload", response_model=ResumeUploadExtractResponse)
@app.post("/candidate/resume/upload", response_model=ResumeUploadExtractResponse)
async def upload_resume_document(
    file: UploadFile = File(...),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Extracts candidate resume text and structure from uploaded document (PDF, DOCX, TXT).
    """
    filename = file.filename or "uploaded_resume.txt"
    fname_lower = filename.lower()
    if not (fname_lower.endswith(".pdf") or fname_lower.endswith(".docx") or fname_lower.endswith(".doc") or fname_lower.endswith(".txt")):
        return ResumeUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message="Unsupported document format. Please upload a PDF, DOCX, or TXT file, or paste your resume text directly.",
            extracted_text=None,
            normalized_resume=None
        )
        
    try:
        content_bytes = await file.read()
    except Exception as e:
        return ResumeUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message=f"Failed to read uploaded file: {str(e)}. Please paste the resume text directly.",
            extracted_text=None,
            normalized_resume=None
        )
        
    if not content_bytes or len(content_bytes) < 10:
        return ResumeUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message="Uploaded document is empty. Please paste your resume text directly.",
            extracted_text=None,
            normalized_resume=None
        )
        
    if len(content_bytes) > 5 * 1024 * 1024:
        return ResumeUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message="Uploaded file exceeds 5MB limit. Please upload a smaller file or paste your resume text directly.",
            extracted_text=None,
            normalized_resume=None
        )

    try:
        raw_text = extract_text_from_document(filename, content_bytes)
    except Exception as parse_err:
        return ResumeUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message=f"Error extracting text from document: {str(parse_err)}. Please paste the resume text directly.",
            extracted_text=None,
            normalized_resume=None
        )
        
    if not raw_text or len(raw_text.strip()) < 10:
        return ResumeUploadExtractResponse(
            success=False,
            status="fallback_required",
            fallback_required=True,
            filename=filename,
            message="Could not extract readable text from document. Please copy and paste your resume text directly.",
            extracted_text=None,
            normalized_resume=None
        )
        
    normalized = normalize_resume(raw_text)
    return ResumeUploadExtractResponse(
        success=True,
        status="extracted",
        fallback_required=False,
        filename=filename,
        message="Resume extracted from document successfully.",
        extracted_text=raw_text,
        normalized_resume=normalized
    )


# ==============================================================================
# PHASE 5C: RESUME ↔ JD MATCH PERSISTENCE & RETRIEVAL API
# ==============================================================================

@app.post("/api/candidate/resume-jd/match", response_model=ResumeJDMatchResponse)
@app.post("/candidate/resume-jd/match", response_model=ResumeJDMatchResponse)
async def create_resume_jd_match(
    payload: ResumeJDMatchRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Executes multi-dimensional match between Resume and JD and securely persists
    the exact result tied to the authenticated user account with a unique scan_id.
    """
    # 1. Validate inputs
    logger.info("Resume/JD match evaluation initiated", extra={"user_id": current_user.id, "source_type": payload.source_type})
    if not payload.resume_text and not payload.normalized_resume:
        raise HTTPException(
            status_code=400,
            detail="Resume content is required. Please provide resume_text or normalized_resume."
        )
    if not payload.jd_text and not payload.jd_url and not payload.normalized_jd:
        raise HTTPException(
            status_code=400,
            detail="Job description is required. Please provide jd_text, jd_url, or normalized_jd."
        )

    # 2. Extract & Normalize JD
    if payload.normalized_jd:
        normalized_jd = payload.normalized_jd
    elif payload.jd_url:
        fetch_result = safe_fetch_job_url(payload.jd_url)
        if isinstance(fetch_result, dict):
            success = fetch_result.get("success", False)
            text_or_err = fetch_result.get("extracted_text") or fetch_result.get("error", "")
            final_url = fetch_result.get("source_url") or payload.jd_url
        elif isinstance(fetch_result, (tuple, list)):
            success = bool(fetch_result[0])
            text_or_err = fetch_result[2] if len(fetch_result) > 2 else ""
            final_url = fetch_result[3] if len(fetch_result) > 3 else payload.jd_url
        else:
            success = False
            text_or_err = "Fetch failed"
            final_url = payload.jd_url

        if not success:
            logger.warning("Job URL fetch failed", extra={"user_id": current_user.id})
            raise HTTPException(
                status_code=400,
                detail=f"Unable to fetch JD from URL: {text_or_err}. Please paste the JD text directly."
            )
        normalized_jd = normalize_job_description(
            raw_text=text_or_err,
            source_type="public_url",
            source_url=final_url
        )
    else:
        normalized_jd = normalize_job_description(
            raw_text=payload.jd_text or "",
            source_type=payload.source_type or "paste",
            source_url=payload.source_url
        )
    logger.info("Job description normalized successfully", extra={"user_id": current_user.id, "job_title": normalized_jd.job_title})

    # 3. Extract & Normalize Resume
    if payload.normalized_resume:
        normalized_resume = payload.normalized_resume
    else:
        normalized_resume = normalize_resume(payload.resume_text or "")
    logger.info("Resume normalized successfully", extra={"user_id": current_user.id, "candidate_name": normalized_resume.candidate_name})

    # 4. Execute Multi-Dimensional Match Engine (Phase 5B)
    try:
        match_result = calculate_resume_jd_match(
            jd_input=normalized_jd,
            resume_input=normalized_resume
        )
        logger.info(
            "Matching engine execution completed",
            extra={
                "user_id": current_user.id,
                "overall_score": match_result.overall_match_score,
                "confidence": match_result.match_confidence
            }
        )
    except Exception as match_err:
        logger.exception("Resume/JD match calculation failed", extra={"user_id": current_user.id})
        raise HTTPException(
            status_code=500,
            detail=f"Matching calculation failed: {str(match_err)}"
        )

    # 5. Determine Metadata
    target_role = (
        payload.target_role or
        normalized_jd.job_title or
        "General Tech"
    )
    candidate_name = (
        payload.candidate_name or
        normalized_resume.candidate_name or
        current_user.full_name or
        "Candidate"
    )
    if payload.jd_url:
        source_type = "public_url"
        source_url = payload.jd_url
    else:
        source_type = payload.source_type if payload.source_type and payload.source_type != "paste" else (normalized_jd.source_type or "paste")
        source_url = payload.source_url or normalized_jd.source_url

    engine_version = "match-v1.0.0"

    # 6. Generate Secure Unique Scan ID
    scan_id = f"scan_{uuid.uuid4().hex}"

    # 7. Persist to Database (Phase 5C)
    now = datetime.utcnow()
    try:
        matched_skills_str = ", ".join([item.skill for item in match_result.skill_matrix if item.gap_status == "matched"])
        missing_skills_str = ", ".join([item.skill for item in match_result.skill_matrix if item.gap_status == "gap"])

        scan_record = ResumeScan(
            scan_id=scan_id,
            user_id=current_user.id,
            matching_engine_version=engine_version,
            candidate_name=candidate_name,
            target_role=target_role,
            match_score=match_result.overall_match_score,
            overall_match_score=match_result.overall_match_score,
            match_confidence=match_result.match_confidence,
            sub_scores=json.dumps(match_result.sub_scores.model_dump()),
            skill_matrix=json.dumps([item.model_dump() for item in match_result.skill_matrix]),
            strengths=json.dumps(match_result.strengths),
            skill_gaps=json.dumps(match_result.skill_gaps),
            critical_gaps=json.dumps(match_result.critical_gaps),
            recommendations=json.dumps(match_result.recommendations),
            normalized_jd=json.dumps(normalized_jd.model_dump()),
            normalized_resume=json.dumps(normalized_resume.model_dump()),
            matched_skills=matched_skills_str,
            missing_skills=missing_skills_str,
            source_type=source_type,
            source_url=source_url,
            fetched_at=normalized_jd.fetched_at,
            created_at=now,
            updated_at=now
        )
        db.add(scan_record)
        db.commit()
        db.refresh(scan_record)
        logger.info("Resume/JD match record persisted", extra={"user_id": current_user.id, "scan_id": scan_id})
    except Exception as db_err:
        db.rollback()
        logger.exception("Failed to persist match result to database", extra={"user_id": current_user.id, "scan_id": scan_id})
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist match result to database: {str(db_err)}"
        )

    # 8. Return Validated Response
    return ResumeJDMatchResponse(
        scan_id=scan_id,
        matching_engine_version=engine_version,
        overall_match_score=match_result.overall_match_score,
        match_confidence=match_result.match_confidence,
        sub_scores=match_result.sub_scores,
        skill_matrix=match_result.skill_matrix,
        strengths=match_result.strengths,
        skill_gaps=match_result.skill_gaps,
        critical_gaps=match_result.critical_gaps,
        recommendations=match_result.recommendations,
        target_role=target_role,
        candidate_name=candidate_name,
        source_type=source_type,
        source_url=source_url,
        created_at=now.isoformat()
    )


@app.get("/api/candidate/resume-jd/match/{scan_id}", response_model=ResumeJDMatchResponse)
@app.get("/candidate/resume-jd/match/{scan_id}", response_model=ResumeJDMatchResponse)
def get_resume_jd_match(
    scan_id: str,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves exact persisted scan result for the authenticated candidate.
    Returns 404 if not found or if the scan belongs to another user.
    """
    scan = (
        db.query(ResumeScan)
        .filter(ResumeScan.scan_id == scan_id, ResumeScan.user_id == current_user.id)
        .first()
    )

    if not scan:
        raise HTTPException(
            status_code=404,
            detail="Match result not found or access denied."
        )

    # Parse persisted JSON fields
    sub_scores_data = json.loads(scan.sub_scores) if scan.sub_scores else {}
    skill_matrix_data = json.loads(scan.skill_matrix) if scan.skill_matrix else []
    strengths_data = json.loads(scan.strengths) if scan.strengths else []
    skill_gaps_data = json.loads(scan.skill_gaps) if scan.skill_gaps else []
    critical_gaps_data = json.loads(scan.critical_gaps) if scan.critical_gaps else []
    recommendations_data = json.loads(scan.recommendations) if scan.recommendations else []

    sub_scores = SubScores(**sub_scores_data) if sub_scores_data else SubScores()
    skill_matrix = [SkillMatrixItem(**item) for item in skill_matrix_data]

    return ResumeJDMatchResponse(
        scan_id=scan.scan_id,
        matching_engine_version=scan.matching_engine_version or "match-v1.0.0",
        overall_match_score=scan.overall_match_score if scan.overall_match_score is not None else scan.match_score,
        match_confidence=scan.match_confidence or "MEDIUM",
        sub_scores=sub_scores,
        skill_matrix=skill_matrix,
        strengths=strengths_data,
        skill_gaps=skill_gaps_data,
        critical_gaps=critical_gaps_data,
        recommendations=recommendations_data,
        target_role=scan.target_role,
        candidate_name=scan.candidate_name,
        source_type=scan.source_type or "paste",
        source_url=scan.source_url,
        created_at=scan.created_at.isoformat() if scan.created_at else datetime.utcnow().isoformat()
    )


@app.get("/api/candidate/resume-jd/history", response_model=List[ResumeJDMatchSummaryItem])
@app.get("/candidate/resume-jd/history", response_model=List[ResumeJDMatchSummaryItem])
def get_resume_jd_history(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns historical scan summaries for the authenticated candidate (privacy safe: no raw texts).
    """
    scans = (
        db.query(ResumeScan)
        .filter(ResumeScan.user_id == current_user.id, ResumeScan.scan_id.isnot(None))
        .order_by(ResumeScan.created_at.desc())
        .limit(50)
        .all()
    )

    history = []
    for s in scans:
        history.append(ResumeJDMatchSummaryItem(
            scan_id=s.scan_id,
            target_role=s.target_role,
            overall_match_score=s.overall_match_score if s.overall_match_score is not None else s.match_score,
            match_confidence=s.match_confidence or "MEDIUM",
            matching_engine_version=s.matching_engine_version or "match-v1.0.0",
            source_type=s.source_type or "paste",
            created_at=s.created_at.isoformat() if s.created_at else ""
        ))
    return history


# ---------- REAL-TIME VIDEO + VOICE CONVERSATIONAL INTERVIEW API ----------

@app.post("/api/interview/start", response_model=InterviewStartResponse)
def start_realtime_interview(
    payload: InterviewStartRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Initializes a real-time conversational AI interview session.
    Generates Question 1 tailored for the candidate's target role, skills, and selected persona.
    """
    _require_candidate_account(current_user)
    context = build_candidate_context(db, current_user)
    evidence = {
        "target_role": context["candidate"]["target_role"],
        "experience": context["candidate"]["experience"],
        "skills": context["candidate"]["skills"][:20],
        "interview_stats": context["interview_stats"],
        "skill_scores": context["skill_scores"][:8],
        "mistakes": context["mistakes"][:5],
        "resume_match": context["resume_match"],
    }
    try:
        return start_interview_session(
            role=payload.role,
            skills=payload.skills,
            persona=payload.persona,
            mode=payload.mode,
            user_id=current_user.id,
            db=db,
            experience=payload.experience,
            interview_type=payload.interview_type,
            company=payload.company,
            custom_question=payload.custom_question,
            questions=payload.questions,
            question_count=payload.question_count,
            candidate_context=evidence,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/interview/{interview_id}/answer", response_model=InterviewAnswerResponse)
def answer_realtime_interview_turn(
    interview_id: str,
    payload: InterviewAnswerRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Processes candidate spoken answer, performs multi-factor rubric evaluation,
    and synthesizes a contextual follow-up or next competency question.
    """
    _require_candidate_account(current_user)
    _get_owned_mock_interview(interview_id, current_user, db)
    try:
        return evaluate_and_generate_next_question(
            interview_id=interview_id,
            answer_text=payload.answer_text,
            db=db,
            user_id=current_user.id,
            is_final=payload.is_final,
            turn_index=payload.turn_index,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Interview session not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/interview/{interview_id}/complete", response_model=InterviewCompleteResponse)
def complete_realtime_interview(
    interview_id: str,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Finalizes the real-time interview, generates the holistic multi-dimensional scorecard,
    and persists the record for Candidate Dashboard sync.
    """
    _require_candidate_account(current_user)
    _get_owned_mock_interview(interview_id, current_user, db)
    try:
        return complete_interview_session(
            interview_id=interview_id,
            db=db,
            user_id=current_user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Interview session not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/mock-interview/history")
def get_candidate_mock_interview_history(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_candidate_account(current_user)
    records = (
        db.query(MockInterview)
        .filter(MockInterview.user_id == current_user.id)
        .order_by(MockInterview.created_at.desc())
        .limit(100)
        .all()
    )
    return [_mock_interview_history_item(record) for record in records]


@app.get("/api/mock-interview/{interview_id}")
def get_candidate_mock_interview(
    interview_id: str,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_candidate_account(current_user)
    record = _get_owned_mock_interview(interview_id, current_user, db)
    return _mock_interview_history_item(record)


@app.delete("/api/mock-interview/{interview_id}")
def delete_candidate_mock_interview(
    interview_id: str,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_candidate_account(current_user)
    record = _get_owned_mock_interview(interview_id, current_user, db)
    db.delete(record)
    db.commit()
    return {"message": "Mock interview deleted.", "id": record.id}


@app.post("/api/candidate/mock-interview", include_in_schema=False)
@app.post("/candidate/mock-interview", include_in_schema=False)
def reject_legacy_mock_interview_submission(
    current_user: UserAccount = Depends(get_current_user),
):
    _require_candidate_account(current_user)
    raise HTTPException(
        status_code=410,
        detail="Client-submitted scorecards are no longer accepted. Complete the saved interview session instead.",
    )


@app.get("/api/interview/providers")
def get_interview_providers():
    """
    Returns active STT, TTS, and Avatar capabilities and configuration tokens for frontend initialization.
    """
    stt = get_stt_provider()
    tts = get_tts_provider()
    avatar = get_avatar_provider()
    return {
        "stt": stt.get_client_config(),
        "tts": {
            "provider": tts.get_provider_name(),
            "client_synthesis": True
        },
        "avatar": {
            "provider": avatar.get_provider_name(),
            "supported_personas": ["alex", "elena", "marcus"]
        }
    }


# ---------- AI ANSWER EVALUATOR API ----------

@app.get("/api/evaluator/presets", response_model=EvaluatorPresetsResponse)
def get_evaluator_presets():
    """
    Returns curated preset question library grouped by roles, categories, seniority, and target tiers.
    """
    return get_curated_presets()


@app.post("/api/evaluator/evaluate", response_model=AnswerEvaluationResponse)
def evaluate_single_answer(
    req: AnswerEvaluationRequest,
    current_user: Optional[UserAccount] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Evaluates candidate interview answer against FAANG rubrics, STAR framework,
    computes multi-dimensional scores, strengths/weaknesses, and generates gold standard rewrite.
    """
    check_feature_enabled("Answer Evaluator", db)
    
    result = evaluate_candidate_answer(
        question=req.question,
        answer=req.answer,
        role=req.role or "Backend & Distributed Systems",
        seniority=req.seniority or "Senior (5-8 yrs)",
        company_tier=req.company_tier or "FAANG / Tier-1",
        category=req.category,
        jd_context=req.jd_context
    )
    
    # Optionally persist in MockInterview/History if candidate is logged in
    saved = False
    if current_user:
        try:
            history_record = MockInterview(
                user_id=current_user.id,
                role=req.role or "Engineering",
                company_target=req.company_tier or "FAANG Tier",
                interviewer_persona="AI Answer Evaluator (Staff Bar Raiser)",
                score=float(result.get("overall_score", 80)),
                technical_accuracy=float(result.get("dimensions", {}).get("technical_accuracy", 80)),
                communication_clarity=float(result.get("dimensions", {}).get("communication_clarity", 80)),
                star_depth=float(result.get("star_breakdown", {}).get("action_score", 20)) * 4.0,
                confidence_score=float(result.get("dimensions", {}).get("trade_off_analysis", 80)),
                duration_seconds=120,
                transcript=json.dumps([{
                    "question": req.question,
                    "answer": req.answer,
                    "evaluation": result
                }]),
                status="completed",
                interview_mode="answer_evaluator",
                created_at=datetime.utcnow()
            )
            db.add(history_record)
            db.commit()
            saved = True
        except Exception as e:
            logger.warning(f"[Answer Evaluator] DB save warning: {e}")
            db.rollback()
            
    result["saved_to_history"] = saved
    return result



# ---------- VISITOR & CLICK ANALYTICS API ----------

@app.post("/api/analytics/track")
@app.post("/api/track")
@app.post("/track")
def track_page_view(
    payload: PageViewPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        # Resolve real client IP
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "127.0.0.1"

        user_agent = request.headers.get("user-agent", "")

        event = PageViewEvent(
            session_id=payload.session_id,
            page_url=payload.page_url,
            page_title=payload.page_title,
            referrer=payload.referrer,
            ip_address=ip,
            user_agent=user_agent,
            browser=payload.browser,
            os=payload.os,
            device_type=payload.device_type,
            screen_resolution=payload.screen_resolution,
            timestamp=datetime.utcnow()
        )
        db.add(event)
        db.commit()
        return {"status": "ok", "event": "page_view_logged"}
    except Exception as e:
        print(f"[Analytics] Track error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/analytics/click")
@app.post("/api/click")
@app.post("/click")
@app.post("/api/analytics/events")
def track_click_event(
    payload: ClickEventPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "127.0.0.1"

        event = ClickEvent(
            session_id=payload.session_id,
            page_url=payload.page_url,
            element_tag=payload.element_tag,
            element_id=payload.element_id,
            element_text=payload.element_text,
            element_class=payload.element_class,
            target_role=payload.target_role,
            action_type=payload.action_type,
            browser=payload.browser,
            os=payload.os,
            device_type=payload.device_type,
            ip_address=ip,
            timestamp=datetime.utcnow()
        )
        db.add(event)
        db.commit()
        return {"status": "ok", "event": "click_logged"}
    except Exception as e:
        print(f"[Analytics] Click error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/analytics/stats")
def get_analytics_stats(db: Session = Depends(get_db)):
    try:
        now = datetime.utcnow()
        active_window = now - timedelta(minutes=5)
        day_ago = now - timedelta(hours=24)

        # 1. High-level totals
        total_pageviews = db.query(func.count(PageViewEvent.id)).scalar() or 0
        unique_visitors = db.query(func.count(func.distinct(PageViewEvent.session_id))).scalar() or 0
        total_clicks = db.query(func.count(ClickEvent.id)).scalar() or 0

        # Active sessions in last 5 minutes
        active_sessions = db.query(func.count(func.distinct(PageViewEvent.session_id))).filter(
            PageViewEvent.timestamp >= active_window
        ).scalar() or 0
        if active_sessions == 0 and total_pageviews > 0:
            active_sessions = 1  # current active admin

        # 2. Top pages visited
        pages_query = db.query(
            PageViewEvent.page_url,
            func.count(PageViewEvent.id).label("count")
        ).group_by(PageViewEvent.page_url).order_by(desc("count")).limit(8).all()
        views_by_page = [{"page": r[0] or "Unknown", "views": r[1]} for r in pages_query]

        # 3. Top Clicked Roles
        role_clicks_query = db.query(
            ClickEvent.target_role,
            func.count(ClickEvent.id).label("count")
        ).filter(ClickEvent.target_role.isnot(None), ClickEvent.target_role != "").group_by(ClickEvent.target_role).order_by(desc("count")).limit(10).all()
        clicks_by_role = [{"role": r[0], "count": r[1]} for r in role_clicks_query]

        # 4. Top Clicked Actions / Elements
        action_clicks_query = db.query(
            ClickEvent.element_text,
            ClickEvent.action_type,
            func.count(ClickEvent.id).label("count")
        ).group_by(ClickEvent.element_text, ClickEvent.action_type).order_by(desc("count")).limit(10).all()
        clicks_by_action = [{"label": r[0] or r[1] or "Click", "action": r[1] or "general", "count": r[2]} for r in action_clicks_query]

        # 5. Device & Browser Breakdowns
        device_query = db.query(
            PageViewEvent.device_type,
            func.count(PageViewEvent.id).label("count")
        ).group_by(PageViewEvent.device_type).all()
        device_breakdown = [{"device": r[0] or "Desktop", "count": r[1]} for r in device_query]

        browser_query = db.query(
            PageViewEvent.browser,
            func.count(PageViewEvent.id).label("count")
        ).group_by(PageViewEvent.browser).all()
        browser_breakdown = [{"browser": r[0] or "Chrome", "count": r[1]} for r in browser_query]

        os_query = db.query(
            PageViewEvent.os,
            func.count(PageViewEvent.id).label("count")
        ).group_by(PageViewEvent.os).all()
        os_breakdown = [{"os": r[0] or "Windows", "count": r[1]} for r in os_query]

        # 6. Recent Clickstream Feed (Latest 40 clicks)
        recent_clicks_rows = db.query(ClickEvent).order_by(desc(ClickEvent.id)).limit(40).all()
        recent_clicks = [{
            "id": c.id,
            "session_id": c.session_id[:8] + "..." if c.session_id else "anon",
            "page": c.page_url,
            "element_text": c.element_text or c.element_tag or "Element",
            "element_id": c.element_id,
            "target_role": c.target_role,
            "action_type": c.action_type or "click",
            "device": c.device_type or "Desktop",
            "os": c.os or "Windows",
            "browser": c.browser or "Chrome",
            "ip": c.ip_address or "127.0.0.1",
            "timestamp": c.timestamp.isoformat() if c.timestamp else None
        } for c in recent_clicks_rows]

        # 7. Recent Visitor Pageviews (Latest 30 views)
        recent_views_rows = db.query(PageViewEvent).order_by(desc(PageViewEvent.id)).limit(30).all()
        recent_visitors = [{
            "id": v.id,
            "session_id": v.session_id[:8] + "..." if v.session_id else "anon",
            "page": v.page_url,
            "page_title": v.page_title,
            "referrer": v.referrer or "Direct",
            "device": v.device_type or "Desktop",
            "os": v.os or "Windows",
            "browser": v.browser or "Chrome",
            "ip": v.ip_address or "127.0.0.1",
            "timestamp": v.timestamp.isoformat() if v.timestamp else None
        } for v in recent_views_rows]

        return {
            "total_pageviews": total_pageviews,
            "unique_visitors": unique_visitors,
            "total_clicks": total_clicks,
            "active_sessions": active_sessions,
            "views_by_page": views_by_page,
            "clicks_by_role": clicks_by_role,
            "clicks_by_action": clicks_by_action,
            "device_breakdown": device_breakdown,
            "browser_breakdown": browser_breakdown,
            "os_breakdown": os_breakdown,
            "recent_clicks": recent_clicks,
            "recent_visitors": recent_visitors,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load analytics: {str(e)}")


@app.delete("/api/analytics/clear")
def clear_analytics(db: Session = Depends(get_db)):
    try:
        db.query(ClickEvent).delete()
        db.query(PageViewEvent).delete()
        db.commit()
        return {"status": "ok", "message": "Analytics data cleared successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to clear analytics: {str(e)}")


# ---------- SUPER ADMIN PORTAL (PHASE 1) ----------
@app.get("/admin", include_in_schema=False)
@app.get("/Admin", include_in_schema=False)
@app.get("/Admin.html", include_in_schema=False)
@app.get("/admin/{subpath:path}", include_in_schema=False)
def serve_admin_portal(subpath: str = ""):
    f = BASE_DIR / "Admin.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Admin.html not found")


# ---------- FRONTEND PAGES & ASSETS ----------

@app.get("/analytics", include_in_schema=False)
@app.get("/Analytics", include_in_schema=False)
@app.get("/Analytics.html", include_in_schema=False)
@app.get("/candidate/analytics", include_in_schema=False)
@app.get("/candidate/Analytics.html", include_in_schema=False)
def serve_analytics():
    f = BASE_DIR / "Analytics.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Analytics.html not found")

@app.get("/analytics-tracker.js", include_in_schema=False)
def serve_tracker_script():
    f = BASE_DIR / "analytics-tracker.js"
    return FileResponse(f, media_type="application/javascript") if f.exists() else HTTPException(404, "analytics-tracker.js not found")

@app.get("/typography.css", include_in_schema=False)
def serve_typography_stylesheet():
    f = BASE_DIR / "typography.css"
    return FileResponse(f, media_type="text/css") if f.exists() else HTTPException(404, "typography.css not found")

def get_html_response(filename: str, db: Session = None):
    """
    Robustly serves HTML files in Vercel Serverless environment.
    Searches multiple candidate paths and falls back to string content reading before 404.
    """
    if db:
        check_feature_enabled(filename, db)
    
    paths_to_try = [
        BASE_DIR / filename,
        BASE_DIR / "api" / filename,
        Path(__file__).resolve().parent.parent / filename,
        Path(__file__).resolve().parent.parent / "api" / filename,
        Path(__file__).resolve().parent / filename,
        Path("/var/task") / filename,
        Path("/var/task/api") / filename,
        Path(os.getcwd()) / filename,
        Path(os.getcwd()) / "api" / filename,
    ]
    for p in paths_to_try:
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as file_obj:
                    res = HTMLResponse(content=file_obj.read(), media_type="text/html", status_code=200)
                    res.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
                    res.headers["Pragma"] = "no-cache"
                    res.headers["Expires"] = "0"
                    return res
            except Exception as read_err:
                print(f"[HTML Load Warning] {p}: {read_err}")
                
    f = BASE_DIR / filename
    if f.exists():
        return FileResponse(f)
        
    raise HTTPException(status_code=404, detail=f"{filename} not found")


@app.get("/", include_in_schema=False)
@app.get("/Candidate-login.html", include_in_schema=False)
@app.get("/candidate/login", include_in_schema=False)
@app.get("/api/candidate/login", include_in_schema=False)
@app.get("/login", include_in_schema=False)
@app.get("/api/login", include_in_schema=False)
@app.get("/Login", include_in_schema=False)
@app.get("/Login.html", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def serve_login():
    if is_development_auth_bypass_enabled():
        return RedirectResponse(url="/candidate/dashboard", status_code=307)
    return get_html_response("Candidate-login.html")

@app.get("/candidate", include_in_schema=False)
@app.get("/candidate/", include_in_schema=False)
@app.get("/candidate/dashboard", include_in_schema=False)
@app.get("/api/candidate/dashboard", include_in_schema=False)
@app.get("/candidate/Dashboard.html", include_in_schema=False)
@app.get("/candidate/Candidate-dashboard.html", include_in_schema=False)
@app.get("/Candidate-dashboard.html", include_in_schema=False)
def serve_candidate_dashboard(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Dashboard", db)
    if block_res: return block_res
    return get_html_response("Candidate-dashboard.html", db)

@app.get("/dashboard", include_in_schema=False)
@app.get("/Dashboard", include_in_schema=False)
@app.get("/Dashboard.html", include_in_schema=False)
def serve_dashboard(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Dashboard", db)
    if block_res: return block_res
    return get_html_response("Dashboard.html", db)

@app.get("/candidate/evaluator", include_in_schema=False)
@app.get("/api/candidate/evaluator", include_in_schema=False)
@app.get("/evaluator", include_in_schema=False)
def serve_evaluator(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Interview Studio", db)
    if block_res: return block_res
    return get_html_response("Interview-studio.html", db)

@app.get("/admin", include_in_schema=False)
@app.get("/admin/dashboard", include_in_schema=False)
@app.get("/admin/menu-management", include_in_schema=False)
@app.get("/admin/users", include_in_schema=False)
@app.get("/admin/roles-permissions", include_in_schema=False)
@app.get("/admin/prompts", include_in_schema=False)
@app.get("/Admin.html", include_in_schema=False)
def serve_admin_page():
    return get_html_response("Admin.html")

@app.get("/candidate/interview-studio", include_in_schema=False)
@app.get("/api/candidate/interview-studio", include_in_schema=False)
@app.get("/candidate/Interview-studio.html", include_in_schema=False)
@app.get("/studio", include_in_schema=False)
@app.get("/Studio", include_in_schema=False)
@app.get("/Interview-studio", include_in_schema=False)
@app.get("/interview-studio", include_in_schema=False)
@app.get("/Interview-studio.html", include_in_schema=False)
def serve_studio(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Interview Studio", db)
    if block_res: return block_res
    return get_html_response("Interview-studio.html", db)

@app.get("/candidate/answer-evaluator", include_in_schema=False)
@app.get("/api/candidate/answer-evaluator", include_in_schema=False)
@app.get("/candidate/Answer-evaluator.html", include_in_schema=False)
@app.get("/answer-evaluator", include_in_schema=False)
@app.get("/Answer-evaluator", include_in_schema=False)
@app.get("/Answer-evaluator.html", include_in_schema=False)
@app.get("/evaluator", include_in_schema=False)
def serve_answer_evaluator(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Answer Evaluator", db)
    if block_res: return block_res
    return get_html_response("Answer-evaluator.html", db)

@app.get("/candidate/mock-interview", include_in_schema=False)
@app.get("/api/candidate/mock-interview", include_in_schema=False)
@app.get("/candidate/Mock-interview.html", include_in_schema=False)
@app.get("/mock-interview", include_in_schema=False)
@app.get("/Mock-interview", include_in_schema=False)
@app.get("/Mock-interview.html", include_in_schema=False)
def serve_mock(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("AI Mock Interview", db)
    if block_res: return block_res
    return get_html_response("Mock-interview.html", db)

@app.get("/candidate/resume-jd-match", include_in_schema=False)
@app.get("/api/candidate/resume-jd-match", include_in_schema=False)
@app.get("/candidate/resume-match", include_in_schema=False)
@app.get("/api/candidate/resume-match", include_in_schema=False)
@app.get("/candidate/Resume-match.html", include_in_schema=False)
@app.get("/resume-match", include_in_schema=False)
@app.get("/Resume-match", include_in_schema=False)
@app.get("/Resume-match.html", include_in_schema=False)
def serve_resume_match(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Resume & JD Match", db)
    if block_res: return block_res
    return get_html_response("Resume-match.html", db)

@app.get("/candidate/company-playbooks", include_in_schema=False)
@app.get("/api/candidate/company-playbooks", include_in_schema=False)
@app.get("/candidate/Company-playbooks.html", include_in_schema=False)
@app.get("/company-playbooks", include_in_schema=False)
@app.get("/Company-playbooks", include_in_schema=False)
@app.get("/Company-playbooks.html", include_in_schema=False)
def serve_company_playbooks(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Company Playbooks", db)
    if block_res: return block_res
    return get_html_response("Company-playbooks.html", db)

@app.get("/candidate/history", include_in_schema=False)
@app.get("/api/candidate/history", include_in_schema=False)
@app.get("/candidate/Interview history.html", include_in_schema=False)
@app.get("/candidate/Interview%20history.html", include_in_schema=False)
@app.get("/history-page", include_in_schema=False)
@app.get("/Interview-history", include_in_schema=False)
@app.get("/interview-history", include_in_schema=False)
@app.get("/Interview history.html", include_in_schema=False)
@app.get("/Interview%20history.html", include_in_schema=False)
def serve_history_page(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Session History", db)
    if block_res: return block_res
    return get_html_response("Interview history.html", db)

@app.get("/candidate/upgrade-pro", include_in_schema=False)
@app.get("/api/candidate/upgrade-pro", include_in_schema=False)
@app.get("/candidate/Upgrade-pro.html", include_in_schema=False)
@app.get("/upgrade-pro", include_in_schema=False)
@app.get("/Upgrade-pro", include_in_schema=False)
@app.get("/Upgrade-pro.html", include_in_schema=False)
def serve_upgrade(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Upgrade Pro", db)
    if block_res: return block_res
    return get_html_response("Upgrade-pro.html", db)

@app.get("/candidate/user-guide", include_in_schema=False)
@app.get("/api/candidate/user-guide", include_in_schema=False)
@app.get("/candidate/User-guide.html", include_in_schema=False)
@app.get("/user-guide", include_in_schema=False)
@app.get("/User-guide", include_in_schema=False)
@app.get("/User-guide.html", include_in_schema=False)
def serve_user_guide(db: Session = Depends(get_db)):
    return get_html_response("User-guide.html", db)

@app.get("/candidate/scorecard", include_in_schema=False)
@app.get("/candidate/scorecard.html", include_in_schema=False)
@app.get("/scorecard", include_in_schema=False)
@app.get("/Scorecard", include_in_schema=False)
@app.get("/scorecard.html", include_in_schema=False)
@app.get("/scorecard/{score_id}", include_in_schema=False)
def serve_scorecard(score_id: str = None, db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Public Scorecards", db)
    if block_res: return block_res
    return get_html_response("scorecard.html")

@app.get("/analytics-tracker.js", include_in_schema=False)
@app.get("/candidate/analytics-tracker.js", include_in_schema=False)
def serve_analytics_tracker():
    f = BASE_DIR / "analytics-tracker.js"
    return FileResponse(f) if f.exists() else HTTPException(404, "analytics-tracker.js not found")

@app.get("/logo.png", include_in_schema=False)
@app.get("/candidate/logo.png", include_in_schema=False)
def serve_logo():
    f = BASE_DIR / "logo.png"
    return FileResponse(f) if f.exists() else HTTPException(404, "logo.png not found")

COACH_RATE_LIMIT = 12
COACH_RATE_WINDOW = timedelta(minutes=1)


def _require_candidate_account(current_user: UserAccount) -> None:
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="Candidate access is required.")


def _get_owned_mock_interview(
    interview_id: str,
    current_user: UserAccount,
    db: Session,
) -> MockInterview:
    if not interview_id.startswith("mock_"):
        raise HTTPException(status_code=404, detail="Interview session not found.")
    try:
        record_id = int(interview_id.removeprefix("mock_"))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Interview session not found.") from exc
    record = db.query(MockInterview).filter(MockInterview.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this interview session.")
    return record


def _mock_interview_history_item(record: MockInterview) -> dict:
    try:
        turns = json.loads(record.transcript or "[]")
    except (TypeError, ValueError):
        turns = []
    if not isinstance(turns, list):
        turns = []
    context = turns[0].get("session_context", {}) if turns and isinstance(turns[0], dict) else {}
    if not isinstance(context, dict):
        context = {}
    evaluated = [
        turn for turn in turns
        if isinstance(turn, dict) and turn.get("evaluation")
    ]
    return {
        "id": record.id,
        "role": record.role,
        "experience": context.get("experience"),
        "interview_type": context.get("interview_type"),
        "skills": context.get("skills", []),
        "company": record.company_target,
        "interviewer_persona": record.interviewer_persona,
        "interview_mode": record.interview_mode,
        "status": record.status,
        "score": record.score if record.status == "completed" else None,
        "technical_score": record.technical_accuracy if record.status == "completed" else None,
        "communication_score": record.communication_clarity if record.status == "completed" else None,
        "problem_solving_score": record.confidence_score if record.status == "completed" else None,
        "count": len(evaluated),
        "question_count": context.get("question_count", len(context.get("planned_questions", []))),
        "questions": [
            {
                "question": turn.get("question", ""),
                "answer": turn.get("answer", ""),
                "evaluation": turn.get("evaluation"),
            }
            for turn in evaluated
        ],
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _require_coach_candidate(current_user: UserAccount) -> None:
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="Interview Coach is available to candidate accounts.")


@app.get("/Interview-coach.html", include_in_schema=False)
@app.get("/interview-coach.html", include_in_schema=False)
@app.get("/candidate/Interview-coach.html", include_in_schema=False)
@app.get("/candidate/interview-coach", include_in_schema=False)
@app.get("/interview-coach", include_in_schema=False)
def serve_interview_coach(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Interview Coach", db)
    if block_res:
        return block_res
    return get_html_response("Interview-coach.html", db)


@app.get("/api/coach/conversation", include_in_schema=False)
def get_coach_conversation(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_coach_candidate(current_user)
    if not is_candidate_menu_enabled("Interview Coach", db):
        raise HTTPException(status_code=403, detail="Interview Coach is currently unavailable.")

    conversation = (
        db.query(CoachSession)
        .filter(CoachSession.user_id == current_user.id)
        .order_by(CoachSession.updated_at.desc(), CoachSession.id.desc())
        .first()
    )
    if not conversation:
        return {"conversation_id": None, "messages": []}

    messages = (
        db.query(CoachMessage)
        .filter(CoachMessage.session_id == conversation.id)
        .order_by(CoachMessage.id.desc())
        .limit(100)
        .all()
    )
    messages.reverse()
    return {
        "conversation_id": conversation.id,
        "messages": [
            {
                "role": item.role,
                "message": item.content,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in messages
        ],
    }


@app.get("/api/coach/context", include_in_schema=False)
def get_coach_context(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_coach_candidate(current_user)
    if not is_candidate_menu_enabled("Interview Coach", db):
        raise HTTPException(status_code=403, detail="Interview Coach is currently unavailable.")
    return build_candidate_context(db, current_user)


@app.get("/api/coach/conversations", include_in_schema=False)
def list_coach_conversations(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_coach_candidate(current_user)
    if not is_candidate_menu_enabled("Interview Coach", db):
        raise HTTPException(status_code=403, detail="Interview Coach is currently unavailable.")

    conversations = (
        db.query(CoachSession)
        .filter(CoachSession.user_id == current_user.id)
        .order_by(CoachSession.updated_at.desc(), CoachSession.id.desc())
        .limit(50)
        .all()
    )
    result = []
    for conversation in conversations:
        first_message = (
            db.query(CoachMessage)
            .filter(
                CoachMessage.session_id == conversation.id,
                CoachMessage.role == "user",
            )
            .order_by(CoachMessage.id.asc())
            .first()
        )
        result.append({
            "conversation_id": conversation.id,
            "title": (
                (first_message.content[:60] + "…")
                if first_message and len(first_message.content) > 60
                else first_message.content if first_message else "New conversation"
            ),
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
        })
    return {"conversations": result}


@app.post("/api/coach/conversations", include_in_schema=False)
def create_coach_conversation(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_coach_candidate(current_user)
    if not is_candidate_menu_enabled("Interview Coach", db):
        raise HTTPException(status_code=403, detail="Interview Coach is currently unavailable.")
    conversation = CoachSession(user_id=current_user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return {"conversation_id": conversation.id, "messages": []}


@app.get("/api/coach/conversations/{conversation_id}", include_in_schema=False)
def get_coach_conversation_by_id(
    conversation_id: int,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_coach_candidate(current_user)
    if not is_candidate_menu_enabled("Interview Coach", db):
        raise HTTPException(status_code=403, detail="Interview Coach is currently unavailable.")
    conversation = (
        db.query(CoachSession)
        .filter(
            CoachSession.id == conversation_id,
            CoachSession.user_id == current_user.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Coach conversation not found.")
    messages = (
        db.query(CoachMessage)
        .filter(CoachMessage.session_id == conversation.id)
        .order_by(CoachMessage.id.desc())
        .limit(100)
        .all()
    )
    messages.reverse()
    return {
        "conversation_id": conversation.id,
        "messages": [
            {
                "role": item.role,
                "message": item.content,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in messages
        ],
    }


@app.post("/api/coach/chat", include_in_schema=False)
def chat_with_coach(
    payload: CoachChatRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_coach_candidate(current_user)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")
    if not is_candidate_menu_enabled("Interview Coach", db):
        raise HTTPException(status_code=403, detail="Interview Coach is currently unavailable.")

    now = datetime.utcnow()
    recent_message_count = (
        db.query(func.count(CoachMessage.id))
        .join(CoachSession, CoachMessage.session_id == CoachSession.id)
        .filter(
            CoachSession.user_id == current_user.id,
            CoachMessage.role == "user",
            CoachMessage.created_at >= now - COACH_RATE_WINDOW,
        )
        .scalar()
        or 0
    )
    if recent_message_count >= COACH_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="The Coach is receiving messages too quickly. Please try again shortly.",
        )

    if payload.conversation_id is not None:
        conversation = (
            db.query(CoachSession)
            .filter(
                CoachSession.id == payload.conversation_id,
                CoachSession.user_id == current_user.id,
            )
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Coach conversation not found.")
    else:
        conversation = CoachSession(user_id=current_user.id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    prior_messages = (
        db.query(CoachMessage)
        .filter(CoachMessage.session_id == conversation.id)
        .order_by(CoachMessage.id.desc())
        .limit(10)
        .all()
    )
    prior_messages.reverse()

    try:
        conversation.updated_at = datetime.utcnow()
        db.add(CoachMessage(
            session_id=conversation.id,
            role="user",
            content=message,
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Could not persist Interview Coach message for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=503,
            detail="The AI Coach could not save this conversation. Please try again.",
        ) from exc

    try:
        reply = generate_coach_reply(
            db,
            current_user,
            [(item.role, item.content) for item in prior_messages],
            message,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Interview Coach reply generation failed for user_id=%s",
            current_user.id,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The AI Coach is temporarily unavailable. Please try again in a moment.",
                "conversation_id": conversation.id,
            },
        )

    try:
        conversation.updated_at = datetime.utcnow()
        db.add(CoachMessage(
            session_id=conversation.id,
            role="assistant",
            content=reply,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not persist Interview Coach conversation for user_id=%s", current_user.id)
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The AI Coach could not save this conversation. Please try again.",
                "conversation_id": conversation.id,
            },
        )

    return {"message": reply, "conversation_id": conversation.id}





# NOTE: Database initialization is handled by:
# 1. The FastAPI lifespan handler (on app startup)
# 2. The get_db() dependency (on first request)
# Module-level DB init was REMOVED to prevent FUNCTION_INVOCATION_FAILED on Vercel.
# See: https://vercel.com/docs/functions/runtimes/python — import must be side-effect free.
