import csv
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
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
    Condition,
    FeedbackItem,
    FeedbackView,
    IssueRecord,
    LearnerState,
    Participant,
    RevisionEvent,
    Study,
    SystemVersion,
    Task,
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
from .services.validation.agreement import annotation_agreement


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
        speaking_target=task.speaking_target or "",
        difficulty=task.difficulty or "medium",
        model_audio_path=task.model_audio_path or "",
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


@router.post("/studies/{study_id}/conditions")
def create_condition(study_id: int, payload: dict, db: Session = Depends(get_db)):
    condition = Condition(study_id=study_id, **payload)
    db.add(condition)
    db.commit()
    db.refresh(condition)
    return condition


@router.get("/studies/{study_id}/conditions")
def list_conditions(study_id: int, db: Session = Depends(get_db)):
    return db.query(Condition).filter(Condition.study_id == study_id).order_by(Condition.id.asc()).all()


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
    task = Task(
        task_code=payload.task_code,
        task_type=payload.task_type,
        target_text=payload.target_text,
        issue_types_json=json.dumps(payload.issue_types),
        focus_words=json.dumps(payload.focus_words),
        speaking_target=payload.speaking_target,
        difficulty=payload.difficulty,
        model_audio_path=payload.model_audio_path,
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
    for key, value in payload.model_dump().items():
        if key == "focus_words":
            task.focus_words = json.dumps(value)
        elif key == "issue_types":
            task.issue_types_json = json.dumps(value)
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
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    if feedback_shown:
        db.add(FeedbackView(participant_id=participant_id, task_id=task_id, attempt_id=attempt.id, feedback_item_id=item.id))

    task_issues = _json(task.issue_types_json, "[]")
    focus_words = _json(task.focus_words, "[]")
    for issue in issue_records_for_alignment(task_issues, focus_words, alignment, features):
        db.add(IssueRecord(
            participant_id=participant_id,
            task_id=task_id,
            attempt_id=attempt.id,
            issue_type=issue["issue_type"],
            target_word=issue["target_word"],
            severity=0.5 if issue["severity"] == "moderate" else 1.0,
            evidence_json=json.dumps({"evidence": issue["evidence"], "alignment": alignment, "extra": issue["extra"]}),
        ))

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


@router.get("/feedback/{attempt_id}")
def feedback_for_attempt(attempt_id: int, db: Session = Depends(get_db)):
    return db.query(FeedbackItem).filter(FeedbackItem.attempt_id == attempt_id).all()


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
    by_participant_task = defaultdict(list)
    for a in attempts:
        by_condition[a.group_id].append(a)
        missing.update(_json(a.missing_words_json, "[]"))
        issues.update(_json(a.issue_types_detected_json, "[]"))
        policy.update([a.feedback_type])
        by_participant_task[(a.participant_id, a.task_id)].append(a)
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
        "average_improvement_first_to_latest": round(sum(improvements) / len(improvements), 2) if improvements else 0,
        "feedback_views": db.query(FeedbackView).count(),
        "revision_events": db.query(RevisionEvent).count(),
        "learner_state_count": db.query(LearnerState).count(),
        "system_version": db.query(SystemVersion).order_by(SystemVersion.id.desc()).first(),
    }


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
    return export_attempts(db)


@router.get("/exports/participant/{participant_id}")
def export_participant(participant_id: str, db: Session = Depends(get_db)):
    rows = [_attempt_to_dict(db, a) for a in db.query(Attempt).filter(Attempt.participant_id == participant_id).all()]
    return _write_csv(db, "participant_%s" % participant_id, rows)


@router.get("/exports/tasks")
def export_tasks(db: Session = Depends(get_db)):
    return _write_csv(db, "tasks", [clean_model(t) for t in db.query(Task).all()])


def clean_model(model):
    data = dict(model.__dict__)
    data.pop("_sa_instance_state", None)
    return data
