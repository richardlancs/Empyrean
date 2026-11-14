"""The dashboard read model: what the page shows, built only from bus messages.

Objects in view, the current touch, speech progress, naming progress, real and
simulated warnings, the event log and measured diagnostics. Bus handlers may
call in from any thread, so every change happens under a lock. Handlers only
update memory and return; they never wait on the web page.

The backend is authoritative for touch, naming, hazards and audio. Nothing here
is invented: missing evidence is reported as null or "unknown".
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import Any

from config import HAZARD_COOLDOWN_SECONDS, NAME_TIMEOUT_SECONDS
from contracts import (
    FrameResult,
    HazardEvent,
    ModuleStatus,
    NameRequest,
    NameResult,
    SceneSnapshot,
    SpeechStatus,
    TouchEvent,
)
from dashboard.services.health import HealthMonitor

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

MAX_TOUCH_TRACKS = 16  # touched objects remembered for current_touch
MAX_NAMING_TRACKS = 256  # objects whose naming lifecycle is remembered
NAMING_FORGET_SECONDS = 60.0  # forget naming of objects gone this long
# A request with no answer this long is no longer called pending.
NAMING_PENDING_SECONDS = NAME_TIMEOUT_SECONDS * 2
SPEECH_ORDER = {"queued": 0, "speaking": 1, "completed": 2, "interrupted": 2, "failed": 2}


def _is_later_step(previous: dict[str, Any] | None, msg: SpeechStatus) -> bool:
    """False when msg is an out-of-order earlier step of a phrase already further on."""
    return not (
        previous is not None
        and previous["speech_id"] == msg.speech_id
        and SPEECH_ORDER[previous["status"]] > SPEECH_ORDER.get(msg.status, 0)
    )


class DashboardState:
    """Read model for the page; snapshot() returns plain JSON-ready data."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        """Start empty; clock returns seconds since the Unix epoch."""
        self._clock = clock
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._events: deque[dict[str, Any]] = deque(maxlen=EVENT_LOG_SIZE)
        self._latest_warning: dict[str, Any] | None = None
        self._latest_real_warning: dict[str, Any] | None = None
        self._latest_simulated_warning: dict[str, Any] | None = None
        self._objects: list[dict[str, Any]] = []
        self._touches: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._current_touch_id: int | None = None
        self._naming: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._speech: dict[str, Any] | None = None
        self._speech_by_object: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._speech_reported = False
        self._listeners: list[Callable[[], None]] = []
        self.health = HealthMonitor(clock)
        # Attached by register()/create_app(); None means the capability is absent.
        self.thumbnails: Any = None
        self.last_seen: Any = None

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Call listener (from the updating thread) after every change."""
        with self._lock:
            self._listeners.append(listener)

    # Bus handlers.

    def on_hazard(self, msg: HazardEvent) -> None:
        """Show a real HazardEvent as the latest real warning and log it."""
        detail = f"{msg.source}, {round(msg.confidence * 100)}%"
        self._add_warning(
            msg.ts,
            msg.type,
            simulated=False,
            detail=detail,
            source=msg.source,
            confidence=float(msg.confidence),
        )

    def on_touch(self, msg: TouchEvent) -> None:
        """Track the current touch, and log touches. Releases are not logged."""
        now = self._clock()
        with self._lock:
            track = self._touches.get(msg.object_id)
            if msg.kind == "touch":
                self._touches[msg.object_id] = {
                    "object_id": msg.object_id,
                    "class_label": msg.class_label,
                    "name": msg.name or (track["name"] if track else ""),
                    "state": "touching",
                    "ts": msg.ts,
                    "released_ts": None,
                    "received_at": now,
                }
                self._touches.move_to_end(msg.object_id)
                self._current_touch_id = msg.object_id
                while len(self._touches) > MAX_TOUCH_TRACKS:
                    self._touches.popitem(last=False)
                self._events.appendleft(
                    {
                        "id": next(self._ids),
                        "ts": msg.ts,
                        "kind": "touch",
                        "type": None,
                        "text": msg.name or msg.class_label,
                        "detail": "" if msg.name else "not named yet",
                        "simulated": False,
                        "object_id": msg.object_id,
                    }
                )
            elif track is not None and track["state"] != "released":
                track.update(state="released", released_ts=msg.ts)
                if msg.name and not track["name"]:
                    track["name"] = msg.name
                if self._current_touch_id == msg.object_id:
                    # Another object still in a hand takes over; otherwise nothing
                    # is touched and current_touch becomes null.
                    active = [t for t in self._touches.values() if t["state"] != "released"]
                    self._current_touch_id = active[-1]["object_id"] if active else None
        self._notify()

    def on_scene(self, msg: SceneSnapshot) -> None:
        """Replace the object list with this snapshot's objects, touched ones first."""
        self.health.on_scene(msg)
        now = self._clock()
        objects = [
            {
                "object_id": obj.object_id,
                "text": obj.name or obj.class_label,
                "class_label": obj.class_label,
                "name": obj.name,
                "named": bool(obj.name),
                "state": obj.state,
                "last_seen_ts": obj.last_seen_ts,
                "box": [float(v) for v in obj.box],
            }
            for obj in msg.objects
        ]
        objects.sort(key=lambda o: (STATE_ORDER.get(o["state"], 9), o["object_id"]))
        with self._lock:
            self._objects = objects
            by_id = {o["object_id"]: o for o in objects}
            for object_id, track in self._touches.items():
                obj = by_id.get(object_id)
                if obj is None:
                    continue
                if obj["name"]:
                    track["name"] = obj["name"]
                if track["state"] != "released" and obj["state"] in ("touching", "held"):
                    track["state"] = obj["state"]
            for object_id in by_id:
                entry = self._naming.get(object_id)
                if entry is not None:
                    entry["seen_at"] = now
            for object_id in [
                k
                for k, v in self._naming.items()
                if k not in by_id and now - v["seen_at"] > NAMING_FORGET_SECONDS
            ]:
                del self._naming[object_id]
        self._notify()

    def on_frame(self, msg: FrameResult) -> None:
        """Measure the camera (no page push: frames arrive five times a second)."""
        self.health.on_frame(msg)

    def on_name_request(self, msg: NameRequest) -> None:
        """Mark an object's name as pending."""
        self.health.on_name_request(msg)
        now = self._clock()
        with self._lock:
            entry = self._naming.setdefault(msg.object_id, {"requests": 0, "result": None})
            entry.update(requested_at=now, seen_at=now, outstanding=True)
            entry["requests"] += 1
            self._naming.move_to_end(msg.object_id)
            while len(self._naming) > MAX_NAMING_TRACKS:
                self._naming.popitem(last=False)
        self._notify()

    def on_name_result(self, msg: NameResult) -> None:
        """Record how naming ended for an object: named, generic fallback, or failed."""
        self.health.on_name_result(msg)
        now = self._clock()
        ok = bool(msg.ok)
        named = ok and bool(msg.name.strip())
        with self._lock:
            entry = self._naming.setdefault(msg.object_id, {"requests": 0, "requested_at": None})
            entry.update(
                outstanding=False,
                seen_at=now,
                result="named" if named else ("fallback" if ok else "failed"),
            )
            track = self._touches.get(msg.object_id)
            if named and track is not None and not track["name"]:
                track["name"] = msg.name.strip()
        self._notify()

    def on_speech(self, msg: SpeechStatus) -> None:
        """Keep the newest step of the newest phrase, and the newest per object."""
        entry = {
            "speech_id": msg.speech_id,
            "text": msg.text,
            "status": msg.status,
            "ts": msg.ts,
            "mode": msg.mode,
            "kind": msg.kind,
            "object_id": msg.object_id,
            "source": msg.source,
            "detail": msg.detail,
        }
        with self._lock:
            self._speech_reported = True
            if not _is_later_step(self._speech, msg):
                return  # a late step of a phrase that already finished
            self._speech = entry
            if msg.object_id is not None and _is_later_step(
                self._speech_by_object.get(msg.object_id), msg
            ):
                self._speech_by_object[msg.object_id] = entry
                self._speech_by_object.move_to_end(msg.object_id)
                while len(self._speech_by_object) > MAX_TOUCH_TRACKS:
                    self._speech_by_object.popitem(last=False)
        self._notify()

    def on_module_status(self, msg: ModuleStatus) -> None:
        """Record an explicit module status for diagnostics."""
        self.health.on_module_status(msg)
        if msg.module == "audio" and msg.status != "offline":
            with self._lock:
                self._speech_reported = True
        self._notify()

    # Page-only actions.

    def simulate_hazard(self) -> dict[str, Any]:
        """Add one simulated stairs warning to this page only, and return the new state.

        Nothing is published on the bus, so no alarm sounds and nothing is stored.
        latest_real_warning is untouched, so a real warning keeps its priority.
        """
        self._add_warning(self._clock(), SIMULATED_HAZARD, simulated=True, detail="")
        return self.snapshot()

    # Read side.

    def snapshot(self) -> dict[str, Any]:
        """Return the page state as plain JSON-ready data."""
        now = self._clock()
        thumbs = self.thumbnails.fresh_ids() if self.thumbnails is not None else {}
        with self._lock:
            latest = dict(self._latest_warning) if self._latest_warning else None
            real = self._warning_view(self._latest_real_warning, now)
            simulated = self._warning_view(self._latest_simulated_warning, now)
            events = [dict(e) for e in self._events]
            objects = []
            for o in self._objects:
                item = dict(o, box=list(o["box"]))
                item["naming_status"] = self._naming_status(o["object_id"], o["name"], now)
                stamp = thumbs.get(o["object_id"])
                item["thumbnail_url"] = (
                    f"/api/objects/{o['object_id']}/thumbnail?v={int(stamp * 1000)}"
                    if stamp is not None and o["state"] != "lost"
                    else None
                )
                objects.append(item)
            current_touch = self._touch_view(self._current_touch_id, now)
            last_touch = self._touch_view(
                next(reversed(self._touches)) if self._touches else None, now
            )
            speech = dict(self._speech) if self._speech else None
            speech_reported = self._speech_reported
        return {
            "now": now,
            "hazard_active_seconds": HAZARD_COOLDOWN_SECONDS,
            "event_log_size": EVENT_LOG_SIZE,
            "latest_warning": latest,
            "latest_real_warning": real,
            "latest_simulated_warning": simulated,
            "events": events,
            "objects": objects,
            "current_touch": current_touch,
            "last_touch": last_touch,
            "speech": speech,
            "diagnostics": self.health.diagnostics(),
            "capabilities": {
                # Searching needs a bus and a storage module running in this launch.
                "last_seen": bool(
                    self.last_seen is not None
                    and self.last_seen.available
                    and not self.health.not_started("storage")
                ),
                "thumbnails": bool(
                    self.thumbnails is not None and getattr(self.thumbnails, "receiving", False)
                ),
                "overlays": True,
                "speech_status": speech_reported,
            },
        }

    def tick(self) -> None:
        """Heartbeat: push the state so time-based statuses update when nothing else does."""
        self._notify()

    # Internals; callers of the _view helpers hold the lock.

    def _warning_view(self, warning: dict[str, Any] | None, now: float) -> dict[str, Any] | None:
        """Copy a warning and say whether it is still within the hazard cooldown."""
        if warning is None:
            return None
        view = dict(warning)
        view["active"] = 0 <= now - warning["ts"] <= HAZARD_COOLDOWN_SECONDS
        return view

    def _naming_status(self, object_id: int, name: str, now: float) -> str:
        """pending, named, fallback, failed or unknown, from the real naming lifecycle."""
        if name:
            return "named"
        entry = self._naming.get(object_id)
        if entry is None:
            return "unknown"
        if entry.get("outstanding"):
            requested_at = entry.get("requested_at")
            if requested_at is not None and now - requested_at <= NAMING_PENDING_SECONDS:
                return "pending"
            return "unknown"
        result = entry.get("result")
        return result if result in ("named", "fallback", "failed") else "unknown"

    def _touch_view(self, object_id: int | None, now: float) -> dict[str, Any] | None:
        """One touched object as the page shows it; state is touching, held or released."""
        if object_id is None:
            return None
        track = self._touches.get(object_id)
        if track is None:
            return None
        name = track["name"] or ""
        speech = self._speech_by_object.get(track["object_id"])
        if speech is not None and speech["ts"] < track["received_at"] - 1.0:
            speech = None  # speech from an earlier touch of the same object
        return {
            "object_id": track["object_id"],
            "text": name or track["class_label"],
            "state": track["state"],
            "ts": track["ts"],
            "class_label": track["class_label"],
            "name": name,
            "named": bool(name),
            "naming_status": self._naming_status(track["object_id"], name, now),
            "released_ts": track["released_ts"],
            "speech": dict(speech) if speech else None,
        }

    def _add_warning(
        self,
        ts: float,
        hazard_type: str,
        simulated: bool,
        detail: str,
        source: str | None = None,
        confidence: float | None = None,
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
            "source": "simulation" if simulated else source,
            "confidence": None if simulated else confidence,
        }
        with self._lock:
            self._latest_warning = entry
            if simulated:
                self._latest_simulated_warning = entry
            else:
                self._latest_real_warning = entry
            self._events.appendleft(entry)
        self._notify()

    def _notify(self) -> None:
        """Tell listeners the state changed."""
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener()
