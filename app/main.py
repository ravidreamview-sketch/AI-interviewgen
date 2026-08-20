from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent.parent

from app.models import InterviewRequest
from app.prompts import interview_prompt
from app.services import generate_ai_questions, parse_raw_questions
from app.database import get_db, init_db
from app.db_models import InterviewHistory


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


# ---------- FRONTEND PAGES & ASSETS ----------

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