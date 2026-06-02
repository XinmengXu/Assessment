from collections import Counter

from ..analysis.text_alignment import normalize_words
from ..config import ASR_MODE, MIN_TRANSCRIPT_TOKENS


FILLER_WORDS = {"um", "uh", "erm", "hmm", "mmm", "ah", "oh"}


def check_asr_sanity(target_text, transcript, features=None, transcript_hint=""):
    words = normalize_words(transcript)
    target_words = normalize_words(target_text)
    warnings = []
    quality = "valid"

    if not words:
        warnings.append("empty_transcript")
        quality = "empty"
    elif len(words) < MIN_TRANSCRIPT_TOKENS:
        warnings.append("transcript_too_short")
        quality = "too_short"

    if words and all(word in FILLER_WORDS for word in words):
        warnings.append("filler_only_transcript")
        quality = "suspicious"

    if _has_repeated_hallucination(words):
        warnings.append("repeated_hallucination_pattern")
        quality = "suspicious"

    if ASR_MODE == "mock" and words == target_words and not (transcript_hint or "").strip():
        warnings.append("mock_perfect_match_without_transcript_evidence")
        quality = "suspicious"

    if features and features.get("no_speech_detected") and words:
        warnings.append("audio_invalid_but_transcript_present")
        quality = "suspicious"

    if words and target_words:
        overlap = len(set(words).intersection(target_words)) / max(len(set(target_words)), 1)
        if overlap < 0.1 and len(words) >= 2:
            warnings.append("transcript_far_from_target")

    asr_valid = quality == "valid"
    return {
        "asr_valid": asr_valid,
        "warnings": warnings,
        "transcript_quality": quality,
    }


def _has_repeated_hallucination(words):
    if len(words) < 4:
        return False
    counts = Counter(words)
    _, count = counts.most_common(1)[0]
    return count / len(words) >= 0.75
