from sqlalchemy import Column, Integer, String, Text
from app.database import Base


class InterviewHistory(Base):
    __tablename__ = "interview_history"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String)
    experience = Column(String)
    skills = Column(Text)
    difficulty = Column(String)
    questions = Column(Text)