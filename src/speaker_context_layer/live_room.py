"""Experimental: an in-person room shared by several people and an AI.

The demo this project exists for. Several humans and an assistant in one
physical room, with no login between them — Picovoice Eagle recognises enrolled
speakers on-device, Gemini Live carries the conversation, and small identity
events are pushed into the model's context so it knows who just spoke.

Experimental means experimental. It is not authentication, not covert
monitoring, and not a claim that every noisy or overlapping room labels
correctly. Everyone present must consent, and the Eagle profile directory is
biometric data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from array import array
from pathlib import Path
from typing import Iterable

HOME = Path(os.getenv("SCL_HOME", Path.home() / ".speaker-context-layer"))
PROFILE_DIR = HOME / "eagle_profiles"
PROFILE_INDEX = PROFILE_DIR / "profiles.json"

UNKNOWN_FLOOR = 0.35
AMBIGUOUS_MARGIN = 0.05
STABLE_FRAMES = 3

SYSTEM_INSTRUCTION = (
    "You are a participant in an in-person conversation between several people. "
    "Identity events from the local speaker layer are factual context about who is "
    "speaking. Attribute statements only to the person named in an identity event. "
    "Never invent a name. If an event says UNKNOWN or AMBIGUOUS, say you are not sure "
    "who spoke rather than guessing. Never disclose voiceprints or the roster. "
    "Wait until the group asks you something."
)


def _require_eagle():
    try:
        import pveagle
        from pvrecorder import PvRecorder
    except ImportError as exc:
        raise RuntimeError(
            "Install the live-room extras first:  pip install 'speaker-context-layer[live]'"
        ) from exc
    return pveagle, PvRecorder


def _load_index() -> dict[str, dict]:
    if not PROFILE_INDEX.exists():
        return {}
    return json.loads(PROFILE_INDEX.read_text(encoding="utf-8"))


def _save_index(index: dict[str, dict]) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_INDEX.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _safe_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Name must contain 1 to 80 characters.")
    return name


def choose_identity(names: list[str], scores: Iterable[float] | None, margin: float = AMBIGUOUS_MARGIN) -> dict:
    """Pick a speaker, or decline to. Declining is a valid answer."""
    scores = list(scores or [])
    if not scores or not names:
        return {"speaker": "UNKNOWN", "confidence": 0.0}
    ranked = sorted(zip(names, scores), key=lambda pair: pair[1], reverse=True)
    best_name, best_score = ranked[0]
    if best_score < UNKNOWN_FLOOR:
        return {"speaker": "UNKNOWN", "confidence": round(float(best_score), 3)}
    if len(ranked) > 1 and best_score - ranked[1][1] < margin:
        return {
            "speaker": "AMBIGUOUS",
            "confidence": round(float(best_score), 3),
            "candidates": [ranked[0][0], ranked[1][0]],
        }
    return {"speaker": best_name, "confidence": round(float(best_score), 3)}


class EagleProfiles:
    """Enroll and recognise people on-device with Picovoice Eagle."""

    def __init__(self, access_key: str | None = None):
        self.access_key = access_key or os.getenv("PICOVOICE_ACCESS_KEY")
        if not self.access_key:
            raise RuntimeError("Set PICOVOICE_ACCESS_KEY before using the live room.")
        self.pveagle, self.PvRecorder = _require_eagle()

    def names(self) -> list[str]:
        return sorted(_load_index())

    def enroll_from_microphone(self, name: str, device_index: int = -1) -> dict:
        name = _safe_name(name)
        profiler = self.pveagle.create_profiler(self.access_key)
        recorder = self.PvRecorder(frame_length=profiler.min_enroll_samples, device_index=device_index)
        try:
            recorder.start()
            percentage = 0.0
            print(f"Speak naturally, {name}. Everyone present must have consented.")
            while percentage < 100.0:
                percentage, _feedback = profiler.enroll(recorder.read())
                print(f"\r  enrollment {percentage:5.1f}%", end="", flush=True)
            profile = profiler.export()
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            (PROFILE_DIR / f"{name}.eagle").write_bytes(profile.to_bytes())
            index = _load_index()
            index[name] = {"profile": f"{name}.eagle", "created_at": time.time()}
            _save_index(index)
            print()
            return {"status": "enrolled", "name": name, "percentage": percentage}
        finally:
            recorder.stop()
            recorder.delete()
            profiler.delete()

    def load_profiles(self):
        index = _load_index()
        names, profiles = [], []
        for name in sorted(index):
            path = PROFILE_DIR / index[name]["profile"]
            if path.is_file():
                names.append(name)
                profiles.append(self.pveagle.EagleProfile.from_bytes(path.read_bytes()))
        return names, profiles

    def recognizer(self, profiles):
        return self.pveagle.create_recognizer(self.access_key, profiles)


async def run_room(model: str, device_index: int = -1) -> None:
    """Run the shared room until Ctrl+C."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY before starting the room.")

    profiles = EagleProfiles()
    names, speaker_profiles = profiles.load_profiles()
    if not names:
        raise RuntimeError("Enroll at least one person first:  scl-room enroll NAME")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    config = {
        "response_modalities": ["AUDIO"],
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "system_instruction": SYSTEM_INSTRUCTION,
    }

    eagle = profiles.recognizer(speaker_profiles)
    recorder = profiles.PvRecorder(frame_length=eagle.frame_length, device_index=device_index)
    previous, stable, stable_count = None, None, 0

    async def receive(session):
        output = None
        try:
            import sounddevice as sd

            output = sd.RawOutputStream(samplerate=24000, channels=1, dtype="int16")
            output.start()
        except Exception:
            print("  (no audio playback available — showing transcription only)")
        try:
            async for response in session.receive():
                content = response.server_content
                if not content:
                    continue
                if content.input_transcription:
                    print(f"\n  [room] {content.input_transcription.text}", flush=True)
                if content.output_transcription:
                    print(f"\n  [AI]   {content.output_transcription.text}", flush=True)
                if content.model_turn and output:
                    for part in content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            output.write(part.inline_data.data)
        finally:
            if output:
                output.stop()
                output.close()

    print(f"  room active — participants: {', '.join(names)}")
    print("  everyone present must have consented. Ctrl+C to stop.")
    recorder.start()
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            asyncio.create_task(receive(session))
            while True:
                frame = await asyncio.to_thread(recorder.read)
                await session.send_realtime_input(
                    audio=types.Blob(data=array("h", frame).tobytes(), mime_type="audio/pcm;rate=16000")
                )
                identity = choose_identity(names, eagle.process(frame))
                speaker = identity["speaker"]
                if speaker == stable:
                    stable_count += 1
                else:
                    stable, stable_count = speaker, 1
                if stable_count >= STABLE_FRAMES and speaker != previous:
                    previous = speaker
                    await session.send_realtime_input(
                        text=(
                            f"[IDENTITY EVENT] {speaker} is speaking. "
                            f"Confidence {identity['confidence']}. Do not guess beyond this event."
                        )
                    )
                    print(f"\n  [{speaker}]", flush=True)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n  room stopped.")
    finally:
        recorder.stop()
        recorder.delete()
        eagle.delete()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scl-room", description="Experimental in-person shared AI room.")
    sub = parser.add_subparsers(dest="command", required=True)

    enroll = sub.add_parser("enroll", help="enroll a consenting person with Eagle")
    enroll.add_argument("name")
    enroll.add_argument("--device", type=int, default=-1)

    room = sub.add_parser("room", help="start the shared room")
    room.add_argument("--model", default=os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001"))
    room.add_argument("--device", type=int, default=-1)

    args = parser.parse_args(argv)
    if args.command == "enroll":
        print(EagleProfiles().enroll_from_microphone(args.name, args.device))
    else:
        asyncio.run(run_room(args.model, args.device))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
