"""Microphone capture helpers.

Capture is deliberately bounded: a fixed duration, requested explicitly, with
no always-on path anywhere in this package. Continuous ambient capture is a
different product with a different consent model.
"""

from __future__ import annotations

import time
from pathlib import Path

SAMPLE_RATE = 16_000
MIN_RECORDING_SECONDS = 3.0
MAX_RECORDING_SECONDS = 60.0


def list_input_devices() -> list[dict]:
    """Return microphones that can be selected by the capture tools."""
    import sounddevice as sd

    return [
        {
            "index": index,
            "name": device["name"],
            "default_sample_rate": device["default_samplerate"],
        }
        for index, device in enumerate(sd.query_devices())
        if device["max_input_channels"] > 0
    ]


def record_mic(
    duration_seconds: float = 10.0,
    output_path: str | None = None,
    sample_rate: int = SAMPLE_RATE,
    device: int | None = None,
) -> str:
    """Capture a mono WAV from the selected (or default) microphone."""
    import sounddevice as sd
    from scipy.io import wavfile

    if not MIN_RECORDING_SECONDS <= duration_seconds <= MAX_RECORDING_SECONDS:
        raise ValueError(
            f"duration_seconds must be between {MIN_RECORDING_SECONDS:g} and {MAX_RECORDING_SECONDS:g}."
        )

    if output_path is None:
        target = Path.home() / ".speaker-context-layer" / "tmp"
        target.mkdir(parents=True, exist_ok=True)
        output_path = str(target / f"capture_{int(time.time())}.wav")
    else:
        Path(output_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    try:
        recording = sd.rec(
            int(duration_seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device,
        )
        sd.wait()
    except Exception as exc:
        raise RuntimeError(
            "Could not record from the microphone. Check the operating system's microphone "
            "permission, then use list_microphones to select a working input device."
        ) from exc

    wavfile.write(output_path, sample_rate, recording)
    return str(Path(output_path).resolve())
