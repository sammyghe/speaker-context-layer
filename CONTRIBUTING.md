# Contributing

## The one rule

**Never commit a voiceprint, a consent record, or an audio clip of a real person.**

Before every commit:

```bash
git status
```

No `.wav`, no `registry.json`, no `.eagle`. The `.gitignore` covers these, but check anyway — this is the failure that cannot be undone by a follow-up commit.

## Setup

```bash
pip install -e ".[dev]"
python -m pytest tests -q
```

22 tests, about a second, no model download. Tests use a stub encoder so they exercise the logic rather than the ML.

## What is especially welcome

**Calibration results.** The most valuable contribution is not code. Run `scl-calibrate` on a real population, then open an issue with the report — worst genuine, best impostor, separation, and the same-vs-cross-language means. Never attach the clips or the registry; the numbers are the contribution.

Populations that would move this project furthest:

- Ugandan, Kenyan, Tanzanian English
- Luganda, Swahili, Acholi, and English/Luganda code-switching
- Nigerian English and Yoruba/English mixing
- Any tonal language
- Cheap phone microphones and speakerphones, which is what real rooms use

**Alternative encoders.** Resemblyzer is a default, not a commitment. If an African-language embedding model separates these voices better, the layer should sit on it. The encoder is injected — `SpeakerRegistry(path, encoder=...)`.

## What will be declined

- **Authentication features.** Verification for access control, payment approval, or anything that treats a similarity score as a signature. This is out of scope permanently, not for now.
- **A hosted registry or cloud sync.** Local-first is the trust story and the legal position at once.
- **Accuracy claims without a calibration run.** A benchmark table from someone else's corpus is exactly what this project argues against.
- **Silent-overwrite conveniences.** Enroll refuses to replace an existing profile without `merge=true`, and rename refuses to clobber. That friction is deliberate.
- **A diarization implementation.** Compose with pyannote.audio.

## Style

Match the surrounding code. Type hints on public functions, docstrings that explain *why* rather than restating the signature, and no comment that a clearer name would replace.

New behaviour needs a test. If it changes what the system claims about a person, it needs a test that proves it declines to guess.
