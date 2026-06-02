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
