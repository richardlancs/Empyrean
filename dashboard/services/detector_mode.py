"""Regular/Demo detector switching for the page: one shared request at a time.

The page asks; vision answers. A request publishes ModeChange (an in-memory bus
enqueue, never a model load) and is remembered as pending. Only a DetectorStatus
from vision changes which detector the page calls active. A request vision never
answers expires as failed after MODE_SWITCH_TIMEOUT_SECONDS, and any later
status still updates the page to whatever vision really runs. The service is
shared by every open page, because the detector is shared by the whole engine.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from config import MODE_SWITCH_TIMEOUT_SECONDS
from contracts import DetectorStatus, ModeChange

MODES = ("actual", "demo")
LABELS = {"actual": "Regular", "demo": "Demo"}


class ModeRejected(Exception):
    """A switch that was not sent; status_code says which HTTP error fits."""

    def __init__(self, status_code: int, message: str) -> None:
        """Keep the HTTP status and a plain message for the page."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class DetectorModeService:
    """Send detector switch requests over the bus and track vision's answers."""

    def __init__(
        self,
        publish: Callable[[Any], None] | None,
        clock: Callable[[], float] = time.time,
        timeout: float = MODE_SWITCH_TIMEOUT_SECONDS,
    ) -> None:
        """publish is bus.publish, or None when the dashboard runs with no bus."""
        self._publish = publish
        self._clock = clock
        self._timeout = timeout
        self._lock = threading.Lock()
        self._status: DetectorStatus | None = None
        self._pending: dict[str, Any] | None = None
        self._note = ""  # dashboard-side failure note (timeout), cleared by the next status
        self._listeners: list[Callable[[], None]] = []

    @property
    def available(self) -> bool:
        """True when switch requests can reach vision over a bus."""
        return self._publish is not None

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Call listener after the detector state changes."""
        with self._lock:
            self._listeners.append(listener)

    def request(self, mode: str) -> dict[str, Any]:
        """Ask vision to switch. Returns the reply body; raises ModeRejected."""
        if mode not in MODES:
            raise ModeRejected(422, "Choose Regular or Demo.")
        if self._publish is None:
            raise ModeRejected(503, "Switching detectors needs the full app; this page has no engine attached.")
        self.expire()
        with self._lock:
            if self._status is None:
                raise ModeRejected(503, "Vision has not reported which detector is running yet.")
            if self._pending is not None:
                pending = LABELS[self._pending["mode"]]
                raise ModeRejected(409, f"A switch to {pending} is already in progress.")
            if self._status.active_mode == mode and self._status.state != "switching":
                return {"state": "active", "mode": mode, "request_id": None}
            request_id = uuid.uuid4().hex
            self._pending = {"mode": mode, "request_id": request_id, "at": self._clock()}
            self._note = ""
        self._publish(ModeChange(ts=self._clock(), mode=mode, request_id=request_id))  # type: ignore[arg-type]
        self._notify()
        return {"state": "switching", "mode": mode, "request_id": request_id}

    def on_status(self, msg: DetectorStatus) -> None:
        """Bus handler: vision's report is the truth about the running detector."""
        with self._lock:
            self._status = msg
            self._note = ""
            pending = self._pending
            if pending is not None:
                answered = msg.request_id == pending["request_id"] and msg.state in ("active", "failed")
                reached = msg.state == "active" and msg.active_mode == pending["mode"]
                if answered or reached:
                    self._pending = None
        self._notify()

    def expire(self) -> bool:
        """Fail a request vision has not answered in time; True if anything changed."""
        with self._lock:
            pending = self._pending
            if pending is None or self._clock() - pending["at"] <= self._timeout:
                return False
            self._pending = None
            self._note = (
                f"Vision did not confirm the switch to {LABELS[pending['mode']]} within "
                f"{self._timeout:.0f} s. The page shows the detector vision last reported."
            )
        self._notify()
        return True

    def view(self) -> dict[str, Any]:
        """The detector state for the page snapshot (plain JSON)."""
        with self._lock:
            status, pending, note = self._status, self._pending, self._note
        if status is None:
            return {
                "state": "unknown",
                "active_mode": None,
                "switching_to": pending["mode"] if pending else None,
                "detector": None,
                "checkpoint": "",
                "demo_kind": "none",
                "demo_available": None,
                "message": "Vision has not reported which detector is running.",
                "fake": False,
                "request_id": None,
                "updated_ts": None,
                "can_switch": False,
            }
        if pending is not None:
            state, switching_to = "switching", pending["mode"]
        elif note:
            state, switching_to = "failed", None
        elif status.state == "switching":
            state, switching_to = "switching", status.requested_mode
        else:
            state, switching_to = status.state, None
        return {
            "state": state,
            "active_mode": status.active_mode,
            "switching_to": switching_to,
            "detector": status.detector,
            "checkpoint": status.checkpoint,
            "demo_kind": status.demo_kind,
            "demo_available": status.demo_available,
            "message": note or status.message,
            # The mode that could not be reached, when vision reported the failure.
            "failed_mode": status.requested_mode if state == "failed" and not note else None,
            "fake": status.fake,
            "request_id": pending["request_id"] if pending else status.request_id,
            "updated_ts": status.ts,
            "can_switch": self._publish is not None and pending is None and state != "switching",
        }

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener()
