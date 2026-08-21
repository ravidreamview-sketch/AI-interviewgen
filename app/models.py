from pydantic import BaseModel, Field
from typing import List, Optional

class InterviewRequest(BaseModel):
    role: str = Field(..., min_length=2)
    experience: str
    skills: List[str]
    difficulty: str
    number_of_questions: int = Field(..., ge=1, le=50)
    custom_question: Optional[str] = Field(None, description="Optional specific focus question, case study, or seed prompt to branch related questions from")