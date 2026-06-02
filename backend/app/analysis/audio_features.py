from pathlib import Path
import wave
import audioop

from ..config import (
    LONG_PAUSE_SECONDS,
    MAX_VALID_AUDIO_SECONDS,
    MIN_TRANSCRIPT_TOKENS,
    MIN_VALID_AUDIO_BYTES,
    MIN_VALID_AUDIO_SECONDS,
    MIN_VALID_RMS,
)


def _wav_duration(path):
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        return frames / float(rate or 1)


def _wav_energy(path):
    with wave.open(str(path), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
        width = wav.getsampwidth()
        return audioop.rms(frames, width) if frames else 0


def analyze_audio(path, transcript):
    audio_path = Path(path)
    duration = 0.0
    mean_energy = 0.0
    audio_decoded = False
    invalid_reasons = []
    file_size = 0
    try:
        file_size = audio_path.stat().st_size
        if audio_path.suffix.lower() == ".wav":
            duration = _wav_duration(audio_path)
            mean_energy = float(_wav_energy(audio_path))
            audio_decoded = True
        else:
            duration = max(file_size / 16000.0, 1.0)
    except Exception as exc:
        duration = 0.0
        invalid_reasons.append("audio_decode_failed:%s" % exc.__class__.__name__)

    words = [w for w in (transcript or "").split() if w.strip()]
    speech_rate = len(words) / max(duration / 60.0, 0.01)
    no_speech_detected = False
    if file_size < MIN_VALID_AUDIO_BYTES:
        invalid_reasons.append("file_too_small")
        no_speech_detected = True
    if duration < MIN_VALID_AUDIO_SECONDS:
        invalid_reasons.append("audio_too_short")
        no_speech_detected = True
    if duration > MAX_VALID_AUDIO_SECONDS:
        invalid_reasons.append("audio_too_long")
    if audio_decoded and mean_energy < MIN_VALID_RMS:
        invalid_reasons.append("audio_too_silent")
        no_speech_detected = True
    if len(words) < MIN_TRANSCRIPT_TOKENS:
        invalid_reasons.append("transcript_too_short")
        no_speech_detected = True

    # Lightweight version-1 pause estimate. Real silence detection can be added
    # behind this function without changing API routes or scoring code.
    expected_duration = max(len(words) * 0.45, 1.0)
    long_pause_count = int(max(duration - expected_duration, 0) // LONG_PAUSE_SECONDS)

    return {
        "duration_seconds": round(duration, 2),
        "speech_rate_wpm": round(speech_rate, 2),
        "long_pause_count": long_pause_count,
        "mean_energy": round(mean_energy, 2),
        "file_size_bytes": file_size,
        "audio_decoded": audio_decoded,
        "no_speech_detected": no_speech_detected,
        "valid_audio": not no_speech_detected,
        "invalid_reasons": invalid_reasons,
    }
