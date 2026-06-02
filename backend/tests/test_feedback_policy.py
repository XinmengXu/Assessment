from app.services.feedback.feedback_policy import condition_policy, derive_feedback_use_state, filter_feedback_for_condition


def test_assessment_only_hides_feedback():
    result = filter_feedback_for_condition("assessment_only", "hello", 80, {"diagnosis": "hidden"})
    assert result["asr_transcript"] == ""
    assert result["overall_score"] is None
    assert result["feedback_type"] == "assessment_only"


def test_explainable_shows_structured_sections():
    result = filter_feedback_for_condition(
        "explainable",
        "hello",
        80,
        {"diagnosis": "d", "explanation": "e", "action_guidance": "a", "revision_instruction": "r"},
    )
    assert result["show_diagnosis"] is True
    assert result["diagnosis"] == "d"


def test_feedback_use_state_derivation():
    assert derive_feedback_use_state(False, False, False) == "F0"
    assert derive_feedback_use_state(True, False, False) == "F1"
    assert derive_feedback_use_state(True, True, False) == "F2"
    assert derive_feedback_use_state(True, True, True) == "F3"
    assert derive_feedback_use_state(True, True, True, sustained=True) == "F4"


def test_condition_alias():
    assert condition_policy("control")["feedback_type"] == "score_only"
