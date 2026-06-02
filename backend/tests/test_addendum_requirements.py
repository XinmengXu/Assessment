import csv
import io
import wave

from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Task
from app.seed import seed_database


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
    assert {row["condition_code"] for row in response.json()} == {"G0", "G1", "G2", "G3"}


def test_seeded_practice_tasks_have_focus_metadata():
    db = SessionLocal()
    try:
        seed_database(db)
        tasks = db.query(Task).filter(Task.task_type == "practice", Task.task_code.like("P%")).all()
        assert len(tasks) >= 40
        assert all(task.focus_words and task.focus_words != "[]" for task in tasks)
        assert all(task.issue_types_json and task.issue_types_json != "[]" for task in tasks)
        rich = [task for task in tasks if task.focus_phonemes_json and task.focus_phonemes_json != "[]" and task.word_phoneme_map_json and task.word_phoneme_map_json != "{}"]
        assert len(rich) / len(tasks) >= 0.8
    finally:
        db.close()


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


def test_asr_phoneme_feedback_uses_task_focus_sound():
    response = client.post(
        "/api/attempts/analyze",
        data={"participant_id": "phoneme_feedback_asr", "group_id": "explainable_word_sound_feedback", "task_id": "5", "transcript_hint": "She the weather would improve by Thursday."},
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 200
    feedback = response.json()["feedback"]
    assert feedback["word_label"] == "thought"
    assert feedback["sound_focus_label"]
    assert feedback["evidence_note"] == "AI cue based on speech recognition. Use it as practice support."
    assert "not an exact pronunciation diagnosis" not in feedback["practice_suggestion"]


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


def test_external_phoneme_import_creates_model_supported_diagnosis():
    client.post(
        "/api/attempts/analyze",
        data={"participant_id": "external_phoneme_test", "group_id": "explainable_word_sound_feedback", "task_id": "5", "transcript_hint": "She thought the weather would improve by Thursday."},
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    )
    csv_text = "\n".join([
        "participant_code,task_code,attempt_number,source_name,score_level,target_word,target_phoneme,observed_phoneme_optional,score,confidence,issue_type_optional,notes_optional",
        "external_phoneme_test,P005,1,external_model,phoneme,thought,th,,40,0.9,theta_words,low score",
    ])
    response = client.post("/api/external-scores/import", files={"file": ("scores.csv", csv_text, "text/csv")})
    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert "model_supported_diagnosis" in client.get("/api/exports/diagnosis-records").text


def test_teacher_feedback_release_creates_human_validated_evidence():
    attempt = client.post(
        "/api/attempts/analyze",
        data={"participant_id": "human_release_test", "group_id": "G3", "task_id": "1", "transcript_hint": "The thin path winds through three quiet fields."},
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    ).json()
    feedback = client.post("/api/teacher/feedback", json={
        "participant_id": "human_release_test",
        "task_id": 1,
        "attempt_id": attempt["id"],
        "target_word": "thin",
        "target_phoneme": "th",
        "observed_phoneme": "s",
        "comment": "Practise the target sound.",
    }).json()
    released = client.post(f"/api/teacher/feedback/{feedback['id']}/release")
    assert released.status_code == 200
    assert released.json()["status"] == "released"
    assert "human_validated_diagnosis" in client.get("/api/exports/pronunciation-evidence").text


def test_teacher_action_log_endpoint():
    response = client.post("/api/teacher/orchestration-event", json={"teacher_id": "t1", "issue_type": "theta_words", "teacher_action_taken": "class review"})
    assert response.status_code == 200
    assert response.json()["teacher_action_taken"] == "class review"
