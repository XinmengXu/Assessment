from pathlib import Path

from .base import BaseASRAdapter


class MockASRAdapter(BaseASRAdapter):
    name = "mock_asr"

    def transcribe(self, audio_path, target_text=""):
        sidecar = Path(audio_path).with_suffix(".txt")
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8").strip()
        return target_text
