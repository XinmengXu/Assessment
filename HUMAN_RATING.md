# Human Rating

Human rating is a blinded workflow for research outcome analysis.

Raters log in with a `rater` account, for example `rater001`. The rating queue shows anonymized participant code, session type, task code or task ID, attempt number, and recording audio.

It does not show participant real ID, participant name, G0-G3 condition, ASR transcript, or automatic scores.

Rating dimensions:

- pronunciation
- fluency
- intelligibility
- comprehensibility
- task completion
- overall speaking quality
- confidence
- unusable recording flag
- optional comment

Backend endpoints:

- `GET /api/human-ratings/queue?rater_id=rater001&include_intervention=true`
- `POST /api/human-ratings`
- `GET /api/exports/human-ratings`

The export is one row per rating and includes anonymized participant code, study ID, session type, task code, attempt ID, rater ID, rubric version, scores, confidence, comments, unusable flag, start/submission timestamps, and duration. It is suitable for ICC, weighted kappa, Cohen's kappa, or correlation analysis in R or Python.
