# Thesis

Why this project exists, what it is betting on, and what would prove it wrong.

## 1. The gap is not where people assume

The obvious claim — "nobody has built speaker identification" — is false, and anyone in this field will say so immediately. Speaker ID is well served:

- **pyannoteAI** sells voiceprints and identification through their Precision-2 model, with an open MIT toolkit underneath.
- **Picovoice Eagle** does on-device, real-time, enrolled-speaker recognition.
- **Otter and Fireflies** label speakers in meetings every day.

So the project makes a narrower and checkable claim instead. Three of them.

### Claim A — the platforms are leaving, not arriving

- **September 2025** — Microsoft retired Azure AI Speaker Recognition outright.
- **May 2026** — AWS retired Amazon Connect Voice ID, citing performance under real call conditions and a 30-second uninterrupted enrollment nobody would sit through. They pointed customers at Pindrop and left.

Two of three hyperscalers exited the category inside eight months. What remains is a specialist on-device vendor and a French diarization lab. This is a market being vacated at the top, not crowded.

### Claim B — the consent layer is orphaned

**Limitless built the right thing.** Consent Mode detected an unfamiliar voice, chimed, and refused to record until that person verbally agreed. The exact ceremony ambient voice needs.

**December 2025** — Meta acquired Limitless, ended the Pendant, and withdrew the service from the EU, UK, Brazil, Israel, South Korea and Turkey. Every strict-consent jurisdiction, abandoned rather than served.

The same month, Fireflies was sued under Illinois BIPA over voiceprint collection — $1,000 per negligent violation, $5,000 per reckless one, no proof of harm required.

So the consent layer is not unbuilt. It is **orphaned**: the team that shipped it is gone, and the acquirer's answer to consent-strict jurisdictions was to leave them. That is a specific, dated, defensible gap.

### Claim C — nobody has put this where the assistants can reach it

Queried against the official MCP registry on 12 August 2026, searching `speaker` returns a keynote speaker's booking server and two smart-home speaker controllers. **Nothing for speaker identity, recognition, diarization or voiceprints.**

pyannoteAI ships a REST API. An assistant cannot pick up a REST API by itself. It can pick up an MCP server.

## 2. The technical bet

Here is where the project stops being packaging and starts being an argument.

### The threshold is the bug, not the model

The intuitive story is that speaker models fail on African voices because they can't tell those voices apart, so someone must train a better model. That story is **wrong**, and getting it wrong sends you to compete with Intron, Lelapa and Google over data you don't have.

What the fairness literature actually found, evaluating speaker verification across accent groups:

> Discrimination performance is reasonably robust across accent groups, while **calibration** performance degrades dramatically on accents that are not well represented in the training data.

Discrimination is *can it tell Sammy from Amara.* Calibration is *is 0.94 the right place to draw the line.* The first survives. The second does not.

And the failure is silent. A miscalibrated threshold does not raise an error — it returns a confident wrong name. For a system whose whole output is attribution, that is the worst available failure mode.

**Therefore:** a threshold is not a property of a model. It is a property of a model applied to a population. Shipping one global constant is the actual defect, and every product surveyed ships one.

This project treats the threshold as installation state: unset by default, flagged in every response until measured, and measured by a command that reports its own uncertainty and refuses to guess when genuine and impostor scores overlap.

### Code-switching splits a person in two

The DISPLACE challenge states it directly: current diarization systems are not equipped for multilingual conversation *where the same talker speaks in multiple code-mixed languages*. A person's embedding shifts with the language they are speaking, so the same human reads as two speakers.

Most of the world code-switches. A Ugandan meeting moves between English, Luganda and Swahili inside a single sentence. A clinician explains a diagnosis half in Swahili. This is ordinary speech, not an edge case.

The architecture that answers it is not a better model either. It is a schema change: **one person, several voiceprints, one per language mode**, matched against all of them, best profile wins. Modest to implement. Absent from every shipping product surveyed.

## 3. What this project deliberately is not

- **Not diarization.** "When did the speaker change" is harder than "who is this" and pyannote already solved it under MIT. Compose, don't reimplement.
- **Not a model.** Resemblyzer today, swappable tomorrow. If Intron's Sahara embeddings are better on African speech, this layer should sit on those instead. The layer is the product; the encoder is a dependency.
- **Not a cloud service.** Local-first is the trust story and the legal position at once. Biometric data on someone else's servers is exactly the exposure the 2025–26 lawsuits are about.
- **Not authentication.** No presentation-attack defence exists here. Attribution for comprehension, never attribution for authorisation. Azure and AWS just demonstrated what happens when you take voice authentication seriously and it still doesn't work.

## 4. What would prove this wrong

Stated in advance, so the project can actually be wrong:

1. **Calibration turns out not to matter.** If a real run on Ugandan English, Luganda and code-switched speech shows the default 0.94 was fine all along, Claim C collapses to packaging and the honest response is to say so in this file.
2. **Per-language profiles don't help.** If cross-language genuine pairs score about the same as same-language ones, the code-switching architecture is unnecessary complexity. The calibration report measures exactly this and prints both means.
3. **pyannoteAI or Picovoice ships an MCP server.** Then the distribution advantage is gone within a release cycle. Likely eventually; the window is now.
4. **The consent gate stays unenforceable.** Consent recorded locally by the person doing the recording proves what they wrote down, not what the other person agreed to. This is a real limitation, not a solved problem.

## 5. The honest state, today

Every threshold in this repository is a placeholder. The tests prove the logic and prove nothing about accuracy. No calibration run on real voices has happened yet.

That is written into the product rather than the footnotes — `calibration_status` reports it, and every identification carries the warning until someone does the work.

The next thing that matters is not code. It is five people, four clips each, two who sound similar, one over a phone speaker, at least two languages, in the room where this will actually be used.

---

### Sources

- Azure AI Speaker Recognition retirement — [Picovoice migration note](https://picovoice.ai/blog/microsoft-azure-ai-speaker-recognition-alternatives/)
- Amazon Connect Voice ID end of support — [AWS docs](https://docs.aws.amazon.com/connect/latest/adminguide/amazonconnect-voiceid-end-of-support.html), [Biometric Update](https://www.biometricupdate.com/202506/amazon-to-end-support-for-voice-biometrics-recommends-pindrop)
- Meta / Limitless — [Sacra](https://sacra.com/research/why-meta-bought-limitless/), [SF Standard](https://sfstandard.com/2025/12/14/big-tech-scooping-ai-wearable-startups-customers-spooked/)
- Bias in Automated Speaker Recognition — [Toussaint Hutiri & Ding, FAccT 2022](https://facctconference.org/static/pdfs_2022/facct22-3533089.pdf)
- Fairness of Speaker Verification on Underrepresented Accents — [arXiv:2204.12649](https://arxiv.org/html/2204.12649)
- DISPLACE Challenge — [arXiv:2303.00830](https://arxiv.org/pdf/2303.00830), [second edition](https://arxiv.org/pdf/2406.09494)
- pyannote.audio — [MIT licence](https://github.com/pyannote/pyannote-audio/blob/main/LICENSE), [pyannoteAI models](https://www.pyannote.ai/md/models)
- Official MCP Registry — [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io/)
