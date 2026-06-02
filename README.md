# Speech-AI Feedback Research Platform

A runnable lightweight research platform for controlled education-AI experiments on second-language speaking feedback, feedback use, learner modelling, adaptive formative feedback, and human validation of speech-AI diagnosis.

## Main Features

- Learners enter a participant ID, group, and session ID.
- Learners select a read-aloud task, record in the browser, or upload audio.
- Backend stores audio locally and analyzes transcript match, duration, speech rate, long pauses, missing words, substitutions, and score.
- Experimental conditions A-G are supported: assessment-only, transcript-only, score-only, explainable, adaptive, human-validated, and optional LLM-verbalized feedback.
- Explainable and adaptive groups receive diagnosis, explanation, action guidance, revision goals, and metacognitive prompts.
- Attempt history shows multiple attempts and improvement indicators.
- Researcher dashboard reports condition-level statistics, feedback use, learner state, issue types, and revision events.
- Annotation Review supports human validation of automatic diagnosis.
- Study Design supports default conditions and participant assignment.
- CSV exports support participants, attempts, feedback, revisions, learner states, annotations, tasks, and study design.
- Mock ASR mode runs without downloading a speech model.
- Optional faster-whisper integration can be enabled for real ASR.

## Tech Stack

- Frontend: React, Vite, TypeScript, MediaRecorder API
- Backend: FastAPI, SQLite, SQLAlchemy, Pydantic
- Analysis: modular ASR, text alignment, audio features, scoring, feedback generation
- Learner model: interpretable rule-based state update
- Validation: human annotation plus simple agreement report
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

## GitHub Pages Demo

The repository includes a GitHub Actions workflow that builds the React frontend and deploys it to GitHub Pages. On GitHub Pages, the app runs in a browser-local demo mode because GitHub Pages cannot run the FastAPI backend. Demo tasks, attempts, dashboard summaries, and CSV exports are stored in the browser's localStorage.

For full research data collection with SQLite, audio files, and backend analysis, run the FastAPI backend locally or deploy it to a server and set `VITE_API_BASE` for the frontend build.

## Mock ASR Mode

Mock ASR is the default in `backend/app/config.py`.

In the learner page, use the optional mock transcript hint to simulate what ASR recognized. If the hint is blank, mock mode returns an empty transcript and the score will be low. This avoids pretending that arbitrary audio was recognized correctly.

## Real ASR Mode

Install faster-whisper and FFmpeg, then edit `backend/app/config.py`:

```python
ASR_MODE = "faster_whisper"
WHISPER_MODEL_SIZE = "base"
```

CPU mode uses `int8` by default in `app/analysis/asr.py`. If the model cannot load, the backend falls back to mock ASR.

## Export Data

Use the dashboard buttons or these endpoints:

- `GET /api/exports/full`
- `GET /api/exports/participants`
- `GET /api/exports/attempts`
- `GET /api/exports/feedback`
- `GET /api/exports/revisions`
- `GET /api/exports/learner-states`
- `GET /api/exports/annotations`
- `GET /api/exports/study-design`
- `GET /api/exports/tasks`

Exports are also written under `data/exports`.

## Important Research Note

The automatic score is an interpretable practice indicator, not a validated proficiency score. Human expert ratings are required for final learning-outcome claims.

## Tests

```powershell
cd backend
pytest
```
