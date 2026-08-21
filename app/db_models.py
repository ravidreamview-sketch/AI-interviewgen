from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.database import Base


class InterviewHistory(Base):
    __tablename__ = "interview_history"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False)
    experience = Column(String, nullable=False)
    skills = Column(Text, nullable=False)
    difficulty = Column(String, nullable=False)
    questions = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PageViewEvent(Base):
    __tablename__ = "page_view_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    page_url = Column(String, nullable=False)
    page_title = Column(String, nullable=True)
    referrer = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    browser = Column(String, nullable=True)
    os = Column(String, nullable=True)
    device_type = Column(String, nullable=True)
    screen_resolution = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class ClickEvent(Base):
    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    page_url = Column(String, nullable=False)
    element_tag = Column(String, nullable=True)
    element_id = Column(String, nullable=True)
    element_text = Column(String, nullable=True)
    element_class = Column(String, nullable=True)
    target_role = Column(String, nullable=True)
    action_type = Column(String, nullable=True)
    browser = Column(String, nullable=True)
    os = Column(String, nullable=True)
    device_type = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)