from .base import PronunciationAdapter


class RuleBasedPronunciationAdapter(PronunciationAdapter):
    adapter_name = "rule_based_asr_supported"

    def build(self, task, alignment):
        focus_words = _json_list(task.focus_words)
        phoneme_map = _json_map(getattr(task, "word_phoneme_map_json", "{}"))
        missing = set(alignment.get("missing_words", []))
        substituted = {item.get("expected", "") for item in alignment.get("substitutions", [])}
        diagnosis = []
        for word in focus_words:
            key = word.lower()
            if key in missing or key in substituted:
                for phoneme in phoneme_map.get(key, []):
                    diagnosis.append({
                        "target_word": key,
                        "target_phoneme": phoneme,
                        "observed_phoneme": None,
                        "score": None,
                        "confidence": "medium",
                        "evidence_level": "asr_supported_cue",
                        "evidence_source": "asr_focus_word_missing_or_substituted",
                        "message": "Focus word missing or substituted in ASR transcript.",
                    })
        return {
            "adapter": self.adapter_name,
            "sentence_scores": {},
            "word_scores": {},
            "phoneme_scores": {},
            "phoneme_diagnosis": diagnosis,
            "evidence_quality": "medium" if diagnosis else "low",
        }


def _json_list(value):
    import json
    try:
        parsed = json.loads(value or "[]") if isinstance(value, str) else value
        return [str(item).lower() for item in parsed]
    except Exception:
        return []


def _json_map(value):
    import json
    try:
        parsed = json.loads(value or "{}") if isinstance(value, str) else value
        return {str(k).lower(): v for k, v in parsed.items()}
    except Exception:
        return {}
