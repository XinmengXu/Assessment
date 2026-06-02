import csv
import json
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from .analysis.asr import asr_service
from .analysis.audio_features import analyze_audio
from .analysis.feedback_generator import generate_feedback
from .analysis.scoring import compute_practice_score
from .analysis.text_alignment import align_text
from .config import AUDIO_DIR, EXPORT_DIR
from .config import ASR_MODE, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL_SIZE
from .database import (
    Annotation,
    Attempt,
    ClassRoom,
    Condition,
    FeedbackItem,
    FeedbackView,
    DiagnosisRecord,
    ExternalAssessmentScore,
    IssueRecord,
    LearnerState,
    LearnerGroup,
    Participant,
    PeerFeedback,
    PeerReviewAssignment,
    PronunciationEvidence,
    RevisionEvent,
    Study,
    SystemVersion,
    TeacherFeedback,
    TeacherOrchestrationEvent,
    Task,
    User,
    get_db,
)
from .schemas import AnnotationCreate, ParticipantCreate, ParticipantRead, TaskCreate, TaskRead
from .services.feedback.feedback_policy import (
    condition_policy,
    derive_feedback_use_state,
    filter_feedback_for_condition,
    normalize_condition,
)
from .services.feedback.issue_taxonomy import issue_records_for_alignment
from .services.asr_sanity import check_asr_sanity
from .services.learner_model.state_update import update_learner_state
from .services.pronunciation.evidence_builder import build_rule_based_evidence
from .services.validation.agreement import annotation_agreement
from .services.verbalization.template_verbalizer import feedback_from_issue, feedback_from_diagnosis


router = APIRouter()


def _json(value, default):
    try:
        return json.loads(value or default)
    except Exception:
        return json.loads(default)


def _task_to_schema(task):
    return TaskRead(
        id=task.id,
        task_code=task.task_code or "",
        task_type=task.task_type or "practice",
        target_text=task.target_text,
        issue_types=_json(task.issue_types_json, "[]"),
        focus_words=_json(task.focus_words, "[]"),
        focus_phonemes=_json(getattr(task, "focus_phonemes_json", "[]"), "[]"),
        word_phoneme_map=_json(getattr(task, "word_phoneme_map_json", "{}"), "{}"),
        speaking_target=task.speaking_target or "",
        difficulty=task.difficulty or "medium",
        model_audio_path=task.model_audio_path or "",
        model_audio_source=getattr(task, "model_audio_source", "tts") or "tts",
        tts_sentence_audio_path=getattr(task, "tts_sentence_audio_path", "") or "",
        tts_focus_word_audio_json=_json(getattr(task, "tts_focus_word_audio_json", "{}"), "{}"),
        uploaded_sentence_audio_path_optional=getattr(task, "uploaded_sentence_audio_path_optional", "") or "",
        uploaded_focus_word_audio_json_optional=_json(getattr(task, "uploaded_focus_word_audio_json_optional", "{}"), "{}"),
        tts_voice=getattr(task, "tts_voice", "browser-default") or "browser-default",
        tts_status=getattr(task, "tts_status", "browser_only") or "browser_only",
        feedback_allowed=bool(task.feedback_allowed),
        revision_allowed=bool(task.revision_allowed),
        active=bool(task.active),
        created_at=task.created_at,
    )


def _attempt_score(attempt):
    feedback = _json(attempt.feedback_json, "{}")
    if feedback.get("no_speech_detected") or feedback.get("valid_audio") is False:
        return None
    return feedback.get("overall_score") if feedback.get("overall_score") is not None else attempt.assessment_score


def _feedback_use_state(db, attempt):
    viewed = db.query(FeedbackView).filter(FeedbackView.attempt_id == attempt.id).count() > 0
    revision = db.query(RevisionEvent).filter(RevisionEvent.previous_attempt_id == attempt.id).first()
    improved = bool(revision and (revision.score_delta > 0 or revision.word_match_delta > 0))
    return derive_feedback_use_state(viewed, revision is not None, improved)


def _attempt_to_dict(db, attempt, base_score=None):
    feedback = _json(attempt.feedback_json, "{}")
    score = _attempt_score(attempt)
    improvement = 0 if score is None or base_score is None else round(score - base_score, 2)
    return {
        "id": attempt.id,
        "participant_id": attempt.participant_id,
        "study_id": attempt.study_id,
        "condition_id": attempt.condition_id,
        "task_id": attempt.task_id,
        "group_id": attempt.group_id,
        "condition": attempt.group_id,
        "attempt_number": attempt.attempt_number,
        "audio_path": attempt.audio_path,
        "asr_adapter": attempt.asr_adapter,
        "asr_transcript": attempt.asr_transcript if feedback.get("show_transcript", True) else "",
        "duration_seconds": attempt.duration_seconds,
        "speech_rate_wpm": attempt.speech_rate_wpm,
        "word_match_score": attempt.word_match_score,
        "assessment_score": attempt.assessment_score,
        "missing_words": _json(attempt.missing_words_json, "[]"),
        "substitutions": _json(attempt.substitutions_json, "[]"),
        "issue_types_detected": _json(attempt.issue_types_detected_json, "[]"),
        "long_pause_count": attempt.long_pause_count,
        "valid_audio": bool(getattr(attempt, "valid_audio", True)),
        "no_speech_detected": bool(feedback.get("no_speech_detected", False)),
        "invalid_reasons": feedback.get("invalid_reasons", []),
        "feedback_generated": bool(attempt.feedback_generated),
        "feedback_shown": bool(attempt.feedback_shown),
        "feedback_type": attempt.feedback_type,
        "feedback": feedback,
        "alignment": _json(getattr(attempt, "alignment_json", "{}"), "{}"),
        "asr_sanity": _json(getattr(attempt, "asr_sanity_json", "{}"), "{}"),
        "score_breakdown": _json(getattr(attempt, "score_breakdown_json", "{}"), "{}"),
        "feedback_use_state": _feedback_use_state(db, attempt),
        "feedback_viewed": db.query(FeedbackView).filter(FeedbackView.attempt_id == attempt.id).count() > 0,
        "re_recorded": db.query(RevisionEvent).filter(RevisionEvent.previous_attempt_id == attempt.id).count() > 0,
        "created_at": attempt.created_at,
        "target_text": attempt.task.target_text if attempt.task else "",
        "task_type": attempt.task.task_type if attempt.task else "",
        "score": score,
        "improvement": improvement,
    }


def _detect_issue_types(task, alignment, features):
    task_issues = _json(task.issue_types_json, "[]")
    focus_words = _json(task.focus_words, "[]")
    issue_records = issue_records_for_alignment(task_issues, focus_words, alignment, features)
    issues = {record["issue_type"] for record in issue_records}
    if features["speech_rate_wpm"] < 70:
        issues.add("speech_rate_slow")
    if features["speech_rate_wpm"] > 180:
        issues.add("speech_rate_fast")
    if features["long_pause_count"] > 0:
        issues.add("long_pause")
    if alignment["missing_words"] or alignment["substitutions"]:
        issues.add("generic_unclear_word")
    return sorted(issues)


def _ensure_unlocked_study(db, study_id):
    study = db.query(Study).filter(Study.id == study_id).first()
    if study and getattr(study, "locked", False):
        raise HTTPException(status_code=400, detail="Study is locked for research mode. Create a new version to modify this setting.")


def _focus_phoneme_for_word(task, word):
    mapping = _json(getattr(task, "word_phoneme_map_json", "{}"), "{}")
    phonemes = mapping.get((word or "").lower()) or mapping.get(word or "") or []
    if phonemes:
        return phonemes[0]
    issues = _json(getattr(task, "issue_types_json", "[]"), "[]")
    fallback = {
        "theta_words": "th",
        "r_l_contrast": "r/l",
        "final_consonants": "final consonant",
        "consonant_clusters": "cluster",
        "vowel_length": "vowel length",
        "word_stress": "stress",
        "rhythm": "rhythm",
    }
    for issue in issues:
        if issue in fallback:
            return fallback[issue]
    return ""


def _target_word_from_alignment(task, alignment):
    focus = {word.lower() for word in _json(task.focus_words, "[]")}
    for word in alignment.get("missing_words", []):
        candidate = word.lower()
        if not focus or candidate in focus:
            return candidate
    for item in alignment.get("substitutions", []):
        candidate = item.get("expected", "").lower()
        if candidate and (not focus or candidate in focus):
            return candidate
    return ""


