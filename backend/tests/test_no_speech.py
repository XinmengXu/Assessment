import wave
from pathlib import Path

from fastapi.testclient import TestClient

from app.analysis.audio_features import analyze_audio
from app.main import app


def write_silent_wav(path: Path, seconds=1, rate=16000):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * rate * seconds)


def test_silent_wav_sets_no_speech_detected(tmp_path):
    audio = tmp_path / "silent.wav"
    write_silent_wav(audio)
    features = analyze_audio(audio, "")
    assert features["no_speech_detected"] is True
    assert features["mean_energy"] == 0


def test_blank_transcript_attempt_returns_invalid_audio(tmp_path):
    audio = tmp_path / "silent.wav"
    write_silent_wav(audio)
    client = TestClient(app)
    with audio.open("rb") as handle:
        response = client.post(
            "/api/attempts/analyze",
            data={
                "participant_id": "no_speech_test",
                "group_id": "explainable",
                "task_id": "1",
                "transcript_hint": "",
            },
            files={"audio": ("silent.wav", handle, "audio/wav")},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["no_speech_detected"] is True
    assert payload["feedback_type"] == "invalid_audio"
    assert payload["feedback"]["overall_score"] is None


def test_demo_client_labels_simulated_scores():
    client_path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "client.ts"
    text = client_path.read_text(encoding="utf-8")
    assert "simulated practice score" in text
    assert "Demo mode: no real audio analysis is running." in text
