from app.analysis.scoring import compute_practice_score, compute_score


def test_compute_score_penalizes_errors():
    clean = compute_score(
        {"word_match_score": 100, "missing_words": [], "substitutions": []},
        {"speech_rate_wpm": 120, "long_pause_count": 0},
    )
    rough = compute_score(
        {"word_match_score": 70, "missing_words": ["thin"], "substitutions": [{"expected": "ray", "heard": "lay"}]},
        {"speech_rate_wpm": 40, "long_pause_count": 2},
    )
    assert clean > rough
    assert 0 <= rough <= 100


def test_practice_score_has_breakdown_and_note():
    result = compute_practice_score(
        {"word_match_score": 100, "missing_words": [], "substitutions": []},
        {"speech_rate_wpm": 120, "long_pause_count": 0, "valid_audio": True},
    )
    assert result["practice_score"] == 70
    assert result["score_breakdown"]["word_match_component"] == 70
    assert "practice indicator" in result["score_note"]


def test_invalid_audio_has_no_practice_score():
    result = compute_practice_score(
        {"word_match_score": 100, "missing_words": [], "substitutions": []},
        {"speech_rate_wpm": 0, "long_pause_count": 0, "valid_audio": False, "no_speech_detected": True},
    )
    assert result["practice_score"] is None
    assert result["score_breakdown"]["invalid_audio_penalty"] == 100