def _create_asr_supported_records(db, attempt, task, alignment, issue_records):
    rule_evidence = build_rule_based_evidence(task, alignment)
    diagnosis_items = rule_evidence.get("phoneme_diagnosis") or []
    if diagnosis_items:
        issue_records = [{
            "issue_type": (issue_records[0].get("issue_type") if issue_records else "generic_unclear_word"),
            "target_word": item["target_word"],
            "evidence": item["evidence_source"],
            "severity": "moderate",
            "extra": item,
        } for item in diagnosis_items]
    for issue in issue_records:
        target_word = issue.get("target_word") or (alignment.get("missing_words") or [""])[0]
        target_phoneme = _focus_phoneme_for_word(task, target_word)
        text = "The focus word '%s' may not have been clearly recognized." % target_word if target_word else "A focus word may not have been clearly recognized."
        if target_phoneme:
            text += " This may relate to the target sound in this task."
        db.add(PronunciationEvidence(
            study_id=attempt.study_id,
            condition_id=attempt.condition_id,
            participant_id=attempt.participant_id,
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            source_name="asr_alignment",
            evidence_level="asr_supported_cue",
            score_level="word",
            target_word=target_word,
            target_phoneme=target_phoneme,
            observed_phoneme=None,
            score=attempt.word_match_score,
            confidence=0.5 if target_word else 0.25,
            issue_type=issue.get("issue_type", "generic_unclear_word"),
            notes="ASR alignment cue only; no exact phoneme claim.",
            system_version_id=getattr(attempt, "system_version_id", 1),
        ))
        db.add(DiagnosisRecord(
            study_id=attempt.study_id,
            condition_id=attempt.condition_id,
            participant_id=attempt.participant_id,
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            evidence_level="asr_supported_cue",
            diagnosis_level="phoneme" if target_phoneme else "word",
            evidence_source="asr_alignment",
            confidence_level="medium" if target_word else "low",
            target_word=target_word,
            target_phoneme=target_phoneme,
            observed_phoneme=None,
            issue_type=issue.get("issue_type", "generic_unclear_word"),
            speaking_target=task.speaking_target or "pronunciation_clarity",
            severity="moderate",
            pedagogical_interpretation=text,
            requires_human_validation=False,
            allowed_feedback_strength="cautious",
            feedback_text=text,
            system_version_id=getattr(attempt, "system_version_id", 1),
        ))


@router.get("/health")
def health():
    return {
        "status": "ok",
        "mock_mode": ASR_MODE == "mock",
        "asr_adapter": ASR_MODE,
        "whisper_model_size": WHISPER_MODEL_SIZE if ASR_MODE == "faster_whisper" else "",
        "whisper_device": WHISPER_DEVICE if ASR_MODE == "faster_whisper" else "",
        "whisper_compute_type": WHISPER_COMPUTE_TYPE if ASR_MODE == "faster_whisper" else "",
        "app_version": "0.2.0",
    }


ROLE_LABELS = {
    "assessment_only": "Practice score only",
    "ai_feedback": "AI-supported practice feedback",
    "ai_plus_teacher_feedback": "AI feedback plus teacher feedback",
    "ai_plus_peer_feedback": "AI feedback plus peer feedback",
    "ai_plus_teacher_moderated_peer_feedback": "AI plus teacher-moderated peer feedback",
    "teacher_feedback_only": "Teacher feedback only",
    "peer_feedback_only": "Peer feedback only",
}


def _user_dict(user):
    if not user:
        return None
    return {
        "id": user.id,
        "user_code": user.user_code,
        "role": user.role,
        "display_name": user.display_name or user.user_code,
        "class_id": user.class_id,
        "group_id": user.group_id,
        "active": bool(user.active),
        "created_at": user.created_at,
    }


def _user_by_code(db, user_code):
    return db.query(User).filter(User.user_code == user_code, User.active == True).first()  # noqa: E712


def _participant_id_for_user(user):
    return user.user_code if user and user.role == "student" else ""


def _attempt_with_task(db, attempt):
    data = _attempt_to_dict(db, attempt)
    data["audio_url"] = "/api/attempts/%s/audio" % attempt.id
    return data


@router.post("/login")
def login(payload: dict, db: Session = Depends(get_db)):
    user_code = (payload or {}).get("user_code", "").strip()
    if not user_code:
        raise HTTPException(status_code=400, detail="user_code is required")
    user = _user_by_code(db, user_code)
    if not user:
        raise HTTPException(status_code=404, detail="User code not found or inactive")
    return {"user": _user_dict(user), "token_type": "pilot_user_code", "student_friendly_workflows": ROLE_LABELS}


@router.get("/me")
def me(user_code: str, db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code)
    if not user:
        raise HTTPException(status_code=404, detail="User code not found or inactive")
    return _user_dict(user)


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    return [_user_dict(user) for user in db.query(User).order_by(User.id.asc()).all()]


@router.post("/users")
def create_user(payload: dict, db: Session = Depends(get_db)):
    user_code = (payload or {}).get("user_code", "").strip()
    role = (payload or {}).get("role", "student").strip()
    if not user_code:
        raise HTTPException(status_code=400, detail="user_code is required")
    if role not in ["student", "teacher", "peer_reviewer", "researcher_admin"]:
        raise HTTPException(status_code=400, detail="Unknown role")
    user = db.query(User).filter(User.user_code == user_code).first()
    if not user:
        user = User(user_code=user_code, role=role)
        db.add(user)
    user.role = role
    user.display_name = payload.get("display_name", user_code)
    user.class_id = int(payload.get("class_id") or 0)
    user.group_id = int(payload.get("group_id") or 0)
    user.active = bool(payload.get("active", True))
    db.commit()
    db.refresh(user)
    if user.role == "student":
        participant = db.query(Participant).filter(Participant.participant_id == user.user_code).first()
        if not participant:
            db.add(Participant(participant_id=user.user_code, participant_code=user.user_code, group_id="ai_feedback", class_id=str(user.class_id)))
            db.commit()
    return _user_dict(user)


