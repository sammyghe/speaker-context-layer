# Speaker Context Layer

**AI knows who logged in. It has no idea who is in the room.**

A local MCP server that gives any AI assistant a persistent, consented answer to *who is speaking* — with two things nobody else ships: a voiceprint per language, and a match threshold you calibrate on your own voices.

Voiceprints never leave your machine. There is no account, no cloud, no hosted registry.

```
[Sammy]: We push the follow-up to Thursday.
[Ema]: I'll own the documentation pack.
[UNVERIFIED, possibly Sammy]: And we approve the extra spend.
[UNKNOWN SPEAKER]: I don't agree with that.
```

Misattributing a decision is worse than admitting you don't know. So the layer has three answers, not two, and it says which one it is.

---

## Scope, stated once

**Attribution for comprehension. Never attribution for authorisation.**

Use it to label a transcript, to let an assistant follow a conversation between several people, or to caption a meeting for someone who can't hear it. Do not use it to unlock anything, approve a payment, gate access, or stand in for a signature. It has no defence against a recording or a cloned voice, and a 0.96 similarity score is not a signature.

---

## Why this exists

Fireflies, Otter and every meeting assistant resolve identity by reading the **calendar invite and the login**. On Zoom and Google Meet they show real names; everywhere else they fall back to `Speaker 1`. That works, and it means:

> Identity is already solved wherever there is a login. It is unsolved wherever there is only a microphone in a room.

This project lives in the second place — several people and several assistants in one physical room, no login between them.

## The two things that are actually different

### 1. One person, several voiceprints — one per language

Speaker embeddings shift when the same person switches language. The DISPLACE benchmark documents the consequence: diarization systems are *"not equipped to deal with multilingual conversations, where the same talker speaks in multiple code-mixed languages."* The same human reads as two speakers.

Most of the world code-switches. So a person here holds a profile per language, and matches against all of them:

```
Sammy    en                      0.961
Sammy    lg                      0.948
Sammy    mixed                   0.939
Ema      en                      0.907
```

```python
enroll_speaker(name="Sammy", audio_path="a.wav", language="en",  consent_confirmed=True, consent_method="verbal, in person")
enroll_speaker(name="Sammy", audio_path="b.wav", language="lg",  consent_confirmed=True, consent_method="verbal, in person")
```

### 2. The threshold is calibrated, not inherited

Published thresholds are tuned on English-heavy corpora. The fairness research is specific about what happens next: **discrimination stays reasonably robust across accent groups, while calibration degrades sharply on accents under-represented in training.**

The model can still tell two people apart. What breaks is the *number* — and it breaks in the dangerous direction, returning a confident wrong name rather than an error.

So the shipped threshold is marked uncalibrated, and every result says so:

```json
"calibration": {
  "calibrated": false,
  "warning": "Thresholds are uncalibrated defaults tuned on English-heavy corpora.
              Treat every score as provisional until `scl-calibrate` has run."
}
```

Fix it with your own voices:

```bash
scl-calibrate ./clips --population "Kampala team, mixed EN/LG" --apply
```

It reports the gap between your worst genuine match and your best impostor, and **refuses to invent a threshold when the two overlap** — reporting the expected error rate instead.

---

## Install

```bash
pip install -e .
```

Live-room extras (optional, experimental):

```bash
pip install -e ".[live]"
```

The first identification downloads the Resemblyzer model (~17 MB). Tests never do.

## Connect it to an assistant

Full setup for Claude Code, Claude Desktop, ChatGPT and Gemini: **[docs/mcp-clients.md](docs/mcp-clients.md)**

Claude Code, in one line:

```bash
claude mcp add speaker-context-layer -- speaker-context-layer
```

Then say:

> Ask everyone in the room for permission. Then use `record_and_enroll` to save my voice as Sammy in English — I consent, verbally, right now.

## Tools

| Tool | What it does |
| --- | --- |
| `list_microphones` | Available inputs and their index |
| `enroll_speaker` | Store a voiceprint from a file, per language |
| `record_and_enroll` | Record a consenting person, store the print, delete the clip |
| `identify_speaker` | Attribute a clip, or return `NEW_SPEAKER` / `AMBIGUOUS` |
| `record_and_identify` | Record, identify, delete the clip |
| `list_known_speakers` | Roster, languages, consent records, threshold |
| `forget_speaker` | Erase one language or the whole person |
| `calibration_status` | Whether the threshold has been tested on this population |

Every writing tool refuses without `consent_confirmed=true` **and** a `consent_method` describing how the person agreed. Being able to demonstrate consent is a separate obligation from having asked.

## Verify

```bash
python -m pytest tests -q
```

22 tests, about a second, no model download — they test the logic, not the model's accuracy. **Nothing in this repository establishes accuracy on real voices.** That is what calibration is for.

## Command line

```bash
speaker-context-layer          # run the MCP server (stdio)
scl-calibrate ./clips --population "..." --apply
scl-room enroll Sammy          # experimental live room
scl-room room
```

## Where your data lives

```
~/.speaker-context-layer/registry.json
```

Voiceprints, consent records and your calibrated threshold. Treat it as biometric data: it is `.gitignore`d here, and it should stay off shared storage. `forget_speaker` deletes.

## Composes with

Diarization ("when did the speaker change") is a harder problem than identification and this project does not attempt it. Pair it with [pyannote.audio](https://github.com/pyannote/pyannote-audio) (MIT) or WhisperX for long recordings. [Picovoice Eagle](https://picovoice.ai/products/voice/speaker-recognition/) does the real-time on-device recognition in the live room.

## Roadmap

- [ ] A calibration run on real Ugandan English, Luganda and Swahili-English code-switching
- [ ] Published calibration profiles per population, so others start from a real number
- [ ] Evaluate [Intron Sahara](https://www.intron.io/) as an African-language embedding backend
- [ ] Consent ceremony on first contact — chime, ask, wait, then enroll

## Licence

MIT. See [LICENSE](LICENSE).
