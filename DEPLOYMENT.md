# Deployment

This project has two deployment surfaces:

- Frontend: static Vite app, suitable for GitHub Pages.
- Backend: FastAPI service, required for real ASR, pronunciation assessment, audio storage, research logs, and exports.

GitHub Pages alone is demo-only unless the frontend is built with `VITE_API_BASE` pointing to a deployed backend.

## Environment Variables

Backend:

```bash
DATABASE_URL=sqlite:///data/app.db
DATA_DIR=/path/to/data
AUDIO_STORAGE_PATH=/path/to/data/audio
EXPORT_STORAGE_PATH=/path/to/data/exports
FRONTEND_ORIGINS=https://xinmengxu.github.io,http://localhost:5173
API_BASE_URL=https://your-backend.example.com/api
RESEARCH_MODE=false
PRONUNCIATION_PROVIDER=mock
ASR_MODE=faster_whisper
WHISPER_MODEL_SIZE=tiny
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
MAX_AUDIO_MB=25
```

Optional PostgreSQL:

```bash
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/assessment
```

Optional Azure Pronunciation Assessment:

```bash
PRONUNCIATION_PROVIDER=azure_pronunciation
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=...
```

Frontend:

```bash
VITE_API_BASE=https://your-backend.example.com/api
```

## Local Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
PYTHONPATH=. .venv/Scripts/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/api/health`.

## Frontend Build

```bash
cd frontend
npm install
npm run build
```

For GitHub Pages, set `VITE_API_BASE` in the Pages build workflow or local build environment. If it is missing or set to `demo`, the app clearly enters demo mode.

## Verify Real Backend Mode

1. Open `/api/health` and confirm `status: ok`.
2. Confirm `pronunciation_provider` is not `mock` for formal research collection.
3. Open the frontend and check the top status banner.
4. Submit a valid recording and confirm the debug panel shows backend connected, ASR transcript, valid audio, and provider status.
