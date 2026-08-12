# Speaker Context Layer

**AI knows who logged in. It has no idea who is in the room.**

A local MCP server that tells any AI assistant *who is speaking*. Voiceprints never leave your machine — no account, no cloud.

```
[Sammy]: We push the follow-up to Thursday.
[Ema]: I'll own the documentation pack.
[UNKNOWN SPEAKER]: I don't agree with that.
```

---

## Try it in two minutes

```bash
pip install git+https://github.com/sammyghe/speaker-context-layer.git
scl-demo
```

It asks for a name, records 8 seconds, repeats for each person — then guesses who is speaking. Nothing is kept: `scl-demo --reset` deletes it.

## Use it in an assistant

**Claude Code**

```bash
claude mcp add speaker-context-layer -- speaker-context-layer
```

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{ "mcpServers": { "speaker-context-layer": { "command": "speaker-context-layer" } } }
```

Then say:

> Use `record_and_enroll` to save my voice as Sammy in English — I consent, verbally, right now.

Gemini CLI, troubleshooting, and why ChatGPT is a bad fit: **[docs/mcp-clients.md](docs/mcp-clients.md)**

---

## What it does that others don't

**One person, several voiceprints — one per language.** A voice embedding shifts when you switch language, so a code-switching speaker reads as two different people. Enroll each person once per language they use:

```
enroll_speaker(name="Sammy", language="en", ...)
enroll_speaker(name="Sammy", language="lg", ...)
```

**It refuses to guess.** Three answers, not two: a name, `NEW_SPEAKER`, or `AMBIGUOUS` when two people score too closely. Misattributing a decision is worse than admitting you don't know.

**The threshold is yours, not inherited.** Everyone else ships one number tuned on English-heavy data. On other accents that number is wrong — and it fails silently, returning a confident wrong name. So it ships unset, every answer is marked `calibrated: false`, and you fix it with your own voices:

```bash
scl-calibrate ./clips --population "Kampala team, EN/LG" --apply
```

It reports the gap between your worst genuine match and your best impostor — and refuses to invent a threshold when the two overlap.

The reasoning, the evidence, and what would prove it wrong: **[THESIS.md](THESIS.md)**

---

## Not authentication

Use it to label a transcript, follow a conversation, or caption a meeting. **Never** to unlock anything, approve a payment, gate access, or stand in for a signature. It cannot detect a recording or a cloned voice. A 0.96 score is not a signature.

## Tools

| Tool | |
| --- | --- |
| `record_and_enroll` | Record a consenting person, store the print, delete the clip |
| `record_and_identify` | Record, identify, delete the clip |
| `enroll_speaker` | Store a voiceprint from a file |
| `identify_speaker` | Attribute a clip, or return `NEW_SPEAKER` / `AMBIGUOUS` |
| `list_known_speakers` | Roster, languages, consent records |
| `forget_speaker` | Erase one language or the whole person |
| `list_microphones` | Available inputs |
| `calibration_status` | Whether the threshold has been tested on your voices |

Writing tools refuse without `consent_confirmed=true` **and** a `consent_method` describing how the person agreed.

## Your data

```
~/.speaker-context-layer/registry.json
```

Voiceprints, consent records, your threshold. Treat it as biometric data — it is gitignored, and CI fails the build if audio or a registry is ever committed. See [SECURITY.md](SECURITY.md).

## Honest status

v0.1.0. The logic is tested (22 tests, ~0.5s). **Accuracy on real voices is not established** — no calibration run has happened yet. That is the next real step, and the software tells you so on every answer instead of hiding it.

## Composes with

[pyannote.audio](https://github.com/pyannote/pyannote-audio) (MIT) for diarization on long recordings — this project does not attempt it. [Picovoice Eagle](https://picovoice.ai/products/voice/speaker-recognition/) drives the experimental live room (`scl-room`).

## Roadmap

- [ ] Calibration on real Ugandan English, Luganda, and Swahili-English code-switching
- [ ] Published calibration profiles per population, so others start from a real number
- [ ] Evaluate [Intron Sahara](https://www.intron.io/) as an African-language embedding backend
- [ ] Consent ceremony on first contact — chime, ask, wait, then enroll

## Credits

Built by [Sammy Gedamu](https://github.com/sammyghe) with [Claude Code](https://claude.com/claude-code) as engineering coworker — architecture, research, and implementation paired throughout.

MIT — see [LICENSE](LICENSE).
