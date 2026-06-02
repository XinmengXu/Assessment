from app.analysis.text_alignment import align_text
from app.services.feedback.issue_taxonomy import issue_records_for_alignment


def test_focus_word_uses_task_issue_type():
    alignment = align_text("The teacher thought the theory was difficult.", "the teacher the theory was difficult")
    records = issue_records_for_alignment(["theta_words"], ["thought", "theory"], alignment, {"speech_rate_wpm": 120, "long_pause_count": 0})
    assert any(record["issue_type"] == "theta_words" and record["target_word"] == "thought" for record in records)


def test_speech_rate_issue_is_recorded():
    records = issue_records_for_alignment([], [], {"missing_words": [], "substitutions": []}, {"speech_rate_wpm": 220, "long_pause_count": 0})
    assert any(record["issue_type"] == "speech_rate_fast" for record in records)
