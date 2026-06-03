import io
import json
import wave

from fastapi.testclient import TestClient

from app.main import app
from app.services.pronunciation_assessment.factory import get_pronunciation_provider
from app.services.pronunciation_assessment.azure_provider import AzurePronunciationAssessmentProvider


client = TestClient(app)


def wav_bytes(seconds=2):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes((b"\x01\x08" * 16000 * seconds))
    buffer.seek(0)
    return buffer.read()


def submit_attempt(participant_id="research_test_student"):
    task = client.get("/api/tasks").json()[0]
    return client.post(
        "/api/attempts/analyze",
        data={
            "participant_id": participant_id,
            "group_id": "G3",
            "task_id": str(task["id"]),
            "transcript_hint": task["target_text"],
        },
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    )


def test_mock_pronunciation_provider_is_labelled_practice_indicator():
    provider = get_pronunciation_provider(provider_name="mock")
    result = provider.assess(
        audio_path=None,
        reference_text="The thin path winds through three quiet fields.",
        task_metadata={},
        participant=None,
        attempt_context={"practice_score": 88, "asr_transcript": "The thin path winds through three quiet fields."},
    )
    assert result.provider_name == "mock"
    assert result.evidence_level == "practice_indicator"
    assert result.raw_response_json["simulated"] is True


def test_azure_provider_parses_mocked_response(monkeypatch, tmp_path):
    import app.services.pronunciation_assessment.azure_provider as azure_module

    audio = tmp_path / "speech.wav"
    audio.write_bytes(wav_bytes())
    monkeypatch.setattr(azure_module, "AZURE_SPEECH_KEY", "test-key")
    monkeypatch.setattr(azure_module, "AZURE_SPEECH_REGION", "eastus")

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return json.dumps({
                "DisplayText": "The thin path.",
                "NBest": [{
                    "PronunciationAssessment": {"PronScore": 82, "AccuracyScore": 80, "FluencyScore": 78, "CompletenessScore": 90, "ProsodyScore": 75},
                    "Words": [{
                        "Word": "thin",
                        "Confidence": 0.91,
                        "PronunciationAssessment": {"AccuracyScore": 70, "ErrorType": "None"},
                        "Phonemes": [{"Phoneme": "th", "Confidence": 0.8, "PronunciationAssessment": {"AccuracyScore": 68}}],
                    }],
                }],
            }).encode("utf-8")

    monkeypatch.setattr(azure_module.urllib.request, "urlopen", lambda request, timeout=30: FakeResponse())
    result = AzurePronunciationAssessmentProvider().assess(audio, "The thin path.", {}, None, {})
    assert result.status == "ok"
    assert result.pronunciation_score == 82
    assert result.word_level_results[0]["word"] == "thin"
    assert result.phoneme_level_results[0]["phoneme"] == "th"
    assert result.evidence_level == "model_supported_diagnosis"


def test_pilot_readiness_endpoint_reports_provider_and_checks():
    response = client.get("/api/pilot-readiness")
    assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "overall_status" in payload
    assert "ready_for_formal_data_collection" in payload
    assert "provider" in payload
    assert any(item["check"] == "backend_connected" and item["status"] == "PASS" for item in payload["checks"])


def test_attempt_stores_pronunciation_result_and_feedback_uptake():
    first = submit_attempt("uptake_research_student")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["assessment_provider"] == "mock"
    assert "practice_clarity_score" in first_payload
    assert "pronunciation_assessment_score" in first_payload
    assert first_payload["pronunciation_score_valid_for_research"] is False
    assert first_payload["backend_diagnostics"]["assessment_provider"] == "mock"

    second = submit_attempt("uptake_research_student")
    assert second.status_code == 200

    events = client.get("/api/exports/feedback-events")
    assert events.status_code == 200
    assert "feedback_generated" in events.text
    assert "learner_submitted_revised_attempt" in events.text

    uptake = client.get("/api/exports/feedback-uptake-states")
    assert uptake.status_code == 200
    assert "uptake_research_student" in uptake.text


