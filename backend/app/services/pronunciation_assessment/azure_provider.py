import base64
import json
import time
import urllib.error
import urllib.request
from uuid import uuid4

from ...config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
from .base import MODEL_SUPPORTED_DIAGNOSIS, PronunciationAssessmentProvider, PronunciationAssessmentResultDTO


class AzurePronunciationAssessmentProvider(PronunciationAssessmentProvider):
    provider_name = "azure_pronunciation"
    provider_version = "azure_speech_pronunciation_v1"

    def status(self):
        configured = bool(AZURE_SPEECH_KEY and AZURE_SPEECH_REGION)
        return {
            **super().status(),
            "configured": configured,
            "research_usable": configured,
            "region": AZURE_SPEECH_REGION if configured else "",
            "error": "" if configured else "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required.",
        }

    def assess(self, audio_path, reference_text, task_metadata, participant, attempt_context):
        if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
            return PronunciationAssessmentResultDTO(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                reference_text=reference_text,
                status="error",
                error_message="Azure Pronunciation Assessment credentials are missing.",
            )
        request_id = str(uuid4())
        config = {
            "ReferenceText": reference_text,
            "GradingSystem": "HundredMark",
            "Granularity": "Phoneme",
            "Dimension": "Comprehensive",
            "EnableProsodyAssessment": True,
        }
        endpoint = "https://%s.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=en-US" % AZURE_SPEECH_REGION
        headers = {
            "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Pronunciation-Assessment": base64.b64encode(json.dumps(config).encode("utf-8")).decode("ascii"),
            "X-ConnectionId": request_id,
        }
        try:
            data = audio_path.read_bytes()
            request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return PronunciationAssessmentResultDTO(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                request_id=request_id,
                reference_text=reference_text,
                status="error",
                error_message=str(exc),
                raw_response_json={"error": str(exc)},
            )
        assessment = raw.get("NBest", [{}])[0].get("PronunciationAssessment", {})
        words = raw.get("NBest", [{}])[0].get("Words", []) or []
        word_level = []
        phoneme_level = []
        for word in words:
            word_assessment = word.get("PronunciationAssessment", {})
            word_level.append({
                "word": word.get("Word", ""),
                "reference_word": word.get("Word", ""),
                "accuracy_score": word_assessment.get("AccuracyScore"),
                "error_type": word_assessment.get("ErrorType", ""),
                "confidence": word.get("Confidence", 0),
                "raw": word,
            })
            for phoneme in word.get("Phonemes", []) or []:
                phoneme_level.append({
                    "word": word.get("Word", ""),
                    "phoneme": phoneme.get("Phoneme", ""),
                    "accuracy_score": (phoneme.get("PronunciationAssessment") or {}).get("AccuracyScore"),
                    "confidence": phoneme.get("Confidence", 0),
                    "raw": phoneme,
                })
        return PronunciationAssessmentResultDTO(
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            request_id=request_id,
            reference_text=reference_text,
            recognized_text=raw.get("DisplayText", ""),
            overall_score=assessment.get("PronScore"),
            accuracy_score=assessment.get("AccuracyScore"),
            fluency_score=assessment.get("FluencyScore"),
            completeness_score=assessment.get("CompletenessScore"),
            prosody_score=assessment.get("ProsodyScore"),
            pronunciation_score=assessment.get("PronScore"),
            word_level_results=word_level,
            phoneme_level_results=phoneme_level,
            confidence=1.0 if assessment else 0.5,
            evidence_level=MODEL_SUPPORTED_DIAGNOSIS,
            raw_response_json={**raw, "received_at_epoch": time.time()},
        )
