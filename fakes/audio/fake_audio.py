"""Fake audio: records what audio/ would play instead of making any sound.

Run the demo:  python -m fakes.audio

Subscribes to the same messages as audio/ (SPEC.md section 3.1): HazardEvent,
TouchEvent, NameResult and SpeakRequest. Publishes nothing, because audio/
publishes nothing on the bus. Each would-be sound is appended to `played` and
passed to an optional callback, so tests and --fake runs need no speaker.

Follows the SPEC.md section 4.8 phrases and the section 4.5 late-name rule.
It does not model timing, the one-item speech queue, or the alarm cutting off
speech: every message is "played" the moment it arrives.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from config import LATE_NAME_WINDOW_SECONDS
from contracts import HazardEvent, NameResult, SpeakRequest, TouchEvent

HAZARD_PHRASES: dict[str, str] = {
    "stairs_down": "Stop. Stairs.",
    "drop_off": "Stop. Drop ahead.",
    "vehicle": "Stop. Vehicle.",
    "obstacle": "Stop. Obstacle.",
}


@dataclass
class Played:
    """One sound the real audio manager would have played."""

    ts: float  # ts of the message that caused it
    kind: Literal["alarm", "speech"]
    text: str  # spoken words; for an alarm, the phrase after the beeps


class FakeAudio:
    """Stand-in for audio/: records alarms and speech, plays nothing."""

    def __init__(self, on_play: Callable[[Played], None] | None = None) -> None:
        """Start with nothing played; on_play is called for every recorded sound."""
        self.played: list[Played] = []
        self._on_play = on_play
        self._lock = threading.Lock()
        # object_id -> ts of a touch that was spoken with the class label only
        self._awaiting_name: dict[int, float] = {}

    def on_hazard(self, msg: HazardEvent) -> None:
        """Record the alarm and its spoken phrase."""
        with self._lock:
            self._awaiting_name.clear()
        self._play(Played(ts=msg.ts, kind="alarm", text=HAZARD_PHRASES[msg.type]))

    def on_touch(self, msg: TouchEvent) -> None:
        """Speak the name on a touch, or the class label if the name is not known yet."""
        with self._lock:
            if msg.kind == "release":
                self._awaiting_name.pop(msg.object_id, None)
                return
            if not msg.name:
                self._awaiting_name[msg.object_id] = msg.ts
        self._play(Played(ts=msg.ts, kind="speech", text=msg.name or msg.class_label))

    def on_name_result(self, msg: NameResult) -> None:
        """Speak a late name once if it arrives in time while the object is still touched."""
        with self._lock:
            touch_ts = self._awaiting_name.pop(msg.object_id, None)
        if touch_ts is None or not msg.ok or not msg.name:
            return
        if msg.ts - touch_ts <= LATE_NAME_WINDOW_SECONDS:
            self._play(Played(ts=msg.ts, kind="speech", text=msg.name))

    def on_speak_request(self, msg: SpeakRequest) -> None:
        """Speak the requested text."""
        self._play(Played(ts=msg.ts, kind="speech", text=msg.text))

    def stop(self) -> None:
        """Nothing to shut down; present so app/ can stop fake and real audio alike."""

    def _play(self, item: Played) -> None:
        """Record one sound and pass it to the callback."""
        with self._lock:
            self.played.append(item)
        if self._on_play is not None:
            self._on_play(item)


def register(bus: Any, on_play: Callable[[Played], None] | None = None) -> FakeAudio:
    """Subscribe a FakeAudio to the bus for every message audio/ consumes, and return it."""
    audio = FakeAudio(on_play)
    bus.subscribe(HazardEvent, audio.on_hazard)
    bus.subscribe(TouchEvent, audio.on_touch)
    bus.subscribe(NameResult, audio.on_name_result)
    bus.subscribe(SpeakRequest, audio.on_speak_request)
    return audio
