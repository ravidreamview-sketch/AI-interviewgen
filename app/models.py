from pydantic import BaseModel, Field
from typing import List, Optional

class InterviewRequest(BaseModel):
    role: str = Field(..., min_length=2)
    experience: str
    skills: List[str]
    difficulty: str
    number_of_questions: int = Field(..., ge=1, le=50)
    custom_question: Optional[str] = Field(None, description="Optional specific focus question, case study, or seed prompt to branch related questions from")


class PageViewPayload(BaseModel):
    session_id: str
    page_url: str
    page_title: Optional[str] = None
    referrer: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    device_type: Optional[str] = None
    screen_resolution: Optional[str] = None


class ClickEventPayload(BaseModel):
    session_id: str
    page_url: str
    element_tag: Optional[str] = None
    element_id: Optional[str] = None
    element_text: Optional[str] = None
    element_class: Optional[str] = None
    target_role: Optional[str] = None
    action_type: Optional[str] = None
    browser: Optional[str] = None
    os: Optional[str] = None
    device_type: Optional[str] = None