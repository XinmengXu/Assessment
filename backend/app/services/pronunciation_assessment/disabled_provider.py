from .base import PronunciationAssessmentProvider, PronunciationAssessmentResultDTO


class DisabledPronunciationAssessmentProvider(PronunciationAssessmentProvider):
    provider_name = "disabled"
    provider_version = "disabled_v1"

    def status(self):
        return {
            **super().status(),
            "configured": False,
            "research_usable": False,
            "error": "No pronunciation assessment provider is configured.",
        }

    def assess(self, audio_path, reference_text, task_metadata, participant, attempt_context):
        return PronunciationAssessmentResultDTO(
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            reference_text=reference_text,
            status="error",
            error_message="Pronunciation assessment is disabled. Configure PRONUNCIATION_PROVIDER for research collection.",
            raw_response_json={"provider": "disabled"},
        )
