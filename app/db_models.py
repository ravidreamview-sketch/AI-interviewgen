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