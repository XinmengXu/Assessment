import io
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes((b"\x01\x08" * 16000 * 2))
    buffer.seek(0)
    return buffer.read()


def submit(group):
    task = client.get("/api/tasks").json()[0]
    return client.post(
        "/api/attempts/analyze",
        data={
            "participant_id": f"student_{group.lower()}_test",
            "group_id": group,
            "task_id": str(task["id"]),
            "transcript_hint": task["target_text"],
        },
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    )


def submit_with_workflow(workflow_request):
    task = client.get("/api/tasks").json()[0]
    return client.post(
        "/api/attempts/analyze",
        data={
            "participant_id": f"student_{workflow_request}_test",
            "group_id": "G3",
            "workflow_request": workflow_request,
            "task_id": str(task["id"]),
            "transcript_hint": task["target_text"],
        },
        files={"audio": ("speech.wav", wav_bytes(), "audio/wav")},
    )


def test_g0_g1_g2_g3_feedback_visibility():
    expected = {
        "G0": (False, False),
        "G1": (True, False),
        "G2": (False, True),
        "G3": (True, True),
    }
    for group, (show_score, show_comment) in expected.items():
        response = submit(group)
        assert response.status_code == 200
        data = response.json()
        feedback = data["feedback"]
        assert feedback["condition_group"] == group
        assert feedback["show_score"] is show_score
        assert feedback["show_comment"] is show_comment
        assert (feedback["practice_score"] is not None) is show_score
        assert bool(feedback["comment"]) is show_comment
        assert feedback["tts_required"] is True


def test_comment_feedback_is_practical_not_generic_explanation():
    data = submit("G3").json()
    feedback = data["feedback"]
    assert "word_to_practise" in feedback
    assert "practice_suggestion" in feedback
    assert "revision_goal" in feedback
    main_text = " ".join(str(feedback.get(key, "")) for key in ["comment", "practice_suggestion", "revision_goal"])
    assert "not an exact pronunciation diagnosis" not in main_text


def test_four_group_exports_include_analysis_fields():
    attempts = client.get("/api/exports/attempts")
    assert attempts.status_code == 200
    text = attempts.text
    assert "condition_group" in text
    assert "score_shown" in text
    assert "comment_shown" in text

    ai_feedback = client.get("/api/exports/ai-feedback")
    assert ai_feedback.status_code == 200
    text = ai_feedback.text
    assert "word_to_practise" in text
    assert "score_hidden" in text
    assert "comment_hidden" in text


def test_study_setup_assignment_import_and_preview_workflow():
    activate = client.post("/api/studies/1/activate-four-group-design")
    assert activate.status_code == 200
    assert activate.json()["groups"] == ["G0", "G1", "G2", "G3"]

    for group in ["G0", "G1", "G2", "G3"]:
        response = client.post("/api/users", json={
            "user_code": f"assign_{group.lower()}",
            "role": "student",
            "display_name": f"Assigned {group}",
            "class_id": 1,
            "group_id": 1,
            "condition_group": group,
        })
        assert response.status_code == 200
        assert response.json()["condition_group"] == group

    bad_csv = "user_code,role,display_name,class_id,group_id,condition_group\nbad001,student,Bad,1,1,G9\n"
    imported = client.post("/api/users/import", files={"file": ("users.csv", bad_csv, "text/csv")})
    assert imported.status_code == 200
    assert imported.json()["imported"] == 0
    assert imported.json()["errors"]

    task = client.get("/api/tasks").json()[0]
    preview = client.post("/api/studies/1/feedback-preview", json={"task_id": task["id"], "transcript": task["target_text"], "condition_group": "G2"})
    assert preview.status_code == 200
    assert preview.json()["feedback"]["show_comment"] is True
    assert preview.json()["feedback"]["show_score"] is False


def test_users_export_includes_condition_group():
    response = client.get("/api/exports/users")
    assert response.status_code == 200
    assert "condition_group" in response.text


def test_teacher_ui_is_student_first_static_check():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "Student List" in text
    assert "Student Detail" in text
    assert "Review one selected student attempt at a time" in text


def test_student_ui_has_six_mode_options_static_check():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "frontend" / "src" / "pages" / "LearnerPractice.tsx").read_text(encoding="utf-8")
    for value in ["G0", "G1", "G2", "G3", "teacher_feedback", "peer_feedback"]:
        assert f'value="{value}"' in text


def test_student_teacher_and_peer_review_modes_create_requests():
    teacher = submit_with_workflow("teacher_feedback")
    assert teacher.status_code == 200
    assert teacher.json()["feedback"]["workflow_request"] == "teacher_feedback"

    peer = submit_with_workflow("peer_feedback")
    assert peer.status_code == 200
    assert peer.json()["feedback"]["workflow_request"] == "peer_feedback"
    assignments = client.get("/api/exports/peer-review-assignments")
    assert assignments.status_code == 200
    assert "student_peer_feedback_test" in assignments.text
