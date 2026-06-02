from .base import BaseASRAdapter


class FasterWhisperASRAdapter(BaseASRAdapter):
    name = "faster_whisper_asr"

    def __init__(self, model_size="base"):
        self.model_size = model_size

    def transcribe(self, audio_path, target_text=""):
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise RuntimeError("faster-whisper is optional. Install it or use ASR_MODE=mock.") from exc
        model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio_path), beam_size=1)
        return " ".join(segment.text.strip() for segment in segments).strip()
