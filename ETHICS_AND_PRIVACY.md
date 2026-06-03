# Ethics And Privacy

This platform is designed for controlled L2 speaking practice research, not high-stakes speaking assessment.

Safeguards:

- Use participant codes rather than real names.
- Do not expose API keys to the frontend.
- Keep raw audio on the backend storage path.
- Record consent and withdrawal requests.
- Default research exports anonymize participant identifiers.
- Withdrawn participants are excluded from analysis-ready exports.
- Admin changes to locked study settings are written to `audit_log`.
- Human raters use blinded queues that hide condition group and participant names.

Automatic feedback should be worded cautiously. ASR or text matching alone may say a word may need attention; it must not claim exact phoneme substitution.
