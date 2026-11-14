"""Audio manager: speak touched objects and answers, and sound the alarm first.

Implements SPEC.md section 4.8 and the late-name rule in section 4.5.

Subscribes to: HazardEvent, TouchEvent, NameResult, SpeakRequest.
Publishes: nothing. Output is sound on the system speaker (the JBL Go 3).

Every bus handler only updates state under a lock and returns. Speech runs on
one worker thread that owns the text-to-speech engine. The alarm beeps start on
the hazard handler's own thread, so they never wait behind speech.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from audio.backends import LogSpeaker, Pyttsx3Speaker, load_alarm
from config import LATE_NAME_WINDOW_SECONDS
from contracts import HazardEvent, NameResult, SpeakRequest, TouchEvent

log = logging.getLogger("audio")

# Spoken hazard phrases, SPEC.md section 4.8.
HAZARD_PHRASES: dict[str, str] = {
    "stairs_down": "Stop. Stairs.",
    "drop_off": "Stop. Drop ahead.",
    "vehicle": "Stop. Vehicle.",
    "obstacle": "Stop. Obstacle.",
}
FALLBACK_HAZARD_PHRASE = "Stop."

# Lower number wins, SPEC.md section 4.8.
PRIORITY_ALARM = 1
PRIORITY_TOUCH = 2
PRIORITY_ANSWER = 3


class Speaker(Protocol):
    """Blocking text to speech that can be cut off between words."""

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Speak text, returning early once should_stop() is true."""


class Alarm(Protocol):
    """Non-blocking alarm sound."""

    duration: float

    def play(self) -> None:
        """Start the alarm and return at once."""

    def close(self) -> None:
        """Release the sound device."""


@dataclass
class _Item:
    """One thing waiting to be spoken."""

    priority: int
    text: str
    generation: int  # alarm count when queued; a newer alarm cancels it
    created_at: float
    not_before: float = 0.0  # the hazard phrase waits for the beeps to end


@dataclass
class _Touch:
    """An object that is being touched right now."""

    received_at: float
    spoke_label: bool  # True when the class label was used because no name was known
    late_name_done: bool = False


@dataclass
class _State:
    """Everything the handlers and the worker share, guarded by one condition."""

    slot: _Item | None = None  # the speech queue holds one item
    generation: int = 0
    closed: bool = False
    touches: dict[int, _Touch] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)


