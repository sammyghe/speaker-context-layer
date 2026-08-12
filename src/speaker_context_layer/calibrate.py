"""Calibrate the match threshold against the voices you will actually hear.

Why this exists
---------------
Published speaker-verification thresholds are calibrated against English-heavy
corpora. The fairness literature finds that discrimination (can the model tell
two people apart) stays reasonably robust across accent groups, while
*calibration* degrades sharply on accents that are under-represented in
training. A threshold is therefore not a property of the model — it is a
property of the model applied to a population.

That failure is dangerous rather than obvious: a miscalibrated threshold does
not throw an error, it returns a confident wrong name.

So this command measures two numbers on your own consented recordings:

    worst genuine   the lowest score between two clips of the same person
    best impostor   the highest score between clips of two different people

If the worst genuine sits above the best impostor, the population is separable
and a threshold exists. If they overlap, no single threshold works and the
honest answer is to say so rather than to pick one.

Usage
-----
    scl-calibrate ./clips --population "Kampala team, mixed EN/LG" --apply

Clips are named:  <person>__<language>__<take>.wav

    sammy__en__1.wav   sammy__lg__1.wav   amara__en__1.wav   amara__ig__1.wav
    wei__en__1.wav     wei__zh__1.wav     yuki__ja__1.wav    thabo__en__1.wav

Every clip must be of a person who consented to being recorded and enrolled.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from .registry import DEFAULT_MARGIN, SpeakerRegistry, _cosine

AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}


def parse_clip_name(path: Path) -> tuple[str, str, str] | None:
    """Split `<person>__<language>__<take>` out of a filename."""
    parts = path.stem.split("__")
    if len(parts) < 2:
        return None
    person = parts[0].strip()
    language = parts[1].strip().lower()
    take = parts[2].strip() if len(parts) > 2 else "1"
    if not person or not language:
        return None
    return person, language, take


def collect_clips(directory: Path) -> list[tuple[str, str, str, Path]]:
    clips = []
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        parsed = parse_clip_name(path)
        if parsed is None:
            print(f"  skipping {path.name} — expected <person>__<language>__<take>", file=sys.stderr)
            continue
        clips.append((*parsed, path))
    return clips


def embed_clips(registry: SpeakerRegistry, clips) -> list[tuple[str, str, Path, np.ndarray]]:
    embedded = []
    for person, language, _take, path in clips:
        try:
            embedded.append((person, language, path, registry._embedding_from_audio(str(path))))
        except Exception as exc:
            print(f"  skipping {path.name} — {exc}", file=sys.stderr)
    return embedded


def score_pairs(embedded) -> tuple[list[dict], list[dict]]:
    """Return (genuine, impostor) pairwise comparisons."""
    genuine, impostor = [], []
    for (p1, l1, f1, e1), (p2, l2, f2, e2) in itertools.combinations(embedded, 2):
        entry = {
            "score": round(_cosine(e1, e2), 4),
            "a": f"{p1}/{l1}/{f1.name}",
            "b": f"{p2}/{l2}/{f2.name}",
            "cross_language": l1 != l2,
        }
        (genuine if p1 == p2 else impostor).append(entry)
    return genuine, impostor


def equal_error_threshold(genuine: list[dict], impostor: list[dict]) -> tuple[float, float]:
    """Sweep for the threshold where false-accept and false-reject rates meet."""
    candidates = sorted({entry["score"] for entry in genuine + impostor})
    best_threshold, best_gap, best_rate = candidates[0], float("inf"), 1.0
    for threshold in candidates:
        false_reject = sum(1 for e in genuine if e["score"] < threshold) / max(len(genuine), 1)
        false_accept = sum(1 for e in impostor if e["score"] >= threshold) / max(len(impostor), 1)
        gap = abs(false_reject - false_accept)
        if gap < best_gap:
            best_threshold, best_gap, best_rate = threshold, gap, (false_reject + false_accept) / 2
    return best_threshold, best_rate


def analyse(genuine: list[dict], impostor: list[dict]) -> dict:
    if not genuine:
        raise SystemExit(
            "No genuine pairs. Each person needs at least two clips — otherwise there is "
            "nothing to measure a threshold against."
        )
    if not impostor:
        raise SystemExit(
            "No impostor pairs. Calibration needs at least two different people, and it is "
            "most useful when two of them sound similar."
        )

    worst_genuine = min(genuine, key=lambda e: e["score"])
    best_impostor = max(impostor, key=lambda e: e["score"])
    separation = round(worst_genuine["score"] - best_impostor["score"], 4)

    cross = [e for e in genuine if e["cross_language"]]
    same = [e for e in genuine if not e["cross_language"]]

    report = {
        "pairs": {"genuine": len(genuine), "impostor": len(impostor)},
        "worst_genuine": worst_genuine,
        "best_impostor": best_impostor,
        "separation": separation,
        "separable": separation > 0,
        "code_switching": {
            "same_language_mean": round(float(np.mean([e["score"] for e in same])), 4) if same else None,
            "cross_language_mean": round(float(np.mean([e["score"] for e in cross])), 4) if cross else None,
            "cross_language_pairs": len(cross),
        },
    }

    if separation > 0:
        midpoint = (worst_genuine["score"] + best_impostor["score"]) / 2
        report["recommended"] = {
            "match": round(midpoint, 4),
            "margin": round(max(separation / 2, DEFAULT_MARGIN), 4),
            "basis": "midpoint of a clean separation between genuine and impostor scores",
        }
    else:
        threshold, error_rate = equal_error_threshold(genuine, impostor)
        report["recommended"] = {
            "match": round(threshold, 4),
            "margin": DEFAULT_MARGIN,
            "basis": "equal-error point — genuine and impostor scores OVERLAP",
            "expected_error_rate": round(error_rate, 4),
            "warning": (
                "No threshold separates these voices cleanly. At best this setting is wrong "
                f"about {error_rate:.1%} of the time. Record longer or cleaner clips, or treat "
                "attribution in this population as advisory only."
            ),
        }
    return report


def render(report: dict) -> str:
    lines = [
        "",
        "  CALIBRATION REPORT",
        "  " + "-" * 58,
        f"  genuine pairs        {report['pairs']['genuine']}",
        f"  impostor pairs       {report['pairs']['impostor']}",
        "",
        f"  worst genuine        {report['worst_genuine']['score']:.4f}",
        f"    {report['worst_genuine']['a']}",
        f"    {report['worst_genuine']['b']}",
        f"  best impostor        {report['best_impostor']['score']:.4f}",
        f"    {report['best_impostor']['a']}",
        f"    {report['best_impostor']['b']}",
        "",
        f"  separation           {report['separation']:+.4f}"
        f"   {'separable' if report['separable'] else 'OVERLAPPING'}",
    ]
    cs = report["code_switching"]
    if cs["cross_language_pairs"]:
        lines += [
            "",
            f"  same-language mean   {cs['same_language_mean']:.4f}",
            f"  cross-language mean  {cs['cross_language_mean']:.4f}"
            f"   ({cs['cross_language_pairs']} pairs)",
            "  a large drop here is the code-switching effect — enroll per language",
        ]
    rec = report["recommended"]
    lines += [
        "",
        f"  recommended match    {rec['match']:.4f}",
        f"  recommended margin   {rec['margin']:.4f}",
        f"  basis                {rec['basis']}",
    ]
    if "warning" in rec:
        lines += ["", "  WARNING", f"  {rec['warning']}"]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scl-calibrate",
        description="Measure a match threshold against your own consented recordings.",
    )
    parser.add_argument("clips", type=Path, help="directory of <person>__<language>__<take> clips")
    parser.add_argument("--population", default="", help="what these voices represent, e.g. 'Kampala team, EN/LG'")
    parser.add_argument("--registry", type=Path, default=None, help="registry to read and optionally update")
    parser.add_argument("--apply", action="store_true", help="write the recommended threshold into the registry")
    parser.add_argument("--json", type=Path, default=None, help="also write the full report here")
    args = parser.parse_args(argv)

    if not args.clips.is_dir():
        parser.error(f"{args.clips} is not a directory")
    if args.apply and not args.population.strip():
        parser.error("--apply requires --population, so the stored threshold records who it was measured on")

    registry_path = args.registry or (Path.home() / ".speaker-context-layer" / "registry.json")
    registry = SpeakerRegistry(str(registry_path))

    print(f"  reading clips from {args.clips}")
    clips = collect_clips(args.clips)
    if not clips:
        parser.error("no usable clips found; expected names like sammy__en__1.wav")

    people = defaultdict(set)
    for person, language, _take, _path in clips:
        people[person].add(language)
    print(f"  {len(clips)} clips, {len(people)} people: " + ", ".join(f"{p} ({'/'.join(sorted(l))})" for p, l in sorted(people.items())))
    print("  embedding — first run downloads the model, please wait")

    embedded = embed_clips(registry, clips)
    if len(embedded) < 2:
        parser.error("fewer than two clips could be embedded")

    report = analyse(*score_pairs(embedded))
    report["population"] = args.population or None
    print(render(report))

    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  full report written to {args.json}")

    if args.apply:
        rec = report["recommended"]
        applied = registry.set_threshold(rec["match"], rec["margin"], args.population)
        print(f"  applied to {registry_path}")
        print(f"  match={applied['match']} margin={applied['margin']} population={applied['population']!r}")
    else:
        print("  nothing written — re-run with --apply to store this threshold")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
