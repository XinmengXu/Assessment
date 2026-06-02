from pathlib import Path

from ..config import ASR_MODE, WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL_SIZE


class ASRService:
    def transcribe(self, audio_path, target_text=""):
        if ASR_MODE == "faster_whisper":
            try:
                return self._faster_whisper(audio_path)
            except Exception as exc:
                raise RuntimeError("faster-whisper ASR failed. Check model availability, FFmpeg, and GPU/CPU settings.") from exc
        return self._mock(audio_path, target_text)

    def _mock(self, audio_path, target_text):
        path = Path(audio_path)
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8").strip()
        return ""

    def _faster_whisper(self, audio_path):
        from faster_whisper import WhisperModel

        model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
        segments, _ = model.transcribe(str(audio_path), beam_size=1)
        return " ".join(seg.text.strip() for seg in segments).strip()


asr_service = ASRService()
