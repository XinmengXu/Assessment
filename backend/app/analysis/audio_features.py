from pathlib import Path
import wave
import audioop

from ..config import LONG_PAUSE_SECONDS


MIN_VALID_AUDIO_SECONDS = 0.5
MIN_VALID_RMS = 80


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
    try:
        if audio_path.suffix.lower() == ".wav":
            duration = _wav_duration(audio_path)
            mean_energy = float(_wav_energy(audio_path))
            audio_decoded = True
        else:
            duration = max(audio_path.stat().st_size / 16000.0, 1.0)
    except Exception:
        duration = 0.0

    words = [w for w in (transcript or "").split() if w.strip()]
    speech_rate = len(words) / max(duration / 60.0, 0.01)
    no_speech_detected = duration < MIN_VALID_AUDIO_SECONDS
    if audio_decoded and mean_energy < MIN_VALID_RMS:
        no_speech_detected = True
    if not words:
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
        "audio_decoded": audio_decoded,
        "no_speech_detected": no_speech_detected,
    }
