import io
import wave

from fastapi.testclient import TestClient

from app.main import app
from app.services.pronunciation_assessment.factory import get_pronunciation_provider


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


def test_pilot_readiness_endpoint_reports_provider_and_checks():
    response = client.get("/api/pilot-readiness")
    assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "provider" in payload
    assert any(item["check"] == "backend_connected" for item in payload["checks"])


def test_attempt_stores_pronunciation_result_and_feedback_uptake():
    first = submit_attempt("uptake_research_student")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["assessment_provider"] == "mock"
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
    assert "analysis_ready_student" not in response.text
