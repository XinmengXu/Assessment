from ..config import MAX_REASONABLE_WPM, MIN_REASONABLE_WPM, SCORE_WEIGHTS


def compute_score(alignment, features):
    score = alignment["word_match_score"] * (SCORE_WEIGHTS["word_match"] / 100.0)
    score -= len(alignment["missing_words"]) * SCORE_WEIGHTS["missing_penalty"]
    score -= len(alignment["substitutions"]) * SCORE_WEIGHTS["substitution_penalty"]

    rate = features["speech_rate_wpm"]
    if rate and (rate < MIN_REASONABLE_WPM or rate > MAX_REASONABLE_WPM):
        score -= SCORE_WEIGHTS["speech_rate_penalty"]

    score -= features["long_pause_count"] * SCORE_WEIGHTS["pause_penalty"]
    return round(max(0.0, min(100.0, score)), 2)
