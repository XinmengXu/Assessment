from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "app.db"

ASR_MODE = os.getenv("ASR_MODE", "mock")  # "mock" or "faster_whisper"
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

MIN_VALID_AUDIO_SECONDS = float(os.getenv("MIN_VALID_AUDIO_SECONDS", "0.8"))
MAX_VALID_AUDIO_SECONDS = float(os.getenv("MAX_VALID_AUDIO_SECONDS", "180"))
MIN_VALID_AUDIO_BYTES = int(os.getenv("MIN_VALID_AUDIO_BYTES", "512"))
MIN_VALID_RMS = float(os.getenv("MIN_VALID_RMS", "80"))
MIN_TRANSCRIPT_TOKENS = int(os.getenv("MIN_TRANSCRIPT_TOKENS", "1"))

SCORE_WEIGHTS = {
    "word_match": 70,
    "missing_penalty": 4,
    "substitution_penalty": 3,
    "speech_rate_penalty": 8,
    "pause_penalty": 3,
}

MIN_REASONABLE_WPM = 70
MAX_REASONABLE_WPM = 180
LONG_PAUSE_SECONDS = 1.2


def ensure_data_dirs():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
