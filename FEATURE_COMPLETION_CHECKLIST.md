# Feature Completion Checklist

Visible features must have backend logic, database storage, frontend UI, role control, CSV export when relevant, tests, documentation, and a limitation statement.

## Complete And Visible For Pilot Use

- Role login by `user_code`: complete. Roles: student, teacher, peer_reviewer, researcher_admin. Limitation: pilot login is not production authentication.
- Role-based navigation: complete. Students see only Practice, My Feedback, and My Progress.
- Student read-aloud practice: complete. Audio is sent to FastAPI `/attempts/analyze` when a backend is connected.
- Backend status and demo warning: complete. GitHub Pages is demo-only unless `VITE_API_BASE` points to a live backend.
- ASR-supported practice clarity scoring: complete. Limitation: score is formative, not a validated proficiency score.
- Invalid or silent audio handling: complete. Invalid audio returns `no_speech_detected`, `valid_audio=false`, and invalid-audio feedback.
- Browser TTS model pronunciation fallback: complete. Student, teacher, peer, and Task Bank pages can play a browser-generated reference voice. Limitation: backend cached TTS files are not yet generated in this lightweight deployment.
- Optional uploaded model audio: complete at API level. Admin can upload sentence-level override audio.
- Teacher feedback: complete. Draft, edit, release, ratings, target/observed sounds, and human-validated evidence storage are implemented.
- Peer feedback: complete. Assigned review tasks and submitted peer feedback are stored and exported.
- Student feedback separation: complete. AI-supported, teacher, and peer feedback are separated.
- Student progress: complete. Attempts, practiced tasks, feedback views, revisions, and latest score are summarized.
- Admin users/groups: complete. Create, import, export users; create classes and groups.
- Data exports: complete. Users, classes, groups, tasks, TTS status, attempts, AI feedback, teacher feedback, peer feedback, feedback views, revisions, learner progress, teacher events, peer assignments, and full zip are available.
- System status: complete. Shows backend/ASR mode and key row counts.

## Hidden Or Disabled In Normal UI

- LLM verbalized feedback: hidden and disabled. Future optional module only.
- GOPT/GOP/wav2vec2/MDD model adapter settings: hidden. Use external score import for model-supported evidence until these adapters are fully implemented.
- Raw research annotation dashboard: hidden from normal role navigation.
- Experimental condition labels A-G: hidden from students, teachers, and peer reviewers.
- Exact phoneme substitution diagnosis from ASR: forbidden. Requires model-supported or human-validated evidence.

## Future Features

- Backend cached free TTS generation beyond browser SpeechSynthesis fallback.
- Production authentication and password support.
- Rich teacher class analytics beyond the current actionable summary.
- Moderated peer-review queue with teacher approval before release.
