from app.services.feedback.feedback_policy import derive_feedback_use_state


def test_feedback_use_states_are_ordered():
    states = [derive_feedback_use_state(False, False, False), derive_feedback_use_state(True, False, False), derive_feedback_use_state(True, True, True)]
    assert states == ["F0", "F1", "F3"]
