import csv
import hashlib
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
from .config import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_AUDIO_TYPES,
    API_BASE_URL,
    AUDIO_DIR,
    DATABASE_URL,
    EXPORT_DIR,
    FRONTEND_ORIGINS,
    MAX_AUDIO_MB,
    PRONUNCIATION_PROVIDER,
    RESEARCH_MODE,
    SYSTEM_VERSION,
)
from .config import ASR_MODE, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL_SIZE
from .database import (
    Annotation,
    AudioFile,
    AuditLog,
    Attempt,
    ClassRoom,
    Condition,
    ConsentRecord,
    ExportJob,
    FeedbackEvent,
    FeedbackItem,
    FeedbackUptakeState,
    FeedbackView,
    HumanRating,
    DiagnosisRecord,
    ExternalAssessmentScore,
    IssueRecord,
    LearnerState,
    LearnerGroup,
    Participant,
    PeerFeedback,
    PeerReviewAssignment,
    PhonemeLevelAssessment,
    PronunciationEvidence,
    PronunciationAssessmentResult,
    QuestionnaireResponse,
    ResearchSession,
    RevisionEvent,
    Study,
    StudyVersion,
    SystemVersion,
    TeacherFeedback,
    TeacherOrchestrationEvent,
    Task,
    TaskSet,
    User,
    WordLevelAssessment,
    get_db,
)
from .schemas import AnnotationCreate, ParticipantCreate, ParticipantRead, TaskCreate, TaskRead
from .services.feedback.feedback_policy import (
    CONDITION_PRESETS,
    condition_policy,
    derive_feedback_use_state,
    filter_feedback_for_condition,
    normalize_condition,
)
from .services.feedback.issue_taxonomy import issue_records_for_alignment
from .services.asr_sanity import check_asr_sanity
from .services.learner_model.state_update import update_learner_state
from .services.pronunciation_assessment import get_pronunciation_provider, provider_status
from .services.pronunciation.evidence_builder import build_rule_based_evidence
from .services.validation.agreement import annotation_agreement
from .services.verbalization.template_verbalizer import feedback_from_issue, feedback_from_diagnosis


router = APIRouter()


def _json(value, default):
    try:
        return json.loads(value or default)
    except Exception:
        return json.loads(default)


def _anonymized_code(value):
    text = str(value or "")
    digest = hashlib.sha256(("assessment:" + text).encode("utf-8")).hexdigest()
    return "P" + digest[:10].upper()


def _participant_anonymous_code(participant_or_id):
    if hasattr(participant_or_id, "participant_id"):
        participant = participant_or_id
        if not getattr(participant, "anonymous_code", ""):
            participant.anonymous_code = _anonymized_code(participant.participant_id)
        return participant.anonymous_code
    return _anonymized_code(participant_or_id)


def _storage_status(path):
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"path": str(path), "writable": True}
    except Exception as exc:
        return {"path": str(path), "writable": False, "error": str(exc)}


def _database_status(db):
    try:
        db.query(Study).count()
        return {"connected": True, "url": "configured" if DATABASE_URL else "sqlite"}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def _audit(db, action, entity_type="", entity_id="", reason="", actor_id="", before=None, after=None):
    db.add(AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        reason=reason or "",
        before_json=json.dumps(before or {}, default=str),
        after_json=json.dumps(after or {}, default=str),
    ))


def _validate_upload_metadata(audio):
    content_type = (audio.content_type or "application/octet-stream").lower()
    ext = (Path(audio.filename or "audio.webm").suffix or ".webm").lower()
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported audio content type: %s" % content_type)
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio file extension: %s" % ext)
    return content_type, ext


def _structured_audio_folder(study, participant, task):
    study_code = "study_%s" % getattr(study, "id", 1)
    participant_code = getattr(participant, "participant_code", "") or getattr(participant, "participant_id", "participant")
    task_code = getattr(task, "task_code", "") or ("task_%s" % getattr(task, "id", "0"))
    return AUDIO_DIR / study_code / participant_code / task_code


