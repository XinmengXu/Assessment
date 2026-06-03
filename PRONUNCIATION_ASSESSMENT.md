# Pronunciation Assessment

The platform separates ordinary ASR from pronunciation assessment.

ASR is supplementary evidence for transcript sanity checks. It must not be treated as exact phoneme-level diagnosis. Exact observed phoneme claims require model-supported pronunciation assessment evidence or human validation.

Provider modes:

- `mock`: UI testing only. Results are marked `practice_indicator` and simulated.
- `external_import`: uses previously imported rows from an external pronunciation assessment system.
- `azure_pronunciation`: calls Microsoft Azure Speech Pronunciation Assessment when credentials are configured.
- `disabled`: returns a clear backend error in research mode.

Set the provider:

```bash
PRONUNCIATION_PROVIDER=azure_pronunciation
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=...
```

Evidence levels:

- `practice_indicator`: low-stakes heuristic or mock result.
- `asr_supported_cue`: weak cue from ASR or text matching.
- `model_supported_diagnosis`: real pronunciation assessment provider evidence.
- `human_validated_diagnosis`: human reviewer confirmed or corrected evidence.

Azure note: the lightweight adapter sends WAV audio to Azure Speech. For production, record or convert to the audio format expected by Azure and validate this with pilot data before formal collection.
