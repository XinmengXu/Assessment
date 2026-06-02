from pathlib import Path

from app.analysis.asr import ASRService


def test_mock_asr_without_hint_returns_empty_transcript(tmp_path: Path):
    audio = tmp_path / "attempt.webm"
    audio.write_bytes(b"fake audio")
    assert ASRService().transcribe(audio, "The target sentence") == ""


def test_mock_asr_uses_sidecar_hint(tmp_path: Path):
    audio = tmp_path / "attempt.webm"
    audio.write_bytes(b"fake audio")
    audio.with_suffix(".txt").write_text("the recognized words", encoding="utf-8")
    assert ASRService().transcribe(audio, "The target sentence") == "the recognized words"
