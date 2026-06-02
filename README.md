# Speech-AI Formative Speaking Practice Platform

A runnable, role-based platform for controlled L2 read-aloud speaking practice. The first formal study is a focused feedback-information comparison: practice-only, score-only, comment-only, and score-plus-comment feedback.

This is not a high-stakes speaking assessment system. Automatic scores and automatic diagnoses are formative practice indicators only. Human ratings are needed for strong learning-outcome claims.

## Main Features

- Pilot login uses `user_code` only.
- Roles: `student`, `teacher`, `peer_reviewer`, `researcher_admin`.
- Student navigation: Practice, My Feedback, My Progress.
- Teacher navigation: Student List, Give Feedback, Class Summary.
- Peer reviewer navigation: Peer Review Tasks, Submitted Reviews.
- Researcher/admin navigation: Study Setup, Task Bank, Users and Groups, Data Export, System Status.
- Students select a read-aloud task, listen to model pronunciation, record or upload audio, submit to FastAPI, and see feedback according to their assigned G0-G3 group.
- TTS model pronunciation is available by default through browser SpeechSynthesis fallback and is clearly labelled as a browser-generated reference voice when backend cached TTS is unavailable.
- Backend stores audio locally and analyzes transcript match, duration, speech rate, pauses, missing words, substitutions, ASR sanity warnings, invalid-audio status, and a lightweight practice clarity score.
- Teachers can optionally draft and release human feedback with ratings, comments, target sounds, observed sounds, and action guidance. Teacher feedback is not a condition label.
- Peer reviewers can optionally submit supportive peer feedback for assigned review tasks. Peer feedback is separate from the main four-group experiment.
- Researcher/admin users can create/import/export users, manage classes/groups/tasks, check system status, and export clean study data.
- Mock ASR mode runs without downloading a speech model. Optional faster-whisper integration can be enabled for real ASR.

Default pilot accounts created on first startup:

```text
student001
teacher001
peer001
admin001
```

## First Formal Experiment: G0-G3

The normal visible experimental groups are:

- `G0 practice_only`: TTS model audio, recording, re-recording, no AI score, no AI comment.
- `G1 score_only`: TTS model audio plus `Practice clarity score`; no diagnostic comment.
- `G2 comment_only`: TTS model audio plus word/sound practice comment; no score.
- `G3 score_plus_comment`: TTS model audio plus score and practical comment.

Do not use labels such as human-validated feedback, teacher-orchestrated feedback, adaptive feedback, or LLM-verbalized feedback as student-facing or teacher-facing condition names. Teacher and peer feedback are optional workflows controlled separately from the G0-G3 comparison.

Assign a student to a group:

```powershell
Invoke-RestMethod -Method Post -ContentType "application/json" `
  -Uri http://127.0.0.1:8000/api/users `
  -Body '{"user_code":"s001","role":"student","display_name":"Student 001","class_id":1,"group_id":1,"condition_group":"G2"}'
```

Or use Study Setup in the admin UI and select `G0`, `G1`, `G2`, or `G3`.

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

## Role-Based Pilot Workflow

Login:

- `POST /api/login` with JSON `{ "user_code": "student001" }`
- `GET /api/me?user_code=student001`

Account and grouping:

- `GET/POST /api/users`
- `POST /api/users/import`
- `GET /api/users/export`
- `GET/POST /api/classes`
- `GET/POST /api/groups`

Student:

- `GET /api/student/tasks?user_code=student001`
- `POST /api/attempts/analyze`
- `GET /api/student/feedback?user_code=student001`
- `GET /api/student/progress?user_code=student001`

Teacher:

- `GET /api/teacher/submissions?user_code=teacher001`
- `POST /api/teacher/feedback`
- `PUT /api/teacher/feedback/{feedback_id}`
- `POST /api/teacher/feedback/{feedback_id}/release`
- `GET /api/teacher/class-review?user_code=teacher001`
- `GET /api/teacher/class-summary?user_code=teacher001`

Peer reviewer:

- `GET /api/peer/review-tasks?user_code=peer001`
- `POST /api/peer/feedback`
- `GET /api/peer/submitted-reviews?user_code=peer001`

Task audio:

- `POST /api/tasks/{task_id}/generate-tts`
- `POST /api/tasks/{task_id}/model-audio`
- `GET /api/tasks/{task_id}/model-audio`
- `GET /api/tasks/{task_id}/focus-word-audio?word=thin`

TTS note: the current lightweight deployment uses browser SpeechSynthesis as the free default model pronunciation fallback and stores `tts_status=browser_only`. Uploaded model audio can override the browser voice. Backend cached TTS generation is listed as a future feature in `FEATURE_COMPLETION_CHECKLIST.md`.

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

## Word And Sound-Level Feedback

Learner-facing diagnostic feedback now includes:

- Word needing attention.
- Target sound focus when task metadata defines it.
- Evidence level: ASR-supported cue, model-supported diagnosis, or human-validated diagnosis.
- Speaking target.
- Diagnosis.
- Criterion link.
- Explanation.
- Action guidance.
- Revision goal.
- Practice path such as `sound -> word -> phrase -> sentence`.

If a practice task has no `focus_phonemes` or `word_phoneme_map`, sound-specific feedback is not generated. The task management page warns researchers: `This task cannot produce sound-level feedback until focus phonemes are defined.`

ASR-supported feedback may say that a focus word was not clearly recognized and that this may relate to the target sound in the task. It may not claim an exact observed phoneme. Model-supported and human-validated evidence can support stronger phoneme-level feedback.

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

- `GET /api/exports/all`
- `GET /api/exports/users`
- `GET /api/exports/classes`
- `GET /api/exports/groups`
- `GET /api/exports/tasks`
- `GET /api/exports/tts-audio-status`
- `GET /api/exports/attempts`
- `GET /api/exports/ai-feedback`
- `GET /api/exports/teacher-feedback`
- `GET /api/exports/peer-feedback`
- `GET /api/exports/feedback-views`
- `GET /api/exports/revisions`
- `GET /api/exports/revision-events`
- `GET /api/exports/learner-progress`
- `GET /api/exports/teacher-orchestration-events`
- `GET /api/exports/peer-review-assignments`

Exports are also written under `data/exports`.

For G0/G1/G2/G3 analysis:

- `attempts.csv` includes `student_id`, `condition_group`, `show_score`, `show_comment`, `attempt_number`, `task_id`, `score_shown`, `comment_shown`, `revision_allowed`, and `created_at`.
- `ai_feedback.csv` includes `word_to_practise`, `target_sound`, `practice_suggestion`, `revision_goal`, `score_value`, `score_hidden`, and `comment_hidden`.
- `feedback_views.csv` separates `score`, `comment`, `teacher`, `peer`, or practice feedback views where available.
- `revision_events.csv` includes `condition_group`, previous/new attempt IDs, score delta, and target-word improvement proxy.

## Important Research Note

The automatic score is an interpretable practice indicator, not a validated proficiency score. Human expert ratings are required for final learning-outcome claims.

## Tests

```powershell
cd backend
pytest
```
