# Design

## Architecture

```text
React + Vite UI
  |-- learner practice
  |-- attempt history
  |-- researcher dashboard
  |-- task management
        |
        v
FastAPI REST API
  |-- participants, tasks, attempts
  |-- dashboard summaries
  |-- CSV exports
        |
        v
Analysis modules
  |-- asr.py
  |-- audio_features.py
  |-- text_alignment.py
  |-- scoring.py
  |-- feedback_generator.py
        |
        v
SQLite + local files
  |-- data/app.db
  |-- data/audio/{participant}/{task}/attempt_n.*
  |-- data/exports/*.csv
```

## Backend Modules

- `database.py`: SQLAlchemy models, SQLite engine, session dependency.
- `schemas.py`: Pydantic request and response models.
- `api.py`: REST endpoints for participants, tasks, attempts, dashboard, and exports.
- `asr.py`: mock ASR by default, optional faster-whisper backend.
- `audio_features.py`: duration, speech rate, and lightweight pause estimate.
- `text_alignment.py`: target/transcript normalization and alignment.
- `scoring.py`: interpretable weighted score from alignment and fluency features.
- `feedback_generator.py`: score-only and explainable rule-based feedback.
- `export.py`: CSV writers for full, participant-level, and task-level data.
- `seed.py`: 20 original read-aloud tasks plus a sample participant.

## Frontend Pages

- Learner Practice: participant context, task selector, browser recording, upload fallback, transcript hint for mock ASR, feedback display, and revision submission.
- Attempt History: participant-level attempt table and CSV download.
- Researcher Dashboard: aggregate statistics, filters, common error lists, and exports.
- Task Management: add/edit target sentence, focus words, speaking target, difficulty, and optional model audio path.

## Data Flow

```text
learner recording
  -> backend analysis
  -> ASR transcript
  -> text alignment and audio features
  -> scoring
  -> feedback generation
  -> database logging
  -> learner revision
  -> dashboard and CSV export
```

## Extension Points

The ASR module can be replaced with WhisperX, Montreal Forced Aligner, wav2vec2, GOP scoring, or phoneme-level diagnosis while keeping the API response shape stable.
