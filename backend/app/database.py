from datetime import datetime
from sqlalchemy import create_engine, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DB_PATH, ensure_data_dirs


ensure_data_dirs()
engine = create_engine(
    "sqlite:///" + str(DB_PATH),
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Participant(Base):
    __tablename__ = "participants"

    participant_id = Column(String, primary_key=True, index=True)
    group_id = Column(String, index=True, nullable=False)
    session_id = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    target_text = Column(Text, nullable=False)
    focus_words = Column(Text, default="[]")
    speaking_target = Column(String, default="")
    difficulty = Column(String, default="medium")
    model_audio_path = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Attempt(Base):
    __tablename__ = "attempts"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(String, ForeignKey("participants.participant_id"), index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), index=True)
    group_id = Column(String, index=True)
    attempt_number = Column(Integer, nullable=False)
    audio_path = Column(String, nullable=False)
    asr_transcript = Column(Text, default="")
    duration_seconds = Column(Float, default=0.0)
    speech_rate_wpm = Column(Float, default=0.0)
    word_match_score = Column(Float, default=0.0)
    missing_words_json = Column(Text, default="[]")
    substitutions_json = Column(Text, default="[]")
    long_pause_count = Column(Integer, default=0)
    feedback_type = Column(String, default="score_only")
    feedback_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task")


class FeedbackView(Base):
    __tablename__ = "feedback_views"

    id = Column(Integer, primary_key=True)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    viewed_at = Column(DateTime, default=datetime.utcnow)


class RevisionEvent(Base):
    __tablename__ = "revision_events"

    id = Column(Integer, primary_key=True)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    previous_attempt_id = Column(Integer)
    new_attempt_id = Column(Integer)
    score_delta = Column(Float, default=0.0)
    transcript_change = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class ExportedReport(Base):
    __tablename__ = "exported_reports"

    id = Column(Integer, primary_key=True)
    report_type = Column(String, index=True)
    path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
