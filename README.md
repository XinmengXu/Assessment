# Explainable Speech-AI Feedback App

A runnable research prototype for studying automated speaking feedback in second-language read-aloud practice. The app compares score-only feedback with explainable feedback that supports diagnosis, explanation, action guidance, revision, and continuity tracking.

## Main Features

- Learners enter a participant ID, group, and session ID.
- Learners select a read-aloud task, record in the browser, or upload audio.
- Backend stores audio locally and analyzes transcript match, duration, speech rate, long pauses, missing words, substitutions, and score.
- Control group receives score-only feedback.
- Explainable group receives diagnosis, explanation, action guidance, and revision prompts.
- Attempt history shows multiple attempts and improvement indicators.
- Researcher dashboard reports aggregate study statistics.
- CSV exports support full, participant-level, and task-level analysis.
- Mock ASR mode runs without downloading a speech model.
- Optional faster-whisper integration can be enabled for real ASR.

## Tech Stack

- Frontend: React, Vite, TypeScript, MediaRecorder API
- Backend: FastAPI, SQLite, SQLAlchemy, Pydantic
- Analysis: modular ASR, text alignment, audio features, scoring, feedback generation
- Storage: local SQLite database and local audio/export folders under `data/`

## Run Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend seeds 20 original L2 speaking tasks at startup.

## Run Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Mock ASR Mode

Mock ASR is the default in `backend/app/config.py`.

In the learner page, use the optional mock transcript hint to simulate recognition errors. If the hint is blank, the backend uses the target sentence as the transcript.

## Real ASR Mode

Install faster-whisper and FFmpeg, then edit `backend/app/config.py`:

```python
ASR_MODE = "faster_whisper"
WHISPER_MODEL_SIZE = "base"
```

CPU mode uses `int8` by default in `app/analysis/asr.py`. If the model cannot load, the backend falls back to mock ASR.

## Export Data

Use the dashboard buttons or these endpoints:

- `GET /exports/full`
- `GET /exports/participant/{participant_id}`
- `GET /exports/tasks`

Exports are also written under `data/exports`.

## Tests

```powershell
cd backend
pytest
```
