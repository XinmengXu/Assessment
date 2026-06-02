# Speech-AI Feedback Research Platform

A runnable lightweight research platform for controlled education-AI experiments on second-language speaking feedback, feedback use, learner modelling, adaptive formative feedback, and human validation of speech-AI diagnosis.

## Main Features

- Learners enter a participant ID, group, and session ID.
- Learners select a read-aloud task, record in the browser, or upload audio.
- Backend stores audio locally and analyzes transcript match, duration, speech rate, long pauses, missing words, substitutions, ASR sanity warnings, invalid-audio status, and a lightweight practice clarity score.
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

## GitHub Pages Deployment

The repository includes a GitHub Actions workflow that builds the React frontend and deploys it to GitHub Pages. GitHub Pages can host only the static React frontend; it cannot run the FastAPI backend.

Important:

- If `VITE_API_BASE` is missing or set to `demo`, GitHub Pages runs in demo mode.
- Demo mode does not analyze audio. Recording and upload controls are accepted only for interface testing.
- Demo scores are labelled as simulated and use only the optional transcript hint.
- If `VITE_API_BASE` points to a deployed FastAPI backend and `${VITE_API_BASE}/health` succeeds, GitHub Pages uses the real backend and sends audio to `/attempts/analyze`.

For full research data collection with SQLite, audio files, real ASR, backend diagnostics, and exports, deploy the FastAPI backend to a server and build the frontend with:

```powershell
cd frontend
$env:VITE_API_BASE="https://your-backend.example.com/api"
npm run build
```

For GitHub Actions / GitHub Pages, set repository variable `VITE_API_BASE` to your deployed backend API base, for example:

```text
https://your-backend.example.com/api
```

The frontend performs a startup health check:

```text
GET ${VITE_API_BASE}/health
```

If the health check fails, the UI shows `Demo mode: no real backend connected` and uses browser-local demo data only.

For local real testing, run the backend at `http://127.0.0.1:8000` and the frontend dev server. Vite proxies `/api` to FastAPI in local development.

## Mock ASR Mode

Mock ASR is the default in `backend/app/config.py`.

In the learner page, use the optional mock transcript hint to simulate what ASR recognized. If the hint is blank, mock mode returns an empty transcript and the score will be low. This avoids pretending that arbitrary audio was recognized correctly.

If no transcript is detected, or if a WAV file is silent or too short, the backend returns `no_speech_detected=true`, `valid_audio=false`, `feedback_type=invalid_audio`, and the message: `No valid speech was detected. Please record your voice again.`

## Real ASR Mode

Install faster-whisper and FFmpeg, then edit `backend/app/config.py`:

```python
ASR_MODE = "faster_whisper"
WHISPER_MODEL_SIZE = "base"
```

CPU mode uses `int8` by default in `app/analysis/asr.py`. If the configured model cannot load, the backend raises an error instead of silently falling back to mock ASR.

## Lightweight Practice Scoring

The learner-facing score is a `Practice clarity score`. It is a transparent practice indicator based on word match, missing words, substitutions, speech-rate penalty, pause penalty, and invalid-audio checks. It is not a validated speaking proficiency score.

Each attempt stores:

- `valid_audio` and invalid-audio reasons.
- `asr_sanity` warnings such as empty transcript or repeated hallucination patterns.
- Complete alignment JSON with matched, missing, substituted, and inserted words.
- `score_breakdown` with the components used to produce the practice score.

## Evidence Levels And Diagnosis Limits

The platform separates evidence levels:

- `asr_supported_cue`: ASR alignment only. Feedback must use cautious wording such as "may not have been clearly recognized." It must not include `observed_phoneme`.
- `model_supported_diagnosis`: imported external model evidence. The source name, score, confidence, and score level are stored.
- `human_validated_diagnosis`: reviewer-supported evidence. Exact observed-phoneme claims require this or model-supported evidence.

ASR alone never supports wording such as "you pronounced X as Y."

## External Scores Import

Researchers can download a CSV template from `GET /api/external-scores/template` and import scores with `POST /api/external-scores/import`.

Required columns:

`participant_code, task_code, attempt_number, source_name, score_level, target_word, target_phoneme, observed_phoneme_optional, score, confidence, issue_type_optional, notes_optional`

Imported phoneme-level rows create `pronunciation_evidence`. Low phoneme-level scores can create `model_supported_diagnosis` records.

## Human Validation Release

For `human_validated_feedback`, draft feedback is hidden until review. Reviewers can approve, edit, reject, and release feedback:

- `POST /api/feedback/{feedback_item_id}/approve`
- `POST /api/feedback/{feedback_item_id}/edit`
- `POST /api/feedback/{feedback_item_id}/reject`
- `POST /api/feedback/{feedback_item_id}/release`
- `GET /api/feedback/pending-review`

## Research Mode Lock

Use `POST /api/studies/{study_id}/lock` to lock a study. Locked studies reject task and condition edits with a clear error. Create a new system version with `POST /api/system-version/create` before changing study-critical settings.

## Pilot Readiness Check

Run:

```powershell
cd backend
$env:PYTHONPATH="."
python scripts/pilot_readiness_check.py
```

The script prints `PASS` or `FAIL` for health, valid attempt evidence, revision tracking, human validation release, teacher action logging, and full export.

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
