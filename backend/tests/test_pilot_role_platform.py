from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_role_login_and_student_endpoints():
    payload = {
        "user_code": "pilot_student_role_test",
        "role": "student",
        "display_name": "Pilot Student Role Test",
        "class_id": 1,
        "group_id": 1,
    }
    created = client.post("/api/users", json=payload)
    assert created.status_code == 200
    login = client.post("/api/login", json={"user_code": payload["user_code"]})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "student"

    tasks = client.get("/api/student/tasks", params={"user_code": payload["user_code"]})
    assert tasks.status_code == 200
    assert isinstance(tasks.json(), list)

    progress = client.get("/api/student/progress", params={"user_code": payload["user_code"]})
    assert progress.status_code == 200
    assert "attempt_count" in progress.json()


def test_tts_generation_is_labeled_browser_only():
    task = client.get("/api/tasks").json()[0]
    response = client.post(f"/api/tasks/{task['id']}/generate-tts", json={"tts_voice": "browser-default"})
    assert response.status_code == 200
    assert response.json()["tts_status"] == "browser_only"
    assert "browser SpeechSynthesis" in response.json()["message"]


def test_teacher_feedback_release_and_export():
    teacher = client.post("/api/users", json={"user_code": "pilot_teacher_role_test", "role": "teacher", "display_name": "Pilot Teacher", "class_id": 1}).json()
    feedback = client.post("/api/teacher/feedback", json={
        "teacher_user_id": teacher["id"],
        "participant_id": "pilot_student_role_test",
        "task_id": 1,
        "attempt_id": 0,
        "pronunciation_rating": 4,
        "fluency_rating": 3,
        "comprehensibility_rating": 4,
        "target_word": "thin",
        "target_phoneme": "th",
        "observed_phoneme": "s",
        "comment": "Keep the tongue tip gentle for the target sound.",
        "action_guidance": "Practise thin, then the full sentence.",
    })
    assert feedback.status_code == 200
    released = client.post(f"/api/teacher/feedback/{feedback.json()['id']}/release")
    assert released.status_code == 200
    assert released.json()["status"] == "released"

    export = client.get("/api/exports/teacher-feedback")
    assert export.status_code == 200
    assert "text/csv" in export.headers["content-type"]


def test_peer_feedback_and_required_exports():
    peer = client.post("/api/users", json={"user_code": "pilot_peer_role_test", "role": "peer_reviewer", "display_name": "Pilot Peer", "class_id": 1}).json()
    submitted = client.post("/api/peer/feedback", json={
        "assignment_id": 0,
        "reviewer_user_id": peer["id"],
        "participant_id": "pilot_student_role_test",
        "task_id": 1,
        "attempt_id": 0,
        "clarity_rating": 3,
        "encouragement": "The sentence rhythm was easy to follow.",
        "suggestion": "Try the focus word once more before recording.",
    })
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"

    for path in [
        "/api/exports/users",
        "/api/exports/classes",
        "/api/exports/groups",
        "/api/exports/tasks",
        "/api/exports/tts-audio-status",
        "/api/exports/attempts",
        "/api/exports/ai-feedback",
        "/api/exports/peer-feedback",
        "/api/exports/feedback-views",
        "/api/exports/revisions",
        "/api/exports/learner-progress",
        "/api/exports/teacher-orchestration-events",
        "/api/exports/peer-review-assignments",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path


def test_frontend_role_nav_hides_research_pages_from_students():
    repo_root = Path(__file__).resolve().parents[2]
    main_tsx = (repo_root / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    student_nav = main_tsx.split("student: [", 1)[1].split("teacher:", 1)[0]
    assert "Practice" in student_nav
    assert "My Feedback" in student_nav
    assert "My Progress" in student_nav
    assert "Study Setup" not in student_nav
    assert "Annotation Review" not in student_nav
    assert "System Status" not in student_nav
