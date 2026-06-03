from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).expanduser()
AUDIO_DIR = Path(os.getenv("AUDIO_STORAGE_PATH", os.getenv("AUDIO_DIR", str(DATA_DIR / "audio")))).expanduser()
EXPORT_DIR = Path(os.getenv("EXPORT_STORAGE_PATH", os.getenv("EXPORT_DIR", str(DATA_DIR / "exports")))).expanduser()
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "app.db"))).expanduser()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "").strip()
FRONTEND_ORIGINS = os.getenv(
    "FRONTEND_ORIGINS",
    os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://xinmengxu.github.io"),
)
SYSTEM_VERSION = os.getenv("SYSTEM_VERSION", "0.3.0-research")
RESEARCH_MODE = os.getenv("RESEARCH_MODE", "false").lower() in {"1", "true", "yes", "on"}

ASR_MODE = os.getenv("ASR_MODE", "mock")  # "mock" or "faster_whisper"
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

PRONUNCIATION_PROVIDER = os.getenv("PRONUNCIATION_PROVIDER", os.getenv("ASSESSMENT_PROVIDER", "mock")).strip() or "mock"
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "").strip()
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "").strip()
EXTERNAL_IMPORT_SOURCE_NAME = os.getenv("EXTERNAL_IMPORT_SOURCE_NAME", "external_import")

MIN_VALID_AUDIO_SECONDS = float(os.getenv("MIN_VALID_AUDIO_SECONDS", "0.8"))
MAX_VALID_AUDIO_SECONDS = float(os.getenv("MAX_VALID_AUDIO_SECONDS", "180"))
MIN_VALID_AUDIO_BYTES = int(os.getenv("MIN_VALID_AUDIO_BYTES", "512"))
MIN_VALID_RMS = float(os.getenv("MIN_VALID_RMS", "80"))
MIN_TRANSCRIPT_TOKENS = int(os.getenv("MIN_TRANSCRIPT_TOKENS", "1"))
MAX_AUDIO_MB = float(os.getenv("MAX_AUDIO_MB", "25"))
ALLOWED_AUDIO_TYPES = {
    item.strip().lower()
    for item in os.getenv("ALLOWED_AUDIO_TYPES", "audio/wav,audio/x-wav,audio/webm,audio/mpeg,audio/mp4,audio/ogg,application/octet-stream").split(",")
    if item.strip()
}
ALLOWED_AUDIO_EXTENSIONS = {
    item.strip().lower()
    for item in os.getenv("ALLOWED_AUDIO_EXTENSIONS", ".wav,.webm,.mp3,.m4a,.ogg").split(",")
    if item.strip()
}

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
