"""Fake audio: the real audio manager's rules, printed instead of played.

Used by `python -m app --fake audio`. It subscribes to the same messages as
audio/ (HazardEvent, TouchEvent, NameResult, SpeakRequest, VoiceChange) and
prints what would be heard, with timing, so teammates can check requested answers and alarm order on
a machine with no speaker, Piper, pyttsx3 or pygame. Touches stay silent, as in audio/
(question-only speech). Like audio/, it publishes only SpeechStatus,
VoiceStatus and ModuleStatus telemetry, always with mode "fake" so the dashboard
never shows printed speech as real playback. Every voice preset is listed as
installed, so the dashboard's voice picker can switch.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from audio.audio import AudioManager
from audio.voices import PRESETS, piper_voice_id, startup_voice_key
from contracts import HazardEvent, NameResult, SpeakRequest, TouchEvent, VoiceChange

SECONDS_PER_CHAR = 0.06  # roughly the calm rate of 165 words a minute
ALARM_SECONDS = 0.61  # length of audio/sounds/alarm.wav


class PrintSpeaker:
    """Prints each phrase and takes about as long as speaking it would."""

    mode = "fake"

    def installed_voices(self) -> list[tuple[str, str]]:
        """List every preset's Piper voice as installed."""
        return [(piper_voice_id(p), p.voice_name) for p in PRESETS]

    def set_voice(self, voice_id: str | None) -> None:
        """Print the voice that later phrases would use."""
        print(f"[fake audio] voice: {voice_id}", flush=True)

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
    mode = "fake"

    def play(self) -> None:
        """Print the alarm."""
        print("[fake audio] BEEP BEEP BEEP", flush=True)

    def close(self) -> None:
        """Nothing to release."""


def register(bus: Any) -> AudioManager:
    """Subscribe a printing audio manager to the bus and return it for shutdown."""
    manager = AudioManager(
        PrintSpeaker,
        PrintAlarm(),
        publish=bus.publish,
        voice=startup_voice_key(os.environ),
    )
    bus.subscribe(HazardEvent, manager.on_hazard)
    bus.subscribe(TouchEvent, manager.on_touch)
    bus.subscribe(NameResult, manager.on_name)
    bus.subscribe(SpeakRequest, manager.on_speak)
    bus.subscribe(VoiceChange, manager.on_voice_change)
    return manager
