from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "app.db"

ASR_MODE = "mock"  # "mock" or "faster_whisper"
WHISPER_MODEL_SIZE = "base"

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
