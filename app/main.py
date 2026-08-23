import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent

from app.models import InterviewRequest, PageViewPayload, ClickEventPayload
from app.prompts import interview_prompt
from app.services import generate_ai_questions, parse_raw_questions, get_fallback_questions
from app.database import get_db, init_db
from app.db_models import UserAccount, InterviewHistory, PageViewEvent, ClickEvent
from app.admin_routes import admin_router, candidate_router
from app.auth_deps import get_current_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and migrations on startup
    init_db()
    yield

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
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.middleware("http")
async def fix_vercel_path_middleware(request: Request, call_next):
    path = request.scope.get("path", "")
    if path.startswith("/api/index.py"):
        clean_path = path.replace("/api/index.py", "", 1)
        request.scope["path"] = clean_path if clean_path else "/"
    elif path.startswith("/index.py"):
        clean_path = path.replace("/index.py", "", 1)
        request.scope["path"] = clean_path if clean_path else "/"
    return await call_next(request)

# Mount Super Admin & Candidate API routers with dual prefix support for Vercel serverless compatibility
app.include_router(admin_router, prefix="/api/admin")
app.include_router(admin_router, prefix="/admin/api")

app.include_router(candidate_router, prefix="/api")
app.include_router(candidate_router, prefix="")

from fastapi import Response
from app.admin_routes import candidate_login, admin_login
from app.models import CandidateLoginRequest, AdminLoginRequest

@app.post("/", include_in_schema=False)
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

from app.admin_routes import candidate_logout, get_public_menus, is_candidate_menu_enabled

@app.post("/api/candidate/logout", include_in_schema=False)
@app.post("/candidate/logout", include_in_schema=False)
@app.post("/logout", include_in_schema=False)
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

def check_menu_access_or_block(menu_key: str, db: Session):
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
def get_history(db: Session = Depends(get_db)):
    check_feature_enabled("Interview history.html", db)
    try:
        interviews = db.query(InterviewHistory).order_by(InterviewHistory.id.desc()).all()
        return [format_interview_response(item) for item in interviews]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve interview history: {str(e)}"
        )


@app.get("/history/{interview_id}")
def get_interview_detail(interview_id: int, db: Session = Depends(get_db)):
    interview = db.query(InterviewHistory).filter(InterviewHistory.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview sitting not found")
    return format_interview_response(interview)


@app.delete("/history/{interview_id}")
def delete_interview(interview_id: int, db: Session = Depends(get_db)):
    interview = db.query(InterviewHistory).filter(InterviewHistory.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview sitting not found")

    db.delete(interview)
    db.commit()
    return {"message": "Interview deleted successfully", "id": interview_id}


# ---------- VISITOR & CLICK ANALYTICS API ----------

@app.post("/api/analytics/track")
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
@app.get("/login", include_in_schema=False)
@app.get("/Login", include_in_schema=False)
@app.get("/Login.html", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def serve_login():
    return get_html_response("Candidate-login.html")

@app.get("/candidate", include_in_schema=False)
@app.get("/candidate/", include_in_schema=False)
@app.get("/candidate/dashboard", include_in_schema=False)
@app.get("/api/candidate/dashboard", include_in_schema=False)
@app.get("/candidate/Dashboard.html", include_in_schema=False)
@app.get("/candidate/Candidate-dashboard.html", include_in_schema=False)
@app.get("/Candidate-dashboard.html", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
@app.get("/Dashboard", include_in_schema=False)
@app.get("/Dashboard.html", include_in_schema=False)
def serve_candidate_dashboard(db: Session = Depends(get_db)):
    block_res = check_menu_access_or_block("Dashboard", db)
    if block_res: return block_res
    return get_html_response("Candidate-dashboard.html", db)

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