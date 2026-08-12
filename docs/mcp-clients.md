# Connecting Speaker Context Layer to an assistant

The server speaks MCP over stdio. Anything that can launch a local process and speak MCP can use it.

First, install and note the executable path:

```bash
pip install -e .
```

```bash
# macOS / Linux
which speaker-context-layer
```

```powershell
# Windows
(Get-Command speaker-context-layer).Source
```

Everything below uses `speaker-context-layer` as the command. If it is not on your `PATH`, substitute the absolute path that command printed.

---

## Claude Code

One line:

```bash
claude mcp add speaker-context-layer -- speaker-context-layer
```

Confirm it registered:

```bash
claude mcp list
```

---

## Claude Desktop

Edit `claude_desktop_config.json`:

- **macOS** — `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows** — `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "speaker-context-layer": {
      "command": "speaker-context-layer"
    }
  }
}
```

Restart Claude Desktop. If the command is not on `PATH`, use the absolute path — on Windows, escape backslashes (`C:\\Users\\you\\...\\speaker-context-layer.exe`).

---

## Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "speaker-context-layer": {
      "command": "speaker-context-layer"
    }
  }
}
```

The experimental live room in `scl-room` talks to Gemini Live directly rather than through MCP, because it needs a continuous audio stream rather than discrete tool calls. See the README.

---

## ChatGPT

ChatGPT connectors expect a **remote** MCP server over HTTP, not a local stdio process, and they run on OpenAI's servers rather than your machine.

That is in direct tension with the point of this project: voiceprints stay local, and the microphone is on your computer, not in a datacentre. Exposing this server to the public internet would mean shipping biometric data off the machine that owns it.

If you want it in ChatGPT anyway, that is your call to make deliberately:

1. Run the server behind an HTTP transport on a host you control.
2. Put authentication in front of it. Anything less publishes a biometric registry.
3. Add it as a custom connector in ChatGPT settings.

There is no supported recipe here, on purpose. Use Claude Code, Claude Desktop, or Gemini CLI for the local-first path.

---

## First run

Ask the assistant, out loud, in the room:

> Everyone here has agreed to be recorded. Use `record_and_enroll` to save my voice as Sammy in English — I consent, verbally, right now.

The assistant should call:

```
record_and_enroll(
  name="Sammy",
  language="en",
  consent_confirmed=true,
  consent_method="verbal, in person, 12 Aug 2026"
)
```

Both halves are required. `consent_confirmed` alone is refused — the method is what makes consent demonstrable later.

Enroll each person once per language they speak. This is the part that makes code-switching work — the same person in two languages needs two profiles:

```
record_and_enroll(name="Sammy", language="lg", consent_confirmed=true, consent_method="verbal, in person")
record_and_enroll(name="Amara", language="en", consent_confirmed=true, consent_method="verbal, in person")
record_and_enroll(name="Amara", language="ig", consent_confirmed=true, consent_method="verbal, in person")
record_and_enroll(name="Wei",   language="zh", consent_confirmed=true, consent_method="verbal, in person")
record_and_enroll(name="Yuki",  language="ja", consent_confirmed=true, consent_method="verbal, in person")
```

`list_known_speakers` then shows who is enrolled in what:

```
Sammy   en, lg
Amara   en, ig
Wei     zh
Yuki    ja
```

Then check where you stand:

```
calibration_status()
```

It will report `calibrated: false` until you run `scl-calibrate`. Until then every identification is provisional, and the server says so in each response rather than leaving you to remember.

---

## Troubleshooting

**`consent_required` even though I said yes** — `consent_method` is missing or empty. Both are required.

**`already_enrolled`** — that person already has a profile in that language. Pass `merge=true` to fold the new sample in, or use a different `language` tag.

**No microphone found** — call `list_microphones` and pass the `index` as `microphone_index`. On Windows, check microphone permission in Settings → Privacy → Microphone.

**First identification takes a while** — Resemblyzer downloads its model (~17 MB) on first use, once.

**Everyone matches everyone** — the threshold is uncalibrated and probably too permissive for your voices. This is the expected failure. Run `scl-calibrate`.
