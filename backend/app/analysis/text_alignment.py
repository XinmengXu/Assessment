import re
from difflib import SequenceMatcher


WORD_RE = re.compile(r"[A-Za-z']+")


def normalize_words(text):
    return [w.lower().strip("'") for w in WORD_RE.findall(text or "")]


def align_text(target_text, transcript):
    target = normalize_words(target_text)
    spoken = normalize_words(transcript)
    matcher = SequenceMatcher(a=target, b=spoken)
    missing = []
    substitutions = []
    matched = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
        elif tag == "delete":
            missing.extend(target[i1:i2])
        elif tag == "replace":
            left = target[i1:i2]
            right = spoken[j1:j2]
            for idx, expected in enumerate(left):
                heard = right[idx] if idx < len(right) else ""
                substitutions.append({"expected": expected, "heard": heard})
        elif tag == "insert":
            continue

    score = matched / max(len(target), 1)
    return {
        "target_words": target,
        "spoken_words": spoken,
        "word_match_score": round(score * 100, 2),
        "missing_words": missing,
        "substitutions": substitutions,
    }
