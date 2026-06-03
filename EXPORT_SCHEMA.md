# Export Schema

Main research exports:

- `/api/exports/participants`
- `/api/exports/attempts`
- `/api/exports/pronunciation-assessment-results`
- `/api/exports/word-level-results`
- `/api/exports/phoneme-level-results`
- `/api/exports/feedback`
- `/api/exports/feedback-events`
- `/api/exports/feedback-uptake-states`
- `/api/exports/human-ratings`
- `/api/exports/questionnaire-responses`
- `/api/exports/audit-log`
- `/api/exports/analysis-ready-long`
- `/api/exports/analysis-ready-wide`
- `/api/exports/full`

Default analysis-ready exports use anonymized participant IDs and skip withdrawn participants. Use participant codes in the platform; do not store real names unless your ethics protocol explicitly permits it.

Core analysis-ready fields include condition group, class/proficiency fields, session type, task code, attempt number, automatic pronunciation scores, feedback visibility, feedback viewed flag, revision count, uptake state, human rating fields, system version, and provider version.

Score columns are intentionally separated:

- `practice_clarity_score`
- `practice_clarity_score_source`
- `pronunciation_assessment_score`
- `pronunciation_assessment_score_source`
- `score_valid_for_formal_research`
- `evidence_level`

Default participant exports are anonymized. Identifiable participant exports require `GET /api/exports/participants-identifiable?admin_confirm=true` and are logged in `audit_log`.
