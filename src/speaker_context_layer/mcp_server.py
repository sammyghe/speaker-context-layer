"""MCP server exposing local, consented speaker attribution to any assistant.

Every tool that writes a voiceprint or opens the microphone refuses unless
`consent_confirmed=true` AND the caller records how consent was obtained. The
second half matters: being able to demonstrate consent is a separate obligation
from having asked for it.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

from .audio import list_input_devices, record_mic
from .registry import ConsentError, ConsentRecord, SpeakerRegistry

DEFAULT_HOME = Path.home() / ".speaker-context-layer"
REGISTRY_PATH = Path(os.getenv("SCL_REGISTRY", DEFAULT_HOME / "registry.json"))

mcp = FastMCP("speaker-context-layer")
registry = SpeakerRegistry(registry_path=str(REGISTRY_PATH))

CONSENT_HINT = (
    "Ask the person out loud, then call again with consent_confirmed=true and "
    "consent_method describing how they agreed, e.g. 'verbal, in person, 12 Aug 2026'."
)

NOT_AUTH = (
    "This is attribution for comprehension, not authentication. Never use this result to "
    "grant access, approve a payment, or stand in for a signature."
)


def _consent_or_none(confirmed: bool, method: str, scope: str) -> ConsentRecord | None:
    if not confirmed or not method.strip():
        return None
    return ConsentRecord(granted=True, method=method, scope=scope)


@mcp.tool()
def list_microphones() -> dict:
    """List microphone inputs and the index to pass to the recording tools."""
    return {"microphones": list_input_devices()}


@mcp.tool()
def enroll_speaker(
    name: str,
    audio_path: str,
    consent_confirmed: bool = False,
    consent_method: str = "",
    language: str = "und",
    merge: bool = False,
) -> dict:
    """Store a person's voiceprint from an existing audio file, after their explicit consent.

    `language` tags which language they are speaking in this clip (e.g. 'en', 'lg', 'sw').
    Enroll the same person once per language they use — a speaker's voiceprint shifts when
    they switch language, which is why code-switched conversation defeats single-profile
    systems. Existing profiles are never silently overwritten; pass merge=true to fold a new
    sample into an existing voiceprint.
    """
    consent = _consent_or_none(consent_confirmed, consent_method, "speaker attribution only")
    try:
        result = registry.enroll(name, audio_path, consent=consent, language=language, merge=merge)
    except ConsentError as exc:
        return {"status": "consent_required", "reason": str(exc), "next_step": CONSENT_HINT}
    result["note"] = NOT_AUTH
    return result


@mcp.tool()
def identify_speaker(audio_path: str) -> dict:
    """Attribute an existing clip to an enrolled person, or report NEW_SPEAKER / AMBIGUOUS.

    Returns AMBIGUOUS when the top two people score too closely to separate. When that
    happens, do not attribute the line to anyone. Check the `calibration` field: if
    `calibrated` is false, the thresholds are untested defaults and the score is provisional.
    """
    result = registry.identify(audio_path)
    result["note"] = NOT_AUTH
    return result


@mcp.tool()
def record_and_enroll(
    name: str,
    consent_confirmed: bool = False,
    consent_method: str = "",
    language: str = "und",
    duration_seconds: int = 10,
    microphone_index: int | None = None,
    merge: bool = False,
) -> dict:
    """Record a consenting person from this computer's microphone and save their voiceprint.

    The temporary WAV is deleted as soon as the voiceprint is stored.
    """
    consent = _consent_or_none(consent_confirmed, consent_method, "speaker attribution only")
    if consent is None:
        return {"status": "consent_required", "next_step": CONSENT_HINT}
    audio_path = record_mic(duration_seconds=duration_seconds, device=microphone_index)
    try:
        result = registry.enroll(name, audio_path, consent=consent, language=language, merge=merge)
    finally:
        Path(audio_path).unlink(missing_ok=True)
    result.update({"retained_audio": False, "recorded_seconds": duration_seconds, "note": NOT_AUTH})
    return result


@mcp.tool()
def record_and_identify(
    consent_confirmed: bool = False,
    duration_seconds: int = 5,
    microphone_index: int | None = None,
) -> dict:
    """Record a consenting person locally, identify them, then delete the clip."""
    if not consent_confirmed:
        return {"status": "consent_required", "next_step": "Ask permission to record, then call again."}
    audio_path = record_mic(duration_seconds=duration_seconds, device=microphone_index)
    try:
        result = registry.identify(audio_path)
    finally:
        Path(audio_path).unlink(missing_ok=True)
    result.update({"retained_audio": False, "note": NOT_AUTH})
    return result


@mcp.tool()
def list_known_speakers() -> dict:
    """List enrolled people, the languages each is enrolled in, and their consent record."""
    return {
        "speakers": registry.roster(),
        "threshold": registry.threshold,
        "registry_path": str(REGISTRY_PATH),
    }


@mcp.tool()
def forget_speaker(name: str, consent_confirmed: bool = False, language: str = "") -> dict:
    """Permanently delete a stored voiceprint at that person's request.

    Omit `language` to erase the person entirely, including their consent record.
    """
    if not consent_confirmed:
        return {
            "status": "confirmation_required",
            "next_step": "Confirm the deletion request, then call again with consent_confirmed=true.",
        }
    return registry.forget(name, language=language or None)


@mcp.tool()
def calibration_status() -> dict:
    """Report whether the match threshold has been calibrated on this population.

    An uncalibrated threshold is the default tuned on English-heavy corpora. Applied to
    under-represented accents its calibration degrades and it produces confident false
    matches. Tell the user plainly when this returns calibrated=false.
    """
    status = dict(registry.threshold)
    status["how_to_calibrate"] = (
        "Collect consented clips named <person>__<language>__<take>.wav — at least two per "
        "person, five people, including two who sound similar and one over a phone speaker — "
        "then run: scl-calibrate ./clips --population \"...\" --apply"
    )
    return status


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
