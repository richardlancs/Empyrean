"""Fake audio: the real audio manager's rules, printed instead of played.

Used by `python -m app --fake audio`. It subscribes to the same messages as
audio/ (HazardEvent, TouchEvent, NameResult, SpeakRequest) and prints what would
be heard, with timing, so teammates can check touch-to-speech and alarm order on
a machine with no speaker, pyttsx3 or pygame. audio/ publishes nothing, so this
fake publishes nothing either.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from audio.audio import AudioManager
from contracts import HazardEvent, NameResult, SpeakRequest, TouchEvent

SECONDS_PER_CHAR = 0.06  # roughly pyttsx3's default rate of 200 words a minute
ALARM_SECONDS = 0.61  # length of audio/sounds/alarm.wav


class PrintSpeaker:
    """Prints each phrase and takes about as long as speaking it would."""

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Print text, then wait its spoken length unless cut off."""
        print(f"[fake audio] say: {text}", flush=True)
        end = time.monotonic() + SECONDS_PER_CHAR * len(text)
        while time.monotonic() < end:
            if should_stop():
                print(f"[fake audio] cut off: {text}", flush=True)
                return
            time.sleep(0.01)


class PrintAlarm:
    """Prints the beeps instead of playing them."""

    duration = ALARM_SECONDS

    def play(self) -> None:
        """Print the alarm."""
        print("[fake audio] BEEP BEEP BEEP", flush=True)

    def close(self) -> None:
        """Nothing to release."""


def register(bus: Any) -> AudioManager:
    """Subscribe a printing audio manager to the bus and return it for shutdown."""
    manager = AudioManager(PrintSpeaker, PrintAlarm())
    bus.subscribe(HazardEvent, manager.on_hazard)
    bus.subscribe(TouchEvent, manager.on_touch)
    bus.subscribe(NameResult, manager.on_name)
    bus.subscribe(SpeakRequest, manager.on_speak)
    return manager
