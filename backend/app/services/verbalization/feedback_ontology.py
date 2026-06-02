EVIDENCE_LABELS = {
    "asr_supported_cue": "ASR-supported cue",
    "model_supported_diagnosis": "model-supported diagnosis",
    "human_validated_diagnosis": "human-validated diagnosis",
}


def evidence_label(level):
    return EVIDENCE_LABELS.get(level, "ASR-supported cue")
