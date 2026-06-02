import re
from difflib import SequenceMatcher


WORD_RE = re.compile(r"[A-Za-z']+")
CONTRACTIONS = {
    "can't": ["can", "not"],
    "won't": ["will", "not"],
    "i'm": ["i", "am"],
    "it's": ["it", "is"],
    "that's": ["that", "is"],
    "they're": ["they", "are"],
    "we're": ["we", "are"],
    "you're": ["you", "are"],
}


def normalize_words(text):
    words = []
    for raw in WORD_RE.findall(text or ""):
        word = raw.lower().strip("'")
        words.extend(CONTRACTIONS.get(word, [word]))
    return words


def align_text(target_text, transcript):
    target = normalize_words(target_text)
    spoken = normalize_words(transcript)
    matcher = SequenceMatcher(a=target, b=spoken)
    missing = []
    substitutions = []
    insertions = []
    operations = []
    matched = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        operations.append({
            "op": tag,
            "target": target[i1:i2],
            "spoken": spoken[j1:j2],
            "target_span": [i1, i2],
            "spoken_span": [j1, j2],
        })
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
            insertions.extend(spoken[j1:j2])

    score = matched / max(len(target), 1)
    focus_word_results = []
    return {
        "target_words": target,
        "spoken_words": spoken,
        "alignment_operations": operations,
        "word_match_score": round(score * 100, 2),
        "matched_words": matched,
        "missing_words": missing,
        "substitutions": substitutions,
        "inserted_words": insertions,
        "focus_word_results": focus_word_results,
    }
