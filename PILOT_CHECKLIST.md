# Pilot Checklist

Run:

```bash
curl https://your-backend.example.com/api/pilot-readiness
```

Check that:

- backend is connected
- database is writable
- audio directory is writable
- export directory is writable
- pronunciation provider is configured
- provider is research usable for formal collection
- at least one study exists
- G0-G3 conditions exist
- participants are assigned
- tasks are active
- model audio or browser fallback is available
- no demo/mock provider is used in research collection

Before formal data collection, submit several test recordings, download `/api/exports/full`, and verify that attempts, pronunciation results, feedback events, uptake states, and human rating exports contain the expected rows.
