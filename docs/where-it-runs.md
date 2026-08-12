# Where this actually runs

Short version: **it works today in Claude Code, Claude Desktop and Gemini CLI. It does not work in ChatGPT voice mode, and that is a platform limitation nobody can code around.**

This page exists because the answer is not obvious and the obvious guess is wrong.

## The status table

| Where | Works? | Why |
| --- | --- | --- |
| **Claude Code** | Yes | Local stdio MCP. `claude mcp add` and you're done. |
| **Claude Desktop** | Yes | Local stdio MCP via `claude_desktop_config.json`. |
| **Gemini CLI** | Yes | Local stdio MCP via `settings.json`. |
| **Claude mobile / voice** | Not yet | Mobile supports *remote* MCP servers only, added from claude.ai first. This server is local. |
| **ChatGPT text** | Partly, badly | Custom MCP connectors need Developer Mode, and connectors are largely restricted to `search` and `fetch` tools. `identify_speaker` is neither. |
| **ChatGPT voice mode** | **No** | MCP tools are not available at all while a voice conversation is running. |
| **Anthropic Connector Directory** | Not submitted | Requires a public HTTPS server, OAuth with PKCE, a privacy policy, and a Team/Enterprise org to submit. See below. |

## Why voice mode is the hard one

The intuition is that voice mode is the *most* natural home for a speaker-identity tool. It is currently the least available one.

In ChatGPT, MCP tools are simply switched off during a voice conversation. There is no configuration that changes this, and no amount of work on this repository affects it.

There is a deeper reason to expect this to stay awkward even when it opens up: **an MCP tool call carries text, not audio.** By the time the model decides to call a tool, the microphone audio has already been transcribed and discarded. A tool cannot reach back for the waveform it would need in order to tell you who spoke.

So speaker identity cannot be *computed inside* a voice conversation via MCP. It has to be computed alongside it, by something that holds the microphone.

## Which is what `scl-room` is

That constraint is the whole reason [`live_room.py`](../src/speaker_context_layer/live_room.py) exists and takes a different shape from the MCP server:

```
microphone ──┬──> Eagle (on-device)  ──> "Amara is speaking"  ──┐
             │                                                  ├──> the model
             └──> raw audio stream ─────────────────────────────┘
```

A local process owns the microphone, recognises the speaker itself, and pushes short identity events into the model's context *next to* the audio. The model never calls a tool to ask who is talking — it is simply told.

Two architectures, two jobs:

- **MCP server** — files, transcripts, desktop assistants, anything turn-based.
- **`scl-room`** — live conversation, where audio is streaming and tools are unavailable.

`scl-room` is experimental and needs a Picovoice key. But it is the architecturally correct answer for voice, not a workaround.

## Getting into the Claude Connector Directory

The directory you see inside Claude is curated. A local server never appears there, no matter how good it is. To submit one, it must be:

- Reachable at a **public HTTPS endpoint** with streamable HTTP or SSE transport
- Validating the `Origin` header and rejecting requests that aren't from Claude
- Authenticating with **OAuth 2.0 + PKCE (S256)** — plain OAuth does not pass review
- Backed by a privacy policy, documentation, a support channel, and production hosting
- Submitted from a **Team or Enterprise** organisation

None of that is unreasonable, and all of it points the same direction: a hosted service.

## The honest tension

Hosting this remotely would mean voiceprints on a server. That is precisely the exposure the 2025–26 biometric lawsuits are about, and "your voice never leaves your machine" is the reason to choose this project over a cloud API.

So the directory listing is not a to-do item. It is a decision with a real cost, and it should be made deliberately rather than drifted into.

One shape that might resolve it, unbuilt and unproven: a remote server that holds **no biometric data at all** — enrollment and matching stay on the user's machine, and the hosted endpoint only carries the *result* ("Amara, 0.94") for assistants that cannot run a local process. Whether that is worth building depends on whether anyone actually wants it, which is not yet known.

## Recommended path today

1. `scl-demo` — see it work with your own voice in two minutes.
2. `claude mcp add speaker-context-layer -- speaker-context-layer` — use it in Claude Code and Desktop.
3. `scl-calibrate` — make the numbers mean something for your voices.
4. `scl-room` — if you want the live, multi-person, in-the-room version.

Ignore the directory until step 3 has produced a real calibration number. A listing for something whose accuracy is unmeasured is a liability, not a milestone.
