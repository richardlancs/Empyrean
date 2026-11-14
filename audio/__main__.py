"""Run the audio manager alone on the real speaker with scripted messages.

Run:  python -m audio

Touches and retouches announce automatically, including eligible late names.
The independent scripted answer is interrupted by a stairs alarm. No bus,
camera or network is needed. Uses the system's selected audio output.
"""

from __future__ import annotations

import logging
import time

from audio.audio import AudioManager
from audio.backends import Pyttsx3Speaker, load_alarm
from contracts import HazardEvent, NameResult, SpeakRequest, TouchEvent

log = logging.getLogger("audio")
BOTTLE_BOX = (120.0, 75.0, 220.0, 300.0)
CUP_BOX = (320.0, 155.0, 425.0, 292.0)


def touch(
    object_id: int, label: str, name: str, box: tuple[float, ...], kind: str
) -> TouchEvent:
    """Build a TouchEvent for the script."""
    return TouchEvent(time.time(), object_id, label, name, kind, box, [])  # type: ignore[arg-type]


def main() -> int:
    """Play the scripted sequence and return 0."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    manager = AudioManager(Pyttsx3Speaker, load_alarm())
    try:
        steps: list[tuple[str, object, float]] = [
            (
                "Touch a named object",
                touch(1, "bottle", "Heinz ketchup", BOTTLE_BOX, "touch"),
                2.0,
            ),
            (
                "Release (not spoken)",
                touch(1, "bottle", "", BOTTLE_BOX, "release"),
                0.5,
            ),
            ("Touch before naming", touch(2, "cup", "", CUP_BOX, "touch"), 0.4),
            (
                "Name arrives late",
                NameResult(time.time(), 2, "Starbucks coffee cup", True),
                2.5,
            ),
            ("Release", touch(2, "cup", "", CUP_BOX, "release"), 0.3),
            ("Retouch", touch(1, "bottle", "Heinz ketchup", BOTTLE_BOX, "touch"), 2.0),
            (
                "Spoken answer",
                SpeakRequest(
                    time.time(),
                    "Heinz ketchup, 4 minutes ago, next to mug and cereal box.",
                    "normal",
                    "storage",
                ),
                1.2,
            ),
            (
                "Hazard cuts it off",
                HazardEvent(time.time(), "stairs_down", "grok", 0.9),
                3.0,
            ),
            (
                "Touch after the alarm",
                touch(2, "cup", "Starbucks coffee cup", CUP_BOX, "touch"),
                2.5,
            ),
        ]
        handlers = {
            TouchEvent: manager.on_touch,
            NameResult: manager.on_name,
            SpeakRequest: manager.on_speak,
            HazardEvent: manager.on_hazard,
        }
        for label, message, pause in steps:
            log.info("--> %s", label)
            handlers[type(message)](message)
            time.sleep(pause)
    finally:
        manager.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
