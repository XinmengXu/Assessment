# Research Workflow

The formal experiment remains the G0-G3 feedback information comparison.

- G0: practice only; model pronunciation plus recording/re-recording, no score and no diagnostic comment.
- G1: score only.
- G2: diagnostic/practical comment only.
- G3: score plus diagnostic/practical comment.

Recommended session types:

- `familiarization`
- `pre_test`
- `practice_intervention`
- `immediate_post_test`
- `delayed_post_test`
- `backup_task`

Use participant codes rather than real names. Assign students to G0-G3 before data collection, then lock the study. Locked studies block task/condition edits and group-assignment changes unless an admin unlocks with a reason. Lock/unlock actions are written to `audit_log`.

Feedback uptake is logged as:

- F0: feedback generated but not viewed.
- F1: feedback viewed but no revision attempt.
- F2: feedback viewed and revised, but no target improvement.
- F3: feedback viewed and revised with target improvement.
- F4: improvement maintained in later task/session.

Use `/api/pilot-readiness` before data collection.
