from datetime import datetime
from sqlalchemy import Boolean, create_engine, Column, DateTime, Float, ForeignKey, Integer, String, Text
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
    id = Column(Integer, index=True)
    participant_code = Column(String, index=True)
    study_id = Column(Integer, default=1)
    condition_id = Column(Integer, default=4)
    group_id = Column(String, index=True, nullable=False)
    group_label = Column(String, default="")
    class_id = Column(String, default="")
    proficiency_level = Column(String, default="")
    l1_background_optional = Column(String, default="")
    session_id = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Study(Base):
    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, index=True)
    study_name = Column(String, nullable=False)
    description = Column(Text, default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Condition(Base):
    __tablename__ = "conditions"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id"), default=1)
    condition_name = Column(String, nullable=False)
    condition_code = Column(String, default="")
    show_transcript = Column(Boolean, default=True)
    show_score = Column(Boolean, default=True)
    show_diagnosis = Column(Boolean, default=False)
    show_explanation = Column(Boolean, default=False)
    show_action_guidance = Column(Boolean, default=False)
    adaptive_feedback = Column(Boolean, default=False)
    human_validation_required = Column(Boolean, default=False)
    llm_verbalization_enabled = Column(Boolean, default=False)
    revision_allowed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_code = Column(String, default="")
    task_type = Column(String, default="practice")
    target_text = Column(Text, nullable=False)
    issue_types_json = Column(Text, default="[]")
    focus_words = Column(Text, default="[]")
    speaking_target = Column(String, default="")
    difficulty = Column(String, default="medium")
    model_audio_path = Column(String, default="")
    feedback_allowed = Column(Boolean, default=True)
    revision_allowed = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Attempt(Base):
    __tablename__ = "attempts"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(String, ForeignKey("participants.participant_id"), index=True)
    study_id = Column(Integer, default=1)
    condition_id = Column(Integer, default=4)
    task_id = Column(Integer, ForeignKey("tasks.id"), index=True)
    group_id = Column(String, index=True)
    attempt_number = Column(Integer, nullable=False)
    audio_path = Column(String, nullable=False)
    asr_adapter = Column(String, default="mock_asr")
    asr_transcript = Column(Text, default="")
    transcript_confidence_optional = Column(Float, default=0.0)
    duration_seconds = Column(Float, default=0.0)
    speech_rate_wpm = Column(Float, default=0.0)
    word_match_score = Column(Float, default=0.0)
    assessment_score = Column(Float, default=0.0)
    missing_words_json = Column(Text, default="[]")
    substitutions_json = Column(Text, default="[]")
    issue_types_detected_json = Column(Text, default="[]")
    alignment_json = Column(Text, default="{}")
    asr_sanity_json = Column(Text, default="{}")
    score_breakdown_json = Column(Text, default="{}")
    valid_audio = Column(Boolean, default=True)
    long_pause_count = Column(Integer, default=0)
    feedback_generated = Column(Boolean, default=True)
    feedback_shown = Column(Boolean, default=True)
    feedback_type = Column(String, default="score_only")
    feedback_policy_id = Column(String, default="")
    feedback_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task")


class FeedbackView(Base):
    __tablename__ = "feedback_views"

    id = Column(Integer, primary_key=True)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    feedback_item_id = Column(Integer, default=0)
    view_duration_ms_optional = Column(Integer, default=0)
    viewed_at = Column(DateTime, default=datetime.utcnow)


class FeedbackItem(Base):
    __tablename__ = "feedback_items"

    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, index=True)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    issue_type = Column(String, default="")
    diagnosis = Column(Text, default="")
    explanation = Column(Text, default="")
    action_guidance = Column(Text, default="")
    revision_goal = Column(Text, default="")
    metacognitive_prompt = Column(Text, default="")
    source = Column(String, default="template")
    approved_by_human = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RevisionEvent(Base):
    __tablename__ = "revision_events"

    id = Column(Integer, primary_key=True)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    previous_attempt_id = Column(Integer)
    new_attempt_id = Column(Integer)
    score_delta = Column(Float, default=0.0)
    word_match_delta = Column(Float, default=0.0)
    repeated_issue_reduced = Column(Boolean, default=False)
    transcript_change = Column(Text, default="")
    transcript_change_summary = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class LearnerState(Base):
    __tablename__ = "learner_states"

    id = Column(Integer, primary_key=True)
    participant_id = Column(String, index=True)
    after_attempt_id = Column(Integer, index=True)
    pronunciation_clarity = Column(Float, default=0.0)
    fluency_stability = Column(Float, default=0.0)
    feedback_uptake = Column(Float, default=0.0)
    revision_responsiveness = Column(Float, default=0.0)
    persistent_issues_json = Column(Text, default="[]")
    state_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class IssueRecord(Base):
    __tablename__ = "issue_records"

    id = Column(Integer, primary_key=True)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    issue_type = Column(String, index=True)
    target_word = Column(String, default="")
    severity = Column(Float, default=1.0)
    evidence_json = Column(Text, default="{}")
    repeated_count = Column(Integer, default=1)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True)
    annotator_id = Column(String, default="")
    attempt_id = Column(Integer, index=True)
    transcript_acceptable = Column(Boolean, default=True)
    human_missing_words_json = Column(Text, default="[]")
    human_unclear_words_json = Column(Text, default="[]")
    human_substitutions_json = Column(Text, default="[]")
    human_long_pause_count = Column(Integer, default=0)
    pronunciation_rating = Column(Float, default=0.0)
    fluency_rating = Column(Float, default=0.0)
    comprehensibility_rating = Column(Float, default=0.0)
    feedback_appropriate = Column(Boolean, default=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class FeedbackTemplate(Base):
    __tablename__ = "feedback_templates"

    id = Column(Integer, primary_key=True)
    issue_type = Column(String, index=True)
    feedback_level = Column(String, default="standard")
    condition = Column(String, default="explainable")
    diagnosis_template = Column(Text, default="")
    explanation_template = Column(Text, default="")
    action_template = Column(Text, default="")
    revision_goal_template = Column(Text, default="")
    metacognitive_prompt_template = Column(Text, default="")
    expert_review_status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemVersion(Base):
    __tablename__ = "system_versions"

    id = Column(Integer, primary_key=True)
    asr_adapter = Column(String, default="mock_asr")
    assessment_adapter = Column(String, default="rule_assessment")
    scoring_version = Column(String, default="v1")
    feedback_policy_version = Column(String, default="v1")
    template_bank_version = Column(String, default="v1")
    app_version = Column(String, default="0.2.0")
    created_at = Column(DateTime, default=datetime.utcnow)


class ExportedReport(Base):
    __tablename__ = "exported_reports"

    id = Column(Integer, primary_key=True)
    report_type = Column(String, index=True)
    path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_columns()


def migrate_sqlite_columns():
    columns = {
        "participants": {
            "id": "INTEGER",
            "participant_code": "VARCHAR",
            "study_id": "INTEGER DEFAULT 1",
            "condition_id": "INTEGER DEFAULT 4",
            "group_label": "VARCHAR DEFAULT ''",
            "class_id": "VARCHAR DEFAULT ''",
            "proficiency_level": "VARCHAR DEFAULT ''",
            "l1_background_optional": "VARCHAR DEFAULT ''",
        },
        "tasks": {
            "task_code": "VARCHAR DEFAULT ''",
            "task_type": "VARCHAR DEFAULT 'practice'",
            "issue_types_json": "TEXT DEFAULT '[]'",
            "feedback_allowed": "BOOLEAN DEFAULT 1",
            "revision_allowed": "BOOLEAN DEFAULT 1",
            "active": "BOOLEAN DEFAULT 1",
        },
        "attempts": {
            "study_id": "INTEGER DEFAULT 1",
            "condition_id": "INTEGER DEFAULT 4",
            "asr_adapter": "VARCHAR DEFAULT 'mock_asr'",
            "transcript_confidence_optional": "FLOAT DEFAULT 0",
            "assessment_score": "FLOAT DEFAULT 0",
            "issue_types_detected_json": "TEXT DEFAULT '[]'",
            "alignment_json": "TEXT DEFAULT '{}'",
            "asr_sanity_json": "TEXT DEFAULT '{}'",
            "score_breakdown_json": "TEXT DEFAULT '{}'",
            "valid_audio": "BOOLEAN DEFAULT 1",
            "feedback_generated": "BOOLEAN DEFAULT 1",
            "feedback_shown": "BOOLEAN DEFAULT 1",
            "feedback_policy_id": "VARCHAR DEFAULT ''",
        },
        "feedback_views": {
            "feedback_item_id": "INTEGER DEFAULT 0",
            "view_duration_ms_optional": "INTEGER DEFAULT 0",
        },
        "revision_events": {
            "word_match_delta": "FLOAT DEFAULT 0",
            "repeated_issue_reduced": "BOOLEAN DEFAULT 0",
            "transcript_change_summary": "TEXT DEFAULT ''",
        },
    }
    with engine.begin() as conn:
        for table_name, table_columns in columns.items():
            existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(%s)" % table_name).fetchall()}
            for column_name, definition in table_columns.items():
                if column_name not in existing:
                    conn.exec_driver_sql("ALTER TABLE %s ADD COLUMN %s %s" % (table_name, column_name, definition))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


Base.metadata.create_all(bind=engine)
migrate_sqlite_columns()
