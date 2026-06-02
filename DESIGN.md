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
  |-- participants, studies, conditions
  |-- tasks, attempts, feedback views
  |-- learner states, annotations
  |-- dashboard summaries and CSV exports
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
- `services/feedback/feedback_policy.py`: condition A-G feedback visibility and feedback use states F0-F4.
- `services/learner_model/state_update.py`: rule-based learner state update.
- `services/validation/agreement.py`: simple system-human agreement metrics.
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
- Task Management: add/edit task type, target sentence, issue types, focus words, speaking target, difficulty, revision settings, and optional model audio path.
- Annotation Review: inspect automatic output and save human validation ratings.
- Study Design: inspect default A-G conditions and assign participants.

## Data Flow

```text
learner recording
  -> backend analysis
  -> ASR transcript
  -> text alignment and audio features
  -> scoring
  -> feedback policy
  -> learner state update
  -> database logging
  -> learner revision
  -> annotation validation
  -> dashboard and CSV export
```

## Experimental Condition Logic

Condition A hides transcript, score, and feedback for assessment. Condition B shows transcript only. Condition C shows score plus generic comment. Condition D shows explainable rule-based feedback. Condition E adds learner-state-aware metacognitive prompting. Condition F creates draft feedback for human validation. Condition G is reserved for optional LLM verbalization and falls back to templates by default.

## Learner Model Logic

Learner state is updated after each attempt using word match, speech rate, long pauses, feedback views, revision deltas, and repeated issue types. The model is intentionally interpretable and lightweight for version 1.

## Feedback Use Tracker

Feedback use is represented as F0-F4. See `DATA_DICTIONARY.md` for definitions.

## Extension Points

The ASR module can be replaced with WhisperX, Montreal Forced Aligner, wav2vec2, GOP scoring, or phoneme-level diagnosis while keeping the API response shape stable.
