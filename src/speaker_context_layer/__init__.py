"""Speaker Context Layer — local, consented speaker attribution for AI assistants.

Attribution for comprehension, never attribution for authorisation.
"""

from .registry import (
    ConsentError,
    ConsentRecord,
    SpeakerRegistry,
    label_transcript_line,
)

__version__ = "0.1.0"
__all__ = [
    "ConsentError",
    "ConsentRecord",
    "SpeakerRegistry",
    "label_transcript_line",
    "__version__",
]
