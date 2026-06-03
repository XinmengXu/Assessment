from .base import PRACTICE_INDICATOR, PronunciationAssessmentProvider, PronunciationAssessmentResultDTO


class MockPronunciationAssessmentProvider(PronunciationAssessmentProvider):
    provider_name = "mock"
    provider_version = "mock_ui_testing_v1"

    def status(self):
        return {
            **super().status(),
            "configured": True,
            "research_usable": False,
            "warning": "Mock pronunciation assessment is for UI testing only.",
        }

    def assess(self, audio_path, reference_text, task_metadata, participant, attempt_context):
        score = attempt_context.get("practice_score")
        recognized_text = attempt_context.get("asr_transcript", "")
        return PronunciationAssessmentResultDTO(
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            reference_text=reference_text,
            recognized_text=recognized_text,
            overall_score=score,
            accuracy_score=score,
            fluency_score=attempt_context.get("fluency_proxy_score"),
            completeness_score=attempt_context.get("word_match_score"),
            confidence=0.25 if recognized_text else 0.0,
            evidence_level=PRACTICE_INDICATOR,
            raw_response_json={
                "simulated": True,
                "message": "Mock provider converts practice heuristics into a simulated result for UI testing.",
            },
        )
