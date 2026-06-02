import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .analysis.asr import asr_service
from .analysis.audio_features import analyze_audio
from .analysis.feedback_generator import generate_feedback
from .analysis.scoring import compute_score
from .analysis.text_alignment import align_text
from .config import AUDIO_DIR
from .database import Attempt, FeedbackView, Participant, RevisionEvent, Task, get_db
from .export import write_attempt_csv, write_task_summary_csv
from .schemas import DashboardSummary, ParticipantCreate, ParticipantRead, TaskCreate, TaskRead


router = APIRouter()


def _task_to_schema(task):
    return TaskRead(
        id=task.id,
        target_text=task.target_text,
        focus_words=json.loads(task.focus_words or "[]"),
        speaking_target=task.speaking_target or "",
        difficulty=task.difficulty or "medium",
        model_audio_path=task.model_audio_path or "",
        created_at=task.created_at,
    )


def _attempt_to_dict(attempt, base_score=None):
    feedback = json.loads(attempt.feedback_json or "{}")
    score = feedback.get("overall_score", 0)
    return {
        "id": attempt.id,
        "participant_id": attempt.participant_id,
        "task_id": attempt.task_id,
        "group_id": attempt.group_id,
        "attempt_number": attempt.attempt_number,
        "audio_path": attempt.audio_path,
        "asr_transcript": attempt.asr_transcript,
        "duration_seconds": attempt.duration_seconds,
        "speech_rate_wpm": attempt.speech_rate_wpm,
        "word_match_score": attempt.word_match_score,
        "missing_words": json.loads(attempt.missing_words_json or "[]"),
        "substitutions": json.loads(attempt.substitutions_json or "[]"),
        "long_pause_count": attempt.long_pause_count,
        "feedback_type": attempt.feedback_type,
        "feedback": feedback,
        "created_at": attempt.created_at,
        "target_text": attempt.task.target_text if attempt.task else "",
        "score": score,
        "improvement": round(score - base_score, 2) if base_score is not None else 0,
    }


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/participants", response_model=ParticipantRead)
def create_participant(payload: ParticipantCreate, db: Session = Depends(get_db)):
    participant = db.query(Participant).filter(Participant.participant_id == payload.participant_id).first()
    if participant:
        participant.group_id = payload.group_id
        participant.session_id = payload.session_id or participant.session_id
    else:
        participant = Participant(**payload.model_dump())
        db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


@router.get("/tasks", response_model=List[TaskRead])
def list_tasks(db: Session = Depends(get_db)):
    return [_task_to_schema(t) for t in db.query(Task).order_by(Task.id.asc()).all()]


