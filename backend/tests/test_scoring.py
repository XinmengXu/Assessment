from app.analysis.scoring import compute_score


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
