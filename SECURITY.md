# Security & data handling

## Reporting a vulnerability

Open a [security advisory](https://github.com/sammyghe/speaker-context-layer/security/advisories/new) rather than a public issue. Please allow a reasonable window before disclosure.

## What this project stores

`~/.speaker-context-layer/registry.json` holds:

- **Voiceprints** — numeric embeddings, one per person per language
- **Consent records** — how and when each person agreed
- **Your calibrated threshold** and the population it was measured on

**A voiceprint is biometric data.** In the EU it is special-category data under GDPR Article 9; in Illinois it falls under BIPA, which carries statutory damages per violation with no requirement to prove harm. Several 2025–26 lawsuits concern exactly this kind of file.

Treat the registry as you would a password store:

- It is `.gitignore`d here. Keep it that way — verify with `git status` before every commit.
- Do not sync it to shared drives, backups you don't control, or issue attachments.
- `forget_speaker(name, consent_confirmed=true)` deletes it. Honour those requests.

Raw audio is **not** retained. `record_and_enroll` and `record_and_identify` delete their temporary WAV as soon as the embedding is computed. `record_audio_clip` does not exist in this version, deliberately.

## What this project is not

**Not authentication.** There is no presentation-attack detection: a recording, a cloned voice, or a good impersonation will not be caught. Never use a result here to grant access, approve a payment, unlock a device, or stand in for a signature.

Both Microsoft and Amazon retired their voice-authentication services in 2025–26 after sustained investment. Treat any voice-as-identity security claim with corresponding suspicion — including one you might be tempted to build on top of this.

**Not calibrated out of the box.** The shipped threshold is a placeholder tuned on English-heavy corpora. Applied to under-represented accents its calibration degrades and it returns *confident wrong names* rather than errors. Every response carries `calibration.calibrated: false` until you run `scl-calibrate` on your own population. Do not suppress that field.

## Consent — a limitation, honestly

The consent record proves what the person operating the software wrote down. It does not, by itself, prove what the other person agreed to. It is an audit trail, not a signature.

Recording law varies: some jurisdictions require all parties to consent. That obligation is yours, and this file does not discharge it.

## Dependencies

The embedding model is downloaded from the network on first use. Run in a controlled environment if that matters to you. The live-room extras additionally require a Picovoice access key and send room audio to Google's Gemini Live API — read that path carefully before using it with anyone else in the room.
