import csv
import json
from datetime import datetime
from pathlib import Path

from .config import EXPORT_DIR
from .database import Attempt, ExportedReport, Task


FIELDS = [
    "attempt_id", "participant_id", "group_id", "task_id", "attempt_number",
    "timestamp", "target_text", "transcript", "score", "duration_seconds",
    "speech_rate_wpm", "word_match_score", "missing_words", "substitutions",
    "long_pause_count", "feedback_type",
]


def _attempt_rows(db, participant_id=None):
    query = db.query(Attempt).join(Task, Attempt.task_id == Task.id)
    if participant_id:
        query = query.filter(Attempt.participant_id == participant_id)
    rows = []
    for attempt in query.order_by(Attempt.created_at.asc()).all():
        feedback = json.loads(attempt.feedback_json or "{}")
        rows.append({
            "attempt_id": attempt.id,
            "participant_id": attempt.participant_id,
            "group_id": attempt.group_id,
            "task_id": attempt.task_id,
            "attempt_number": attempt.attempt_number,
            "timestamp": attempt.created_at.isoformat(),
            "target_text": attempt.task.target_text if attempt.task else "",
            "transcript": attempt.asr_transcript,
            "score": feedback.get("overall_score", 0),
            "duration_seconds": attempt.duration_seconds,
            "speech_rate_wpm": attempt.speech_rate_wpm,
            "word_match_score": attempt.word_match_score,
            "missing_words": attempt.missing_words_json,
            "substitutions": attempt.substitutions_json,
            "long_pause_count": attempt.long_pause_count,
            "feedback_type": attempt.feedback_type,
        })
    return rows


def write_attempt_csv(db, report_type, participant_id=None):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    name = report_type if not participant_id else "%s_%s" % (report_type, participant_id)
    path = EXPORT_DIR / ("%s_%s.csv" % (name, stamp))
    rows = _attempt_rows(db, participant_id)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    db.add(ExportedReport(report_type=report_type, path=str(path)))
    db.commit()
    return path


def write_task_summary_csv(db):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / ("task_summary_%s.csv" % datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
    rows = []
    for task in db.query(Task).all():
        attempts = db.query(Attempt).filter(Attempt.task_id == task.id).all()
        avg = sum(a.word_match_score for a in attempts) / len(attempts) if attempts else 0
        rows.append({"task_id": task.id, "target_text": task.target_text, "attempts": len(attempts), "average_word_match_score": round(avg, 2)})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["task_id", "target_text", "attempts", "average_word_match_score"])
        writer.writeheader()
        writer.writerows(rows)
    return path
