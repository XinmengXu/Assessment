# Feature Completion Checklist

Visible features must have backend logic, database storage, frontend UI, role control, CSV export when relevant, tests, documentation, and a limitation statement.

## Complete And Visible For Pilot Use

- Role login by `user_code`: complete. Roles: student, teacher, peer_reviewer, researcher_admin. Limitation: pilot login is not production authentication.
- Role-based navigation: complete. Students see only Practice, My Feedback, and My Progress.
- Four-group feedback-information experiment: complete. Visible groups are `G0 practice_only`, `G1 score_only`, `G2 comment_only`, and `G3 score_plus_comment`.
- Study Setup experiment group workflow: complete. Admin can activate G0-G3, inspect group cards, assign one student, bulk import assignments, export assignments, and preview student-facing output by group.
- Group-aware student feedback display: complete. G0 shows neither score nor comment; G1 shows score only; G2 shows comment only; G3 shows score and comment.
- Student read-aloud practice: complete. Audio is sent to FastAPI `/attempts/analyze` when a backend is connected.
- Backend status and demo warning: complete. GitHub Pages is demo-only unless `VITE_API_BASE` points to a live backend.
- ASR-supported practice clarity scoring: complete. Limitation: score is formative, not a validated proficiency score.
- Invalid or silent audio handling: complete. Invalid audio returns `no_speech_detected`, `valid_audio=false`, and invalid-audio feedback.
- Browser TTS model pronunciation fallback: complete. Student, teacher, peer, and Task Bank pages can play a browser-generated reference voice. Limitation: backend cached TTS files are not yet generated in this lightweight deployment.
- Optional uploaded model audio: complete at API level. Admin can upload sentence-level override audio.
- Teacher feedback workflow: complete but optional. Teacher starts from Student List, opens Student Detail, then reviews one selected attempt. It is not a condition label for the first G0-G3 experiment.
- Peer feedback workflow: complete but optional. It is separate from the first G0-G3 experiment.
- Student feedback separation: complete. AI-supported, teacher, and peer feedback are separated.
- Student progress: complete. Attempts, practiced tasks, feedback views, revisions, and latest score are summarized.
- Admin users/groups: complete. Create, import, export users; create classes and groups.
- Data exports: complete. Attempts, AI feedback, feedback views, and revision events include `condition_group` and fields needed for G0/G1/G2/G3 comparison.
- System status: complete. Shows backend/ASR mode and key row counts.

## Hidden Or Disabled In Normal UI

- LLM verbalized feedback: hidden and disabled. Future optional module only.
- GOPT/GOP/wav2vec2/MDD model adapter settings: hidden. Use external score import for model-supported evidence until these adapters are fully implemented.
- Raw research annotation dashboard: hidden from normal role navigation.
- Experimental condition labels A-G: replaced in normal UI by G0-G3.
- Human-validated, teacher-orchestrated, adaptive, and LLM condition names: hidden from normal UI. Teacher/peer are optional workflows only.
- Exact phoneme substitution diagnosis from ASR: forbidden. Requires model-supported or human-validated evidence.

## Future Features

- Backend cached free TTS generation beyond browser SpeechSynthesis fallback.
- Production authentication and password support.
- Rich teacher class analytics beyond the current actionable summary.
- Moderated peer-review queue with teacher approval before release.