class AudioManager:
    """Turns bus messages into speech and alarms, alarm first."""

    def __init__(
        self,
        speaker_factory: Callable[[], Speaker],
        alarm: Alarm,
        *,
        clock: Callable[[], float] = time.monotonic,
        late_name_window: float = LATE_NAME_WINDOW_SECONDS,
    ) -> None:
        """Start the speech worker. speaker_factory runs on that worker thread."""
        self._speaker_factory = speaker_factory
        self._alarm = alarm
        self._clock = clock
        self._late_name_window = late_name_window
        self._cond = threading.Condition()
        self._state = _State()
        self._thread = threading.Thread(
            target=self._run, name="audio-speech", daemon=True
        )
        self._thread.start()

    # Bus handlers. Each returns without waiting on sound.

    def on_hazard(self, msg: HazardEvent) -> None:
        """Start the beeps, cut off speech, empty the queue, then queue the phrase."""
        try:
            self._alarm.play()
        except Exception:
            log.exception("Alarm sound failed")
        phrase = HAZARD_PHRASES.get(msg.type, FALLBACK_HAZARD_PHRASE)
        with self._cond:
            state = self._state
            state.generation += 1
            now = self._clock()
            state.slot = _Item(
                PRIORITY_ALARM,
                phrase,
                state.generation,
                now,
                now + self._alarm.duration,
            )
            self._cond.notify_all()
        log.info("Alarm: %s (%s, confidence %.2f)", phrase, msg.source, msg.confidence)

    def on_touch(self, msg: TouchEvent) -> None:
        """Speak a touched object's name, or its class label if not yet named."""
        with self._cond:
            state = self._state
            if msg.kind != "touch":
                state.touches.pop(msg.object_id, None)
                return
            # A NameResult can reach audio just before the TouchEvent that it beat.
            name = msg.name.strip() or state.names.get(msg.object_id, "")
            now = self._clock()
            state.touches[msg.object_id] = _Touch(now, spoke_label=not name)
            self._offer(
                _Item(PRIORITY_TOUCH, name or msg.class_label, state.generation, now)
            )

    def on_name(self, msg: NameResult) -> None:
        """Speak a late name once if its object is still touched (SPEC.md 4.5)."""
        name = msg.name.strip()
        if not msg.ok or not name:
            return
        with self._cond:
            state = self._state
            state.names[msg.object_id] = name
            touch = state.touches.get(msg.object_id)
            if touch is None or not touch.spoke_label or touch.late_name_done:
                return
            now = self._clock()
            if now - touch.received_at > self._late_name_window:
                return
            touch.late_name_done = True
            self._offer(_Item(PRIORITY_TOUCH, name, state.generation, now))

    def on_speak(self, msg: SpeakRequest) -> None:
        """Speak an answer, such as the last-seen reply, at the lowest priority."""
        text = msg.text.strip()
        if not text:
            return
        with self._cond:
            self._offer(
                _Item(PRIORITY_ANSWER, text, self._state.generation, self._clock())
            )

    def stop(self, timeout: float = 2.0) -> None:
        """Cut off speech, stop the worker and release the alarm."""
        with self._cond:
            self._state.closed = True
            self._state.slot = None
            self._cond.notify_all()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout)
        try:
            self._alarm.close()
        except Exception:
            log.exception("Alarm close failed")

    # Internals.

    def _offer(self, item: _Item) -> None:
        """Put item in the one-item queue. Caller holds the lock.

        A newer item replaces a waiting older one unless the waiting one has a
        higher priority. Stale speech is worse than no speech.
        """
        waiting = self._state.slot
        if waiting is not None and waiting.priority < item.priority:
            log.info("Dropped %r: %r is waiting", item.text, waiting.text)
            return
        if waiting is not None:
            log.info("Replaced %r with %r", waiting.text, item.text)
        self._state.slot = item
        self._cond.notify_all()

    def _next_item(self) -> _Item | None:
        """Block until an item is due. Returns None once stopped."""
        with self._cond:
            state = self._state
            while True:
                while state.slot is None and not state.closed:
                    self._cond.wait()
                if state.closed:
                    return None
                item = state.slot
                remaining = item.not_before - self._clock()
                if remaining <= 0:
                    state.slot = None
                    return item
                # Leave the phrase in the slot while the beeps play, so nothing
                # of lower priority can replace it and a newer alarm can.
                self._cond.wait(remaining)

    def _make_speaker(self) -> Speaker:
        """Create the speaker on this thread, or fall back to logging."""
        try:
            return self._speaker_factory()
        except Exception:
            log.exception("Text to speech unavailable; speech will be logged only")
            return LogSpeaker()

    def _run(self) -> None:
        """Speech worker: speak one item at a time until stopped."""
        speaker = self._make_speaker()
        failed_logged = False
        while True:
            item = self._next_item()
            if item is None:
                return
            generation = item.generation

            def should_stop(generation: int = generation) -> bool:
                state = self._state
                return state.closed or state.generation != generation

            if should_stop():
                continue
            log.info(
                "Speaking %r, %.0f ms after the event",
                item.text,
                (self._clock() - item.created_at) * 1000,
            )
            try:
                speaker.say(item.text, should_stop)
            except Exception:
                if not failed_logged:
                    log.exception("Speech failed for %r", item.text)
                    failed_logged = True


def register(bus: Any) -> AudioManager:
    """Subscribe the audio manager to the bus and return it for shutdown."""
    manager = AudioManager(Pyttsx3Speaker, load_alarm())
    bus.subscribe(HazardEvent, manager.on_hazard)
    bus.subscribe(TouchEvent, manager.on_touch)
    bus.subscribe(NameResult, manager.on_name)
    bus.subscribe(SpeakRequest, manager.on_speak)
    return manager
