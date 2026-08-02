from pydantic import BaseModel, Field
from typing import List

class InterviewRequest(BaseModel):
    role: str = Field(..., min_length=2)
    experience: str
    skills: List[str]
    difficulty: str
    number_of_questions: int = Field(..., ge=10, le=50)