# Feature Completion Checklist

Visible features must have backend logic, database persistence, frontend UI, CSV export, tests, documentation, and a limitation statement.

## Enabled For Pilot Use

- Real/demo backend routing: complete.
- ASR-supported practice clarity scoring: complete. Limitation: ASR alignment is only a cue, not phoneme-level diagnosis.
- Invalid audio handling: complete.
- ASR-supported diagnosis records: complete. Limitation: `observed_phoneme` is always null for ASR-only evidence.
- External assessment CSV import: complete for sentence, word, and phoneme rows.
- Human validation release workflow: enabled for approve/reject/release. Limitation: rich inline editing UI is basic.
- Teacher orchestration action logging: backend/export enabled. Limitation: dashboard signal UI is basic and should be expanded before formal study use.
- Research mode lock: backend enabled for tasks and condition creation. Limitation: frontend lock controls are not yet polished.
- Full research export zip: enabled.

## Hidden Or Disabled In Normal UI

- LLM verbalized feedback: disabled and hidden. Future optional module only.
- GOPT/GOP/wav2vec2/MDD adapters: disabled. Use external assessment import instead.
- Exact phoneme replacement diagnosis from ASR: forbidden. Requires model-supported or human-validated evidence.

## Needs Expansion Before Full Study

- Adaptive policy has a lightweight rule base but should be broadened before a larger controlled study.
- Teacher dashboard needs richer class-level signal panels.
- Human validation editing UI should support all feedback moves in a more ergonomic form.
