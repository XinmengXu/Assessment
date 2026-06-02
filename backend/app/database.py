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
    locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Condition(Base):
    __tablename__ = "conditions"

    id = Column(Integer, primary_key=True, index=True)
    study_id = Column(Integer, ForeignKey("studies.id"), default=1)
    condition_name = Column(String, nullable=False)
    condition_code = Column(String, default="")
    show_transcript = Column(Boolean, default=True)
    show_score = Column(Boolean, default=True)
    show_comment = Column(Boolean, default=True)
    show_word_focus = Column(Boolean, default=True)
    show_sound_focus = Column(Boolean, default=True)
    show_practice_suggestion = Column(Boolean, default=True)
    show_diagnosis = Column(Boolean, default=False)
    show_explanation = Column(Boolean, default=False)
    show_action_guidance = Column(Boolean, default=False)
    allow_revision = Column(Boolean, default=True)
    enable_teacher_feedback = Column(Boolean, default=False)
    enable_peer_feedback = Column(Boolean, default=False)
    adaptive_feedback = Column(Boolean, default=False)
    human_validation_required = Column(Boolean, default=False)
    llm_verbalization_enabled = Column(Boolean, default=False)
    revision_allowed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_code = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, index=True, nullable=False)
    display_name = Column(String, default="")
    class_id = Column(Integer, default=0, index=True)
    group_id = Column(Integer, default=0, index=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ClassRoom(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True)
    class_code = Column(String, unique=True, index=True, nullable=False)
    class_name = Column(String, default="")
    teacher_user_id_optional = Column(Integer, default=0, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LearnerGroup(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    group_code = Column(String, unique=True, index=True, nullable=False)
    class_id = Column(Integer, default=0, index=True)
    group_name = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_code = Column(String, default="")
    task_type = Column(String, default="practice")
    target_text = Column(Text, nullable=False)
    issue_types_json = Column(Text, default="[]")
    focus_words = Column(Text, default="[]")
    focus_phonemes_json = Column(Text, default="[]")
    word_phoneme_map_json = Column(Text, default="{}")
    speaking_target = Column(String, default="")
    difficulty = Column(String, default="medium")
    model_audio_path = Column(String, default="")
    model_audio_source = Column(String, default="tts")
    tts_sentence_audio_path = Column(String, default="")
    tts_focus_word_audio_json = Column(Text, default="{}")
    uploaded_sentence_audio_path_optional = Column(String, default="")
    uploaded_focus_word_audio_json_optional = Column(Text, default="{}")
    tts_voice = Column(String, default="browser-default")
    tts_status = Column(String, default="browser_only")
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
    system_version_id = Column(Integer, default=1)
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
    validation_status = Column(String, default="draft_generated")
    released_to_learner = Column(Boolean, default=True)
    original_feedback_json = Column(Text, default="{}")
    validated_feedback_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class PronunciationEvidence(Base):
    __tablename__ = "pronunciation_evidence"

    id = Column(Integer, primary_key=True)
    study_id = Column(Integer, default=1)
    condition_id = Column(Integer, default=0)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    source_name = Column(String, default="")
    evidence_level = Column(String, default="asr_supported_cue")
    score_level = Column(String, default="word")
    target_word = Column(String, default="")
    target_phoneme = Column(String, default="")
    observed_phoneme = Column(String, nullable=True)
    score = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    issue_type = Column(String, default="")
    notes = Column(Text, default="")
    system_version_id = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class DiagnosisRecord(Base):
    __tablename__ = "diagnosis_records"

    id = Column(Integer, primary_key=True)
    study_id = Column(Integer, default=1)
    condition_id = Column(Integer, default=0)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    evidence_level = Column(String, default="asr_supported_cue")
    diagnosis_level = Column(String, default="word")
    evidence_source = Column(String, default="asr_alignment")
    confidence_level = Column(String, default="low")
    target_word = Column(String, default="")
    target_phoneme = Column(String, default="")
    observed_phoneme = Column(String, nullable=True)
    issue_type = Column(String, default="")
    speaking_target = Column(String, default="")
    severity = Column(String, default="moderate")
    pedagogical_interpretation = Column(Text, default="")
    requires_human_validation = Column(Boolean, default=False)
    allowed_feedback_strength = Column(String, default="cautious")
    feedback_text = Column(Text, default="")
    system_version_id = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExternalAssessmentScore(Base):
    __tablename__ = "external_assessment_scores"

    id = Column(Integer, primary_key=True)
    study_id = Column(Integer, default=1)
    condition_id = Column(Integer, default=0)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    participant_code = Column(String, default="")
    task_code = Column(String, default="")
    attempt_number = Column(Integer, default=1)
    source_name = Column(String, default="")
    score_level = Column(String, default="")
    target_word = Column(String, default="")
    target_phoneme = Column(String, default="")
    observed_phoneme_optional = Column(String, default="")
    score = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    issue_type_optional = Column(String, default="")
    notes_optional = Column(Text, default="")
    system_version_id = Column(Integer, default=1)
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
    target_word = Column(String, default="")
    target_phoneme = Column(String, default="")
    observed_phoneme = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class TeacherOrchestrationEvent(Base):
    __tablename__ = "teacher_orchestration_events"

    id = Column(Integer, primary_key=True)
    study_id = Column(Integer, default=1)
    condition_id = Column(Integer, default=0)
    teacher_id = Column(String, default="")
    class_id = Column(String, default="")
    participant_id_optional = Column(String, default="")
    task_id = Column(Integer, default=0)
    attempt_id = Column(Integer, default=0)
    issue_type = Column(String, default="")
    target_phoneme_optional = Column(String, default="")
    dashboard_signal_json = Column(Text, default="{}")
    recommended_action = Column(Text, default="")
    teacher_action_taken = Column(Text, default="")
    notes = Column(Text, default="")
    system_version_id = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)


class TeacherFeedback(Base):
    __tablename__ = "teacher_feedback"

    id = Column(Integer, primary_key=True)
    teacher_user_id = Column(Integer, index=True, default=0)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    pronunciation_rating = Column(Float, default=0.0)
    fluency_rating = Column(Float, default=0.0)
    comprehensibility_rating = Column(Float, default=0.0)
    target_word = Column(String, default="")
    target_phoneme = Column(String, default="")
    observed_phoneme = Column(String, default="")
    comment = Column(Text, default="")
    action_guidance = Column(Text, default="")
    status = Column(String, default="draft")
    released_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PeerReviewAssignment(Base):
    __tablename__ = "peer_review_assignments"

    id = Column(Integer, primary_key=True)
    reviewer_user_id = Column(Integer, index=True, default=0)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    status = Column(String, default="assigned")
    created_at = Column(DateTime, default=datetime.utcnow)


class PeerFeedback(Base):
    __tablename__ = "peer_feedback"

    id = Column(Integer, primary_key=True)
    assignment_id = Column(Integer, index=True, default=0)
    reviewer_user_id = Column(Integer, index=True, default=0)
    participant_id = Column(String, index=True)
    task_id = Column(Integer, index=True)
    attempt_id = Column(Integer, index=True)
    clarity_rating = Column(Float, default=0.0)
    encouragement = Column(Text, default="")
    suggestion = Column(Text, default="")
    status = Column(String, default="submitted")
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
            "focus_phonemes_json": "TEXT DEFAULT '[]'",
            "word_phoneme_map_json": "TEXT DEFAULT '{}'",
            "model_audio_source": "VARCHAR DEFAULT 'tts'",
            "tts_sentence_audio_path": "VARCHAR DEFAULT ''",
            "tts_focus_word_audio_json": "TEXT DEFAULT '{}'",
            "uploaded_sentence_audio_path_optional": "VARCHAR DEFAULT ''",
            "uploaded_focus_word_audio_json_optional": "TEXT DEFAULT '{}'",
            "tts_voice": "VARCHAR DEFAULT 'browser-default'",
            "tts_status": "VARCHAR DEFAULT 'browser_only'",
            "feedback_allowed": "BOOLEAN DEFAULT 1",
            "revision_allowed": "BOOLEAN DEFAULT 1",
            "active": "BOOLEAN DEFAULT 1",
        },
        "studies": {
            "locked": "BOOLEAN DEFAULT 0",
        },
        "conditions": {
            "show_comment": "BOOLEAN DEFAULT 1",
            "show_word_focus": "BOOLEAN DEFAULT 1",
            "show_sound_focus": "BOOLEAN DEFAULT 1",
            "show_practice_suggestion": "BOOLEAN DEFAULT 1",
            "allow_revision": "BOOLEAN DEFAULT 1",
            "enable_teacher_feedback": "BOOLEAN DEFAULT 0",
            "enable_peer_feedback": "BOOLEAN DEFAULT 0",
        },
        "attempts": {
            "study_id": "INTEGER DEFAULT 1",
            "condition_id": "INTEGER DEFAULT 4",
            "system_version_id": "INTEGER DEFAULT 1",
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
        "feedback_items": {
            "validation_status": "VARCHAR DEFAULT 'draft_generated'",
            "released_to_learner": "BOOLEAN DEFAULT 1",
            "original_feedback_json": "TEXT DEFAULT '{}'",
            "validated_feedback_json": "TEXT DEFAULT '{}'",
        },
        "annotations": {
            "target_word": "VARCHAR DEFAULT ''",
            "target_phoneme": "VARCHAR DEFAULT ''",
            "observed_phoneme": "VARCHAR DEFAULT ''",
        },
        "diagnosis_records": {
            "diagnosis_level": "VARCHAR DEFAULT 'word'",
            "issue_type": "VARCHAR DEFAULT ''",
            "speaking_target": "VARCHAR DEFAULT ''",
            "severity": "VARCHAR DEFAULT 'moderate'",
            "pedagogical_interpretation": "TEXT DEFAULT ''",
            "requires_human_validation": "BOOLEAN DEFAULT 0",
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


def seed_pilot_accounts():
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        class_row = ClassRoom(class_code="CLASS-A", class_name="Pilot Class A")
        db.add(class_row)
        db.commit()
        db.refresh(class_row)
        group_row = LearnerGroup(group_code="GROUP-A1", class_id=class_row.id, group_name="AI plus teacher feedback")
        db.add(group_row)
        db.commit()
        db.refresh(group_row)
        teacher = User(user_code="teacher001", role="teacher", display_name="Pilot Teacher", class_id=class_row.id, group_id=group_row.id)
        student = User(user_code="student001", role="student", display_name="Pilot Student", class_id=class_row.id, group_id=group_row.id)
        peer = User(user_code="peer001", role="peer_reviewer", display_name="Peer Reviewer", class_id=class_row.id, group_id=group_row.id)
        admin = User(user_code="admin001", role="researcher_admin", display_name="Research Admin", class_id=class_row.id, group_id=group_row.id)
        db.add_all([teacher, student, peer, admin])
        db.commit()
        class_row.teacher_user_id_optional = teacher.id
        participant = Participant(participant_id="student001", participant_code="student001", group_id="G3", group_label="G3 Score + Comment feedback", class_id=str(class_row.id), condition_id=4)
        db.add(participant)
        db.commit()
    finally:
        db.close()


Base.metadata.create_all(bind=engine)
migrate_sqlite_columns()
seed_pilot_accounts()