@router.post("/users/import")
def import_users(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = file.file.read().decode("utf-8-sig")
    rows = csv.DictReader(content.splitlines())
    imported = 0
    for row in rows:
        create_user(row, db)
        imported += 1
    return {"imported": imported}


@router.get("/users/export")
def export_users_alias(db: Session = Depends(get_db)):
    return _write_csv(db, "users", [clean_model(user) for user in db.query(User).all()])


@router.get("/classes")
def list_classes(db: Session = Depends(get_db)):
    return [clean_model(row) for row in db.query(ClassRoom).order_by(ClassRoom.id.asc()).all()]


@router.post("/classes")
def create_class(payload: dict, db: Session = Depends(get_db)):
    code = (payload or {}).get("class_code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="class_code is required")
    row = db.query(ClassRoom).filter(ClassRoom.class_code == code).first()
    if not row:
        row = ClassRoom(class_code=code)
        db.add(row)
    row.class_name = payload.get("class_name", code)
    row.teacher_user_id_optional = int(payload.get("teacher_user_id_optional") or 0)
    db.commit()
    db.refresh(row)
    return clean_model(row)


@router.get("/groups")
def list_groups(db: Session = Depends(get_db)):
    return [clean_model(row) for row in db.query(LearnerGroup).order_by(LearnerGroup.id.asc()).all()]


@router.post("/groups")
def create_group(payload: dict, db: Session = Depends(get_db)):
    code = (payload or {}).get("group_code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="group_code is required")
    row = db.query(LearnerGroup).filter(LearnerGroup.group_code == code).first()
    if not row:
        row = LearnerGroup(group_code=code)
        db.add(row)
    row.class_id = int(payload.get("class_id") or 0)
    row.group_name = payload.get("group_name", code)
    db.commit()
    db.refresh(row)
    return clean_model(row)


@router.get("/student/tasks")
def student_tasks(user_code: str = "", db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code) if user_code else None
    if user_code and (not user or user.role != "student"):
        raise HTTPException(status_code=403, detail="Student role required")
    return list_tasks(False, db)


@router.get("/student/feedback")
def student_feedback(user_code: str, db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code)
    if not user or user.role != "student":
        raise HTTPException(status_code=403, detail="Student role required")
    participant_id = _participant_id_for_user(user)
    attempts = [_attempt_with_task(db, attempt) for attempt in db.query(Attempt).filter(Attempt.participant_id == participant_id).order_by(Attempt.created_at.desc()).all()]
    teacher_feedback = [clean_model(row) for row in db.query(TeacherFeedback).filter(TeacherFeedback.participant_id == participant_id, TeacherFeedback.status == "released").all()]
    peer_feedback = [clean_model(row) for row in db.query(PeerFeedback).filter(PeerFeedback.participant_id == participant_id).all()]
    return {"ai_feedback": attempts, "teacher_feedback": teacher_feedback, "peer_feedback": peer_feedback}


@router.get("/student/progress")
def student_progress(user_code: str, db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code)
    if not user or user.role != "student":
        raise HTTPException(status_code=403, detail="Student role required")
    attempts = db.query(Attempt).filter(Attempt.participant_id == user.user_code).order_by(Attempt.created_at.asc()).all()
    latest_score = _attempt_score(attempts[-1]) if attempts else None
    return {
        "attempt_count": len(attempts),
        "tasks_practiced": len({attempt.task_id for attempt in attempts}),
        "feedback_views": db.query(FeedbackView).filter(FeedbackView.participant_id == user.user_code).count(),
        "revisions": db.query(RevisionEvent).filter(RevisionEvent.participant_id == user.user_code).count(),
        "latest_score": latest_score,
    }


@router.get("/attempts/{attempt_id}/audio")
def attempt_audio(attempt_id: int, db: Session = Depends(get_db)):
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    path = Path(attempt.audio_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, filename=path.name)


@router.get("/teacher/classes")
def teacher_classes(user_code: str = "", db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code) if user_code else None
    query = db.query(ClassRoom)
    if user and user.role == "teacher":
        query = query.filter(ClassRoom.teacher_user_id_optional == user.id)
    return [clean_model(row) for row in query.order_by(ClassRoom.id.asc()).all()]


@router.get("/teacher/submissions")
def teacher_submissions(user_code: str = "", db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code) if user_code else None
    query = db.query(Attempt).order_by(Attempt.created_at.desc())
    if user and user.role == "teacher":
        student_codes = [u.user_code for u in db.query(User).filter(User.role == "student", User.class_id == user.class_id).all()]
        query = query.filter(Attempt.participant_id.in_(student_codes or ["__none__"]))
    return [_attempt_with_task(db, attempt) for attempt in query.limit(200).all()]


@router.post("/teacher/feedback")
def create_teacher_feedback(payload: dict, db: Session = Depends(get_db)):
    feedback = TeacherFeedback(
        teacher_user_id=int(payload.get("teacher_user_id") or 0),
        participant_id=payload.get("participant_id", ""),
        task_id=int(payload.get("task_id") or 0),
        attempt_id=int(payload.get("attempt_id") or 0),
        pronunciation_rating=float(payload.get("pronunciation_rating") or 0),
        fluency_rating=float(payload.get("fluency_rating") or 0),
        comprehensibility_rating=float(payload.get("comprehensibility_rating") or 0),
        target_word=payload.get("target_word", ""),
        target_phoneme=payload.get("target_phoneme", ""),
        observed_phoneme=payload.get("observed_phoneme", ""),
        comment=payload.get("comment", ""),
        action_guidance=payload.get("action_guidance", ""),
        status=payload.get("status", "draft"),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return clean_model(feedback)


@router.put("/teacher/feedback/{feedback_id}")
def update_teacher_feedback(feedback_id: int, payload: dict, db: Session = Depends(get_db)):
    feedback = db.query(TeacherFeedback).filter(TeacherFeedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Teacher feedback not found")
    for key in ["participant_id", "target_word", "target_phoneme", "observed_phoneme", "comment", "action_guidance", "status"]:
        if key in payload:
            setattr(feedback, key, payload[key])
    for key in ["pronunciation_rating", "fluency_rating", "comprehensibility_rating"]:
        if key in payload:
            setattr(feedback, key, float(payload[key] or 0))
    db.commit()
    return clean_model(feedback)


@router.post("/teacher/feedback/{feedback_id}/release")
def release_teacher_feedback(feedback_id: int, db: Session = Depends(get_db)):
    feedback = db.query(TeacherFeedback).filter(TeacherFeedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Teacher feedback not found")
    feedback.status = "released"
    feedback.released_at = datetime.utcnow()
    if feedback.observed_phoneme or feedback.target_phoneme:
        db.add(PronunciationEvidence(
            participant_id=feedback.participant_id,
            task_id=feedback.task_id,
            attempt_id=feedback.attempt_id,
            source_name="teacher_feedback",
            evidence_level="human_validated_diagnosis",
            score_level="phoneme",
            target_word=feedback.target_word,
            target_phoneme=feedback.target_phoneme,
            observed_phoneme=feedback.observed_phoneme or None,
            score=feedback.pronunciation_rating,
            confidence=1.0,
            issue_type="teacher_observed_pronunciation",
            notes=feedback.comment,
        ))
    db.commit()
    return clean_model(feedback)


@router.get("/teacher/class-review")
def teacher_class_review(user_code: str = "", db: Session = Depends(get_db)):
    submissions = teacher_submissions(user_code, db)
    needs_review = [row for row in submissions if row.get("score") is None or float(row.get("score") or 0) < 70]
    return {"submissions": submissions[:50], "needs_review": needs_review[:50], "recommended_action": "Review low-score or invalid-audio attempts first."}


@router.get("/teacher/class-summary")
def teacher_class_summary(user_code: str = "", db: Session = Depends(get_db)):
    submissions = teacher_submissions(user_code, db)
    scores = [row["score"] for row in submissions if row.get("score") is not None]
    return {
        "students": len({row["participant_id"] for row in submissions}),
        "attempts": len(submissions),
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "teacher_feedback_released": db.query(TeacherFeedback).filter(TeacherFeedback.status == "released").count(),
    }


@router.get("/peer/review-tasks")
def peer_review_tasks(user_code: str, db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code)
    if not user or user.role != "peer_reviewer":
        raise HTTPException(status_code=403, detail="Peer reviewer role required")
    rows = db.query(PeerReviewAssignment).filter(PeerReviewAssignment.reviewer_user_id == user.id).order_by(PeerReviewAssignment.created_at.desc()).all()
    if not rows:
        latest = db.query(Attempt).filter(Attempt.participant_id != user.user_code).order_by(Attempt.created_at.desc()).first()
        if latest:
            assignment = PeerReviewAssignment(reviewer_user_id=user.id, participant_id=latest.participant_id, task_id=latest.task_id, attempt_id=latest.id)
            db.add(assignment)
            db.commit()
            rows = [assignment]
    result = []
    for row in rows:
        data = clean_model(row)
        attempt = db.query(Attempt).filter(Attempt.id == row.attempt_id).first()
        data["attempt"] = _attempt_with_task(db, attempt) if attempt else None
        result.append(data)
    return result


@router.post("/peer/feedback")
def create_peer_feedback(payload: dict, db: Session = Depends(get_db)):
    feedback = PeerFeedback(
        assignment_id=int(payload.get("assignment_id") or 0),
        reviewer_user_id=int(payload.get("reviewer_user_id") or 0),
        participant_id=payload.get("participant_id", ""),
        task_id=int(payload.get("task_id") or 0),
        attempt_id=int(payload.get("attempt_id") or 0),
        clarity_rating=float(payload.get("clarity_rating") or 0),
        encouragement=payload.get("encouragement", ""),
        suggestion=payload.get("suggestion", ""),
    )
    db.add(feedback)
    assignment = db.query(PeerReviewAssignment).filter(PeerReviewAssignment.id == feedback.assignment_id).first()
    if assignment:
        assignment.status = "submitted"
    db.commit()
    db.refresh(feedback)
    return clean_model(feedback)


@router.get("/peer/submitted-reviews")
def peer_submitted_reviews(user_code: str, db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code)
    if not user or user.role != "peer_reviewer":
        raise HTTPException(status_code=403, detail="Peer reviewer role required")
    return [clean_model(row) for row in db.query(PeerFeedback).filter(PeerFeedback.reviewer_user_id == user.id).order_by(PeerFeedback.created_at.desc()).all()]


@router.post("/tasks/{task_id}/generate-tts")
def generate_task_tts(task_id: int, payload: dict = None, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.model_audio_source = "tts"
    task.tts_voice = (payload or {}).get("tts_voice", "browser-default")
    task.tts_status = "browser_only"
    task.tts_sentence_audio_path = ""
    task.tts_focus_word_audio_json = json.dumps({})
    db.commit()
    return {"task_id": task.id, "tts_status": task.tts_status, "tts_voice": task.tts_voice, "message": "Backend TTS cache is unavailable; browser SpeechSynthesis reference voice will be used."}


@router.post("/tasks/{task_id}/model-audio")
def upload_model_audio(task_id: int, audio: UploadFile = File(...), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    folder = AUDIO_DIR / "model_audio" / str(task_id)
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(audio.filename or "model.wav").suffix or ".wav"
    path = folder / ("sentence%s" % ext)
    with path.open("wb") as f:
        shutil.copyfileobj(audio.file, f)
    task.model_audio_source = "uploaded"
    task.uploaded_sentence_audio_path_optional = str(path)
    task.model_audio_path = str(path)
    db.commit()
    return {"ok": True, "model_audio_source": "uploaded", "audio_url": "/api/tasks/%s/model-audio" % task_id}


@router.get("/tasks/{task_id}/model-audio")
def task_model_audio(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    path = Path(task.uploaded_sentence_audio_path_optional or task.tts_sentence_audio_path or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="No cached model audio; use browser SpeechSynthesis fallback")
    return FileResponse(path, filename=path.name)


@router.get("/tasks/{task_id}/focus-word-audio")
def task_focus_word_audio(task_id: int, word: str = "", db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    audio_map = _json(task.uploaded_focus_word_audio_json_optional or task.tts_focus_word_audio_json, "{}")
    path = Path(audio_map.get(word, ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="No cached focus-word audio; use browser SpeechSynthesis fallback")
    return FileResponse(path, filename=path.name)


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "backend": health(),
        "users": db.query(User).count(),
        "tasks": db.query(Task).count(),
        "attempts": db.query(Attempt).count(),
        "teacher_feedback": db.query(TeacherFeedback).count(),
        "peer_feedback": db.query(PeerFeedback).count(),
        "visible_feature_rule": "Only role-scoped pilot features are shown in normal UI.",
    }


@router.post("/participants", response_model=ParticipantRead)
def create_participant(payload: ParticipantCreate, db: Session = Depends(get_db)):
    condition_key = normalize_condition(payload.group_id)
    condition = db.query(Condition).filter(Condition.condition_code == condition_key).first()
    participant = db.query(Participant).filter(Participant.participant_id == payload.participant_id).first()
    if participant:
        participant.group_id = condition_key
        participant.participant_code = payload.participant_id
        participant.study_id = payload.study_id
        participant.condition_id = condition.id if condition else payload.condition_id
        participant.session_id = payload.session_id or participant.session_id
    else:
        participant = Participant(
            participant_id=payload.participant_id,
            participant_code=payload.participant_id,
            study_id=payload.study_id,
            condition_id=condition.id if condition else payload.condition_id,
            group_id=condition_key,
            group_label=condition.condition_name if condition else condition_key,
            session_id=payload.session_id or "",
        )
        db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


@router.get("/participants")
def list_participants(db: Session = Depends(get_db)):
    return db.query(Participant).order_by(Participant.created_at.desc()).all()


@router.get("/participants/{participant_id}")
def get_participant(participant_id: str, db: Session = Depends(get_db)):
    participant = db.query(Participant).filter(Participant.participant_id == participant_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    return participant


@router.post("/studies")
def create_study(payload: dict, db: Session = Depends(get_db)):
    study = Study(study_name=payload.get("study_name", "New Study"), description=payload.get("description", ""), active=payload.get("active", True))
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


@router.get("/studies")
def list_studies(db: Session = Depends(get_db)):
    return db.query(Study).order_by(Study.id.asc()).all()


@router.post("/studies/{study_id}/lock")
def lock_study(study_id: int, db: Session = Depends(get_db)):
    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    study.locked = True
    db.commit()
    return {"ok": True, "locked": True}


@router.post("/system-version/create")
def create_system_version(payload: dict = None, db: Session = Depends(get_db)):
    payload = payload or {}
    version = SystemVersion(
        asr_adapter=payload.get("asr_adapter", ASR_MODE),
        assessment_adapter=payload.get("assessment_adapter", "rule_based_asr_supported"),
        scoring_version=payload.get("scoring_version", "practice_clarity_v1"),
        feedback_policy_version=payload.get("feedback_policy_version", "policy_v1"),
        template_bank_version=payload.get("template_bank_version", "template_bank_v1"),
        app_version=payload.get("app_version", "0.2.0"),
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.post("/studies/{study_id}/conditions")
def create_condition(study_id: int, payload: dict, db: Session = Depends(get_db)):
    _ensure_unlocked_study(db, study_id)
    condition = Condition(study_id=study_id, **payload)
    db.add(condition)
    db.commit()
    db.refresh(condition)
    return condition


@router.get("/studies/{study_id}/conditions")
def list_conditions(study_id: int, db: Session = Depends(get_db)):
    return db.query(Condition).filter(Condition.study_id == study_id, Condition.condition_code != "llm_verbalized").order_by(Condition.id.asc()).all()


@router.post("/studies/{study_id}/assign")
def assign_participant(study_id: int, payload: dict, db: Session = Depends(get_db)):
    participant_id = payload.get("participant_id")
    condition_code = normalize_condition(payload.get("condition", "explainable"))
    condition = db.query(Condition).filter(Condition.study_id == study_id, Condition.condition_code == condition_code).first()
    if not condition:
        raise HTTPException(status_code=404, detail="Condition not found")
    participant = db.query(Participant).filter(Participant.participant_id == participant_id).first()
    if not participant:
        participant = Participant(participant_id=participant_id, participant_code=participant_id, group_id=condition_code)
        db.add(participant)
    participant.study_id = study_id
    participant.condition_id = condition.id
    participant.group_id = condition_code
    participant.group_label = condition.condition_name
    db.commit()
    return participant


@router.get("/tasks", response_model=List[TaskRead])
def list_tasks(include_inactive: bool = False, db: Session = Depends(get_db)):
    query = db.query(Task)
    if not include_inactive:
        query = query.filter(Task.active == True)  # noqa: E712
    return [_task_to_schema(t) for t in query.order_by(Task.id.asc()).all()]


@router.post("/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    _ensure_unlocked_study(db, 1)
    task = Task(
        task_code=payload.task_code,
        task_type=payload.task_type,
        target_text=payload.target_text,
        issue_types_json=json.dumps(payload.issue_types),
        focus_words=json.dumps(payload.focus_words),
        focus_phonemes_json=json.dumps(payload.focus_phonemes),
        word_phoneme_map_json=json.dumps(payload.word_phoneme_map),
        speaking_target=payload.speaking_target,
        difficulty=payload.difficulty,
        model_audio_path=payload.model_audio_path,
        model_audio_source=payload.model_audio_source,
        tts_sentence_audio_path=payload.tts_sentence_audio_path,
        tts_focus_word_audio_json=json.dumps(payload.tts_focus_word_audio_json),
        uploaded_sentence_audio_path_optional=payload.uploaded_sentence_audio_path_optional,
        uploaded_focus_word_audio_json_optional=json.dumps(payload.uploaded_focus_word_audio_json_optional),
        tts_voice=payload.tts_voice,
        tts_status=payload.tts_status,
        feedback_allowed=payload.feedback_allowed,
        revision_allowed=payload.revision_allowed,
        active=payload.active,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_to_schema(task)


@router.put("/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskCreate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_unlocked_study(db, 1)
    for key, value in payload.model_dump().items():
        if key == "focus_words":
            task.focus_words = json.dumps(value)
        elif key == "focus_phonemes":
            task.focus_phonemes_json = json.dumps(value)
        elif key == "word_phoneme_map":
            task.word_phoneme_map_json = json.dumps(value)
        elif key == "issue_types":
            task.issue_types_json = json.dumps(value)
        elif key == "tts_focus_word_audio_json":
            task.tts_focus_word_audio_json = json.dumps(value)
        elif key == "uploaded_focus_word_audio_json_optional":
            task.uploaded_focus_word_audio_json_optional = json.dumps(value)
        else:
            setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return _task_to_schema(task)


@router.delete("/tasks/{task_id}")
def deactivate_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_unlocked_study(db, 1)
    task.active = False
    db.commit()
    return {"ok": True}


@router.post("/attempts/analyze")
def analyze_attempt(
    participant_id: str = Form(...),
    group_id: str = Form("explainable"),
    task_id: int = Form(...),
    study_id: int = Form(1),
    session_id: str = Form(""),
    transcript_hint: str = Form(""),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    condition_key = normalize_condition(group_id)
    condition = db.query(Condition).filter(Condition.condition_code == condition_key).first()
    participant = db.query(Participant).filter(Participant.participant_id == participant_id).first()
    if not participant:
        participant = Participant(participant_id=participant_id, participant_code=participant_id, group_id=condition_key, study_id=study_id, condition_id=condition.id if condition else 4, session_id=session_id)
        db.add(participant)
    else:
        participant.group_id = condition_key
        participant.condition_id = condition.id if condition else participant.condition_id
        participant.study_id = study_id

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    previous = db.query(Attempt).filter(Attempt.participant_id == participant_id, Attempt.task_id == task_id).order_by(Attempt.attempt_number.desc()).first()
    system_version = db.query(SystemVersion).order_by(SystemVersion.id.desc()).first()
    attempt_number = previous.attempt_number + 1 if previous else 1
    ext = Path(audio.filename or "audio.webm").suffix or ".webm"
    folder = AUDIO_DIR / participant_id / str(task_id)
    folder.mkdir(parents=True, exist_ok=True)
    audio_path = folder / ("attempt_%s%s" % (attempt_number, ext))
    with audio_path.open("wb") as f:
        shutil.copyfileobj(audio.file, f)
    if transcript_hint:
        audio_path.with_suffix(".txt").write_text(transcript_hint, encoding="utf-8")

    transcript = asr_service.transcribe(audio_path, task.target_text)
    alignment = align_text(task.target_text, transcript)
    features = analyze_audio(audio_path, transcript)
    asr_sanity = check_asr_sanity(task.target_text, transcript, features, transcript_hint)
    if not asr_sanity["asr_valid"]:
        features["no_speech_detected"] = True
        features["valid_audio"] = False
        features.setdefault("invalid_reasons", []).extend(asr_sanity["warnings"])
    score_result = compute_practice_score(alignment, features)
    score = score_result["practice_score"]
    issues = _detect_issue_types(task, alignment, features)
    structured = generate_feedback("explainable", score or 0, task.target_text, transcript, alignment, features)
    target_word = _target_word_from_alignment(task, alignment)
    target_phoneme = _focus_phoneme_for_word(task, target_word)
    if target_word:
        repeated = False
        if target_phoneme:
            repeated = db.query(DiagnosisRecord).filter(
                DiagnosisRecord.participant_id == participant_id,
                DiagnosisRecord.target_phoneme == target_phoneme,
            ).count() >= 1
        structured.update(feedback_from_issue(
            target_word,
            target_phoneme,
            task.speaking_target or "pronunciation_clarity",
            repeated=repeated and condition_key == "adaptive_word_sound_feedback",
        ))
    structured["practice_score"] = score
    structured["score_breakdown"] = score_result["score_breakdown"]
    structured["score_note"] = score_result["score_note"]
    structured["asr_sanity"] = asr_sanity
    if features.get("no_speech_detected"):
        score = 0
        feedback = {
            "overall_score": None,
            "practice_score": None,
            "score_breakdown": score_result["score_breakdown"],
            "score_note": score_result["score_note"],
            "no_speech_detected": True,
            "valid_audio": False,
            "feedback_type": "invalid_audio",
            "asr_warnings": asr_sanity["warnings"],
            "invalid_reasons": features.get("invalid_reasons", []),
            "comment": "No valid speech was detected. Please record your voice again.",
        }
    else:
        feedback = filter_feedback_for_condition(condition_key, transcript, score, structured)
    if not task.feedback_allowed and not features.get("no_speech_detected"):
        feedback = filter_feedback_for_condition("assessment_only", transcript, score, structured)
    feedback_type = feedback["feedback_type"]
    feedback_shown = feedback_type not in ["assessment_only", "human_validated_pending"]

    attempt = Attempt(
        participant_id=participant_id,
        study_id=study_id,
        condition_id=condition.id if condition else 4,
        system_version_id=system_version.id if system_version else 1,
        task_id=task_id,
        group_id=condition_key,
        attempt_number=attempt_number,
        audio_path=str(audio_path),
        asr_adapter=ASR_MODE,
        asr_transcript=transcript,
        duration_seconds=features["duration_seconds"],
        speech_rate_wpm=features["speech_rate_wpm"],
        word_match_score=alignment["word_match_score"],
        assessment_score=score,
        missing_words_json=json.dumps(alignment["missing_words"]),
        substitutions_json=json.dumps(alignment["substitutions"]),
        issue_types_detected_json=json.dumps(issues),
        alignment_json=json.dumps(alignment),
        asr_sanity_json=json.dumps(asr_sanity),
        score_breakdown_json=json.dumps(score_result),
        valid_audio=bool(features.get("valid_audio", True)),
        long_pause_count=features["long_pause_count"],
        feedback_generated=True,
        feedback_shown=feedback_shown,
        feedback_type=feedback_type,
        feedback_policy_id=condition_key,
        feedback_json=json.dumps(feedback),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    first_issue = issues[0] if issues else "generic_unclear_word"
    item = FeedbackItem(
        attempt_id=attempt.id,
        participant_id=participant_id,
        task_id=task_id,
        issue_type=first_issue,
        diagnosis=str(feedback.get("diagnosis", feedback.get("comment", ""))),
        explanation=str(feedback.get("explanation", "")),
        action_guidance=str(feedback.get("action_guidance", "")),
        revision_goal=str(feedback.get("revision_instruction", feedback.get("revision_goal", ""))),
        metacognitive_prompt=str(feedback.get("metacognitive_prompt", "")),
        source="adaptive_policy" if feedback_type == "adaptive" else "template",
        approved_by_human=feedback_type != "human_validated_pending",
        validation_status="pending_review" if feedback_type == "human_validated_pending" else "draft_generated",
        released_to_learner=feedback_type != "human_validated_pending",
        original_feedback_json=json.dumps(feedback),
        validated_feedback_json=json.dumps({}),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    if feedback_shown:
        db.add(FeedbackView(participant_id=participant_id, task_id=task_id, attempt_id=attempt.id, feedback_item_id=item.id))

    task_issues = _json(task.issue_types_json, "[]")
    focus_words = _json(task.focus_words, "[]")
    alignment_issue_records = issue_records_for_alignment(task_issues, focus_words, alignment, features)
    for issue in alignment_issue_records:
        db.add(IssueRecord(
            participant_id=participant_id,
            task_id=task_id,
            attempt_id=attempt.id,
            issue_type=issue["issue_type"],
            target_word=issue["target_word"],
            severity=0.5 if issue["severity"] == "moderate" else 1.0,
            evidence_json=json.dumps({"evidence": issue["evidence"], "alignment": alignment, "extra": issue["extra"]}),
        ))
    if features.get("valid_audio", True):
        _create_asr_supported_records(db, attempt, task, alignment, alignment_issue_records)

    if previous:
        prev_score = previous.assessment_score or _attempt_score(previous) or 0
        db.add(RevisionEvent(
            participant_id=participant_id,
            task_id=task_id,
            previous_attempt_id=previous.id,
            new_attempt_id=attempt.id,
            score_delta=(score or 0) - prev_score,
            word_match_delta=alignment["word_match_score"] - previous.word_match_score,
            repeated_issue_reduced=len(issues) < len(_json(previous.issue_types_detected_json, "[]")),
            transcript_change="%s -> %s" % (previous.asr_transcript, transcript),
            transcript_change_summary="Word match delta: %.2f" % (alignment["word_match_score"] - previous.word_match_score),
        ))
    if features.get("valid_audio", True):
        update_learner_state(db, participant_id, attempt)
    db.commit()
    return _attempt_to_dict(db, attempt)


@router.get("/attempts")
def list_attempts(participant: str = "", db: Session = Depends(get_db)):
    query = db.query(Attempt).order_by(Attempt.created_at.desc())
    if participant:
        query = query.filter(Attempt.participant_id == participant)
    return [_attempt_to_dict(db, a) for a in query.limit(500).all()]


@router.get("/attempts/{participant_id}")
def participant_attempts(participant_id: str, db: Session = Depends(get_db)):
    attempts = db.query(Attempt).filter(Attempt.participant_id == participant_id).order_by(Attempt.created_at.asc()).all()
    first_scores = {}
    for attempt in attempts:
        first_scores.setdefault(attempt.task_id, _attempt_score(attempt) or 0)
    return [_attempt_to_dict(db, a, first_scores.get(a.task_id)) for a in attempts]


@router.post("/feedback/{feedback_item_id}/view")
def mark_feedback_viewed(feedback_item_id: int, payload: dict = None, db: Session = Depends(get_db)):
    item = db.query(FeedbackItem).filter(FeedbackItem.id == feedback_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback item not found")
    view = FeedbackView(participant_id=item.participant_id, task_id=item.task_id, attempt_id=item.attempt_id, feedback_item_id=item.id, view_duration_ms_optional=(payload or {}).get("view_duration_ms_optional", 0))
    db.add(view)
    db.commit()
    return {"ok": True}


@router.get("/feedback/pending-review")
def pending_feedback_review(db: Session = Depends(get_db)):
    return [clean_model(item) for item in db.query(FeedbackItem).filter(FeedbackItem.validation_status == "pending_review").all()]


@router.get("/feedback/{attempt_id}")
def feedback_for_attempt(attempt_id: int, db: Session = Depends(get_db)):
    items = db.query(FeedbackItem).filter(FeedbackItem.attempt_id == attempt_id).all()
    return [item for item in items if item.released_to_learner or item.validation_status != "pending_review"]


@router.post("/feedback/{feedback_item_id}/approve")
def approve_feedback(feedback_item_id: int, payload: dict = None, db: Session = Depends(get_db)):
    item = _feedback_item_or_404(db, feedback_item_id)
    item.validation_status = "approved"
    item.approved_by_human = True
    db.commit()
    return _feedback_item_dict(item)


@router.post("/feedback/{feedback_item_id}/edit")
def edit_feedback(feedback_item_id: int, payload: dict, db: Session = Depends(get_db)):
    item = _feedback_item_or_404(db, feedback_item_id)
    item.validation_status = "edited"
    item.approved_by_human = True
    item.validated_feedback_json = json.dumps(payload or {})
    item.diagnosis = payload.get("diagnosis", item.diagnosis)
    item.explanation = payload.get("explanation", item.explanation)
    item.action_guidance = payload.get("action_guidance", item.action_guidance)
    item.revision_goal = payload.get("revision_goal", item.revision_goal)
    attempt = db.query(Attempt).filter(Attempt.id == item.attempt_id).first()
    if attempt and payload.get("observed_phoneme"):
        target_word = payload.get("target_word", item.issue_type)
        target_phoneme = payload.get("target_phoneme", "")
        observed = payload.get("observed_phoneme")
        validated_feedback = feedback_from_diagnosis(type("Record", (), {
            "evidence_level": "human_validated_diagnosis",
            "target_word": target_word,
            "target_phoneme": target_phoneme,
            "observed_phoneme": observed,
            "speaking_target": payload.get("speaking_target", "pronunciation_clarity"),
        })())
        item.diagnosis = validated_feedback["diagnosis"]
        item.explanation = validated_feedback["explanation"]
        item.action_guidance = validated_feedback["action_guidance"]
        item.revision_goal = validated_feedback["revision_goal"]
        item.validated_feedback_json = json.dumps(validated_feedback)
        db.add(PronunciationEvidence(
            study_id=attempt.study_id,
            condition_id=attempt.condition_id,
            participant_id=attempt.participant_id,
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            source_name=payload.get("reviewer_id", "human_reviewer"),
            evidence_level="human_validated_diagnosis",
            score_level="phoneme",
            target_word=target_word,
            target_phoneme=target_phoneme,
            observed_phoneme=observed,
            score=payload.get("score", 0),
            confidence=payload.get("confidence", 1.0),
            issue_type=payload.get("issue_type", item.issue_type),
            notes=payload.get("notes", ""),
            system_version_id=getattr(attempt, "system_version_id", 1),
        ))
        db.add(DiagnosisRecord(
            study_id=attempt.study_id,
            condition_id=attempt.condition_id,
            participant_id=attempt.participant_id,
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            evidence_level="human_validated_diagnosis",
            evidence_source=payload.get("reviewer_id", "human_reviewer"),
            confidence_level="high",
            diagnosis_level="phoneme",
            target_word=target_word,
            target_phoneme=target_phoneme,
            observed_phoneme=observed,
            issue_type=payload.get("issue_type", item.issue_type),
            speaking_target=payload.get("speaking_target", "pronunciation_clarity"),
            severity="moderate",
            pedagogical_interpretation=validated_feedback["diagnosis"],
            requires_human_validation=False,
            allowed_feedback_strength="validated",
            feedback_text=validated_feedback["diagnosis"],
            system_version_id=getattr(attempt, "system_version_id", 1),
        ))
    db.commit()
    return _feedback_item_dict(item)


@router.post("/feedback/{feedback_item_id}/reject")
def reject_feedback(feedback_item_id: int, payload: dict = None, db: Session = Depends(get_db)):
    item = _feedback_item_or_404(db, feedback_item_id)
    item.validation_status = "rejected"
    item.released_to_learner = False
    item.validated_feedback_json = json.dumps(payload or {})
    db.commit()
    return _feedback_item_dict(item)


@router.post("/feedback/{feedback_item_id}/release")
def release_feedback(feedback_item_id: int, db: Session = Depends(get_db)):
    item = _feedback_item_or_404(db, feedback_item_id)
    if item.validation_status == "rejected":
        raise HTTPException(status_code=400, detail="Rejected feedback cannot be released.")
    item.validation_status = "released_to_learner"
    item.released_to_learner = True
    item.approved_by_human = True
    db.commit()
    return _feedback_item_dict(item)


def _feedback_item_or_404(db, feedback_item_id):
    item = db.query(FeedbackItem).filter(FeedbackItem.id == feedback_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback item not found")
    return item


def _feedback_item_dict(item):
    data = clean_model(item)
    data["diagnosis"] = item.diagnosis
    data["explanation"] = item.explanation
    data["action_guidance"] = item.action_guidance
    data["revision_goal"] = item.revision_goal
    data["validation_status"] = item.validation_status
    data["released_to_learner"] = bool(item.released_to_learner)
    data["approved_by_human"] = bool(item.approved_by_human)
    return data


@router.get("/learner-states/{participant_id}")
def learner_states(participant_id: str, db: Session = Depends(get_db)):
    return db.query(LearnerState).filter(LearnerState.participant_id == participant_id).order_by(LearnerState.created_at.asc()).all()


@router.get("/annotations/pending")
def pending_annotations(db: Session = Depends(get_db)):
    annotated = {row.attempt_id for row in db.query(Annotation).all()}
    attempts = db.query(Attempt).order_by(Attempt.created_at.desc()).limit(100).all()
    return [_attempt_to_dict(db, a) for a in attempts if a.id not in annotated]


@router.post("/annotations")
def create_annotation(payload: AnnotationCreate, db: Session = Depends(get_db)):
    annotation = Annotation(
        annotator_id=payload.annotator_id,
        attempt_id=payload.attempt_id,
        transcript_acceptable=payload.transcript_acceptable,
        human_missing_words_json=json.dumps(payload.human_missing_words),
        human_unclear_words_json=json.dumps(payload.human_unclear_words),
        human_substitutions_json=json.dumps(payload.human_substitutions),
        human_long_pause_count=payload.human_long_pause_count,
        pronunciation_rating=payload.pronunciation_rating,
        fluency_rating=payload.fluency_rating,
        comprehensibility_rating=payload.comprehensibility_rating,
        feedback_appropriate=payload.feedback_appropriate,
        notes=payload.notes,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.get("/annotations/report")
def annotations_report(db: Session = Depends(get_db)):
    rows = []
    for annotation in db.query(Annotation).all():
        attempt = db.query(Attempt).filter(Attempt.id == annotation.attempt_id).first()
        if attempt:
            rows.append(annotation_agreement(attempt, annotation))
    return rows


@router.get("/dashboard/summary")
def dashboard_summary(group: str = "", participant: str = "", task_id: int = 0, db: Session = Depends(get_db)):
    query = db.query(Attempt)
    if group:
        query = query.filter(Attempt.group_id == normalize_condition(group))
    if participant:
        query = query.filter(Attempt.participant_id == participant)
    if task_id:
        query = query.filter(Attempt.task_id == task_id)
    attempts = query.all()
    tasks = db.query(Task).filter(Task.active == True).count()  # noqa: E712
    participants = len(set(a.participant_id for a in attempts))
    by_condition = defaultdict(list)
    missing = Counter()
    issues = Counter()
    policy = Counter()
    phonemes = Counter()
    by_participant_task = defaultdict(list)
    for a in attempts:
        by_condition[a.group_id].append(a)
        missing.update(_json(a.missing_words_json, "[]"))
        issues.update(_json(a.issue_types_detected_json, "[]"))
        policy.update([a.feedback_type])
        by_participant_task[(a.participant_id, a.task_id)].append(a)
    diagnosis_rows = db.query(DiagnosisRecord).all()
    phonemes.update(row.target_phoneme for row in diagnosis_rows if row.target_phoneme)
    repeated_phonemes = [
        {"participant_id": participant, "target_phoneme": phoneme, "count": count}
        for (participant, phoneme), count in Counter((row.participant_id, row.target_phoneme) for row in diagnosis_rows if row.target_phoneme).items()
        if count >= 2
    ]
    improvements = []
    for group_attempts in by_participant_task.values():
        ordered = sorted(group_attempts, key=lambda item: item.attempt_number)
        if len(ordered) > 1:
            improvements.append((_attempt_score(ordered[-1]) or 0) - (_attempt_score(ordered[0]) or 0))
    condition_rows = []
    for condition, rows in by_condition.items():
        viewed = sum(1 for a in rows if db.query(FeedbackView).filter(FeedbackView.attempt_id == a.id).count())
        rerecorded = sum(1 for a in rows if db.query(RevisionEvent).filter(RevisionEvent.previous_attempt_id == a.id).count())
        condition_rows.append({
            "condition": condition,
            "attempts": len(rows),
            "average_score": round(sum((a.assessment_score or 0) for a in rows) / len(rows), 2),
            "feedback_view_rate": round(viewed / len(rows), 3),
            "re_recording_rate": round(rerecorded / len(rows), 3),
        })
    return {
        "participants": participants,
        "tasks": tasks,
        "attempts": len(attempts),
        "completion_rate_by_condition": condition_rows,
        "average_attempts_per_task": round(len(attempts) / (len(set(a.task_id for a in attempts)) or 1), 2),
        "average_word_match_score": round(sum(a.word_match_score for a in attempts) / len(attempts), 2) if attempts else 0,
        "average_speech_rate_wpm": round(sum(a.speech_rate_wpm for a in attempts) / len(attempts), 2) if attempts else 0,
        "average_score_by_condition": condition_rows,
        "average_revision_gain_by_condition": condition_rows,
        "common_missing_words": [{"word": k, "count": v} for k, v in missing.most_common(10)],
        "common_issue_types": [{"issue_type": k, "count": v} for k, v in issues.most_common(10)],
        "feedback_policy_trigger_distribution": [{"feedback_type": k, "count": v} for k, v in policy.most_common()],
        "common_focus_phonemes": [{"target_phoneme": k, "count": v} for k, v in phonemes.most_common(10)],
        "repeated_phoneme_issues": repeated_phonemes,
        "teacher_recommended_action": _teacher_recommendation(phonemes),
        "average_improvement_first_to_latest": round(sum(improvements) / len(improvements), 2) if improvements else 0,
        "feedback_views": db.query(FeedbackView).count(),
        "revision_events": db.query(RevisionEvent).count(),
        "learner_state_count": db.query(LearnerState).count(),
        "system_version": db.query(SystemVersion).order_by(SystemVersion.id.desc()).first(),
    }


def _teacher_recommendation(phonemes):
    if not phonemes:
        return ""
    phoneme, count = phonemes.most_common(1)[0]
    if count < 2:
        return ""
    return "Several learners showed repeated /%s/ focus-word issues. Consider a short class activity contrasting /%s/ with common substitutions before the next read-aloud practice." % (phoneme, phoneme)


@router.get("/dashboard/condition-comparison")
def condition_comparison(db: Session = Depends(get_db)):
    return dashboard_summary(db=db)["completion_rate_by_condition"]


@router.get("/dashboard/learner-trajectories")
def learner_trajectories(db: Session = Depends(get_db)):
    states = db.query(LearnerState).order_by(LearnerState.created_at.asc()).all()
    return [{
        "participant_id": s.participant_id,
        "after_attempt_id": s.after_attempt_id,
        "pronunciation_clarity": s.pronunciation_clarity,
        "fluency_stability": s.fluency_stability,
        "feedback_uptake": s.feedback_uptake,
        "revision_responsiveness": s.revision_responsiveness,
    } for s in states]


@router.get("/dashboard/issue-summary")
def issue_summary(db: Session = Depends(get_db)):
    counts = Counter(row.issue_type for row in db.query(IssueRecord).all())
    return [{"issue_type": k, "count": v} for k, v in counts.most_common()]


@router.post("/teacher/orchestration-event")
def teacher_orchestration_event(payload: dict, db: Session = Depends(get_db)):
    event = TeacherOrchestrationEvent(
        study_id=payload.get("study_id", 1),
        condition_id=payload.get("condition_id", 0),
        teacher_id=payload.get("teacher_id", ""),
        class_id=payload.get("class_id", ""),
        participant_id_optional=payload.get("participant_id_optional", ""),
        task_id=payload.get("task_id", 0),
        attempt_id=payload.get("attempt_id", 0),
        issue_type=payload.get("issue_type", ""),
        target_phoneme_optional=payload.get("target_phoneme_optional", ""),
        dashboard_signal_json=json.dumps(payload.get("dashboard_signal_json", {})),
        recommended_action=payload.get("recommended_action", ""),
        teacher_action_taken=payload.get("teacher_action_taken", ""),
        notes=payload.get("notes", ""),
        system_version_id=payload.get("system_version_id", 1),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return clean_model(event)


def _write_csv(db, report_type, rows):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / ("%s_%s.csv" % (report_type, datetime.utcnow().strftime("%Y%m%d_%H%M%S")))
    if not rows:
        rows = [{"empty": "true"}]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return FileResponse(path, filename=path.name, media_type="text/csv")


@router.get("/exports/participants")
def export_participants(db: Session = Depends(get_db)):
    return _write_csv(db, "participants", [clean_model(p) for p in db.query(Participant).all()])


@router.get("/exports/attempts")
def export_attempts(db: Session = Depends(get_db)):
    return _write_csv(db, "attempts", [_attempt_to_dict(db, a) for a in db.query(Attempt).all()])


@router.get("/exports/studies")
def export_studies(db: Session = Depends(get_db)):
    return _write_csv(db, "studies", [clean_model(s) for s in db.query(Study).all()])


@router.get("/exports/conditions")
def export_conditions(db: Session = Depends(get_db)):
    return _write_csv(db, "conditions", [clean_model(c) for c in db.query(Condition).all()])


@router.get("/exports/audio-evidence")
def export_audio_evidence(db: Session = Depends(get_db)):
    rows = [{
        "study_id": a.study_id,
        "condition_id": a.condition_id,
        "participant_id": a.participant_id,
        "task_id": a.task_id,
        "attempt_id": a.id,
        "timestamp": a.created_at.isoformat(),
        "system_version_id": getattr(a, "system_version_id", 1),
        "audio_path": a.audio_path,
        "duration_seconds": a.duration_seconds,
        "speech_rate_wpm": a.speech_rate_wpm,
        "long_pause_count": a.long_pause_count,
        "valid_audio": getattr(a, "valid_audio", True),
    } for a in db.query(Attempt).all()]
    return _write_csv(db, "audio_evidence", rows)


@router.get("/exports/asr-evidence")
def export_asr_evidence(db: Session = Depends(get_db)):
    rows = [{
        "study_id": a.study_id,
        "condition_id": a.condition_id,
        "participant_id": a.participant_id,
        "task_id": a.task_id,
        "attempt_id": a.id,
        "timestamp": a.created_at.isoformat(),
        "system_version_id": getattr(a, "system_version_id", 1),
        "asr_adapter": a.asr_adapter,
        "asr_transcript": a.asr_transcript,
        "asr_sanity_json": a.asr_sanity_json,
        "alignment_json": a.alignment_json,
    } for a in db.query(Attempt).all()]
    return _write_csv(db, "asr_evidence", rows)


@router.get("/exports/pronunciation-evidence")
def export_pronunciation_evidence(db: Session = Depends(get_db)):
    return _write_csv(db, "pronunciation_evidence", [clean_model(row) for row in db.query(PronunciationEvidence).all()])


@router.get("/exports/diagnosis-records")
def export_diagnosis_records(db: Session = Depends(get_db)):
    return _write_csv(db, "diagnosis_records", [clean_model(row) for row in db.query(DiagnosisRecord).all()])


@router.get("/exports/external-assessment-scores")
def export_external_assessment_scores(db: Session = Depends(get_db)):
    return _write_csv(db, "external_assessment_scores", [clean_model(row) for row in db.query(ExternalAssessmentScore).all()])


@router.get("/exports/teacher-orchestration-events")
def export_teacher_orchestration_events(db: Session = Depends(get_db)):
    return _write_csv(db, "teacher_orchestration_events", [clean_model(row) for row in db.query(TeacherOrchestrationEvent).all()])


@router.get("/exports/system-versions")
def export_system_versions(db: Session = Depends(get_db)):
    return _write_csv(db, "system_versions", [clean_model(row) for row in db.query(SystemVersion).all()])


@router.get("/exports/feedback")
def export_feedback(db: Session = Depends(get_db)):
    return _write_csv(db, "feedback", [clean_model(f) for f in db.query(FeedbackItem).all()])


@router.get("/exports/revisions")
def export_revisions(db: Session = Depends(get_db)):
    return _write_csv(db, "revisions", [clean_model(r) for r in db.query(RevisionEvent).all()])


@router.get("/exports/learner-states")
def export_learner_states(db: Session = Depends(get_db)):
    return _write_csv(db, "learner_states", [clean_model(s) for s in db.query(LearnerState).all()])


@router.get("/exports/annotations")
def export_annotations(db: Session = Depends(get_db)):
    return _write_csv(db, "annotations", [clean_model(a) for a in db.query(Annotation).all()])


@router.get("/exports/study-design")
def export_study_design(db: Session = Depends(get_db)):
    rows = [clean_model(c) for c in db.query(Condition).all()]
    return _write_csv(db, "study_design", rows)


@router.get("/exports/full")
def export_full(db: Session = Depends(get_db)):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / ("full_research_export_%s.zip" % datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
    export_sets = {
        "participants.csv": [clean_model(p) for p in db.query(Participant).all()],
        "users.csv": [clean_model(row) for row in db.query(User).all()],
        "classes.csv": [clean_model(row) for row in db.query(ClassRoom).all()],
        "groups.csv": [clean_model(row) for row in db.query(LearnerGroup).all()],
        "studies.csv": [clean_model(s) for s in db.query(Study).all()],
        "conditions.csv": [clean_model(c) for c in db.query(Condition).all()],
        "tasks.csv": [clean_model(t) for t in db.query(Task).all()],
        "tts_audio_status.csv": [{
            "task_id": task.id,
            "model_audio_source": getattr(task, "model_audio_source", "tts"),
            "tts_status": getattr(task, "tts_status", "browser_only"),
            "tts_voice": getattr(task, "tts_voice", "browser-default"),
        } for task in db.query(Task).all()],
        "attempts.csv": [_attempt_to_dict(db, a) for a in db.query(Attempt).all()],
        "pronunciation_evidence.csv": [clean_model(row) for row in db.query(PronunciationEvidence).all()],
        "diagnosis_records.csv": [clean_model(row) for row in db.query(DiagnosisRecord).all()],
        "feedback_items.csv": [clean_model(f) for f in db.query(FeedbackItem).all()],
        "teacher_feedback.csv": [clean_model(row) for row in db.query(TeacherFeedback).all()],
        "peer_feedback.csv": [clean_model(row) for row in db.query(PeerFeedback).all()],
        "feedback_views.csv": [clean_model(v) for v in db.query(FeedbackView).all()],
        "revision_events.csv": [clean_model(r) for r in db.query(RevisionEvent).all()],
        "learner_states.csv": [clean_model(s) for s in db.query(LearnerState).all()],
        "learner_progress.csv": [{"user_code": user.user_code, **student_progress(user.user_code, db)} for user in db.query(User).filter(User.role == "student").all()],
        "annotations.csv": [clean_model(a) for a in db.query(Annotation).all()],
        "teacher_orchestration_events.csv": [clean_model(row) for row in db.query(TeacherOrchestrationEvent).all()],
        "peer_review_assignments.csv": [clean_model(row) for row in db.query(PeerReviewAssignment).all()],
        "external_assessment_scores.csv": [clean_model(row) for row in db.query(ExternalAssessmentScore).all()],
        "system_versions.csv": [clean_model(row) for row in db.query(SystemVersion).all()],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, rows in export_sets.items():
            archive.writestr(filename, _csv_text(rows))
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.get("/exports/participant/{participant_id}")
def export_participant(participant_id: str, db: Session = Depends(get_db)):
    rows = [_attempt_to_dict(db, a) for a in db.query(Attempt).filter(Attempt.participant_id == participant_id).all()]
    return _write_csv(db, "participant_%s" % participant_id, rows)


@router.get("/exports/tasks")
def export_tasks(db: Session = Depends(get_db)):
    return _write_csv(db, "tasks", [clean_model(t) for t in db.query(Task).all()])


@router.get("/exports/users")
def export_users(db: Session = Depends(get_db)):
    return _write_csv(db, "users", [clean_model(row) for row in db.query(User).all()])


@router.get("/exports/classes")
def export_classes(db: Session = Depends(get_db)):
    return _write_csv(db, "classes", [clean_model(row) for row in db.query(ClassRoom).all()])


@router.get("/exports/groups")
def export_groups(db: Session = Depends(get_db)):
    return _write_csv(db, "groups", [clean_model(row) for row in db.query(LearnerGroup).all()])


@router.get("/exports/tts-audio-status")
def export_tts_audio_status(db: Session = Depends(get_db)):
    rows = [{
        "task_id": task.id,
        "task_code": task.task_code,
        "model_audio_source": getattr(task, "model_audio_source", "tts"),
        "tts_sentence_audio_path": getattr(task, "tts_sentence_audio_path", ""),
        "tts_focus_word_audio_json": getattr(task, "tts_focus_word_audio_json", "{}"),
        "uploaded_sentence_audio_path_optional": getattr(task, "uploaded_sentence_audio_path_optional", ""),
        "uploaded_focus_word_audio_json_optional": getattr(task, "uploaded_focus_word_audio_json_optional", "{}"),
        "tts_voice": getattr(task, "tts_voice", "browser-default"),
        "tts_status": getattr(task, "tts_status", "browser_only"),
    } for task in db.query(Task).all()]
    return _write_csv(db, "tts_audio_status", rows)


@router.get("/exports/ai-feedback")
def export_ai_feedback(db: Session = Depends(get_db)):
    return _write_csv(db, "ai_feedback", [clean_model(row) for row in db.query(FeedbackItem).all()])


@router.get("/exports/teacher-feedback")
def export_teacher_feedback(db: Session = Depends(get_db)):
    return _write_csv(db, "teacher_feedback", [clean_model(row) for row in db.query(TeacherFeedback).all()])


@router.get("/exports/peer-feedback")
def export_peer_feedback(db: Session = Depends(get_db)):
    return _write_csv(db, "peer_feedback", [clean_model(row) for row in db.query(PeerFeedback).all()])


@router.get("/exports/feedback-views")
def export_feedback_views(db: Session = Depends(get_db)):
    return _write_csv(db, "feedback_views", [clean_model(row) for row in db.query(FeedbackView).all()])


@router.get("/exports/learner-progress")
def export_learner_progress(db: Session = Depends(get_db)):
    rows = []
    for user in db.query(User).filter(User.role == "student").all():
        progress = student_progress(user.user_code, db)
        rows.append({"user_code": user.user_code, **progress})
    return _write_csv(db, "learner_progress", rows)


@router.get("/exports/peer-review-assignments")
def export_peer_review_assignments(db: Session = Depends(get_db)):
    return _write_csv(db, "peer_review_assignments", [clean_model(row) for row in db.query(PeerReviewAssignment).all()])


@router.get("/exports/all")
def export_all(db: Session = Depends(get_db)):
    return export_full(db)


def clean_model(model):
    if hasattr(model, "__table__"):
        return {column.name: getattr(model, column.name) for column in model.__table__.columns}
    data = dict(getattr(model, "__dict__", {}))
    data.pop("_sa_instance_state", None)
    return data


def _csv_text(rows):
    if not rows:
        rows = [{"empty": "true"}]
    from io import StringIO
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


EXTERNAL_SCORE_COLUMNS = [
    "participant_code",
    "task_code",
    "attempt_number",
    "source_name",
    "score_level",
    "target_word",
    "target_phoneme",
    "observed_phoneme_optional",
    "score",
    "confidence",
    "issue_type_optional",
    "notes_optional",
]


@router.get("/external-scores/template")
def external_scores_template():
    sample = ",".join(EXTERNAL_SCORE_COLUMNS) + "\n"
    return Response(sample, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=external_scores_template.csv"})


@router.post("/external-scores/import")
def import_external_scores(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(content.splitlines())
    errors = []
    imported = 0
    for row_number, row in enumerate(reader, start=2):
        error = _validate_external_score_row(row)
        participant = db.query(Participant).filter(Participant.participant_code == row.get("participant_code")).first()
        task = db.query(Task).filter(Task.task_code == row.get("task_code")).first()
        attempt = None
        if participant and task:
            attempt = db.query(Attempt).filter(
                Attempt.participant_id == participant.participant_id,
                Attempt.task_id == task.id,
                Attempt.attempt_number == int(row.get("attempt_number") or 1),
            ).first()
        if not participant:
            error = error or "participant_code not found"
        if not task:
            error = error or "task_code not found"
        if not attempt:
            error = error or "attempt not found"
        if error:
            errors.append({"row": row_number, "reason": error})
            continue
        score = float(row.get("score") or 0)
        confidence = float(row.get("confidence") or 0)
        score_record = ExternalAssessmentScore(
            study_id=attempt.study_id,
            condition_id=attempt.condition_id,
            participant_id=attempt.participant_id,
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            participant_code=row.get("participant_code", ""),
            task_code=row.get("task_code", ""),
            attempt_number=attempt.attempt_number,
            source_name=row.get("source_name", ""),
            score_level=row.get("score_level", ""),
            target_word=row.get("target_word", ""),
            target_phoneme=row.get("target_phoneme", ""),
            observed_phoneme_optional=row.get("observed_phoneme_optional", ""),
            score=score,
            confidence=confidence,
            issue_type_optional=row.get("issue_type_optional", ""),
            notes_optional=row.get("notes_optional", ""),
            system_version_id=getattr(attempt, "system_version_id", 1),
        )
        db.add(score_record)
        evidence_level = "model_supported_diagnosis" if row.get("score_level") == "phoneme" else "asr_supported_cue"
        db.add(PronunciationEvidence(
            study_id=attempt.study_id,
            condition_id=attempt.condition_id,
            participant_id=attempt.participant_id,
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            source_name=row.get("source_name", ""),
            evidence_level=evidence_level,
            score_level=row.get("score_level", ""),
            target_word=row.get("target_word", ""),
            target_phoneme=row.get("target_phoneme", ""),
            observed_phoneme=row.get("observed_phoneme_optional") or None,
            score=score,
            confidence=confidence,
            issue_type=row.get("issue_type_optional", ""),
            notes=row.get("notes_optional", ""),
            system_version_id=getattr(attempt, "system_version_id", 1),
        ))
        if row.get("score_level") == "phoneme" and score < 70:
            model_feedback = feedback_from_diagnosis(type("Record", (), {
                "evidence_level": "model_supported_diagnosis",
                "target_word": row.get("target_word", ""),
                "target_phoneme": row.get("target_phoneme", ""),
                "observed_phoneme": row.get("observed_phoneme_optional") or None,
                "speaking_target": "pronunciation_clarity",
                "score": score,
            })())
            db.add(DiagnosisRecord(
                study_id=attempt.study_id,
                condition_id=attempt.condition_id,
                participant_id=attempt.participant_id,
                task_id=attempt.task_id,
                attempt_id=attempt.id,
                evidence_level="model_supported_diagnosis",
                diagnosis_level="phoneme",
                evidence_source=row.get("source_name", ""),
                confidence_level="medium" if confidence < 0.8 else "high",
                target_word=row.get("target_word", ""),
                target_phoneme=row.get("target_phoneme", ""),
                observed_phoneme=row.get("observed_phoneme_optional") or None,
                issue_type=row.get("issue_type_optional", ""),
                speaking_target="pronunciation_clarity",
                severity="moderate",
                pedagogical_interpretation="Low imported phoneme-level score.",
                requires_human_validation=False,
                allowed_feedback_strength="direct",
                feedback_text=model_feedback["diagnosis"],
                system_version_id=getattr(attempt, "system_version_id", 1),
            ))
            item = db.query(FeedbackItem).filter(FeedbackItem.attempt_id == attempt.id).order_by(FeedbackItem.id.desc()).first()
            if item:
                item.diagnosis = model_feedback["diagnosis"]
                item.explanation = model_feedback["explanation"]
                item.action_guidance = model_feedback["action_guidance"]
                item.revision_goal = model_feedback["revision_goal"]
                item.validated_feedback_json = json.dumps(model_feedback)
        imported += 1
    db.commit()
    return {"imported": imported, "errors": errors}


@router.get("/external-scores/{attempt_id}")
def external_scores_for_attempt(attempt_id: int, db: Session = Depends(get_db)):
    return [clean_model(row) for row in db.query(ExternalAssessmentScore).filter(ExternalAssessmentScore.attempt_id == attempt_id).all()]


def _validate_external_score_row(row):
    missing = [column for column in EXTERNAL_SCORE_COLUMNS if column not in row]
    if missing:
        return "missing columns: %s" % ", ".join(missing)
    level = (row.get("score_level") or "").strip()
    if level not in ["sentence", "word", "phoneme"]:
        return "score_level must be sentence, word, or phoneme"
    if level in ["word", "phoneme"] and not row.get("target_word"):
        return "word-level and phoneme-level rows require target_word"
    if level == "phoneme" and not row.get("target_phoneme"):
        return "phoneme-level rows require target_phoneme"
    try:
        float(row.get("score") or "")
        float(row.get("confidence") or "")
        int(row.get("attempt_number") or "")
    except ValueError:
        return "attempt_number, score, and confidence must be numeric"
    return ""
