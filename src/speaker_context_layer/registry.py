"""Local, consented speaker attribution with per-language voiceprints.

Scope, stated once and enforced throughout: this module answers "who is most
likely speaking" for comprehension tasks such as labelling a transcript. It is
not authentication. It has no presentation-attack defence, so it must never
gate access, approve a payment, or stand in for a signature.

Two design choices distinguish this from the usual speaker-ID registry:

1. A person may hold several voiceprints, one per language they speak. Speaker
   embeddings shift when the same person switches language, which is why
   code-switched conversation defeats single-profile systems.

2. The match threshold is a per-installation, calibrated value rather than a
   constant. Published thresholds are calibrated against English-heavy corpora;
   applied to under-represented accents their calibration degrades and they
   produce confident false matches. Until `calibrate` has run, every result is
   flagged `calibrated: false`.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SCHEMA_VERSION = 2

# Starting points only. See THESIS.md — these are uncalibrated and the registry
# says so in every result until `calibrate` writes real values.
DEFAULT_MATCH_THRESHOLD = 0.94
DEFAULT_MARGIN = 0.03

# A sample must be this similar to an existing profile before it is folded in.
ADAPT_THRESHOLD = 0.97
# Floor on the weight a new sample carries, so adaptation never decays to zero
# and a voiceprint keeps tracking the person over months.
MIN_ADAPT_WEIGHT = 0.05

MIN_SPEECH_SECONDS = 2.0
SAMPLE_RATE = 16_000

# ISO 639-3 "undetermined". The honest default when no language is declared.
DEFAULT_LANGUAGE = "und"


class ConsentError(RuntimeError):
    """Raised when a voiceprint would be stored without a consent record."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(a, b) / denominator)


