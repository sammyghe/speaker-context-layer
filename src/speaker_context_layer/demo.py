"""`scl-demo` — try the whole thing with your own voice in about two minutes.

Enroll a few people from this computer's microphone, then let it guess who is
speaking. Uses a throwaway registry by default so it cannot touch your real one.
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from .audio import list_input_devices, record_mic
from .registry import ConsentRecord, SpeakerRegistry

RULE = "-" * 60


def _ask(prompt: str, default: str = "") -> str:
    try:
        answer = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\n  cancelled.")
    return answer or default


def _pick_microphone() -> int | None:
    devices = list_input_devices()
    if not devices:
        raise SystemExit("  No microphone found. Check your operating system's microphone permission.")
    print("\n  Microphones:")
    for device in devices:
        print(f"    [{device['index']}] {device['name'][:56]}")
    choice = _ask("\n  Which one? (Enter for system default) ")
    if not choice:
        return None
    if not choice.isdigit() or int(choice) not in {d["index"] for d in devices}:
        raise SystemExit(f"  {choice!r} is not one of the listed indexes.")
    return int(choice)


def _record(seconds: int, device: int | None, who: str) -> str:
    input(f"  Press Enter, then {who} speaks for {seconds} seconds... ")
    print("  recording... ", end="", flush=True)
    path = record_mic(duration_seconds=seconds, device=device)
    print("done.")
    return path


def enroll_everyone(registry: SpeakerRegistry, device: int | None, seconds: int) -> None:
    print(f"\n{RULE}\n  STEP 1 — enroll\n{RULE}")
    print("  Everyone here must agree to this. Their voiceprint is stored on")
    print("  this machine only, and `scl-demo --reset` deletes it.\n")

    while True:
        name = _ask("  Name (Enter when everyone is enrolled): ")
        if not name:
            break

        language = _ask(f"  Which language will {name} speak? [en] ", "en")
        agreed = _ask(f"  Has {name} agreed to be recorded? [y/N] ").lower()
        if agreed not in {"y", "yes"}:
            print(f"  Skipping {name}.\n")
            continue

        consent = ConsentRecord(
            granted=True,
            method=f"verbal, in person, confirmed at the scl-demo prompt",
            scope="speaker attribution only; not authentication",
        )
        path = _record(seconds, device, name)
        try:
            result = registry.enroll(name, path, consent=consent, language=language, merge=True)
        finally:
            Path(path).unlink(missing_ok=True)
        print(f"  -> {result['status']} {result['name']} ({result['language']}), "
              f"{result['samples']} sample(s)\n")

        if len(registry.speakers[name]["profiles"]) == 1:
            print(f"  Tip: enroll {name} again in another language to handle code-switching.\n")


def identify_loop(registry: SpeakerRegistry, device: int | None, seconds: int) -> None:
    print(f"\n{RULE}\n  STEP 2 — who is speaking?\n{RULE}")
    print("  Anyone speaks. Ctrl+C to stop.\n")

    while True:
        try:
            path = _record(seconds, device, "someone")
        except (EOFError, KeyboardInterrupt):
            print("\n  done.")
            return
        try:
            result = registry.identify(path)
        finally:
            Path(path).unlink(missing_ok=True)

        speaker = result["speaker"]
        if speaker == "AMBIGUOUS":
            print(f"  -> TOO CLOSE TO CALL between {' and '.join(result['candidates'])} "
                  f"({result['confidence']})")
            print("     Refusing to guess is the correct answer here.")
        elif speaker == "NEW_SPEAKER":
            print(f"  -> NOBODY I KNOW (closest {result.get('closest_known', '?')} "
                  f"at {result['confidence']})")
        else:
            print(f"  -> {speaker.upper()}, speaking {result.get('language', '?')} "
                  f"({result['confidence']})")

        scores = result.get("all_scores", {})
        if scores:
            print("     " + "   ".join(f"{n} {s['score']}" for n, s in scores.items()))
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scl-demo", description="Try Speaker Context Layer with your own voice.")
    parser.add_argument("--keep", action="store_true",
                        help="use your real registry instead of a throwaway one")
    parser.add_argument("--reset", action="store_true", help="delete the demo registry and exit")
    parser.add_argument("--enroll-seconds", type=int, default=8)
    parser.add_argument("--identify-seconds", type=int, default=5)
    args = parser.parse_args(argv)

    demo_home = Path(tempfile.gettempdir()) / "scl-demo"
    if args.reset:
        shutil.rmtree(demo_home, ignore_errors=True)
        print(f"  Deleted {demo_home}")
        return 0

    if args.keep:
        registry_path = Path.home() / ".speaker-context-layer" / "registry.json"
    else:
        demo_home.mkdir(parents=True, exist_ok=True)
        registry_path = demo_home / "registry.json"

    print(f"\n  SPEAKER CONTEXT LAYER — demo")
    print(f"  registry: {registry_path}")
    if not args.keep:
        print("  (throwaway — your real registry is untouched)")

    registry = SpeakerRegistry(str(registry_path))
    device = _pick_microphone()

    if registry.speakers:
        print(f"\n  Already enrolled: {', '.join(sorted(registry.speakers))}")
        if _ask("  Enroll more people? [y/N] ").lower() in {"y", "yes"}:
            enroll_everyone(registry, device, args.enroll_seconds)
    else:
        enroll_everyone(registry, device, args.enroll_seconds)

    if not registry.speakers:
        print("\n  Nobody enrolled, so there is nothing to identify.")
        return 1

    identify_loop(registry, device, args.identify_seconds)

    print(f"\n{RULE}")
    if not registry.threshold.get("calibrated"):
        print("  Note: the threshold is still an untested default. If it confused two")
        print("  people, or called a stranger by name, that is the expected failure —")
        print("  it has never been measured on voices like yours. Fix it with:")
        print("    scl-calibrate ./clips --population \"...\" --apply")
    print(f"  Delete everything from this demo:  scl-demo --reset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
