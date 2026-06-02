import csv
import io
import wave

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x10\x10" * 16000)
    return buffer.getvalue()


def test_llm_condition_hidden_from_condition_api():
    response = client.get("/api/studies/1/conditions")
    assert response.status_code == 200
    assert "llm_verbalized" not in {row["condition_code"] for row in response.json()}


def test_asr_only_diagnosis_has_no_observed_phoneme():
    response = client.post(
        "/api/attempts/analyze",
        data={"participant_id": "diag_asr_only", "group_id": "explainable_diagnostic_feedback", "task_id": "1", "transcript_hint": "The thin path through fields."},
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200
    export = client.get("/api/exports/diagnosis-records")
    assert export.status_code == 200
    text = export.text
    assert "asr_supported_cue" in text
    assert "may not have been clearly recognized" in text


def test_external_score_template_and_invalid_import():
    template = client.get("/api/external-scores/template")
    assert template.status_code == 200
    assert "participant_code,task_code,attempt_number" in template.text
    response = client.post(
        "/api/external-scores/import",
        files={"file": ("bad.csv", "participant_code,task_code,attempt_number\np,t,one\n", "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["errors"]


def test_human_feedback_pending_can_be_released():
    attempt = client.post(
        "/api/attempts/analyze",
        data={"participant_id": "human_release_test", "group_id": "human_validated_feedback", "task_id": "1", "transcript_hint": "The thin path winds through three quiet fields."},
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    ).json()
    pending = client.get("/api/feedback/pending-review").json()
    item = next(row for row in pending if row["attempt_id"] == attempt["id"])
    assert client.post(f"/api/feedback/{item['id']}/approve", json={}).status_code == 200
    assert client.post(f"/api/feedback/{item['id']}/release").json()["released_to_learner"] is True


def test_teacher_action_log_endpoint():
    response = client.post("/api/teacher/orchestration-event", json={"teacher_id": "t1", "issue_type": "theta_words", "teacher_action_taken": "class review"})
    assert response.status_code == 200
    assert response.json()["teacher_action_taken"] == "class review"
