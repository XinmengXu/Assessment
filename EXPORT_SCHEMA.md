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
