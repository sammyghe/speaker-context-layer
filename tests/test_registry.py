"""Behavioural tests for the registry.

A stub encoder stands in for the real model, so these run in milliseconds and
test the logic rather than the ML. Nothing here downloads weights.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from speaker_context_layer.live_room import choose_identity  # noqa: E402
from speaker_context_layer.registry import (  # noqa: E402
    ConsentError,
    ConsentRecord,
    SpeakerRegistry,
    label_transcript_line,
)


CONSENT = {"granted": True, "method": "verbal, in person", "scope": "attribution only"}


def make_registry(tmp_path) -> SpeakerRegistry:
    return SpeakerRegistry(str(tmp_path / "registry.json"), encoder=object())


def put(registry, name, language, vector, samples=1):
    person = registry.speakers.setdefault(name, {"consent": dict(CONSENT), "profiles": {}})
    person["profiles"][language] = {
        "embedding": np.asarray(vector, dtype=np.float32),
        "samples": samples,
        "updated_at": "2026-08-12T00:00:00+00:00",
    }


# -- consent ----------------------------------------------------------------

def test_storing_a_voiceprint_without_consent_is_refused(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(ConsentError):
        registry.enroll("Sammy", "unused.wav", consent=None)
    assert registry.speakers == {}


def test_consent_record_rejects_a_missing_method():
    with pytest.raises(ConsentError):
        ConsentRecord(granted=True, method="   ", scope="attribution")


def test_consent_record_cannot_represent_refusal():
    with pytest.raises(ConsentError):
        ConsentRecord(granted=False, method="verbal", scope="attribution")


def test_consent_is_persisted_beside_the_voiceprint(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Sammy", "en", [1.0, 0.0])
    registry._save()

    saved = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert saved["speakers"]["Sammy"]["consent"]["method"] == "verbal, in person"


# -- per-language profiles --------------------------------------------------

def test_a_person_scores_as_their_best_language_profile(tmp_path):
    registry = make_registry(tmp_path)
    registry.set_threshold(0.90, 0.03, "test")
    put(registry, "Sammy", "en", [1.0, 0.0])
    put(registry, "Sammy", "lg", [0.0, 1.0])

    # A Luganda utterance matches nothing in the English profile at all.
    result = registry._match(np.array([0.0, 1.0], dtype=np.float32), adapt=False)
    assert result["speaker"] == "Sammy"
    assert result["language"] == "lg"


def test_without_the_second_language_the_same_person_reads_as_unknown(tmp_path):
    registry = make_registry(tmp_path)
    registry.set_threshold(0.90, 0.03, "test")
    put(registry, "Sammy", "en", [1.0, 0.0])

    result = registry._match(np.array([0.0, 1.0], dtype=np.float32), adapt=False)
    assert result["speaker"] == "NEW_SPEAKER"


def test_forgetting_one_language_keeps_the_others(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Sammy", "en", [1.0, 0.0])
    put(registry, "Sammy", "lg", [0.0, 1.0])

    assert registry.forget("Sammy", language="en")["status"] == "forgotten"
    assert sorted(registry.speakers["Sammy"]["profiles"]) == ["lg"]


def test_forgetting_the_last_language_removes_the_person(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Sammy", "en", [1.0, 0.0])

    registry.forget("Sammy", language="en")
    assert "Sammy" not in registry.speakers


# -- matching refuses to guess ----------------------------------------------

def test_two_close_speakers_are_reported_as_ambiguous(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "A", "en", [1.0, 0.0])
    put(registry, "B", "en", [0.9998, 0.02])

    result = registry._match(np.array([1.0, 0.0], dtype=np.float32), adapt=False)
    assert result["speaker"] == "AMBIGUOUS"
    assert result["candidates"] == ["A", "B"]
    assert "Do not attribute" in result["instruction"]


def test_first_ever_contact_reports_zero_confidence_not_certainty(tmp_path):
    result = make_registry(tmp_path)._match(np.array([1.0, 0.0], dtype=np.float32), adapt=False)
    assert result["speaker"] == "NEW_SPEAKER"
    assert result["confidence"] == 0.0


def test_uncalibrated_results_carry_a_warning(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Sammy", "en", [1.0, 0.0])

    result = registry._match(np.array([1.0, 0.0], dtype=np.float32), adapt=False)
    assert result["calibration"]["calibrated"] is False
    assert "uncalibrated" in result["calibration"]["warning"]


def test_calibrating_clears_the_warning_and_records_the_population(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Sammy", "en", [1.0, 0.0])
    registry.set_threshold(0.88, 0.04, "Kampala team, EN/LG")

    result = registry._match(np.array([1.0, 0.0], dtype=np.float32), adapt=False)
    assert result["calibration"]["calibrated"] is True
    assert result["calibration"]["population"] == "Kampala team, EN/LG"
    assert "warning" not in result["calibration"]


# -- destructive operations -------------------------------------------------

def test_rename_never_destroys_an_existing_person(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Voice_001", "en", [1.0, 0.0])
    put(registry, "Sammy", "en", [0.0, 1.0])

    assert registry.rename("Voice_001", "Sammy")["status"] == "error"
    assert "Voice_001" in registry.speakers
    assert registry.speakers["Sammy"]["profiles"]["en"]["embedding"].tolist() == [0.0, 1.0]


def test_enrolling_an_existing_profile_does_not_silently_overwrite(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Sammy", "en", [1.0, 0.0])

    result = registry.enroll("Sammy", "unused.wav", language="en")
    assert result["status"] == "already_enrolled"
    assert registry.speakers["Sammy"]["profiles"]["en"]["embedding"].tolist() == [1.0, 0.0]


# -- adaptation -------------------------------------------------------------

def test_adaptation_keeps_a_meaningful_weight_after_many_samples(tmp_path):
    registry = make_registry(tmp_path)
    stored = np.array([1.0, 0.0], dtype=np.float32)
    blended = registry._blend(stored, np.array([0.0, 1.0], dtype=np.float32), prior_samples=500)

    # A plain running mean would give this sample a weight of 1/501 and the
    # voiceprint would stop tracking the person. The floor keeps it drifting.
    assert blended[1] >= 0.05


def test_a_confident_match_folds_the_new_sample_in(tmp_path):
    registry = make_registry(tmp_path)
    registry.set_threshold(0.90, 0.03, "test")
    put(registry, "Sammy", "en", [1.0, 0.0])

    registry._match(np.array([1.0, 0.0], dtype=np.float32), adapt=True)
    assert registry.speakers["Sammy"]["profiles"]["en"]["samples"] == 2


# -- persistence ------------------------------------------------------------

def test_the_registry_survives_a_save_and_reload(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Sammy", "en", [1.0, 0.0], samples=3)
    registry.set_threshold(0.91, 0.05, "Kampala team")

    reloaded = SpeakerRegistry(str(tmp_path / "registry.json"), encoder=object())
    assert reloaded.speakers["Sammy"]["profiles"]["en"]["samples"] == 3
    assert reloaded.threshold["match"] == 0.91
    assert reloaded.threshold["population"] == "Kampala team"


def test_a_failed_save_leaves_no_temporary_files_behind(tmp_path):
    registry = make_registry(tmp_path)
    put(registry, "Sammy", "en", [1.0, 0.0])
    registry._save()

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".registry-")]
    assert leftovers == []


def test_an_unknown_schema_version_refuses_to_load(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"version": 99, "speakers": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="schema version"):
        SpeakerRegistry(str(path), encoder=object())


# -- transcript rendering ---------------------------------------------------

def test_ambiguous_lines_are_not_attributed(tmp_path, monkeypatch):
    registry = make_registry(tmp_path)
    monkeypatch.setattr(
        registry, "identify",
        lambda *_a, **_k: {"speaker": "AMBIGUOUS", "candidates": ["Sammy", "Ema"]},
    )
    assert label_transcript_line(registry, "x.wav", "We approve the spend.") == (
        "[UNVERIFIED, possibly Sammy]: We approve the spend."
    )


# -- live room --------------------------------------------------------------

def test_live_room_does_not_force_a_weak_match():
    assert choose_identity(["Sammy", "Martha"], [0.22, 0.19])["speaker"] == "UNKNOWN"


def test_live_room_reports_close_scores_as_ambiguous():
    result = choose_identity(["Sammy", "Martha"], [0.72, 0.70])
    assert result["speaker"] == "AMBIGUOUS"
    assert result["candidates"] == ["Sammy", "Martha"]
