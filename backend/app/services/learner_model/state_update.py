import json

from ...database import Attempt, FeedbackView, LearnerState, RevisionEvent


def update_learner_state(db, participant_id, attempt):
    previous = (
        db.query(LearnerState)
        .filter(LearnerState.participant_id == participant_id)
        .order_by(LearnerState.id.desc())
        .first()
    )
    clarity = previous.pronunciation_clarity if previous else 50.0
    fluency = previous.fluency_stability if previous else 50.0
    uptake = previous.feedback_uptake if previous else 0.0
    responsiveness = previous.revision_responsiveness if previous else 0.0
    persistent = set(json.loads(previous.persistent_issues_json or "[]")) if previous else set()

    issues = json.loads(attempt.issue_types_detected_json or "[]")
    clarity = _bounded(clarity * 0.7 + attempt.word_match_score * 0.3)
    if 70 <= attempt.speech_rate_wpm <= 180 and attempt.long_pause_count == 0:
        fluency = _bounded(fluency + 5)
    else:
        fluency = _bounded(fluency - 3)

    viewed = db.query(FeedbackView).filter(FeedbackView.attempt_id == attempt.id).count() > 0
    if viewed:
        uptake = _bounded(uptake + 10)

    revision = db.query(RevisionEvent).filter(RevisionEvent.new_attempt_id == attempt.id).first()
    if revision:
        if revision.score_delta > 0 or revision.word_match_delta > 0:
            responsiveness = _bounded(responsiveness + 12)
        else:
            responsiveness = _bounded(responsiveness + 3)

    for issue in issues:
        if issue:
            repeated = (
                db.query(Attempt)
                .filter(Attempt.participant_id == participant_id, Attempt.issue_types_detected_json.like("%" + issue + "%"))
                .count()
            )
            if repeated >= 2:
                persistent.add(issue)
    if attempt.word_match_score >= 90:
        persistent = {issue for issue in persistent if issue not in issues}

    state = LearnerState(
        participant_id=participant_id,
        after_attempt_id=attempt.id,
        pronunciation_clarity=round(clarity, 2),
        fluency_stability=round(fluency, 2),
        feedback_uptake=round(uptake, 2),
        revision_responsiveness=round(responsiveness, 2),
        persistent_issues_json=json.dumps(sorted(persistent)),
        state_json=json.dumps({
            "latest_score": attempt.assessment_score,
            "latest_word_match_score": attempt.word_match_score,
            "latest_speech_rate_wpm": attempt.speech_rate_wpm,
        }),
    )
    db.add(state)
    return state


def _bounded(value):
    return max(0.0, min(100.0, value))
