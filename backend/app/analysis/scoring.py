from ..config import MAX_REASONABLE_WPM, MIN_REASONABLE_WPM, SCORE_WEIGHTS


def compute_score(alignment, features):
    return compute_practice_score(alignment, features)["practice_score"] or 0


def compute_practice_score(alignment, features):
    if features.get("no_speech_detected") or not features.get("valid_audio", True):
        return {
            "practice_score": None,
            "score_breakdown": {
                "word_match_component": 0,
                "missing_penalty": 0,
                "substitution_penalty": 0,
                "speech_rate_penalty": 0,
                "pause_penalty": 0,
                "invalid_audio_penalty": 100,
            },
            "score_note": "This is a practice indicator, not a validated proficiency score.",
        }

    score = alignment["word_match_score"] * (SCORE_WEIGHTS["word_match"] / 100.0)
    missing_penalty = len(alignment["missing_words"]) * SCORE_WEIGHTS["missing_penalty"]
    substitution_penalty = len(alignment["substitutions"]) * SCORE_WEIGHTS["substitution_penalty"]
    score -= missing_penalty
    score -= substitution_penalty

    rate = features["speech_rate_wpm"]
    speech_rate_penalty = 0
    if rate and (rate < MIN_REASONABLE_WPM or rate > MAX_REASONABLE_WPM):
        speech_rate_penalty = SCORE_WEIGHTS["speech_rate_penalty"]
        score -= speech_rate_penalty

    pause_penalty = features["long_pause_count"] * SCORE_WEIGHTS["pause_penalty"]
    score -= pause_penalty
    practice_score = round(max(0.0, min(100.0, score)), 2)
    return {
        "practice_score": practice_score,
        "score_breakdown": {
            "word_match_component": round(alignment["word_match_score"] * (SCORE_WEIGHTS["word_match"] / 100.0), 2),
            "missing_penalty": missing_penalty,
            "substitution_penalty": substitution_penalty,
            "speech_rate_penalty": speech_rate_penalty,
            "pause_penalty": pause_penalty,
            "invalid_audio_penalty": 0,
        },
        "score_note": "This is a practice indicator, not a validated proficiency score.",
    }
