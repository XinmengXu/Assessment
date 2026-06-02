from app.services.feedback.feedback_policy import condition_policy, derive_feedback_use_state, filter_feedback_for_condition


def test_practice_only_hides_score_and_comment():
    result = filter_feedback_for_condition("G0", "hello", 80, {"diagnosis": "hidden"})
    assert result["overall_score"] is None
    assert result["comment"] == ""
    assert result["feedback_type"] == "practice_only"


def test_score_plus_comment_shows_practical_comment():
    result = filter_feedback_for_condition(
        "G3",
        "hello",
        80,
        {"word_label": "thought", "sound_focus_label": "/th/", "practice_suggestion": "Practise /th/ in thought.", "revision_goal": "Make thought clearer."},
    )
    assert result["show_score"] is True
    assert result["show_comment"] is True
    assert result["word_to_practise"] == "thought"


def test_feedback_use_state_derivation():
    assert derive_feedback_use_state(False, False, False) == "F0"
    assert derive_feedback_use_state(True, False, False) == "F1"
    assert derive_feedback_use_state(True, True, False) == "F2"
    assert derive_feedback_use_state(True, True, True) == "F3"
    assert derive_feedback_use_state(True, True, True, sustained=True) == "F4"


def test_condition_alias():
    assert condition_policy("control")["condition_group"] == "G1"
