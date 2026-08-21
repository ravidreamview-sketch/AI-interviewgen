from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent

from app.models import InterviewRequest, PageViewPayload, ClickEventPayload
from app.prompts import interview_prompt
from app.services import generate_ai_questions, parse_raw_questions
from app.database import get_db, init_db
from app.db_models import InterviewHistory, PageViewEvent, ClickEvent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and migrations on startup
    init_db()
    yield


app = FastAPI(
    title="Ravi — AI Interview Question Generator API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/generate")
def generate_questions(
    data: InterviewRequest,
    db: Session = Depends(get_db)
):
    try:
        prompt = interview_prompt(data)
        raw_output = generate_ai_questions(prompt)
        clean_questions = parse_raw_questions(raw_output)

        if not clean_questions:
            clean_questions = [q.strip() for q in raw_output.split("\n") if q.strip()]

        interview = InterviewHistory(
            role=data.role,
            experience=data.experience,
            skills=", ".join(data.skills),
            difficulty=data.difficulty,
            questions=raw_output,
            created_at=datetime.utcnow()
        )

        db.add(interview)
        db.commit()
        db.refresh(interview)

        res = format_interview_response(interview)
        res["message"] = "Interview questions generated and saved successfully"
        return res

    except ValueError as ve:
        raise HTTPException(
            status_code=400,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate interview questions: {str(e)}"
        )


@app.get("/history")
def get_history(db: Session = Depends(get_db)):
    try:
        interviews = db.query(InterviewHistory).order_by(InterviewHistory.id.desc()).all()
        return [format_interview_response(item) for item in interviews]
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


# ---------- FRONTEND PAGES & ASSETS ----------

@app.get("/analytics", include_in_schema=False)
@app.get("/Analytics", include_in_schema=False)
@app.get("/Analytics.html", include_in_schema=False)
def serve_analytics():
    f = BASE_DIR / "Analytics.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Analytics.html not found")

@app.get("/analytics-tracker.js", include_in_schema=False)
def serve_tracker_script():
    f = BASE_DIR / "analytics-tracker.js"
    return FileResponse(f, media_type="application/javascript") if f.exists() else HTTPException(404, "analytics-tracker.js not found")

@app.get("/", include_in_schema=False)
@app.get("/login", include_in_schema=False)
@app.get("/Login", include_in_schema=False)
@app.get("/Login.html", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def serve_login():
    f = BASE_DIR / "Login.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Login.html not found")

@app.get("/dashboard", include_in_schema=False)
@app.get("/Dashboard", include_in_schema=False)
@app.get("/Dashboard.html", include_in_schema=False)
def serve_dashboard():
    f = BASE_DIR / "Dashboard.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Dashboard.html not found")

@app.get("/studio", include_in_schema=False)
@app.get("/Studio", include_in_schema=False)
@app.get("/Interview-studio", include_in_schema=False)
@app.get("/interview-studio", include_in_schema=False)
@app.get("/Interview-studio.html", include_in_schema=False)
def serve_studio():
    f = BASE_DIR / "Interview-studio.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Interview-studio.html not found")

@app.get("/mock-interview", include_in_schema=False)
@app.get("/Mock-interview", include_in_schema=False)
@app.get("/Mock-interview.html", include_in_schema=False)
def serve_mock():
    f = BASE_DIR / "Mock-interview.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Mock-interview.html not found")

@app.get("/resume-match", include_in_schema=False)
@app.get("/Resume-match", include_in_schema=False)
@app.get("/Resume-match.html", include_in_schema=False)
def serve_resume():
    f = BASE_DIR / "Resume-match.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Resume-match.html not found")

@app.get("/company-playbooks", include_in_schema=False)
@app.get("/Company-playbooks", include_in_schema=False)
@app.get("/Company-playbooks.html", include_in_schema=False)
def serve_playbooks():
    f = BASE_DIR / "Company-playbooks.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Company-playbooks.html not found")

@app.get("/history-page", include_in_schema=False)
@app.get("/Interview-history", include_in_schema=False)
@app.get("/interview-history", include_in_schema=False)
@app.get("/Interview history.html", include_in_schema=False)
@app.get("/Interview%20history.html", include_in_schema=False)
def serve_history_page():
    f = BASE_DIR / "Interview history.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Interview history.html not found")

@app.get("/upgrade-pro", include_in_schema=False)
@app.get("/Upgrade-pro", include_in_schema=False)
@app.get("/Upgrade-pro.html", include_in_schema=False)
def serve_upgrade():
    f = BASE_DIR / "Upgrade-pro.html"
    return FileResponse(f) if f.exists() else HTTPException(404, "Upgrade-pro.html not found")

@app.get("/logo.png", include_in_schema=False)
def serve_logo():
    f = BASE_DIR / "logo.png"
    return FileResponse(f) if f.exists() else HTTPException(404, "logo.png not found")