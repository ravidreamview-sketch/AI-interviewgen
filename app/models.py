from pydantic import BaseModel, Field
from typing import List, Optional

class InterviewRequest(BaseModel):
    role: str = Field(..., min_length=2)
    experience: Optional[str] = Field("Mid Level (3-5 Years)")
    skills: Optional[List[str]] = Field(default_factory=list)
    difficulty: Optional[str] = Field("Hard")
    number_of_questions: Optional[int] = Field(5, ge=1, le=50)
    company: Optional[str] = Field("General Tech", description="Target company bar (e.g. Google, Amazon, Meta, Microsoft)")
    interview_type: Optional[str] = Field("Technical & Architecture", description="Interview round format")
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