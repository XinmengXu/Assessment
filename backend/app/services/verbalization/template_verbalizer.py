from .phoneme_feedback_templates import (
    asr_supported_template,
    generic_no_phoneme_template,
    human_validated_template,
    model_supported_template,
    repeated_phoneme_template,
)


def feedback_from_diagnosis(record, repeated=False):
    target_word = record.target_word or "the focus word"
    target_phoneme = record.target_phoneme or ""
    speaking_target = getattr(record, "speaking_target", "") or "pronunciation_clarity"
    if repeated and target_phoneme:
        return repeated_phoneme_template(target_word, target_phoneme, speaking_target)
    if record.evidence_level == "human_validated_diagnosis" and record.observed_phoneme:
        return human_validated_template(target_word, target_phoneme, record.observed_phoneme, speaking_target)
    if record.evidence_level == "model_supported_diagnosis":
        return model_supported_template(target_word, target_phoneme, getattr(record, "score", None), None, speaking_target)
    if target_phoneme:
        return asr_supported_template(target_word, target_phoneme, speaking_target)
    return generic_no_phoneme_template(target_word, speaking_target)


def feedback_from_issue(target_word, target_phoneme, speaking_target, repeated=False):
    if repeated and target_phoneme:
        return repeated_phoneme_template(target_word, target_phoneme, speaking_target)
    return asr_supported_template(target_word, target_phoneme, speaking_target)
