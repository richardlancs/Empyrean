"""Fake storage: keeps events in memory and answers last-seen queries, no network.

Run the demo:  .venv/bin/python -m fakes.storage.fake_store

Consumes: TouchEvent, HazardEvent, LastSeenQuery (SPEC.md section 5).
Publishes: SpeakRequest(priority="normal", source="storage") with the SPEC.md
section 4.10 last-seen sentence, for example
"Heinz ketchup, 4 minutes ago, next to mug and cereal box."
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from fakes.storage._pending import HazardEvent, LastSeenQuery, SpeakRequest, TouchEvent

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


def last_seen_sentence(event: TouchEvent | None, now: float) -> str:
    """Build the spoken last-seen answer for one touch event, or the not-seen line."""
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

    def on_last_seen_query(self, msg: LastSeenQuery) -> None:
        """Answer a last-seen query with a SpeakRequest."""
        now = time.time()
        text = last_seen_sentence(self.find_last_seen(msg.text), now)
        self._publish(SpeakRequest(ts=now, text=text, priority="normal", source="storage"))


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
    print(f"stored {len(store.touch_events)} touch, {len(store.hazard_events)} hazard events")