@router.post("/tasks", response_model=TaskRead)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = Task(
        target_text=payload.target_text,
        focus_words=json.dumps(payload.focus_words),
        speaking_target=payload.speaking_target,
        difficulty=payload.difficulty,
        model_audio_path=payload.model_audio_path,
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
    task.target_text = payload.target_text
    task.focus_words = json.dumps(payload.focus_words)
    task.speaking_target = payload.speaking_target
    task.difficulty = payload.difficulty
    task.model_audio_path = payload.model_audio_path
    db.commit()
    db.refresh(task)
    return _task_to_schema(task)


@router.post("/attempts/analyze")
def analyze_attempt(
    participant_id: str = Form(...),
    group_id: str = Form(...),
    task_id: int = Form(...),
    session_id: str = Form(""),
    transcript_hint: str = Form(""),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    participant = db.query(Participant).filter(Participant.participant_id == participant_id).first()
    if not participant:
        participant = Participant(participant_id=participant_id, group_id=group_id, session_id=session_id)
        db.add(participant)
    else:
        participant.group_id = group_id

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
    score = compute_score(alignment, features)
    feedback_type = "explainable" if group_id == "explainable" else "score_only"
    feedback = generate_feedback(group_id, score, task.target_text, transcript, alignment, features)

    attempt = Attempt(
        participant_id=participant_id,
        task_id=task_id,
        group_id=group_id,
        attempt_number=attempt_number,
        audio_path=str(audio_path),
        asr_transcript=transcript,
        duration_seconds=features["duration_seconds"],
        speech_rate_wpm=features["speech_rate_wpm"],
        word_match_score=alignment["word_match_score"],
        missing_words_json=json.dumps(alignment["missing_words"]),
        substitutions_json=json.dumps(alignment["substitutions"]),
        long_pause_count=features["long_pause_count"],
        feedback_type=feedback_type,
        feedback_json=json.dumps(feedback),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    db.add(FeedbackView(participant_id=participant_id, task_id=task_id, attempt_id=attempt.id))

    if previous:
        prev_score = json.loads(previous.feedback_json or "{}").get("overall_score", 0)
        db.add(RevisionEvent(
            participant_id=participant_id,
            task_id=task_id,
            previous_attempt_id=previous.id,
            new_attempt_id=attempt.id,
            score_delta=score - prev_score,
            transcript_change="%s -> %s" % (previous.asr_transcript, transcript),
        ))
    db.commit()
    return _attempt_to_dict(attempt)


@router.get("/attempts/{participant_id}")
def participant_attempts(participant_id: str, db: Session = Depends(get_db)):
    attempts = db.query(Attempt).filter(Attempt.participant_id == participant_id).order_by(Attempt.created_at.asc()).all()
    first_scores = {}
    for attempt in attempts:
        first_scores.setdefault(attempt.task_id, json.loads(attempt.feedback_json or "{}").get("overall_score", 0))
    return [_attempt_to_dict(a, first_scores.get(a.task_id)) for a in attempts]


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(group: str = "", participant: str = "", task_id: int = 0, db: Session = Depends(get_db)):
    query = db.query(Attempt)
    if group:
        query = query.filter(Attempt.group_id == group)
    if participant:
        query = query.filter(Attempt.participant_id == participant)
    if task_id:
        query = query.filter(Attempt.task_id == task_id)
    attempts = query.all()
    participants = len(set(a.participant_id for a in attempts))
    tasks = len(set(a.task_id for a in attempts)) or 1
    missing = Counter()
    subs = Counter()
    by_participant_task = defaultdict(list)
    for a in attempts:
        missing.update(json.loads(a.missing_words_json or "[]"))
        for s in json.loads(a.substitutions_json or "[]"):
            subs.update(["%s -> %s" % (s.get("expected", ""), s.get("heard", ""))])
        by_participant_task[(a.participant_id, a.task_id)].append(a)
    improvements = []
    for group_attempts in by_participant_task.values():
        ordered = sorted(group_attempts, key=lambda item: item.attempt_number)
        if len(ordered) > 1:
            first = json.loads(ordered[0].feedback_json or "{}").get("overall_score", 0)
            latest = json.loads(ordered[-1].feedback_json or "{}").get("overall_score", 0)
            improvements.append(latest - first)
    return {
        "participants": participants,
        "attempts": len(attempts),
        "average_attempts_per_task": round(len(attempts) / tasks, 2),
        "average_word_match_score": round(sum(a.word_match_score for a in attempts) / len(attempts), 2) if attempts else 0,
        "average_speech_rate_wpm": round(sum(a.speech_rate_wpm for a in attempts) / len(attempts), 2) if attempts else 0,
        "common_missing_words": [{"word": k, "count": v} for k, v in missing.most_common(10)],
        "common_substitutions": [{"substitution": k, "count": v} for k, v in subs.most_common(10)],
        "average_improvement_first_to_latest": round(sum(improvements) / len(improvements), 2) if improvements else 0,
        "feedback_views": db.query(FeedbackView).count(),
        "revision_events": db.query(RevisionEvent).count(),
    }


@router.get("/exports/full")
def export_full(db: Session = Depends(get_db)):
    return FileResponse(write_attempt_csv(db, "full_dataset"), filename="full_dataset.csv")


@router.get("/exports/participant/{participant_id}")
def export_participant(participant_id: str, db: Session = Depends(get_db)):
    return FileResponse(write_attempt_csv(db, "participant", participant_id), filename="participant_%s.csv" % participant_id)


@router.get("/exports/tasks")
def export_tasks(db: Session = Depends(get_db)):
    return FileResponse(write_task_summary_csv(db), filename="task_summary.csv")
