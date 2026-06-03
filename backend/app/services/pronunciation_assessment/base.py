from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


PRACTICE_INDICATOR = "practice_indicator"
MODEL_SUPPORTED_DIAGNOSIS = "model_supported_diagnosis"
HUMAN_VALIDATED_DIAGNOSIS = "human_validated_diagnosis"
ASR_SUPPORTED_CUE = "asr_supported_cue"


@dataclass
class PronunciationAssessmentResultDTO:
    provider_name: str
    provider_version: str
    reference_text: str
    request_id: str = ""
    recognized_text: str = ""
    overall_score: Optional[float] = None
    accuracy_score: Optional[float] = None
    fluency_score: Optional[float] = None
    completeness_score: Optional[float] = None
    prosody_score: Optional[float] = None
    pronunciation_score: Optional[float] = None
    word_level_results: List[Dict[str, Any]] = field(default_factory=list)
    phoneme_level_results: List[Dict[str, Any]] = field(default_factory=list)
    syllable_level_results: List[Dict[str, Any]] = field(default_factory=list)
    pause_silence_indicators: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    raw_response_json: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    status: str = "ok"
    evidence_level: str = PRACTICE_INDICATOR
    created_at: datetime = field(default_factory=datetime.utcnow)


class PronunciationAssessmentProvider:
    provider_name = "base"
    provider_version = "0"

    def status(self) -> Dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "configured": True,
            "research_usable": False,
        }

    def assess(self, audio_path, reference_text, task_metadata, participant, attempt_context) -> PronunciationAssessmentResultDTO:
        raise NotImplementedError