def _store_assessment_result(db, attempt, dto):
    row = PronunciationAssessmentResult(
        study_id=attempt.study_id,
        study_version_id=getattr(attempt, "study_version_id", 0) or 0,
        participant_id=attempt.participant_id,
        task_id=attempt.task_id,
        attempt_id=attempt.id,
        provider_name=dto.provider_name,
        provider_version=dto.provider_version,
        request_id=dto.request_id,
        reference_text=dto.reference_text,
        recognized_text=dto.recognized_text,
        overall_score=dto.overall_score,
        accuracy_score=dto.accuracy_score,
        fluency_score=dto.fluency_score,
        completeness_score=dto.completeness_score,
        prosody_score=dto.prosody_score,
        pronunciation_score=dto.pronunciation_score,
        confidence=dto.confidence,
        evidence_level=dto.evidence_level,
        status=dto.status,
        error_message=dto.error_message,
        raw_response_json=json.dumps(dto.raw_response_json or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    for item in dto.word_level_results:
        db.add(WordLevelAssessment(
            result_id=row.id,
            attempt_id=attempt.id,
            word=str(item.get("word", "")),
            reference_word=str(item.get("reference_word", item.get("word", ""))),
            accuracy_score=item.get("accuracy_score"),
            error_type=str(item.get("error_type", "")),
            confidence=float(item.get("confidence") or 0),
            raw_json=json.dumps(item.get("raw", item)),
        ))
    for item in dto.phoneme_level_results:
        db.add(PhonemeLevelAssessment(
            result_id=row.id,
            attempt_id=attempt.id,
            word=str(item.get("word", "")),
            phoneme=str(item.get("phoneme", "")),
            accuracy_score=item.get("accuracy_score"),
            error_type=str(item.get("error_type", "")),
            confidence=float(item.get("confidence") or 0),
            raw_json=json.dumps(item.get("raw", item)),
        ))
    db.commit()
    return row


def _log_feedback_event(db, participant_id, study_id, task_id, attempt_id, event_type, feedback_item_id=0, event_value="", duration_ms=0, metadata=None):
    event = FeedbackEvent(
        participant_id=participant_id,
        study_id=study_id,
        task_id=task_id,
        attempt_id=attempt_id,
        feedback_item_id=feedback_item_id,
        event_type=event_type,
        event_value=event_value or "",
        duration_ms_optional=int(duration_ms or 0),
        metadata_json=json.dumps(metadata or {}),
    )
    db.add(event)
    return event


def _compute_feedback_uptake(db, participant_id, task_id, attempt_id):
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
    feedback_item = db.query(FeedbackItem).filter(FeedbackItem.attempt_id == attempt_id).order_by(FeedbackItem.id.desc()).first()
    events = db.query(FeedbackEvent).filter(FeedbackEvent.attempt_id == attempt_id).all()
    viewed = db.query(FeedbackEvent).filter(
        FeedbackEvent.attempt_id == attempt_id,
        FeedbackEvent.event_type.in_(["learner_opened_feedback", "feedback_visible_to_learner"]),
    ).count() > 0 or db.query(FeedbackView).filter(FeedbackView.attempt_id == attempt_id).count() > 0
    revision = db.query(RevisionEvent).filter(RevisionEvent.previous_attempt_id == attempt_id).first()
    improved = bool(revision and (revision.score_delta > 0 or revision.word_match_delta > 0))
    later_attempt = None
    sustained = False
    if revision:
        later_attempt = db.query(Attempt).filter(
            Attempt.participant_id == participant_id,
            Attempt.id != revision.new_attempt_id,
            Attempt.created_at > revision.created_at,
            Attempt.score_delta_from_previous_attempt >= 0,
            Attempt.valid_audio == True,  # noqa: E712
        ).order_by(Attempt.created_at.asc()).first()
        sustained = bool(improved and later_attempt)
    state = derive_feedback_use_state(viewed, revision is not None, improved, sustained)
    evidence = {
        "events": [event.event_type for event in events],
        "feedback_view_duration_ms": sum(event.duration_ms_optional or 0 for event in events if event.event_type == "learner_opened_feedback"),
        "feedback_view_rows": db.query(FeedbackView).filter(FeedbackView.attempt_id == attempt_id).count(),
        "revision_event_id": revision.id if revision else 0,
    }
    rules = {"rule_version": "uptake_rules_v1", "viewed": viewed, "has_revision": revision is not None, "improved": improved, "sustained": sustained}
    row = db.query(FeedbackUptakeState).filter(FeedbackUptakeState.attempt_id == attempt_id).first()
    if not row:
        row = FeedbackUptakeState(participant_id=participant_id, task_id=task_id, attempt_id=attempt_id)
        db.add(row)
    row.feedback_item_id = feedback_item.id if feedback_item else 0
    row.uptake_state = state
    row.rule_version = "uptake_rules_v1"
    row.evidence_used = json.dumps(evidence)
    row.previous_attempt_id = attempt_id
    row.revised_attempt_id = revision.new_attempt_id if revision else 0
    row.later_attempt_id = later_attempt.id if later_attempt else 0
    row.score_delta = revision.score_delta if revision else 0
    row.target_issue_resolved = bool(revision.repeated_issue_reduced if revision else False)
    row.rules_json = json.dumps(rules)
    row.computed_at = datetime.utcnow()
    if attempt:
        attempt.feedback_viewed = viewed
    return row


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
    policy = condition_policy(attempt.group_id)
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
        "condition_group": feedback.get("condition_group", policy["condition_group"]),
        "condition_label": feedback.get("condition_label", policy["friendly_label"]),
        "attempt_number": attempt.attempt_number,
        "audio_path": attempt.audio_path,
        "asr_adapter": attempt.asr_adapter,
        "assessment_provider": getattr(attempt, "assessment_provider", ""),
        "assessment_status": getattr(attempt, "assessment_status", ""),
        "pronunciation_provider": getattr(attempt, "assessment_provider", ""),
        "asr_transcript": attempt.asr_transcript if feedback.get("show_transcript", True) else "",
        "raw_asr_transcript": attempt.asr_transcript,
        "duration_seconds": attempt.duration_seconds,
        "audio_duration": getattr(attempt, "audio_duration", attempt.duration_seconds),
        "speech_rate_wpm": attempt.speech_rate_wpm,
        "word_match_score": attempt.word_match_score,
        "assessment_score": attempt.assessment_score,
        "practice_clarity_score": getattr(attempt, "practice_clarity_score", None),
        "practice_clarity_score_source": getattr(attempt, "practice_clarity_score_source", ""),
        "pronunciation_assessment_score": getattr(attempt, "pronunciation_assessment_score", None),
        "pronunciation_assessment_score_source": getattr(attempt, "pronunciation_assessment_score_source", ""),
        "pronunciation_score_valid_for_research": bool(getattr(attempt, "pronunciation_score_valid_for_research", False)),
        "evidence_level": getattr(attempt, "evidence_level", ""),
        "missing_words": _json(attempt.missing_words_json, "[]"),
        "substitutions": _json(attempt.substitutions_json, "[]"),
        "issue_types_detected": _json(attempt.issue_types_detected_json, "[]"),
        "long_pause_count": attempt.long_pause_count,
        "valid_audio": bool(getattr(attempt, "valid_audio", True)),
        "no_speech_detected": bool(feedback.get("no_speech_detected", False)),
        "invalid_reasons": feedback.get("invalid_reasons", []),
        "invalid_audio_reason": getattr(attempt, "invalid_audio_reason", ""),
        "feedback_generated": bool(attempt.feedback_generated),
        "feedback_shown": bool(attempt.feedback_shown),
        "feedback_type": attempt.feedback_type,
        "show_score": bool(feedback.get("show_score", policy["show_score"])),
        "show_comment": bool(feedback.get("show_comment", policy["show_comment"])),
        "score_shown": feedback.get("practice_score") is not None,
        "comment_shown": bool(feedback.get("show_comment") and feedback.get("comment")),
        "revision_allowed": bool(feedback.get("revision_allowed", policy["revision_allowed"])),
        "feedback": feedback,
        "alignment": _json(getattr(attempt, "alignment_json", "{}"), "{}"),
        "asr_sanity": _json(getattr(attempt, "asr_sanity_json", "{}"), "{}"),
        "score_breakdown": _json(getattr(attempt, "score_breakdown_json", "{}"), "{}"),
        "backend_diagnostics": {
            "asr_adapter": attempt.asr_adapter,
            "asr_transcript": attempt.asr_transcript,
            "asr_sanity": _json(getattr(attempt, "asr_sanity_json", "{}"), "{}"),
            "assessment_provider": getattr(attempt, "assessment_provider", ""),
            "assessment_status": getattr(attempt, "assessment_status", ""),
            "practice_clarity_score": getattr(attempt, "practice_clarity_score", None),
            "pronunciation_assessment_score": getattr(attempt, "pronunciation_assessment_score", None),
            "pronunciation_score_valid_for_research": bool(getattr(attempt, "pronunciation_score_valid_for_research", False)),
            "evidence_level": getattr(attempt, "evidence_level", ""),
            "valid_audio": bool(getattr(attempt, "valid_audio", True)),
            "invalid_reasons": feedback.get("invalid_reasons", []),
            "score_breakdown": _json(getattr(attempt, "score_breakdown_json", "{}"), "{}"),
        },
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
def health(db: Session = Depends(get_db)):
    locked_studies = db.query(Study).filter(Study.locked == True).count()  # noqa: E712
    provider = provider_status(db)
    audio_status = _storage_status(AUDIO_DIR)
    export_status = _storage_status(EXPORT_DIR)
    return {
        "status": "ok" if _database_status(db)["connected"] and audio_status["writable"] else "degraded",
        "database": _database_status(db),
        "storage": {"audio": audio_status, "exports": export_status},
        "provider": provider,
        "pronunciation_provider": provider.get("provider_name", PRONUNCIATION_PROVIDER),
        "provider_research_usable": bool(provider.get("research_usable", False)),
        "research_mode": RESEARCH_MODE,
        "api_base_url": API_BASE_URL,
        "frontend_origins": FRONTEND_ORIGINS,
        "study_lock_status": {"locked_studies": locked_studies},
        "mock_mode": ASR_MODE == "mock",
        "asr_adapter": ASR_MODE,
        "asr": {"adapter": ASR_MODE},
        "whisper_model_size": WHISPER_MODEL_SIZE if ASR_MODE == "faster_whisper" else "",
        "whisper_device": WHISPER_DEVICE if ASR_MODE == "faster_whisper" else "",
        "whisper_compute_type": WHISPER_COMPUTE_TYPE if ASR_MODE == "faster_whisper" else "",
        "system_version": SYSTEM_VERSION,
        "app_version": SYSTEM_VERSION,
    }


ROLE_LABELS = {
    "G0": "Practice",
    "G1": "Score feedback",
    "G2": "Comment feedback",
    "G3": "Score and comment feedback",
}


def _user_dict(user, db=None):
    if not user:
        return None
    participant = db.query(Participant).filter(Participant.participant_id == user.user_code).first() if db else None
    condition_group = normalize_condition(participant.group_id if participant else "G3")
    return {
        "id": user.id,
        "user_code": user.user_code,
        "role": user.role,
        "display_name": user.display_name or user.user_code,
        "class_id": user.class_id,
        "group_id": user.group_id,
        "condition_group": condition_group,
        "condition_label": ROLE_LABELS.get(condition_group, "Score and comment feedback"),
        "active": bool(user.active),
        "created_at": user.created_at,
    }


def _user_by_code(db, user_code):
    return db.query(User).filter(User.user_code == user_code, User.active == True).first()  # noqa: E712


def _participant_id_for_user(user):
    return user.user_code if user and user.role == "student" else ""


def _condition_group_for_user(db, user):
    if not user or user.role != "student":
        return ""
    participant = db.query(Participant).filter(Participant.participant_id == user.user_code).first()
    return normalize_condition(participant.group_id if participant else "G3")


def _attempt_with_task(db, attempt):
    data = _attempt_to_dict(db, attempt)
    user = db.query(User).filter(User.user_code == attempt.participant_id).first()
    if user:
        user_data = _user_dict(user, db)
        data["display_name"] = user_data["display_name"]
        data["class_id"] = user_data["class_id"]
        data["user_group_id"] = user_data["group_id"]
        data["condition_group"] = user_data.get("condition_group") or data.get("condition_group")
        data["condition_label"] = user_data.get("condition_label") or data.get("condition_label")
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
    return {"user": _user_dict(user, db), "token_type": "pilot_user_code", "student_friendly_workflows": ROLE_LABELS}


@router.get("/me")
def me(user_code: str, db: Session = Depends(get_db)):
    user = _user_by_code(db, user_code)
    if not user:
        raise HTTPException(status_code=404, detail="User code not found or inactive")
    return _user_dict(user, db)


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    return [_user_dict(user, db) for user in db.query(User).order_by(User.id.asc()).all()]


@router.post("/users")
def create_user(payload: dict, db: Session = Depends(get_db)):
    user_code = (payload or {}).get("user_code", "").strip()
    role = (payload or {}).get("role", "student").strip()
    if not user_code:
        raise HTTPException(status_code=400, detail="user_code is required")
    if role not in ["student", "teacher", "peer_reviewer", "rater", "researcher_admin"]:
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
        condition_group = normalize_condition(payload.get("condition_group", "G3"))
        condition = db.query(Condition).filter(Condition.condition_code == condition_group).first()
        participant = db.query(Participant).filter(Participant.participant_id == user.user_code).first()
        if not participant:
            participant = Participant(participant_id=user.user_code, participant_code=user.user_code, class_id=str(user.class_id))
            db.add(participant)
        participant.anonymous_code = participant.anonymous_code or _participant_anonymous_code(participant)
        participant.group_id = condition_group
        participant.group_label = condition.condition_name if condition else condition_group
        participant.condition_id = condition.id if condition else 4
        db.commit()
    return _user_dict(user, db)


@router.post("/users/import")
def import_users(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = file.file.read().decode("utf-8-sig")
    rows = csv.DictReader(content.splitlines())
    imported = 0
    errors = []
    for row in rows:
        row_number = imported + len(errors) + 2
        role = (row.get("role") or "student").strip()
        condition_group = (row.get("condition_group") or "").strip().upper()
        if role == "student" and condition_group not in ["G0", "G1", "G2", "G3"]:
            errors.append({"row": row_number, "reason": "condition_group must be one of G0, G1, G2, G3"})
            continue
        create_user(row, db)
        imported += 1
    return {"imported": imported, "errors": errors}


@router.get("/users/export")
def export_users_alias(db: Session = Depends(get_db)):
    return export_users(db)


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
        "backend": health(db),
        "users": db.query(User).count(),
        "tasks": db.query(Task).count(),
        "attempts": db.query(Attempt).count(),
        "teacher_feedback": db.query(TeacherFeedback).count(),
        "peer_feedback": db.query(PeerFeedback).count(),
        "pronunciation_provider": provider_status(db),
        "studies_locked": db.query(Study).filter(Study.locked == True).count(),  # noqa: E712
        "research_mode": RESEARCH_MODE,
        "visible_feature_rule": "Only role-scoped pilot features are shown in normal UI.",
    }


@router.get("/pilot-readiness")
def pilot_readiness(db: Session = Depends(get_db)):
    provider = provider_status(db)
    studies = db.query(Study).count()
    study_versions = db.query(StudyVersion).count()
    locked_studies = db.query(Study).filter(Study.locked == True).count()  # noqa: E712
    conditions = {row.condition_code for row in db.query(Condition).all()}
    participants_assigned = db.query(Participant).filter(Participant.group_id.in_(["G0", "G1", "G2", "G3"])).count()
    randomized_groups = {row.group_id for row in db.query(Participant).filter(Participant.group_id.in_(["G0", "G1", "G2", "G3"])).all()}
    tasks = db.query(Task).filter(Task.active == True).count()  # noqa: E712
    consent_enabled = db.query(ConsentRecord).count() > 0
    human_rubric_ready = True
    analysis_ready_available = True
    def check(name, ok, warning=False, critical=True, message=""):
        status = "PASS" if ok else ("WARNING" if warning else "FAIL")
        return {"check": name, "status": status, "ok": ok, "critical": critical, "message": message}
    checks = [
        check("backend_connected", True),
        check("database_writable", _database_status(db)["connected"]),
        check("audio_storage_writable", _storage_status(AUDIO_DIR)["writable"]),
        check("export_path_writable", _storage_status(EXPORT_DIR)["writable"]),
        check("real_pronunciation_provider_configured", bool(provider.get("research_usable")), warning=bool(provider.get("configured")) and not RESEARCH_MODE, message="Mock/external UI mode is acceptable for interface pilots, but not formal collection."),
        check("mock_provider_disabled_in_research_mode", not (RESEARCH_MODE and provider.get("provider_name") == "mock")),
        check("g0_g3_conditions_configured", {"G0", "G1", "G2", "G3"}.issubset(conditions)),
        check("study_created", studies > 0),
        check("study_version_created", study_versions > 0, warning=studies > 0, message="Create a study version before formal data collection."),
        check("tasks_assigned", tasks > 0),
        check("participants_imported", participants_assigned > 0),
        check("participants_randomized", {"G0", "G1", "G2", "G3"}.issubset(randomized_groups), warning=participants_assigned > 0, message="Balanced G0-G3 assignment is recommended before locking."),
        check("model_audio_available", True, warning=True, critical=False, message="Browser TTS fallback is available; uploaded model audio is stronger for controlled studies."),
        check("study_locked", locked_studies > 0, warning=studies > 0, message="Lock the study before formal collection."),
        check("consent_records_enabled", consent_enabled, warning=True, message="Create at least one consent record or verify consent workflow before collection."),
        check("human_rating_rubric_configured", human_rubric_ready),
        check("analysis_ready_export_available", analysis_ready_available),
        check("demo_mode_disabled_for_research_collection", RESEARCH_MODE and provider.get("provider_name") != "mock", warning=not RESEARCH_MODE, message="Set RESEARCH_MODE=true with a real provider for formal collection."),
    ]
    critical_failures = [item for item in checks if item["critical"] and item["status"] == "FAIL"]
    warnings = [item for item in checks if item["status"] == "WARNING"]
    return {
        "ready": not critical_failures,
        "ready_for_formal_data_collection": not critical_failures and not warnings,
        "overall_status": "FAIL" if critical_failures else ("WARNING" if warnings else "PASS"),
        "research_mode": RESEARCH_MODE,
        "provider": provider,
        "checks": checks,
        "critical_failures": critical_failures,
        "warnings": warnings,
    }


@router.post("/feedback-events")
def create_feedback_event(payload: dict, db: Session = Depends(get_db)):
    attempt_id = int(payload.get("attempt_id") or 0)
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    event = _log_feedback_event(
        db,
        attempt.participant_id,
        attempt.study_id,
        attempt.task_id,
        attempt.id,
        payload.get("event_type", "learner_opened_feedback"),
        int(payload.get("feedback_item_id") or 0),
        payload.get("event_value", ""),
        int(payload.get("duration_ms_optional") or 0),
        payload.get("metadata_json") or payload.get("metadata") or {},
    )
    uptake = _compute_feedback_uptake(db, attempt.participant_id, attempt.task_id, attempt.id)
    db.commit()
    return {"event": clean_model(event), "feedback_uptake_state": uptake.uptake_state}


@router.get("/human-ratings/queue")
def human_rating_queue(rater_id: str = "", include_intervention: bool = False, db: Session = Depends(get_db)):
    query = db.query(Attempt).filter(Attempt.valid_audio == True).order_by(Attempt.created_at.asc())  # noqa: E712
    attempts = query.all()
    rows = []
    for attempt in attempts:
        task = db.query(Task).filter(Task.id == attempt.task_id).first()
        session_type = getattr(attempt, "session_type", "") or (task.task_type if task else "")
        if not include_intervention and session_type == "practice_intervention":
            continue
        already = db.query(HumanRating).filter(HumanRating.attempt_id == attempt.id, HumanRating.rater_id == rater_id).first() if rater_id else None
        if already:
            continue
        rows.append({
            "attempt_id": attempt.id,
            "anonymized_participant_id": _participant_anonymous_code(attempt.participant_id),
            "task_id": attempt.task_id,
            "task_code": getattr(attempt, "task_code", ""),
            "session_type": session_type,
            "attempt_number": attempt.attempt_number,
            "audio_url": "/api/attempts/%s/audio" % attempt.id,
        })
    return rows


@router.post("/human-ratings")
def create_human_rating(payload: dict, db: Session = Depends(get_db)):
    attempt = db.query(Attempt).filter(Attempt.id == int(payload.get("attempt_id") or 0)).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    row = HumanRating(
        study_id=attempt.study_id,
        attempt_id=attempt.id,
        anonymized_participant_id=_participant_anonymous_code(attempt.participant_id),
        task_id=attempt.task_id,
        task_code=getattr(attempt, "task_code", ""),
        session_type=getattr(attempt, "session_type", ""),
        rater_id=payload.get("rater_id", ""),
        rubric_version=payload.get("rubric_version", "rubric_v1"),
        pronunciation=payload.get("pronunciation"),
        fluency=payload.get("fluency"),
        intelligibility=payload.get("intelligibility"),
        comprehensibility=payload.get("comprehensibility"),
        task_completion=payload.get("task_completion"),
        overall_quality=payload.get("overall_quality"),
        rating_confidence=payload.get("rating_confidence"),
        unusable_recording=bool(payload.get("unusable_recording", False)),
        comments=payload.get("comments", ""),
        rating_duration_seconds=float(payload.get("rating_duration_seconds") or 0),
        rating_started_at=datetime.fromisoformat(payload["rating_started_at"]) if payload.get("rating_started_at") else None,
        rating_submitted_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return clean_model(row)


@router.post("/questionnaire-responses")
def create_questionnaire_response(payload: dict, db: Session = Depends(get_db)):
    responses = payload.get("responses") if isinstance(payload.get("responses"), list) else [payload]
    rows = []
    for item in responses:
        row = QuestionnaireResponse(
            participant_id=item.get("participant_id", payload.get("participant_id", "")),
            study_id=int(item.get("study_id", payload.get("study_id", 1)) or 1),
            session_id=item.get("session_id", payload.get("session_id", "")),
            questionnaire_type=item.get("questionnaire_type", payload.get("questionnaire_type", "")),
            question_id=item.get("question_id", ""),
            response_value=str(item.get("response_value", "")),
            response_numeric=item.get("response_numeric"),
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return {"created": len(rows), "responses": [clean_model(row) for row in rows]}


@router.post("/consent-records")
def create_consent_record(payload: dict, db: Session = Depends(get_db)):
    row = ConsentRecord(
        participant_id=payload.get("participant_id", ""),
        study_id=int(payload.get("study_id", 1) or 1),
        consent_version=payload.get("consent_version", "v1"),
        consent_given=bool(payload.get("consent_given", False)),
        withdrawal_requested=bool(payload.get("withdrawal_requested", False)),
    )
    if row.withdrawal_requested:
        participant = db.query(Participant).filter(Participant.participant_id == row.participant_id).first()
        if participant:
            participant.withdrawn = True
            participant.withdrawal_reason_optional = payload.get("withdrawal_reason_optional", "")
            participant.withdrawal_timestamp = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return clean_model(row)


@router.post("/participants", response_model=ParticipantRead)
def create_participant(payload: ParticipantCreate, db: Session = Depends(get_db)):
    condition_key = normalize_condition(payload.group_id)
    condition = db.query(Condition).filter(Condition.condition_code == condition_key).first()
    participant = db.query(Participant).filter(Participant.participant_id == payload.participant_id).first()
    if participant:
        participant.group_id = condition_key
        participant.participant_code = payload.participant_id
        participant.anonymous_code = participant.anonymous_code or _participant_anonymous_code(participant)
        participant.study_id = payload.study_id
        participant.condition_id = condition.id if condition else payload.condition_id
        participant.session_id = payload.session_id or participant.session_id
    else:
        participant = Participant(
            participant_id=payload.participant_id,
            participant_code=payload.participant_id,
            anonymous_code=_anonymized_code(payload.participant_id),
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
    before = clean_model(study)
    study.locked = True
    study.lock_reason = "Locked before research data collection."
    study.locked_at = datetime.utcnow()
    _audit(db, "study_locked", "study", study_id, study.lock_reason, before=before, after={"locked": True})
    db.commit()
    return {"ok": True, "locked": True}


@router.post("/studies/{study_id}/unlock")
def unlock_study(study_id: int, payload: dict = None, db: Session = Depends(get_db)):
    payload = payload or {}
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Unlock reason is required.")
    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    before = clean_model(study)
    study.locked = False
    study.unlocked_at = datetime.utcnow()
    _audit(db, "study_unlocked", "study", study_id, reason, actor_id=payload.get("actor_id", ""), before=before, after={"locked": False})
    db.commit()
    return {"ok": True, "locked": False, "reason": reason}


@router.post("/studies/{study_id}/versions")
def create_study_version(study_id: int, payload: dict = None, db: Session = Depends(get_db)):
    payload = payload or {}
    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    version = StudyVersion(
        study_id=study_id,
        version_code=payload.get("version_code", "v%s" % (db.query(StudyVersion).filter(StudyVersion.study_id == study_id).count() + 1)),
        description=payload.get("description", ""),
        task_manifest_json=json.dumps([clean_model(task) for task in db.query(Task).all()]),
        condition_manifest_json=json.dumps([clean_model(condition) for condition in db.query(Condition).filter(Condition.study_id == study_id).all()]),
        provider_name=PRONUNCIATION_PROVIDER,
        feedback_policy_version=payload.get("feedback_policy_version", "policy_v1"),
        created_by=payload.get("created_by", ""),
    )
    db.add(version)
    _audit(db, "study_version_created", "study", study_id, payload.get("reason", ""), actor_id=payload.get("created_by", ""), after={"version_code": version.version_code})
    db.commit()
    db.refresh(version)
    return clean_model(version)


@router.post("/studies/{study_id}/task-sets")
def create_task_set(study_id: int, payload: dict, db: Session = Depends(get_db)):
    _ensure_unlocked_study(db, study_id)
    row = TaskSet(
        study_id=study_id,
        task_set_code=payload.get("task_set_code", "task_set_%s" % (db.query(TaskSet).count() + 1)),
        task_ids_json=json.dumps(payload.get("task_ids", [])),
        description=payload.get("description", ""),
    )
    db.add(row)
    _audit(db, "task_set_created", "study", study_id, after={"task_set_code": row.task_set_code})
    db.commit()
    db.refresh(row)
    return clean_model(row)


@router.post("/studies/{study_id}/sessions")
def create_research_session(study_id: int, payload: dict, db: Session = Depends(get_db)):
    _ensure_unlocked_study(db, study_id)
    session_type = payload.get("session_type", "practice_intervention")
    if session_type not in ["familiarization", "pre_test", "practice_intervention", "immediate_post_test", "delayed_post_test", "backup_task"]:
        raise HTTPException(status_code=400, detail="Unknown session_type")
    row = ResearchSession(
        study_id=study_id,
        session_code=payload.get("session_code", session_type),
        session_type=session_type,
        display_order=int(payload.get("display_order", 0) or 0),
        task_set_id=int(payload.get("task_set_id", 0) or 0),
        active=bool(payload.get("active", True)),
    )
    db.add(row)
    _audit(db, "research_session_created", "study", study_id, after={"session_code": row.session_code, "session_type": row.session_type})
    db.commit()
    db.refresh(row)
    return clean_model(row)


@router.post("/studies/{study_id}/randomize-groups")
def randomize_groups(study_id: int, payload: dict = None, db: Session = Depends(get_db)):
    payload = payload or {}
    _ensure_unlocked_study(db, study_id)
    participants = db.query(Participant).filter(Participant.study_id == study_id).order_by(Participant.class_id.asc(), Participant.participant_id.asc()).all()
    if not participants:
        raise HTTPException(status_code=400, detail="No participants found for study.")
    groups = ["G0", "G1", "G2", "G3"]
    if payload.get("stratify_by") == "class":
        buckets = defaultdict(list)
        for participant in participants:
            buckets[participant.class_id].append(participant)
        ordered = []
        for bucket in buckets.values():
            ordered.extend(bucket)
        participants = ordered
    for index, participant in enumerate(participants):
        participant.group_id = groups[index % len(groups)]
        participant.anonymous_code = participant.anonymous_code or _participant_anonymous_code(participant)
    _audit(db, "participants_randomized", "study", study_id, payload.get("reason", ""), after={"count": len(participants), "groups": groups})
    db.commit()
    return {"ok": True, "assigned": len(participants), "groups": groups}


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
    codes = ["G0", "G1", "G2", "G3"]
    rows = db.query(Condition).filter(Condition.study_id == study_id, Condition.condition_code.in_(codes)).order_by(Condition.id.asc()).all()
    if len(rows) < 4:
        for idx, code in enumerate(codes, start=1):
            policy = CONDITION_PRESETS[code]
            condition = db.query(Condition).filter(Condition.condition_code == code).first() or db.query(Condition).filter(Condition.id == idx).first()
            if not condition:
                condition = Condition(id=idx, study_id=study_id, condition_code=code, condition_name=policy["condition_name"])
                db.add(condition)
            condition.condition_code = code
            condition.condition_name = policy["condition_name"]
            condition.show_score = policy["show_score"]
            condition.show_comment = policy["show_comment"]
            condition.show_word_focus = policy["show_word_focus"]
            condition.show_sound_focus = policy["show_sound_focus"]
            condition.show_practice_suggestion = policy["show_practice_suggestion"]
            condition.revision_allowed = policy["revision_allowed"]
            condition.allow_revision = policy["allow_revision"]
            condition.enable_teacher_feedback = policy["enable_teacher_feedback"]
            condition.enable_peer_feedback = policy["enable_peer_feedback"]
        db.commit()
        rows = db.query(Condition).filter(Condition.study_id == study_id, Condition.condition_code.in_(codes)).order_by(Condition.id.asc()).all()
    result = []
    for row in rows:
        data = clean_model(row)
        data["friendly_label"] = ROLE_LABELS.get(row.condition_code, row.condition_name)
        result.append(data)
    return result


@router.post("/studies/{study_id}/activate-four-group-design")
def activate_four_group_design(study_id: int, db: Session = Depends(get_db)):
    list_conditions(study_id, db)
    return {"ok": True, "active_design": "feedback_information_comparison", "groups": ["G0", "G1", "G2", "G3"]}


@router.post("/studies/{study_id}/workflow-settings")
def workflow_settings(study_id: int, payload: dict, db: Session = Depends(get_db)):
    list_conditions(study_id, db)
    enable_teacher = bool(payload.get("enable_teacher_feedback", False))
    enable_peer = bool(payload.get("enable_peer_feedback", False))
    for condition in db.query(Condition).filter(Condition.study_id == study_id, Condition.condition_code.in_(["G0", "G1", "G2", "G3"])).all():
        condition.enable_teacher_feedback = enable_teacher
        condition.enable_peer_feedback = enable_peer
    db.commit()
    return {"ok": True, "enable_teacher_feedback": enable_teacher, "enable_peer_feedback": enable_peer}


@router.post("/studies/{study_id}/assign")
def assign_participant(study_id: int, payload: dict, db: Session = Depends(get_db)):
    participant_id = payload.get("participant_id")
    condition_code = normalize_condition(payload.get("condition", "G3"))
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
    user = db.query(User).filter(User.user_code == participant_id).first()
    if user:
        user.class_id = int(payload.get("class_id") or user.class_id or 0)
        user.group_id = int(payload.get("group_id") or user.group_id or 0)
    db.commit()
    return participant


@router.post("/studies/{study_id}/feedback-preview")
def preview_feedback(study_id: int, payload: dict, db: Session = Depends(get_db)):
    task_id = int(payload.get("task_id") or 0)
    condition_group = normalize_condition(payload.get("condition_group", "G3"))
    transcript = payload.get("transcript", "")
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    alignment = align_text(task.target_text, transcript)
    features = {
        "duration_seconds": 5,
        "speech_rate_wpm": 120,
        "long_pause_count": 0,
        "valid_audio": bool(transcript.strip()),
        "no_speech_detected": not bool(transcript.strip()),
        "invalid_reasons": [],
    }
    score_result = compute_practice_score(alignment, features)
    target_word = _target_word_from_alignment(task, alignment) or (_json(task.focus_words, "[]") or ["focus word"])[0]
    target_phoneme = _focus_phoneme_for_word(task, target_word)
    structured = feedback_from_issue(target_word, target_phoneme, task.speaking_target or "pronunciation_clarity")
    structured["score_breakdown"] = score_result["score_breakdown"]
    structured["score_note"] = score_result["score_note"]
    feedback = filter_feedback_for_condition(condition_group, transcript, score_result["practice_score"], structured)
    return {
        "task_id": task.id,
        "target_text": task.target_text,
        "condition_group": condition_group,
        "condition_label": feedback["condition_label"],
        "feedback": feedback,
    }


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
    group_id: str = Form("G3"),
    task_id: int = Form(...),
    study_id: int = Form(1),
    session_id: str = Form(""),
    transcript_hint: str = Form(""),
    workflow_request: str = Form(""),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content_type, ext = _validate_upload_metadata(audio)
    condition_key = normalize_condition(group_id)
    condition = db.query(Condition).filter(Condition.condition_code == condition_key).first()
    participant = db.query(Participant).filter(Participant.participant_id == participant_id).first()
    if not participant:
        participant = Participant(participant_id=participant_id, participant_code=participant_id, anonymous_code=_anonymized_code(participant_id), group_id=condition_key, study_id=study_id, condition_id=condition.id if condition else 4, session_id=session_id)
        db.add(participant)
    else:
        participant.anonymous_code = participant.anonymous_code or _participant_anonymous_code(participant)
        participant.group_id = condition_key
        participant.condition_id = condition.id if condition else participant.condition_id
        participant.study_id = study_id

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    study = db.query(Study).filter(Study.id == study_id).first() or db.query(Study).first()

    previous = db.query(Attempt).filter(Attempt.participant_id == participant_id, Attempt.task_id == task_id).order_by(Attempt.attempt_number.desc()).first()
    system_version = db.query(SystemVersion).order_by(SystemVersion.id.desc()).first()
    study_version = db.query(StudyVersion).filter(StudyVersion.study_id == study_id).order_by(StudyVersion.id.desc()).first()
    attempt_number = previous.attempt_number + 1 if previous else 1
    folder = _structured_audio_folder(study, participant, task)
    folder.mkdir(parents=True, exist_ok=True)
    audio_path = folder / ("attempt_%s%s" % (attempt_number, ext))
    with audio_path.open("wb") as f:
        shutil.copyfileobj(audio.file, f)
    file_size = audio_path.stat().st_size
    if file_size > MAX_AUDIO_MB * 1024 * 1024:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="Audio file exceeds %.1f MB limit." % MAX_AUDIO_MB)
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
    practice_clarity_score = score_result["practice_score"]
    display_score = practice_clarity_score
    pronunciation_assessment_score = None
    pronunciation_score_valid_for_research = False
    pronunciation_score_source = ""
    provider_result = None
    if RESEARCH_MODE and PRONUNCIATION_PROVIDER in ["disabled", "mock"]:
        raise HTTPException(status_code=503, detail="Research mode requires a real pronunciation provider, not %s." % PRONUNCIATION_PROVIDER)
    if not features.get("no_speech_detected"):
        provider = get_pronunciation_provider(db=db)
        provider_result = provider.assess(audio_path, task.target_text, {"task_id": task.id, "task_code": task.task_code, "session_type": getattr(task, "session_type", "")}, participant, {
            "practice_score": practice_clarity_score,
            "fluency_proxy_score": max(0, min(100, 100 - abs(features["speech_rate_wpm"] - 120) / 2)),
            "word_match_score": alignment["word_match_score"],
            "asr_transcript": transcript,
        })
        if provider_result.status == "error" and RESEARCH_MODE:
            raise HTTPException(status_code=503, detail=provider_result.error_message)
        raw_pronunciation_score = provider_result.pronunciation_score if provider_result.pronunciation_score is not None else provider_result.overall_score
        if raw_pronunciation_score is not None and provider_result.evidence_level != "practice_indicator" and provider_result.status == "ok":
            pronunciation_assessment_score = round(float(raw_pronunciation_score), 2)
            pronunciation_score_valid_for_research = provider_result.evidence_level in ["model_supported_diagnosis", "human_validated_diagnosis"]
            pronunciation_score_source = "%s:%s" % (provider_result.provider_name, provider_result.provider_version)
            display_score = pronunciation_assessment_score
    issues = _detect_issue_types(task, alignment, features)
    structured = generate_feedback("G3", display_score or 0, task.target_text, transcript, alignment, features)
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
            repeated=False,
        ))
    structured["practice_score"] = display_score
    structured["practice_clarity_score"] = practice_clarity_score
    structured["practice_clarity_score_source"] = "heuristic_practice_indicator"
    structured["pronunciation_assessment_score"] = pronunciation_assessment_score
    structured["pronunciation_assessment_score_source"] = pronunciation_score_source
    structured["pronunciation_score_valid_for_research"] = pronunciation_score_valid_for_research
    structured["score_breakdown"] = score_result["score_breakdown"]
    structured["score_note"] = score_result["score_note"]
    structured["asr_sanity"] = asr_sanity
    structured["evidence_level"] = provider_result.evidence_level if provider_result else "asr_supported_cue"
    structured["pronunciation_provider"] = provider_result.provider_name if provider_result else PRONUNCIATION_PROVIDER
    structured["provider_status"] = provider_result.status if provider_result else "not_run"
    if provider_result and provider_result.evidence_level == "practice_indicator":
        structured["score_note"] = "Practice indicator only. Mock pronunciation assessment is not valid research evidence."
    if features.get("no_speech_detected"):
        display_score = 0
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
        feedback = filter_feedback_for_condition(condition_key, transcript, display_score, structured)
        feedback["practice_clarity_score"] = practice_clarity_score
        feedback["practice_clarity_score_source"] = "heuristic_practice_indicator"
        feedback["pronunciation_assessment_score"] = pronunciation_assessment_score
        feedback["pronunciation_assessment_score_source"] = pronunciation_score_source
        feedback["pronunciation_score_valid_for_research"] = pronunciation_score_valid_for_research
        feedback["score_source"] = "pronunciation_assessment" if pronunciation_assessment_score is not None else "practice_clarity_indicator"
        feedback["score_label"] = "pronunciation assessment score" if pronunciation_assessment_score is not None else "practice clarity indicator"
        if RESEARCH_MODE and pronunciation_assessment_score is None:
            feedback["assessment_failed"] = True
            feedback["score_label"] = "assessment failed"
    if not task.feedback_allowed and not features.get("no_speech_detected"):
        feedback = filter_feedback_for_condition("G0", transcript, display_score, structured)
    workflow_request = (workflow_request or "").strip()
    if workflow_request in ["teacher_feedback", "peer_feedback"] and not features.get("no_speech_detected"):
        feedback["workflow_request"] = workflow_request
        feedback["workflow_request_label"] = "Sent to teacher for review." if workflow_request == "teacher_feedback" else "Sent to peer reviewer."
    feedback_type = feedback["feedback_type"]
    feedback_shown = feedback_type != "practice_only"

    attempt = Attempt(
        participant_id=participant_id,
        study_id=study_id,
        condition_id=condition.id if condition else 4,
        system_version_id=system_version.id if system_version else 1,
        study_version_id=study_version.id if study_version else 0,
        task_id=task_id,
        task_code=task.task_code or ("task_%s" % task.id),
        session_id=session_id,
        session_type=getattr(task, "session_type", "") or getattr(task, "task_type", ""),
        group_id=condition_key,
        attempt_number=attempt_number,
        submitted_at=datetime.utcnow(),
        audio_path=str(audio_path),
        asr_adapter=ASR_MODE,
        asr_transcript=transcript,
        duration_seconds=features["duration_seconds"],
        audio_duration=features["duration_seconds"],
        speech_rate_wpm=features["speech_rate_wpm"],
        word_match_score=alignment["word_match_score"],
        assessment_score=display_score,
        practice_clarity_score=practice_clarity_score,
        practice_clarity_score_source="heuristic_practice_indicator",
        pronunciation_assessment_score=pronunciation_assessment_score,
        pronunciation_assessment_score_source=pronunciation_score_source,
        pronunciation_score_valid_for_research=pronunciation_score_valid_for_research,
        evidence_level=provider_result.evidence_level if provider_result else "asr_supported_cue",
        missing_words_json=json.dumps(alignment["missing_words"]),
        substitutions_json=json.dumps(alignment["substitutions"]),
        issue_types_detected_json=json.dumps(issues),
        alignment_json=json.dumps(alignment),
        asr_sanity_json=json.dumps(asr_sanity),
        score_breakdown_json=json.dumps(score_result),
        valid_audio=bool(features.get("valid_audio", True)),
        invalid_audio_reason="; ".join(features.get("invalid_reasons", [])),
        assessment_provider=provider_result.provider_name if provider_result else PRONUNCIATION_PROVIDER,
        assessment_status=provider_result.status if provider_result else "not_run",
        overall_score=provider_result.overall_score if provider_result else None,
        accuracy_score=provider_result.accuracy_score if provider_result else None,
        fluency_score=provider_result.fluency_score if provider_result else None,
        completeness_score=provider_result.completeness_score if provider_result else None,
        prosody_score=provider_result.prosody_score if provider_result else None,
        long_pause_count=features["long_pause_count"],
        feedback_generated=True,
        feedback_shown=feedback_shown,
        feedback_displayed_to_learner=feedback_shown,
        feedback_type=feedback_type,
        feedback_policy_id=condition_key,
        feedback_json=json.dumps(feedback),
        raw_result_json=json.dumps(provider_result.raw_response_json if provider_result else {}),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    db.add(AudioFile(
        study_id=study_id,
        participant_id=participant_id,
        task_id=task_id,
        attempt_id=attempt.id,
        storage_path=str(audio_path),
        original_filename=audio.filename or "",
        content_type=content_type,
        file_size_bytes=file_size,
        duration_seconds=features["duration_seconds"],
        valid_audio=bool(features.get("valid_audio", True)),
        invalid_reasons_json=json.dumps(features.get("invalid_reasons", [])),
    ))
    if provider_result:
        provider_result.raw_response_json = {
            **(provider_result.raw_response_json or {}),
            "attempt_id": attempt.id,
            "file_name": audio.filename or "",
            "file_size_bytes": file_size,
        }
        _store_assessment_result(db, attempt, provider_result)

    if workflow_request == "teacher_feedback":
        db.add(TeacherOrchestrationEvent(
            study_id=attempt.study_id,
            condition_id=attempt.condition_id,
            teacher_id="",
            class_id=getattr(participant, "class_id", "") or "",
            participant_id_optional=participant_id,
            task_id=task_id,
            attempt_id=attempt.id,
            issue_type=(issues[0] if issues else ""),
            recommended_action="Student requested teacher review for this attempt.",
            teacher_action_taken="student_requested_teacher_feedback",
            notes="Created from student-selected review mode.",
            system_version_id=getattr(attempt, "system_version_id", 1),
        ))
    elif workflow_request == "peer_feedback":
        peer = db.query(User).filter(User.role == "peer_reviewer", User.active == True).order_by(User.id.asc()).first()  # noqa: E712
        if peer:
            exists = db.query(PeerReviewAssignment).filter(PeerReviewAssignment.reviewer_user_id == peer.id, PeerReviewAssignment.attempt_id == attempt.id).first()
            if not exists:
                db.add(PeerReviewAssignment(
                    reviewer_user_id=peer.id,
                    participant_id=participant_id,
                    task_id=task_id,
                    attempt_id=attempt.id,
                    status="assigned",
                ))

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
        source="template",
        approved_by_human=True,
        validation_status="draft_generated",
        released_to_learner=True,
        original_feedback_json=json.dumps(feedback),
        validated_feedback_json=json.dumps({}),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _log_feedback_event(db, participant_id, study_id, task_id, attempt.id, "feedback_generated", item.id, metadata={"feedback_type": feedback_type, "condition_group": condition_key})
    if feedback_shown:
        db.add(FeedbackView(participant_id=participant_id, task_id=task_id, attempt_id=attempt.id, feedback_item_id=item.id))
        attempt.feedback_viewed = True
        _log_feedback_event(db, participant_id, study_id, task_id, attempt.id, "feedback_visible_to_learner", item.id, metadata={"show_score": feedback.get("show_score"), "show_comment": feedback.get("show_comment")})

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
        previous.next_attempt_id = attempt.id
        previous_score = previous.assessment_score or _attempt_score(previous) or 0
        attempt.score_delta_from_previous_attempt = (display_score or 0) - previous_score
        prev_score = previous.assessment_score or _attempt_score(previous) or 0
        repeated_issue_reduced = len(issues) < len(_json(previous.issue_types_detected_json, "[]"))
        attempt.target_issue_resolved = repeated_issue_reduced
        revision = RevisionEvent(
            participant_id=participant_id,
            task_id=task_id,
            previous_attempt_id=previous.id,
            new_attempt_id=attempt.id,
            score_delta=(display_score or 0) - prev_score,
            word_match_delta=alignment["word_match_score"] - previous.word_match_score,
            repeated_issue_reduced=repeated_issue_reduced,
            transcript_change="%s -> %s" % (previous.asr_transcript, transcript),
            transcript_change_summary="Word match delta: %.2f" % (alignment["word_match_score"] - previous.word_match_score),
        )
        db.add(revision)
        _log_feedback_event(db, participant_id, study_id, task_id, previous.id, "learner_submitted_revised_attempt", item.id, event_value=str(attempt.id), metadata={"score_delta": revision.score_delta, "word_match_delta": revision.word_match_delta})
        _compute_feedback_uptake(db, participant_id, task_id, previous.id)
    _compute_feedback_uptake(db, participant_id, task_id, attempt.id)
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
    attempt = db.query(Attempt).filter(Attempt.id == item.attempt_id).first()
    if attempt:
        attempt.feedback_viewed = True
        attempt.feedback_view_time = float((payload or {}).get("view_duration_ms_optional", 0) or 0) / 1000
    _log_feedback_event(
        db,
        item.participant_id,
        attempt.study_id if attempt else 1,
        item.task_id,
        item.attempt_id,
        "learner_opened_feedback",
        item.id,
        duration_ms=(payload or {}).get("view_duration_ms_optional", 0),
        metadata=payload or {},
    )
    uptake = _compute_feedback_uptake(db, item.participant_id, item.task_id, item.attempt_id)
    db.commit()
    return {"ok": True, "feedback_uptake_state": uptake.uptake_state}


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
    db.add(ExportJob(report_type=report_type, path=str(path), anonymized=True, status="completed"))
    db.commit()
    return FileResponse(path, filename=path.name, media_type="text/csv")


@router.get("/exports/participants")
def export_participants(db: Session = Depends(get_db)):
    rows = []
    for participant in db.query(Participant).all():
        rows.append({
            "participant_code_anonymized": _participant_anonymous_code(participant),
            "study_id": participant.study_id,
            "condition_group": participant.group_id,
            "class_id": participant.class_id,
            "proficiency_level": participant.proficiency_level,
            "withdrawn": bool(getattr(participant, "withdrawn", False)),
            "created_at": participant.created_at,
        })
    return _write_csv(db, "participants", rows)


@router.get("/exports/participants-identifiable")
def export_participants_identifiable(admin_confirm: bool = False, db: Session = Depends(get_db)):
    if not admin_confirm:
        raise HTTPException(status_code=403, detail="Identifiable export requires admin_confirm=true.")
    _audit(db, "identifiable_export_requested", "export", "participants-identifiable", "admin_confirm=true")
    return _write_csv(db, "participants_identifiable", [clean_model(p) for p in db.query(Participant).all()])


@router.get("/exports/group-assignments")
def export_group_assignments(db: Session = Depends(get_db)):
    rows = [{
        "participant_code_anonymized": _participant_anonymous_code(participant),
        "study_id": participant.study_id,
        "condition_group": participant.group_id,
        "condition_id": participant.condition_id,
        "class_id": participant.class_id,
        "proficiency_level": participant.proficiency_level,
        "withdrawn": bool(getattr(participant, "withdrawn", False)),
    } for participant in db.query(Participant).all()]
    return _write_csv(db, "group_assignments", rows)


@router.get("/exports/attempts")
def export_attempts(db: Session = Depends(get_db)):
    rows = []
    for attempt in db.query(Attempt).order_by(Attempt.created_at.asc()).all():
        feedback = _json(attempt.feedback_json, "{}")
        policy = condition_policy(attempt.group_id)
        user = db.query(User).filter(User.user_code == attempt.participant_id).first()
        rows.append({
            "student_id": attempt.participant_id,
            "user_code": attempt.participant_id,
            "class_id": user.class_id if user else "",
            "group_id": user.group_id if user else attempt.group_id,
            "condition_group": feedback.get("condition_group", policy["condition_group"]),
            "condition_label": feedback.get("condition_label", policy["friendly_label"]),
            "score_available": attempt.assessment_score is not None,
            "practice_clarity_score": getattr(attempt, "practice_clarity_score", ""),
            "practice_clarity_score_source": getattr(attempt, "practice_clarity_score_source", ""),
            "pronunciation_assessment_score": getattr(attempt, "pronunciation_assessment_score", ""),
            "pronunciation_assessment_score_source": getattr(attempt, "pronunciation_assessment_score_source", ""),
            "provider_name": getattr(attempt, "assessment_provider", ""),
            "provider_version": "",
            "evidence_level": getattr(attempt, "evidence_level", ""),
            "score_valid_for_formal_research": getattr(attempt, "pronunciation_score_valid_for_research", False),
            "comment_available": bool(feedback.get("word_to_practise") or feedback.get("practice_suggestion")),
            "show_score": feedback.get("show_score", policy["show_score"]),
            "show_comment": feedback.get("show_comment", policy["show_comment"]),
            "attempt_number": attempt.attempt_number,
            "task_id": attempt.task_id,
            "score_shown": feedback.get("practice_score") is not None,
            "comment_shown": bool(feedback.get("show_comment") and feedback.get("comment")),
            "revision_allowed": feedback.get("revision_allowed", policy["revision_allowed"]),
            "created_at": attempt.created_at.isoformat(),
            "asr_adapter": attempt.asr_adapter,
            "valid_audio": getattr(attempt, "valid_audio", True),
            "withdrawn": bool(getattr(db.query(Participant).filter(Participant.participant_id == attempt.participant_id).first(), "withdrawn", False)),
        })
    return _write_csv(db, "attempts", rows)


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


@router.get("/exports/pronunciation-assessment-results")
def export_pronunciation_assessment_results(db: Session = Depends(get_db)):
    return _write_csv(db, "pronunciation_assessment_results", [clean_model(row) for row in db.query(PronunciationAssessmentResult).all()])


@router.get("/exports/word-level-results")
def export_word_level_results(db: Session = Depends(get_db)):
    return _write_csv(db, "word_level_results", [clean_model(row) for row in db.query(WordLevelAssessment).all()])


@router.get("/exports/phoneme-level-results")
def export_phoneme_level_results(db: Session = Depends(get_db)):
    return _write_csv(db, "phoneme_level_results", [clean_model(row) for row in db.query(PhonemeLevelAssessment).all()])


@router.get("/exports/feedback-events")
def export_feedback_events(db: Session = Depends(get_db)):
    return _write_csv(db, "feedback_events", [clean_model(row) for row in db.query(FeedbackEvent).all()])


@router.get("/exports/feedback-uptake-states")
def export_feedback_uptake_states(db: Session = Depends(get_db)):
    return _write_csv(db, "feedback_uptake_states", [clean_model(row) for row in db.query(FeedbackUptakeState).all()])


@router.get("/exports/human-ratings")
def export_human_ratings(db: Session = Depends(get_db)):
    return _write_csv(db, "human_ratings", [clean_model(row) for row in db.query(HumanRating).all()])


@router.get("/exports/questionnaire-responses")
def export_questionnaire_responses(db: Session = Depends(get_db)):
    return _write_csv(db, "questionnaire_responses", [clean_model(row) for row in db.query(QuestionnaireResponse).all()])


@router.get("/exports/audit-log")
def export_audit_log(db: Session = Depends(get_db)):
    return _write_csv(db, "audit_log", [clean_model(row) for row in db.query(AuditLog).all()])


def _analysis_ready_rows(db):
    rows = []
    for attempt in db.query(Attempt).order_by(Attempt.created_at.asc()).all():
        participant = db.query(Participant).filter(Participant.participant_id == attempt.participant_id).first()
        if participant and getattr(participant, "withdrawn", False):
            continue
        feedback = _json(attempt.feedback_json, "{}")
        assessment = db.query(PronunciationAssessmentResult).filter(PronunciationAssessmentResult.attempt_id == attempt.id).order_by(PronunciationAssessmentResult.id.desc()).first()
        uptake = db.query(FeedbackUptakeState).filter(FeedbackUptakeState.attempt_id == attempt.id).first()
        ratings = db.query(HumanRating).filter(HumanRating.attempt_id == attempt.id).all()
        base = {
            "participant_code_anonymized": _participant_anonymous_code(participant or attempt.participant_id),
            "study_id": attempt.study_id,
            "study_version_id": getattr(attempt, "study_version_id", 0),
            "condition_group": feedback.get("condition_group", attempt.group_id),
            "class_id": getattr(participant, "class_id", "") if participant else "",
            "proficiency_level": getattr(participant, "proficiency_level", "") if participant else "",
            "session_type": getattr(attempt, "session_type", ""),
            "is_pre_test": getattr(attempt, "session_type", "") == "pre_test",
            "is_immediate_post_test": getattr(attempt, "session_type", "") == "immediate_post_test",
            "is_delayed_post_test": getattr(attempt, "session_type", "") == "delayed_post_test",
            "task_code": getattr(attempt, "task_code", ""),
            "task_id": attempt.task_id,
            "attempt_number": attempt.attempt_number,
            "audio_validity": getattr(attempt, "valid_audio", True),
            "invalid_audio_reason": getattr(attempt, "invalid_audio_reason", ""),
            "automatic_overall_score": getattr(assessment, "overall_score", None) if assessment else getattr(attempt, "overall_score", None),
            "pronunciation_assessment_score": getattr(attempt, "pronunciation_assessment_score", None),
            "pronunciation_assessment_score_source": getattr(attempt, "pronunciation_assessment_score_source", ""),
            "practice_clarity_score": getattr(attempt, "practice_clarity_score", None),
            "practice_clarity_score_source": getattr(attempt, "practice_clarity_score_source", ""),
            "score_valid_for_formal_research": bool(getattr(attempt, "pronunciation_score_valid_for_research", False)),
            "evidence_level": getattr(attempt, "evidence_level", ""),
            "accuracy_score": getattr(assessment, "accuracy_score", None) if assessment else "",
            "fluency_score": getattr(assessment, "fluency_score", None) if assessment else "",
            "completeness_score": getattr(assessment, "completeness_score", None) if assessment else "",
            "feedback_type": attempt.feedback_type,
            "feedback_displayed_to_learner": getattr(attempt, "feedback_displayed_to_learner", False),
            "feedback_viewed": getattr(attempt, "feedback_viewed", False),
            "feedback_view_duration_seconds": getattr(attempt, "feedback_view_time", 0),
            "revision_count": db.query(RevisionEvent).filter(RevisionEvent.previous_attempt_id == attempt.id).count(),
            "uptake_state": uptake.uptake_state if uptake else _feedback_use_state(db, attempt),
            "valid_audio": getattr(attempt, "valid_audio", True),
            "missing_pronunciation_assessment": getattr(attempt, "pronunciation_assessment_score", None) is None,
            "missing_human_rating": len(ratings) == 0,
            "withdrawal_flag": bool(getattr(participant, "withdrawn", False)) if participant else False,
            "system_version": SYSTEM_VERSION,
            "provider_name": getattr(assessment, "provider_name", getattr(attempt, "assessment_provider", "")) if assessment else getattr(attempt, "assessment_provider", ""),
            "provider_version": getattr(assessment, "provider_version", "") if assessment else "",
        }
        if ratings:
            for rating in ratings:
                rows.append({**base, "human_rater_id": rating.rater_id, "human_pronunciation": rating.pronunciation, "human_fluency": rating.fluency, "human_comprehensibility": rating.comprehensibility})
        else:
            rows.append({**base, "human_rater_id": "", "human_pronunciation": "", "human_fluency": "", "human_comprehensibility": ""})
    return rows


@router.get("/exports/analysis-ready-long")
def export_analysis_ready_long(db: Session = Depends(get_db)):
    return _write_csv(db, "analysis_ready_long", _analysis_ready_rows(db))


@router.get("/exports/analysis-ready-wide")
def export_analysis_ready_wide(db: Session = Depends(get_db)):
    rows_by_key = {}
    for row in _analysis_ready_rows(db):
        key = row["participant_code_anonymized"]
        session_key = row["session_type"] or "session"
        base = rows_by_key.setdefault(key, {"participant_code_anonymized": key, "condition_group": row["condition_group"], "class_id": row["class_id"], "proficiency_level": row["proficiency_level"]})
        prefix = "%s_task_%s_attempt_%s" % (session_key, row["task_id"], row["attempt_number"])
        base[prefix + "_score"] = row["automatic_overall_score"]
        base[prefix + "_valid_audio"] = row["valid_audio"]
        base[prefix + "_uptake_state"] = row["uptake_state"]
    return _write_csv(db, "analysis_ready_wide", list(rows_by_key.values()))


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
    return export_revision_events_alias(db)


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
    attempts_rows = []
    for attempt in db.query(Attempt).order_by(Attempt.created_at.asc()).all():
        feedback = _json(attempt.feedback_json, "{}")
        policy = condition_policy(attempt.group_id)
        user = db.query(User).filter(User.user_code == attempt.participant_id).first()
        attempts_rows.append({
            "student_id": attempt.participant_id,
            "user_code": attempt.participant_id,
            "class_id": user.class_id if user else "",
            "group_id": user.group_id if user else attempt.group_id,
            "condition_group": feedback.get("condition_group", policy["condition_group"]),
            "condition_label": feedback.get("condition_label", policy["friendly_label"]),
            "score_available": attempt.assessment_score is not None,
            "comment_available": bool(feedback.get("word_to_practise") or feedback.get("practice_suggestion")),
            "show_score": feedback.get("show_score", policy["show_score"]),
            "show_comment": feedback.get("show_comment", policy["show_comment"]),
            "attempt_number": attempt.attempt_number,
            "task_id": attempt.task_id,
            "score_shown": feedback.get("practice_score") is not None,
            "comment_shown": bool(feedback.get("show_comment") and feedback.get("comment")),
            "revision_allowed": feedback.get("revision_allowed", policy["revision_allowed"]),
            "created_at": attempt.created_at.isoformat(),
        })
    ai_rows = []
    for item in db.query(FeedbackItem).order_by(FeedbackItem.created_at.asc()).all():
        attempt = db.query(Attempt).filter(Attempt.id == item.attempt_id).first()
        feedback = _json(item.original_feedback_json, "{}")
        policy = condition_policy(attempt.group_id if attempt else feedback.get("condition_group", "G3"))
        ai_rows.append({
            "student_id": item.participant_id,
            "condition_group": feedback.get("condition_group", policy["condition_group"]),
            "task_id": item.task_id,
            "attempt_id": item.attempt_id,
            "word_to_practise": feedback.get("word_to_practise", feedback.get("word_label", "")),
            "target_sound": feedback.get("target_sound", feedback.get("sound_focus_label", "")),
            "practice_suggestion": feedback.get("practice_suggestion", feedback.get("action_guidance", "")),
            "revision_goal": feedback.get("revision_goal", ""),
            "score_value": feedback.get("practice_score") if feedback.get("show_score", policy["show_score"]) else "",
            "score_hidden": not bool(feedback.get("show_score", policy["show_score"])),
            "comment_hidden": not bool(feedback.get("show_comment", policy["show_comment"])),
        })
    view_rows = []
    for view in db.query(FeedbackView).order_by(FeedbackView.viewed_at.asc()).all():
        attempt = db.query(Attempt).filter(Attempt.id == view.attempt_id).first()
        feedback = _json(attempt.feedback_json, "{}") if attempt else {}
        policy = condition_policy(attempt.group_id if attempt else "G3")
        feedback_types = []
        if feedback.get("show_score"):
            feedback_types.append("score")
        if feedback.get("show_comment"):
            feedback_types.append("comment")
        if not feedback_types:
            feedback_types.append("practice")
        for feedback_type in feedback_types:
            view_rows.append({
                "student_id": view.participant_id,
                "condition_group": feedback.get("condition_group", policy["condition_group"]),
                "feedback_type": feedback_type,
                "viewed_at": view.viewed_at.isoformat(),
                "task_id": view.task_id,
                "attempt_id": view.attempt_id,
            })
    revision_rows = []
    for revision in db.query(RevisionEvent).order_by(RevisionEvent.created_at.asc()).all():
        attempt = db.query(Attempt).filter(Attempt.id == revision.new_attempt_id).first()
        policy = condition_policy(attempt.group_id if attempt else "G3")
        revision_rows.append({
            "student_id": revision.participant_id,
            "condition_group": policy["condition_group"],
            "task_id": revision.task_id,
            "previous_attempt_id": revision.previous_attempt_id,
            "new_attempt_id": revision.new_attempt_id,
            "score_delta": revision.score_delta,
            "target_word_improved": revision.repeated_issue_reduced,
            "created_at": revision.created_at.isoformat(),
        })
    export_sets = {
        "participants.csv": [{
            "participant_code_anonymized": _participant_anonymous_code(p),
            "study_id": p.study_id,
            "condition_group": p.group_id,
            "class_id": p.class_id,
            "proficiency_level": p.proficiency_level,
            "withdrawn": bool(getattr(p, "withdrawn", False)),
            "created_at": p.created_at,
        } for p in db.query(Participant).all()],
        "group_assignments.csv": [{
            "participant_code_anonymized": _participant_anonymous_code(p),
            "study_id": p.study_id,
            "condition_group": p.group_id,
            "condition_id": p.condition_id,
            "class_id": p.class_id,
            "proficiency_level": p.proficiency_level,
            "withdrawn": bool(getattr(p, "withdrawn", False)),
        } for p in db.query(Participant).all()],
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
        "attempts.csv": attempts_rows,
        "audio_files.csv": [clean_model(row) for row in db.query(AudioFile).all()],
        "pronunciation_assessment_results.csv": [clean_model(row) for row in db.query(PronunciationAssessmentResult).all()],
        "word_level_results.csv": [clean_model(row) for row in db.query(WordLevelAssessment).all()],
        "phoneme_level_results.csv": [clean_model(row) for row in db.query(PhonemeLevelAssessment).all()],
        "pronunciation_evidence.csv": [clean_model(row) for row in db.query(PronunciationEvidence).all()],
        "diagnosis_records.csv": [clean_model(row) for row in db.query(DiagnosisRecord).all()],
        "ai_feedback.csv": ai_rows,
        "feedback_events.csv": [clean_model(row) for row in db.query(FeedbackEvent).all()],
        "feedback_uptake_states.csv": [clean_model(row) for row in db.query(FeedbackUptakeState).all()],
        "teacher_feedback.csv": [clean_model(row) for row in db.query(TeacherFeedback).all()],
        "peer_feedback.csv": [clean_model(row) for row in db.query(PeerFeedback).all()],
        "human_ratings.csv": [clean_model(row) for row in db.query(HumanRating).all()],
        "questionnaire_responses.csv": [clean_model(row) for row in db.query(QuestionnaireResponse).all()],
        "consent_records.csv": [clean_model(row) for row in db.query(ConsentRecord).all()],
        "audit_log.csv": [clean_model(row) for row in db.query(AuditLog).all()],
        "analysis_ready_long.csv": _analysis_ready_rows(db),
        "feedback_views.csv": view_rows,
        "revision_events.csv": revision_rows,
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


@router.get("/exports/sessions")
def export_sessions(db: Session = Depends(get_db)):
    return _write_csv(db, "sessions", [clean_model(row) for row in db.query(ResearchSession).all()])


@router.get("/exports/task-sets")
def export_task_sets(db: Session = Depends(get_db)):
    return _write_csv(db, "task_sets", [clean_model(row) for row in db.query(TaskSet).all()])


@router.get("/exports/users")
def export_users(db: Session = Depends(get_db)):
    rows = []
    for user in db.query(User).order_by(User.id.asc()).all():
        data = _user_dict(user, db)
        rows.append({
            "user_code": data["user_code"],
            "role": data["role"],
            "display_name": data["display_name"],
            "class_id": data["class_id"],
            "group_id": data["group_id"],
            "condition_group": data.get("condition_group", ""),
            "condition_label": data.get("condition_label", ""),
            "active": data["active"],
        })
    return _write_csv(db, "users", rows)


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
    rows = []
    for item in db.query(FeedbackItem).order_by(FeedbackItem.created_at.asc()).all():
        attempt = db.query(Attempt).filter(Attempt.id == item.attempt_id).first()
        feedback = _json(item.original_feedback_json, "{}")
        policy = condition_policy(attempt.group_id if attempt else feedback.get("condition_group", "G3"))
        rows.append({
            "student_id": item.participant_id,
            "condition_group": feedback.get("condition_group", policy["condition_group"]),
            "task_id": item.task_id,
            "attempt_id": item.attempt_id,
            "word_to_practise": feedback.get("word_to_practise", feedback.get("word_label", "")),
            "target_sound": feedback.get("target_sound", feedback.get("sound_focus_label", "")),
            "practice_suggestion": feedback.get("practice_suggestion", feedback.get("action_guidance", "")),
            "revision_goal": feedback.get("revision_goal", ""),
            "score_value": feedback.get("practice_score") if feedback.get("show_score", policy["show_score"]) else "",
            "score_hidden": not bool(feedback.get("show_score", policy["show_score"])),
            "comment_hidden": not bool(feedback.get("show_comment", policy["show_comment"])),
        })
    return _write_csv(db, "ai_feedback", rows)


@router.get("/exports/teacher-feedback")
def export_teacher_feedback(db: Session = Depends(get_db)):
    return _write_csv(db, "teacher_feedback", [clean_model(row) for row in db.query(TeacherFeedback).all()])


@router.get("/exports/peer-feedback")
def export_peer_feedback(db: Session = Depends(get_db)):
    return _write_csv(db, "peer_feedback", [clean_model(row) for row in db.query(PeerFeedback).all()])


@router.get("/exports/feedback-views")
def export_feedback_views(db: Session = Depends(get_db)):
    rows = []
    for view in db.query(FeedbackView).order_by(FeedbackView.viewed_at.asc()).all():
        attempt = db.query(Attempt).filter(Attempt.id == view.attempt_id).first()
        feedback = _json(attempt.feedback_json, "{}") if attempt else {}
        policy = condition_policy(attempt.group_id if attempt else "G3")
        feedback_types = []
        if feedback.get("show_score"):
            feedback_types.append("score")
        if feedback.get("show_comment"):
            feedback_types.append("comment")
        if not feedback_types:
            feedback_types.append("practice")
        for feedback_type in feedback_types:
            rows.append({
                "student_id": view.participant_id,
                "condition_group": feedback.get("condition_group", policy["condition_group"]),
                "feedback_type": feedback_type,
                "viewed_at": view.viewed_at.isoformat(),
                "task_id": view.task_id,
                "attempt_id": view.attempt_id,
            })
    return _write_csv(db, "feedback_views", rows)


@router.get("/exports/learner-progress")
def export_learner_progress(db: Session = Depends(get_db)):
    rows = []
    for user in db.query(User).filter(User.role == "student").all():
        progress = student_progress(user.user_code, db)
        rows.append({"user_code": user.user_code, **progress})
    return _write_csv(db, "learner_progress", rows)


@router.get("/exports/revision-events")
def export_revision_events_alias(db: Session = Depends(get_db)):
    rows = []
    for revision in db.query(RevisionEvent).order_by(RevisionEvent.created_at.asc()).all():
        attempt = db.query(Attempt).filter(Attempt.id == revision.new_attempt_id).first()
        policy = condition_policy(attempt.group_id if attempt else "G3")
        rows.append({
            "student_id": revision.participant_id,
            "condition_group": policy["condition_group"],
            "task_id": revision.task_id,
            "previous_attempt_id": revision.previous_attempt_id,
            "new_attempt_id": revision.new_attempt_id,
            "score_delta": revision.score_delta,
            "target_word_improved": revision.repeated_issue_reduced,
            "created_at": revision.created_at.isoformat(),
        })
    return _write_csv(db, "revision_events", rows)


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
