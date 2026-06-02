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
        wav.writeframes((b"\x10\x10" * 16000))
    buffer.seek(0)
    return buffer


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as exc:
        print(f"FAIL {name}: {exc}")


def health():
    assert client.get("/api/health").status_code == 200


def valid_attempt_and_evidence():
    response = client.post(
        "/api/attempts/analyze",
        data={
            "participant_id": "pilot_check_explainable",
            "group_id": "explainable_diagnostic_feedback",
            "task_id": "1",
            "transcript_hint": "The thin path winds through three quiet fields.",
        },
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["asr_transcript"]
    assert payload["valid_audio"] is True
    assert payload["score"] is not None


def feedback_view_revision_state():
    first = client.post(
        "/api/attempts/analyze",
        data={"participant_id": "pilot_revision", "group_id": "explainable_diagnostic_feedback", "task_id": "1", "transcript_hint": "The thin path through fields."},
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    ).json()
    second = client.post(
        "/api/attempts/analyze",
        data={"participant_id": "pilot_revision", "group_id": "explainable_diagnostic_feedback", "task_id": "1", "transcript_hint": "The thin path winds through three quiet fields."},
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    ).json()
    assert second["attempt_number"] >= 2
    assert second["feedback_use_state"] in ["F1", "F2", "F3"]


def human_validation_release():
    attempt = client.post(
        "/api/attempts/analyze",
        data={"participant_id": "pilot_human", "group_id": "human_validated_feedback", "task_id": "1", "transcript_hint": "The thin path winds through three quiet fields."},
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    ).json()
    pending = client.get("/api/feedback/pending-review").json()
    item = next(row for row in pending if row["attempt_id"] == attempt["id"])
    assert client.post(f"/api/feedback/{item['id']}/approve", json={}).status_code == 200
    released = client.post(f"/api/feedback/{item['id']}/release")
    assert released.status_code == 200


def teacher_action_and_export():
    response = client.post("/api/teacher/orchestration-event", json={
        "teacher_id": "teacher01",
        "class_id": "pilot",
        "issue_type": "theta_words",
        "recommended_action": "class review",
        "teacher_action_taken": "assigned follow-up practice",
    })
    assert response.status_code == 200
    assert client.get("/api/exports/full").status_code == 200


if __name__ == "__main__":
    check("health endpoint", health)
    check("valid attempt produces ASR evidence and score", valid_attempt_and_evidence)
    check("revision updates feedback use state", feedback_view_revision_state)
    check("human validation release workflow", human_validation_release)
    check("teacher action and full export", teacher_action_and_export)