def test_mock_provider_fails_clearly_in_research_mode(monkeypatch):
    import app.api as api_module

    monkeypatch.setattr(api_module, "RESEARCH_MODE", True)
    monkeypatch.setattr(api_module, "PRONUNCIATION_PROVIDER", "mock")
    task = client.get("/api/tasks").json()[0]
    response = client.post(
        "/api/attempts/analyze",
        data={
            "participant_id": "research_mode_mock_blocked",
            "group_id": "G3",
            "task_id": str(task["id"]),
            "transcript_hint": task["target_text"],
        },
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 503
    assert "Research mode requires a real pronunciation provider" in response.text


def test_human_rating_queue_is_blinded_and_exportable():
    attempt = submit_attempt("human_rating_student").json()
    queue = client.get("/api/human-ratings/queue?rater_id=rater_a&include_intervention=true")
    assert queue.status_code == 200
    row = next(item for item in queue.json() if item["attempt_id"] == attempt["id"])
    assert "condition_group" not in row
    assert row["anonymized_participant_id"].startswith("P")

    rating = client.post("/api/human-ratings", json={
        "attempt_id": attempt["id"],
        "rater_id": "rater_a",
        "pronunciation": 4,
        "fluency": 4,
        "comprehensibility": 5,
        "rating_confidence": 0.8,
    })
    assert rating.status_code == 200
    exported = client.get("/api/exports/human-ratings")
    assert exported.status_code == 200
    assert "rater_a" in exported.text
    assert "task_code" in exported.text
    assert "rating_submitted_at" in exported.text
    assert "human_rating_student" not in exported.text


def test_study_lock_prevents_condition_edits_and_audit_export_records_unlock():
    study = client.post("/api/studies", json={"study_name": "Lock Test Study"}).json()
    lock = client.post(f"/api/studies/{study['id']}/lock")
    assert lock.status_code == 200
    blocked = client.post(f"/api/studies/{study['id']}/conditions", json={"condition_name": "Blocked"})
    assert blocked.status_code == 400
    unlock = client.post(f"/api/studies/{study['id']}/unlock", json={"reason": "test cleanup", "actor_id": "tester"})
    assert unlock.status_code == 200
    audit = client.get("/api/exports/audit-log")
    assert audit.status_code == 200
    assert "study_locked" in audit.text
    assert "study_unlocked" in audit.text


def test_analysis_ready_exports_are_anonymized():
    submit_attempt("analysis_ready_student")
    response = client.get("/api/exports/analysis-ready-long")
    assert response.status_code == 200
    assert "participant_code_anonymized" in response.text
    assert "practice_clarity_score" in response.text
    assert "pronunciation_assessment_score" in response.text
    assert "score_valid_for_formal_research" in response.text
    assert "analysis_ready_student" not in response.text


def test_stable_anonymized_participant_export_and_identifiable_guard():
    submit_attempt("anon_guard_student")
    first = client.get("/api/exports/participants")
    second = client.get("/api/exports/participants")
    assert first.status_code == 200
    assert second.status_code == 200
    assert "anon_guard_student" not in first.text
    assert first.text == second.text
    blocked = client.get("/api/exports/participants-identifiable")
    assert blocked.status_code == 403


def test_withdrawn_participant_excluded_from_analysis_ready_export():
    submit_attempt("withdrawn_student")
    consent = client.post("/api/consent-records", json={
        "participant_id": "withdrawn_student",
        "study_id": 1,
        "consent_version": "v1",
        "consent_given": True,
        "withdrawal_requested": True,
        "withdrawal_reason_optional": "test withdrawal",
    })
    assert consent.status_code == 200
    response = client.get("/api/exports/analysis-ready-long")
    assert response.status_code == 200
    assert "withdrawn_student" not in response.text


def test_rater_login_and_frontend_blinded_rating_static_check():
    created = client.post("/api/users", json={"user_code": "rater_static_test", "role": "rater", "display_name": "Rater Static"})
    assert created.status_code == 200
    login = client.post("/api/login", json={"user_code": "rater_static_test"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "rater"
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "Blinded Rating" in text
    assert "Experimental condition and automatic scores are hidden" in text