class ConsentRecord:
    """Evidence that a person agreed, kept beside their voiceprint.

    Asking for consent and being able to *demonstrate* consent are different
    obligations. A boolean argument satisfies the first and not the second, so
    this is persisted and travels with the profile.
    """

    def __init__(self, granted: bool, method: str, scope: str, granted_at: str | None = None, note: str = ""):
        if not granted:
            raise ConsentError("A consent record can only be created for granted consent.")
        if not method.strip():
            raise ConsentError("Record how consent was obtained, e.g. 'verbal, in person'.")
        self.granted = True
        self.method = method.strip()
        self.scope = scope.strip() or "speaker attribution only; not authentication"
        self.granted_at = granted_at or _utc_now()
        self.note = note.strip()

    def to_dict(self) -> dict:
        return {
            "granted": True,
            "method": self.method,
            "scope": self.scope,
            "granted_at": self.granted_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConsentRecord":
        return cls(
            granted=bool(data.get("granted")),
            method=data.get("method", ""),
            scope=data.get("scope", ""),
            granted_at=data.get("granted_at"),
            note=data.get("note", ""),
        )


class SpeakerRegistry:
    """Stores consented voiceprints and performs best-effort attribution."""

    def __init__(self, registry_path: str = "registry.json", encoder=None):
        self.registry_path = Path(registry_path)
        self._encoder = encoder
        self.speakers: dict[str, dict] = {}
        self.threshold = {
            "match": DEFAULT_MATCH_THRESHOLD,
            "margin": DEFAULT_MARGIN,
            "calibrated": False,
            "population": None,
            "calibrated_at": None,
        }
        self._load()

    # -- encoder ------------------------------------------------------------

    @property
    def encoder(self):
        """Load the embedding model lazily, so importing this module is cheap."""
        if self._encoder is None:
            from resemblyzer import VoiceEncoder

            self._encoder = VoiceEncoder()
        return self._encoder

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        if not self.registry_path.exists():
            return
        with self.registry_path.open(encoding="utf-8") as handle:
            data = json.load(handle)

        if data.get("version") != SCHEMA_VERSION:
            raise ValueError(
                f"{self.registry_path} uses schema version {data.get('version')!r}, "
                f"but this build expects {SCHEMA_VERSION}. Re-enroll rather than migrate: "
                "voiceprints are cheap to recreate and a bad migration is not."
            )

        self.threshold.update(data.get("threshold", {}))
        for name, person in data.get("speakers", {}).items():
            self.speakers[name] = {
                "consent": person["consent"],
                "profiles": {
                    language: {
                        "embedding": np.asarray(profile["embedding"], dtype=np.float32),
                        "samples": profile.get("samples", 1),
                        "updated_at": profile.get("updated_at"),
                    }
                    for language, profile in person.get("profiles", {}).items()
                },
            }

    def _save(self) -> None:
        """Write atomically. A crash mid-write must not destroy the registry."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SCHEMA_VERSION,
            "threshold": self.threshold,
            "speakers": {
                name: {
                    "consent": person["consent"],
                    "profiles": {
                        language: {
                            "embedding": profile["embedding"].tolist(),
                            "samples": profile["samples"],
                            "updated_at": profile["updated_at"],
                        }
                        for language, profile in person["profiles"].items()
                    },
                }
                for name, person in self.speakers.items()
            },
        }
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.registry_path.parent,
            prefix=".registry-", suffix=".tmp", delete=False,
        )
        try:
            with handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(handle.name, self.registry_path)
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise

    # -- validation ---------------------------------------------------------

    @staticmethod
    def _validate_name(name: str) -> str:
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("Speaker name must contain 1 to 80 characters.")
        return name

    @staticmethod
    def _validate_language(language: str | None) -> str:
        language = (language or DEFAULT_LANGUAGE).strip().lower()
        if not language or len(language) > 20:
            raise ValueError("Language tag must contain 1 to 20 characters, e.g. 'en', 'lg', 'sw-en'.")
        return language

    def _embedding_from_audio(self, audio_path: str) -> np.ndarray:
        from resemblyzer import preprocess_wav

        path = Path(audio_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")
        try:
            wav = preprocess_wav(path)
        except Exception as exc:
            raise ValueError(
                "Could not read speech from this file. Use a clear WAV, MP3, or FLAC recording."
            ) from exc
        if len(wav) < SAMPLE_RATE * MIN_SPEECH_SECONDS:
            raise ValueError(
                f"Too little speech in this recording. Provide at least {MIN_SPEECH_SECONDS:g} "
                "seconds of clear speech."
            )
        return self.encoder.embed_utterance(wav)

    # -- enrollment ---------------------------------------------------------

    def enroll(
        self,
        name: str,
        audio_path: str,
        consent: ConsentRecord | dict | None = None,
        language: str | None = None,
        merge: bool = False,
    ) -> dict:
        """Store a voiceprint for `name` speaking `language`.

        A person new to the registry requires a consent record; storing a
        voiceprint without one raises ConsentError. Existing profiles are never
        silently replaced — pass `merge=True` to fold the sample in.
        """
        name = self._validate_name(name)
        language = self._validate_language(language)
        person = self.speakers.get(name)

        if person is None:
            if consent is None:
                raise ConsentError(
                    f"No consent record for {name!r}. A voiceprint is biometric data; "
                    "record how and when they agreed before storing it."
                )
            record = consent if isinstance(consent, ConsentRecord) else ConsentRecord.from_dict(consent)
            person = {"consent": record.to_dict(), "profiles": {}}
            self.speakers[name] = person

        existing = person["profiles"].get(language)
        if existing is not None and not merge:
            return {
                "status": "already_enrolled",
                "name": name,
                "language": language,
                "samples": existing["samples"],
                "hint": "Pass merge=true to fold this sample into the existing voiceprint.",
            }

        embedding = self._embedding_from_audio(audio_path)

        if existing is None:
            person["profiles"][language] = {
                "embedding": embedding,
                "samples": 1,
                "updated_at": _utc_now(),
            }
            samples = 1
            status = "enrolled"
        else:
            samples = existing["samples"] + 1
            existing["embedding"] = self._blend(existing["embedding"], embedding, existing["samples"])
            existing["samples"] = samples
            existing["updated_at"] = _utc_now()
            status = "merged"

        self._save()
        return {
            "status": status,
            "name": name,
            "language": language,
            "samples": samples,
            "languages": sorted(person["profiles"]),
        }

    @staticmethod
    def _blend(stored: np.ndarray, fresh: np.ndarray, prior_samples: int) -> np.ndarray:
        """Running mean with a weight floor.

        A plain running mean gives sample 30 a weight of 1/31, so a voiceprint
        stops tracking the person it belongs to. The floor keeps it drifting.
        """
        weight = max(1.0 / (prior_samples + 1), MIN_ADAPT_WEIGHT)
        blended = (1.0 - weight) * stored + weight * fresh
        return blended.astype(np.float32)

    def forget(self, name: str, language: str | None = None) -> dict:
        """Delete one language profile, or the whole person when language is None."""
        name = self._validate_name(name)
        if name not in self.speakers:
            return {"status": "not_found", "name": name}
        if language is None:
            del self.speakers[name]
            self._save()
            return {"status": "forgotten", "name": name, "scope": "all languages and consent record"}
        language = self._validate_language(language)
        if language not in self.speakers[name]["profiles"]:
            return {"status": "not_found", "name": name, "language": language}
        del self.speakers[name]["profiles"][language]
        if not self.speakers[name]["profiles"]:
            del self.speakers[name]
            self._save()
            return {"status": "forgotten", "name": name, "scope": "last profile removed, person deleted"}
        self._save()
        return {"status": "forgotten", "name": name, "language": language}

    def rename(self, old_name: str, new_name: str) -> dict:
        old_name = self._validate_name(old_name)
        new_name = self._validate_name(new_name)
        if old_name not in self.speakers:
            return {"status": "error", "reason": f"{old_name} not found"}
        if new_name in self.speakers and new_name != old_name:
            return {
                "status": "error",
                "reason": f"{new_name} already exists; renaming would destroy their voiceprint",
            }
        self.speakers[new_name] = self.speakers.pop(old_name)
        self._save()
        return {"status": "renamed", "from": old_name, "to": new_name}

    # -- matching -----------------------------------------------------------

    def identify(self, audio_path: str, adapt: bool = True) -> dict:
        return self._match(self._embedding_from_audio(audio_path), adapt=adapt)

    def _match(self, embedding: np.ndarray, adapt: bool = True) -> dict:
        calibration = {
            "calibrated": bool(self.threshold.get("calibrated")),
            "population": self.threshold.get("population"),
        }
        if not calibration["calibrated"]:
            calibration["warning"] = (
                "Thresholds are uncalibrated defaults tuned on English-heavy corpora. "
                "Treat every score as provisional until `scl-calibrate` has run on this population."
            )

        if not self.speakers:
            return {
                "speaker": "NEW_SPEAKER",
                "confidence": 0.0,
                "reason": "nobody is enrolled yet",
                "calibration": calibration,
            }

        # Each person scores as their best-matching language profile.
        per_person: dict[str, tuple[float, str]] = {}
        for name, person in self.speakers.items():
            best = max(
                ((_cosine(embedding, p["embedding"]), language) for language, p in person["profiles"].items()),
                default=(0.0, DEFAULT_LANGUAGE),
            )
            per_person[name] = best

        ranked = sorted(per_person.items(), key=lambda item: item[1][0], reverse=True)
        best_name, (best_score, best_language) = ranked[0]
        all_scores = {
            name: {"score": round(score, 3), "language": language}
            for name, (score, language) in per_person.items()
        }

        threshold = self.threshold.get("match") or DEFAULT_MATCH_THRESHOLD
        margin = self.threshold.get("margin") or DEFAULT_MARGIN

        if best_score < threshold:
            return {
                "speaker": "NEW_SPEAKER",
                "confidence": round(best_score, 3),
                "closest_known": best_name,
                "all_scores": all_scores,
                "calibration": calibration,
            }

        if len(ranked) > 1 and best_score - ranked[1][1][0] < margin:
            return {
                "speaker": "AMBIGUOUS",
                "confidence": round(best_score, 3),
                "candidates": [best_name, ranked[1][0]],
                "all_scores": all_scores,
                "calibration": calibration,
                "instruction": "Do not attribute this line to anyone.",
            }

        if adapt and best_score >= ADAPT_THRESHOLD:
            profile = self.speakers[best_name]["profiles"][best_language]
            profile["embedding"] = self._blend(profile["embedding"], embedding, profile["samples"])
            profile["samples"] += 1
            profile["updated_at"] = _utc_now()
            self._save()

        return {
            "speaker": best_name,
            "language": best_language,
            "confidence": round(best_score, 3),
            "all_scores": all_scores,
            "calibration": calibration,
        }

    # -- introspection ------------------------------------------------------

    def roster(self) -> list[dict]:
        return [
            {
                "name": name,
                "languages": sorted(person["profiles"]),
                "samples": {language: p["samples"] for language, p in person["profiles"].items()},
                "consent": person["consent"],
            }
            for name, person in sorted(self.speakers.items())
        ]

    def set_threshold(self, match: float, margin: float, population: str) -> dict:
        if not 0.0 < match < 1.0:
            raise ValueError("match threshold must be between 0 and 1.")
        if not 0.0 <= margin < 1.0:
            raise ValueError("margin must be between 0 and 1.")
        self.threshold = {
            "match": round(float(match), 4),
            "margin": round(float(margin), 4),
            "calibrated": True,
            "population": population.strip() or "unnamed population",
            "calibrated_at": _utc_now(),
        }
        self._save()
        return dict(self.threshold)


def label_transcript_line(registry: SpeakerRegistry, audio_path: str, text: str) -> str:
    """Render one attributed transcript line, refusing to guess when unsure."""
    result = registry.identify(audio_path)
    speaker = result["speaker"]
    if speaker == "AMBIGUOUS":
        return f"[UNVERIFIED, possibly {result['candidates'][0]}]: {text}"
    if speaker == "NEW_SPEAKER":
        return f"[UNKNOWN SPEAKER]: {text}"
    return f"[{speaker}]: {text}"
