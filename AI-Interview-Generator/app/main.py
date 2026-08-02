from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models import InterviewRequest
from app.prompts import interview_prompt
from app.services import generate_ai_questions
from app.database import get_db
from app.db_models import InterviewHistory
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.post("/generate")
def generate_questions(
    data: InterviewRequest,
    db: Session = Depends(get_db)
):
    try:
        prompt = interview_prompt(data)

        questions = generate_ai_questions(prompt).split("\n")
        questions = [q.strip() for q in questions if q.strip()]

        interview = InterviewHistory(
            role=data.role,
            experience=data.experience,
            skills=", ".join(data.skills),
            difficulty=data.difficulty,
            questions="\n".join(questions)
        )

        db.add(interview)
        db.commit()
        db.refresh(interview)

        return {
            "message": "Interview saved successfully",
            "id": interview.id,
            "role": interview.role,
            "experience": interview.experience,
            "difficulty": interview.difficulty,
            "questions": questions
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate interview questions: {str(e)}"
        )


@app.get("/history")
def get_history(db: Session = Depends(get_db)):
    interviews = db.query(InterviewHistory).all()
    return interviews