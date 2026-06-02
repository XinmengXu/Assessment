from app.services.asr_sanity import check_asr_sanity


def test_empty_transcript_is_invalid():
    result = check_asr_sanity("The thin path", "", {"no_speech_detected": True})
    assert result["asr_valid"] is False
    assert result["transcript_quality"] == "empty"


def test_repeated_hallucination_is_suspicious():
    result = check_asr_sanity("The thin path", "you you you you you", {"no_speech_detected": False})
    assert result["asr_valid"] is False
    assert "repeated_hallucination_pattern" in result["warnings"]


def test_far_transcript_is_warned_but_can_be_scored_low():
    result = check_asr_sanity("The thin path winds through fields", "banana window coffee", {"no_speech_detected": False})
    assert result["asr_valid"] is True
    assert "transcript_far_from_target" in result["warnings"]
