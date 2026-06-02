from pathlib import Path
import wave

from ..config import LONG_PAUSE_SECONDS


def _wav_duration(path):
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        return frames / float(rate or 1)


def analyze_audio(path, transcript):
    audio_path = Path(path)
    duration = 0.0
    try:
        if audio_path.suffix.lower() == ".wav":
            duration = _wav_duration(audio_path)
        else:
            duration = max(audio_path.stat().st_size / 16000.0, 1.0)
    except Exception:
        duration = 1.0

    words = [w for w in (transcript or "").split() if w.strip()]
    speech_rate = len(words) / max(duration / 60.0, 0.01)

    # Lightweight version-1 pause estimate. Real silence detection can be added
    # behind this function without changing API routes or scoring code.
    expected_duration = max(len(words) * 0.45, 1.0)
    long_pause_count = int(max(duration - expected_duration, 0) // LONG_PAUSE_SECONDS)

    return {
        "duration_seconds": round(duration, 2),
        "speech_rate_wpm": round(speech_rate, 2),
        "long_pause_count": long_pause_count,
    }
