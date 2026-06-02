from app.analysis.feedback_generator import generate_feedback


def test_explainable_feedback_has_feedback_use_pathway():
    feedback = generate_feedback(
        "explainable",
        72,
        "She thought clearly",
        "she clearly",
        {"missing_words": ["thought"], "substitutions": [], "word_match_score": 66},
        {"speech_rate_wpm": 110, "long_pause_count": 0},
    )
    assert "diagnosis" in feedback
    assert "explanation" in feedback
    assert "action_guidance" in feedback
    assert "revision_instruction" in feedback


def test_control_feedback_is_score_only():
    feedback = generate_feedback(
        "control",
        80,
        "target",
        "target",
        {"missing_words": [], "substitutions": [], "word_match_score": 100},
        {"speech_rate_wpm": 100, "long_pause_count": 0},
    )
    assert "comment" in feedback
    assert "diagnosis" not in feedback
