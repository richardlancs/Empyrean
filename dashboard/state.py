"""What the dashboard page shows: objects in view, the latest warning and the event log.

Bus handlers may call in from any thread, so every change happens under a lock.
Handlers only update memory and return; they never wait on the web page.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from config import HAZARD_COOLDOWN_SECONDS
from contracts import HazardEvent, ModeChange, SceneSnapshot, SpeakRequest, TouchEvent

EVENT_LOG_SIZE = 10  # SPEC.md 4.9: "last 10 touch and hazard events"
# SPEC.md 4.9: touched objects are sorted to the top of the object list.
STATE_ORDER = {"touching": 0, "held": 1, "idle": 2, "new": 3, "lost": 4}
SIMULATED_HAZARD = "stairs_down"  # a HazardEvent.type from SPEC.md section 5

HAZARD_LABELS: dict[str, str] = {
    "stairs_down": "Stairs",
    "drop_off": "Drop ahead",
    "vehicle": "Vehicle",
    "obstacle": "Obstacle",
}


class DashboardState:
    """Objects in view, latest warning, and the last EVENT_LOG_SIZE events, newest first."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        """Start empty; clock returns seconds since the Unix epoch."""
        self._clock = clock
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._events: deque[dict[str, Any]] = deque(maxlen=EVENT_LOG_SIZE)
        self._latest_warning: dict[str, Any] | None = None
        self._objects: list[dict[str, Any]] = []
        self._mode = "actual"
        self._scene_ts: float | None = None
        self._answer: str = ""
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Call listener (from the updating thread) after every change."""
        with self._lock:
            self._listeners.append(listener)

    def on_hazard(self, msg: HazardEvent) -> None:
        """Show a real HazardEvent as the latest warning and log it."""
        detail = f"{msg.source}, {round(msg.confidence * 100)}%"
        self._add_warning(msg.ts, msg.type, simulated=False, detail=detail)

    def on_touch(self, msg: TouchEvent) -> None:
        """Log a touch. Releases are not logged."""
        if msg.kind != "touch":
            return
        entry = {
            "id": next(self._ids),
            "ts": msg.ts,
            "kind": "touch",
            "type": None,
            "text": msg.name or msg.class_label,
            "detail": "" if msg.name else "not named yet",
            "simulated": False,
        }
        with self._lock:
            self._events.appendleft(entry)
        self._notify()

    def on_scene(self, msg: SceneSnapshot) -> None:
        """Replace the object list with this snapshot's objects, touched ones first."""
        objects = [
            {
                "object_id": obj.object_id,
                "text": obj.name or obj.class_label,
                "class_label": obj.class_label,
                "named": bool(obj.name),
                "state": obj.state,
                "last_seen_ts": obj.last_seen_ts,
            }
            for obj in msg.objects
        ]
        objects.sort(key=lambda o: (STATE_ORDER.get(o["state"], 9), o["object_id"]))
        with self._lock:
            self._objects = objects
            self._scene_ts = msg.ts
        self._notify()

    def on_answer(self, msg: SpeakRequest) -> None:
        """Display requested answers without speaking twice."""
        if msg.source not in {"storage", "dashboard", "namer"}:
            return
        with self._lock:
            self._answer = msg.text
        self._notify()

    def on_mode(self, msg: ModeChange) -> None:
        """Show which mode is running: actual, or demo (demo-object detector)."""
        with self._lock:
            if self._mode == msg.mode:
                return
            self._mode = msg.mode
        self._notify()

    def simulate_hazard(self) -> dict[str, Any]:
        """Add one simulated stairs warning to this page only, and return the new state.

        Nothing is published on the bus, so no alarm sounds and nothing is stored.
        """
        self._add_warning(self._clock(), SIMULATED_HAZARD, simulated=True, detail="")
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Return the page state as plain JSON-ready data."""
        with self._lock:
            latest = dict(self._latest_warning) if self._latest_warning else None
            events = [dict(e) for e in self._events]
            objects = [dict(o) for o in self._objects]
            mode = self._mode
            answer = self._answer
            scene_ts = self._scene_ts
        return {
            "now": self._clock(),
            "mode": mode,
            "hazard_active_seconds": HAZARD_COOLDOWN_SECONDS,
            "latest_warning": latest,
            "events": events,
            "objects": objects,
            "answer": answer,
            "scene_ts": scene_ts,
        }

    def _add_warning(
        self, ts: float, hazard_type: str, simulated: bool, detail: str
    ) -> None:
        """Record one hazard as the latest warning and as a log entry."""
        entry = {
            "id": next(self._ids),
            "ts": ts,
            "kind": "hazard",
            "type": hazard_type,
            "text": HAZARD_LABELS[hazard_type],
            "detail": detail,
            "simulated": simulated,
        }
        with self._lock:
            self._latest_warning = entry
            self._events.appendleft(entry)
        self._notify()

    def _notify(self) -> None:
        """Tell listeners the state changed."""
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener()
