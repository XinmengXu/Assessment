from .base import MODEL_SUPPORTED_DIAGNOSIS, PronunciationAssessmentProvider, PronunciationAssessmentResultDTO


class ExternalImportPronunciationAssessmentProvider(PronunciationAssessmentProvider):
    provider_name = "external_import"
    provider_version = "external_import_v1"

    def __init__(self, db=None):
        self.db = db

    def status(self):
        return {
            **super().status(),
            "configured": True,
            "research_usable": True,
            "message": "Uses previously imported external pronunciation assessment rows.",
        }

    def assess(self, audio_path, reference_text, task_metadata, participant, attempt_context):
        if not self.db:
            return PronunciationAssessmentResultDTO(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                reference_text=reference_text,
                status="pending_external_import",
                error_message="No database session was provided for external score lookup.",
            )
        from ...database import ExternalAssessmentScore

        attempt_id = int(attempt_context.get("attempt_id") or 0)
        rows = self.db.query(ExternalAssessmentScore).filter(ExternalAssessmentScore.attempt_id == attempt_id).all()
        if not rows:
            return PronunciationAssessmentResultDTO(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                reference_text=reference_text,
                status="pending_external_import",
                error_message="No imported pronunciation assessment row matched this attempt.",
                raw_response_json={"attempt_id": attempt_id},
            )
        sentence_rows = [row for row in rows if row.score_level == "sentence"]
        word_rows = [row for row in rows if row.score_level == "word"]
        phoneme_rows = [row for row in rows if row.score_level == "phoneme"]
        overall = sentence_rows[0].score if sentence_rows else sum(row.score for row in rows) / max(len(rows), 1)
        return PronunciationAssessmentResultDTO(
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            reference_text=reference_text,
            overall_score=round(overall, 2),
            accuracy_score=round(overall, 2),
            confidence=max([row.confidence for row in rows] or [0]),
            evidence_level=MODEL_SUPPORTED_DIAGNOSIS,
            word_level_results=[{"word": row.target_word, "accuracy_score": row.score, "confidence": row.confidence, "raw": row.notes_optional} for row in word_rows],
            phoneme_level_results=[{"word": row.target_word, "phoneme": row.target_phoneme, "accuracy_score": row.score, "confidence": row.confidence, "error_type": row.issue_type_optional, "raw": row.notes_optional} for row in phoneme_rows],
            raw_response_json={"source": "external_import", "row_count": len(rows)},
        )
