ISSUE_TAXONOMY = {
    "generic_unclear_word": "General unclear word",
    "theta_words": "TH sounds",
    "r_l_contrast": "R and L contrast",
    "final_consonants": "Final consonants",
    "consonant_clusters": "Consonant clusters",
    "speech_rate_fast": "Fast speech rate",
    "speech_rate_slow": "Slow speech rate",
    "long_pause": "Long pause",
    "word_stress": "Word stress",
    "rhythm": "Rhythm",
    "invalid_audio": "Invalid audio",
}


def issue_for_word(word, task_issue_types, focus_words):
    normalized_focus = {item.lower() for item in focus_words or []}
    if (word or "").lower() in normalized_focus and task_issue_types:
        return task_issue_types[0]
    return "generic_unclear_word"


def issue_records_for_alignment(task_issue_types, focus_words, alignment, features):
    records = []
    seen = set()
    for word in alignment.get("missing_words", []):
        issue_type = issue_for_word(word, task_issue_types, focus_words)
        key = (issue_type, word, "missing_or_substituted_focus_word")
        if key not in seen:
            seen.add(key)
            records.append(_record(issue_type, word, "missing_or_substituted_focus_word"))

    for substitution in alignment.get("substitutions", []):
        word = substitution.get("expected", "")
        issue_type = issue_for_word(word, task_issue_types, focus_words)
        key = (issue_type, word, "missing_or_substituted_focus_word")
        if key not in seen:
            seen.add(key)
            records.append(_record(issue_type, word, "missing_or_substituted_focus_word", substitution))

    if features.get("speech_rate_wpm", 0) > 180:
        records.append(_record("speech_rate_fast", "", "speech_rate_outside_target"))
    if features.get("speech_rate_wpm", 0) and features.get("speech_rate_wpm", 0) < 70:
        records.append(_record("speech_rate_slow", "", "speech_rate_outside_target"))
    if features.get("long_pause_count", 0) > 0:
        records.append(_record("long_pause", "", "pause_estimate"))

    return records or [_record("generic_unclear_word", "", "fallback")]


def _record(issue_type, target_word, evidence, extra=None):
    return {
        "issue_type": issue_type if issue_type in ISSUE_TAXONOMY else "generic_unclear_word",
        "target_word": target_word,
        "evidence": evidence,
        "severity": "moderate",
        "extra": extra or {},
    }
