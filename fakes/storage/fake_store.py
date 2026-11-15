"""Fake storage: keeps events in memory and answers last-seen queries, no network.

Run the demo:  .venv/bin/python -m fakes.storage.fake_store

Consumes: TouchEvent, HazardEvent, LastSeenQuery, VoiceStatus (SPEC.md section 5).
Publishes: SpeakRequest(priority="normal", source="storage") with the SPEC.md
section 4.10 last-seen sentence, for example
"Heinz ketchup, 4 minutes ago, next to mug and cereal box."
A query with a request_id also gets a LastSeenResult (found or not_found; the
fake is never unavailable). register() announces a ModuleStatus with mode "fake".
Answers follow the language of audio's last VoiceStatus, captured when the
query arrives, worded by the same tables as the real store.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from contracts import (
    HazardEvent,
    LastSeenQuery,
    LastSeenResult,
    ModuleStatus,
    SpeakRequest,
    TouchEvent,
    VoiceStatus,
)
from contracts.languages import DEFAULT_LANGUAGE, known_language
from storage.last_seen import format_answer

NOT_SEEN = "I have not seen that."
MAX_NEIGHBOURS = 3

Publish = Callable[[object], None]


def format_age(seconds: float) -> str:
    """Return 'just now', 'N minute(s) ago' or 'N hour(s) ago'."""
    if seconds < 60:
        return "just now"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} minute ago" if minutes == 1 else f"{minutes} minutes ago"
    hours = int(seconds // 3600)
    return f"{hours} hour ago" if hours == 1 else f"{hours} hours ago"


def join_names(names: list[str]) -> str:
    """Join names as 'a', 'a and b', or 'a, b and c'."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def last_seen_sentence(
    event: TouchEvent | None, now: float, language: str = DEFAULT_LANGUAGE
) -> str:
    """Build the spoken last-seen answer for one touch event, or the not-seen line."""
    if language != DEFAULT_LANGUAGE:
        row = None if event is None else {
            "ts": min(event.ts, now),
            "name": event.name,
            "class_label": event.class_label,
            "neighbours": [n for n in event.neighbours if n][:MAX_NEIGHBOURS],
        }
        return format_answer(row, now, language)
    if event is None:
        return NOT_SEEN
    label = event.name or event.class_label
    parts = [label, format_age(max(0.0, now - event.ts))]
    neighbours = [n for n in event.neighbours if n][:MAX_NEIGHBOURS]
    if neighbours:
        parts.append(f"next to {join_names(neighbours)}")
    return ", ".join(parts) + "."


class FakeStore:
    """Stand-in for storage/: in-memory event log plus last-seen answers."""

    def __init__(self, publish: Publish) -> None:
        """Keep the publish callback and empty in-memory tables."""
        self._publish = publish
        self._lock = threading.Lock()
        self.touch_events: list[TouchEvent] = []
        self.hazard_events: list[HazardEvent] = []
        self.language = DEFAULT_LANGUAGE

    def on_touch_event(self, msg: TouchEvent) -> None:
        """Record a touch or release event."""
        with self._lock:
            self.touch_events.append(msg)

    def on_hazard_event(self, msg: HazardEvent) -> None:
        """Record a hazard event."""
        with self._lock:
            self.hazard_events.append(msg)

    def find_last_seen(self, text: str) -> TouchEvent | None:
        """Return the newest touch event whose name or class_label contains text."""
        needle = text.strip().lower()
        if not needle:
            return None
        with self._lock:
            events = sorted(self.touch_events, key=lambda e: e.ts, reverse=True)
        for event in events:
            if needle in event.name.lower() or needle in event.class_label.lower():
                return event
        return None

    def on_voice_status(self, msg: VoiceStatus) -> None:
        """Remember the active voice's language."""
        language = known_language(getattr(msg, "language", None))
        with self._lock:
            self.language = language

    def on_last_seen_query(self, msg: LastSeenQuery) -> None:
        """Answer a last-seen query with a SpeakRequest."""
        with self._lock:
            language = self.language
        now = time.time()
        match = self.find_last_seen(msg.text)
        text = last_seen_sentence(match, now, language)
        self._publish(SpeakRequest(ts=now, text=text, priority="normal", source="storage"))
        request_id = getattr(msg, "request_id", None)
        if request_id is None:
            return
        self._publish(
            LastSeenResult(
                ts=now,
                request_id=str(request_id),
                status="found" if match is not None else "not_found",
                answer=text,
                matched_at=match.ts if match is not None else None,
                label=(match.name or match.class_label) if match is not None else "",
                neighbours=list(match.neighbours[:MAX_NEIGHBOURS]) if match is not None else [],
            )
        )

    def stop(self) -> None:
        """Do nothing: the fake has no worker. Present so app/ can stop it like Store."""


def register(bus: Any) -> FakeStore:
    """Subscribe a FakeStore to the bus exactly as storage.register does, and return it."""
    store = FakeStore(bus.publish)
    bus.subscribe(TouchEvent, store.on_touch_event)
    bus.subscribe(HazardEvent, store.on_hazard_event)
    bus.subscribe(LastSeenQuery, store.on_last_seen_query)
    bus.subscribe(VoiceStatus, store.on_voice_status)
    bus.publish(
        ModuleStatus(
            ts=time.time(),
            module="storage",
            status="active",
            mode="fake",
            detail="Fake in-memory store: nothing is saved to Tiger Data",
        )
    )
    return store


if __name__ == "__main__":

    def _print_publish(msg: object) -> None:
        """Print whatever the fake publishes."""
        print(f"published: {msg}")

    store = FakeStore(_print_publish)
    t = time.time()
    box = (100.0, 100.0, 200.0, 200.0)
    store.on_touch_event(TouchEvent(t - 240, 1, "bottle", "Heinz ketchup", "touch", box,
                                    ["mug", "cereal box"]))
    store.on_touch_event(TouchEvent(t - 7300, 2, "cup", "Starbucks coffee cup", "touch", box,
                                    ["iPhone 15", "Penguin paperback", "bowl"]))
    store.on_touch_event(TouchEvent(t - 65, 3, "book", "", "touch", box, ["laptop"]))
    store.on_touch_event(TouchEvent(t - 5, 4, "cell phone", "iPhone 15", "release", box, []))
    store.on_hazard_event(HazardEvent(t - 30, "stairs_down", "grok", 0.8))
    for query in ["ketchup", "CUP", "book", "phone", "umbrella"]:
        print(f"query: {query!r}")
        store.on_last_seen_query(LastSeenQuery(ts=t, text=query))
    for code in ("zh", "es", "fr", "hi"):
        store.on_voice_status(VoiceStatus(ts=t, state="active", active_voice="", label="",
                                          quality="compact", language=code))
        print(f"query ({code}): 'ketchup'")
        store.on_last_seen_query(LastSeenQuery(ts=t, text="ketchup"))
    print(f"stored {len(store.touch_events)} touch, {len(store.hazard_events)} hazard events")
