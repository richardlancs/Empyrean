"""Measured health of the engine as the dashboard sees it (diagnostics in the page state).

Every status here comes from evidence: a frame timestamp, a scene update, a
naming request or result, or an explicit ModuleStatus from a module or app/.
Anything never instrumented is "unknown". An open WebSocket, or one past
success, is never taken as proof that a module is healthy right now.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from config import CAMERA_STALE_SECONDS, NAME_TIMEOUT_SECONDS, PROCESS_FPS
from contracts import FrameResult, ModuleStatus, NameRequest, NameResult, SceneSnapshot

# Diagnostics keys the page shows, and the module folder each one describes.
MODULE_FOR_ENTRY = {
    "camera": "vision",
    "scene": "scene",
    "naming": "namer",
    "storage": "storage",
    "audio": "audio",
    "hazard": "hazard",
}
FPS_WINDOW_FRAMES = PROCESS_FPS * 3  # measure the rate over about three seconds
CAMERA_OFFLINE_SECONDS = CAMERA_STALE_SECONDS * 5  # stale this long reads as stopped
STARTUP_GRACE_SECONDS = 10.0  # a started module may take this long to show evidence
NAMING_NO_ANSWER_SECONDS = NAME_TIMEOUT_SECONDS * 2  # well past the namer's own timeout
STATUS_VALUES = ("starting", "active", "degraded", "offline", "unknown")
NOT_STARTED_DETAIL = "Not started in this run"  # app/ lifecycle wording


@dataclass
class _Reported:
    """The newest ModuleStatus for one module."""

    status: str
    mode: str
    detail: str
    ts: float
    received_at: float


def _entry(
    status: str, detail: str, last_update_ts: float | None, mode: str = "unknown"
) -> dict[str, Any]:
    """Build one diagnostics entry in the shared page-state shape."""
    return {
        "status": status if status in STATUS_VALUES else "unknown",
        "detail": detail,
        "last_update_ts": last_update_ts,
        "mode": mode,
    }


def _seconds(value: float) -> str:
    """Format an age as whole seconds for a detail line."""
    return f"{max(0, round(value))} s"


class HealthMonitor:
    """Collects evidence from bus handlers and turns it into diagnostics on demand."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        """Start with no evidence; clock returns seconds since the Unix epoch."""
        self._clock = clock
        self._lock = threading.Lock()
        self._started_at = clock()
        # (receive time, capture ts, frame_id) for the newest frames.
        self._frames: deque[tuple[float, float, int]] = deque(maxlen=FPS_WINDOW_FRAMES)
        self._frame_size: tuple[int, int] | None = None
        self._scene_received_at: float | None = None
        self._scene_ts: float | None = None
        self._name_requested_at: float | None = None
        self._name_outstanding = 0
        self._name_result_at: float | None = None
        self._name_result_ok: bool | None = None
        self._reported: dict[str, _Reported] = {}

    # Bus handlers: update memory and return.

    def on_frame(self, msg: FrameResult) -> None:
        """Record one processed frame's arrival, capture time and size."""
        shape = getattr(msg.image, "shape", None)
        size = (int(shape[1]), int(shape[0])) if shape is not None and len(shape) >= 2 else None
        with self._lock:
            self._frames.append((self._clock(), float(msg.ts), int(msg.frame_id)))
            if size is not None:
                self._frame_size = size

    def on_scene(self, msg: SceneSnapshot) -> None:
        """Record that the scene published a snapshot."""
        with self._lock:
            self._scene_received_at = self._clock()
            self._scene_ts = float(msg.ts)

    def on_name_request(self, msg: NameRequest) -> None:
        """Record that the scene asked for a name."""
        with self._lock:
            self._name_requested_at = self._clock()
            self._name_outstanding += 1

    def on_name_result(self, msg: NameResult) -> None:
        """Record a naming answer and whether it succeeded."""
        with self._lock:
            self._name_result_at = self._clock()
            self._name_result_ok = bool(msg.ok)
            self._name_outstanding = max(0, self._name_outstanding - 1)

    def on_module_status(self, msg: ModuleStatus) -> None:
        """Keep the newest explicit status per module.

        "starting" (sent by app/ once everything is registered) never replaces a
        status the module itself has already sent; it only fills in the mode.
        """
        now = self._clock()
        with self._lock:
            current = self._reported.get(msg.module)
            if current is not None and msg.status == "starting" and current.status != "starting":
                if current.mode == "unknown":
                    current.mode = msg.mode
                return
            mode = msg.mode
            if mode == "unknown" and current is not None:
                mode = current.mode
            self._reported[msg.module] = _Reported(msg.status, mode, msg.detail, msg.ts, now)

    # Read side.

    def not_started(self, module: str) -> bool:
        """True when app/ said this module folder is not running in this launch."""
        with self._lock:
            reported = self._reported.get(module)
            return reported is not None and reported.status == "offline" and (
                reported.detail == NOT_STARTED_DETAIL
            )

    def diagnostics(self) -> dict[str, dict[str, Any]]:
        """Return camera, scene, naming, storage, audio and hazard entries for now."""
        now = self._clock()
        with self._lock:
            frames = list(self._frames)
            size = self._frame_size
            scene_at, scene_ts = self._scene_received_at, self._scene_ts
            requested_at, outstanding = self._name_requested_at, self._name_outstanding
            result_at, result_ok = self._name_result_at, self._name_result_ok
            reported = {k: _Reported(**vars(v)) for k, v in self._reported.items()}
        camera = self._camera(now, frames, size, reported.get("vision"))
        return {
            "camera": camera,
            "scene": self._scene(now, scene_at, scene_ts, camera, reported.get("scene")),
            "naming": self._naming(
                now, requested_at, outstanding, result_at, result_ok, reported.get("namer")
            ),
            "storage": self._reported_only(reported.get("storage"), "History storage"),
            "audio": self._reported_only(reported.get("audio"), "Audio"),
            "hazard": self._hazard(reported.get("hazard")),
        }

    def _not_running(self, reported: _Reported | None) -> dict[str, Any] | None:
        """Return an offline entry if app/ said the module is not running."""
        if reported is not None and reported.status == "offline":
            return _entry("offline", reported.detail, reported.ts, reported.mode)
        return None

    def _camera(
        self,
        now: float,
        frames: list[tuple[float, float, int]],
        size: tuple[int, int] | None,
        reported: _Reported | None,
    ) -> dict[str, Any]:
        """Camera status from frame arrival times; fps from capture timestamps."""
        mode = reported.mode if reported is not None else "unknown"
        if not frames:
            entry = self._not_running(reported)
            if entry is None:
                if reported is not None and now - reported.received_at <= STARTUP_GRACE_SECONDS:
                    entry = _entry("starting", "Waiting for the first frame", None, mode)
                elif reported is not None or now - self._started_at > STARTUP_GRACE_SECONDS:
                    entry = _entry("offline", "No camera frames received", None, mode)
                else:
                    entry = _entry("unknown", "No camera frames received yet", None, mode)
            entry.update(
                stale_after_seconds=CAMERA_STALE_SECONDS,
                last_frame_ts=None,
                fps=None,
                width=None,
                height=None,
            )
            return entry
        received_at, last_ts, _ = frames[-1]
        age = now - received_at
        fps: float | None = None
        recent = [f for f in frames if now - f[0] <= CAMERA_STALE_SECONDS * 2]
        if len(recent) >= 2:
            span = recent[-1][1] - recent[0][1]
            count = recent[-1][2] - recent[0][2]
            if span > 0 and count > 0:
                fps = round(count / span, 1)
        elif age > CAMERA_STALE_SECONDS:
            fps = 0.0
        source = " from a recorded clip (fake)" if mode == "fake" else ""
        if age <= CAMERA_STALE_SECONDS:
            entry = _entry("active", f"Receiving frames{source}", received_at, mode)
        elif age <= CAMERA_OFFLINE_SECONDS:
            entry = _entry("degraded", f"No new frame for {_seconds(age)}", received_at, mode)
        else:
            entry = _entry("offline", f"Camera feed stopped {_seconds(age)} ago", received_at, mode)
        entry.update(
            stale_after_seconds=CAMERA_STALE_SECONDS,
            last_frame_ts=last_ts,
            fps=fps,
            width=size[0] if size else None,
            height=size[1] if size else None,
        )
        return entry

    def _scene(
        self,
        now: float,
        received_at: float | None,
        scene_ts: float | None,
        camera: dict[str, Any],
        reported: _Reported | None,
    ) -> dict[str, Any]:
        """Scene status: it updates once per frame, so judge it against the camera."""
        mode = reported.mode if reported is not None else "unknown"
        if received_at is None:
            entry = self._not_running(reported)
            if entry is not None:
                return entry
            if camera["status"] == "active":
                if reported is not None and now - reported.received_at <= STARTUP_GRACE_SECONDS:
                    return _entry("starting", "Waiting for the first scene update", None, mode)
                return _entry("degraded", "Frames arrive but no scene updates", None, mode)
            return _entry("unknown", "No scene updates yet", None, mode)
        age = now - received_at
        if age <= CAMERA_STALE_SECONDS:
            detail = "Updating with each frame"
            if mode == "fake":
                detail = "Scripted fake scene"
            return _entry("active", detail, received_at, mode)
        if camera["status"] == "active":
            return _entry("degraded", f"No scene update for {_seconds(age)}", received_at, mode)
        # Quiet because there is nothing to process, not because it failed.
        return _entry("unknown", "Idle: no new frames to process", received_at, mode)

    def _naming(
        self,
        now: float,
        requested_at: float | None,
        outstanding: int,
        result_at: float | None,
        result_ok: bool | None,
        reported: _Reported | None,
    ) -> dict[str, Any]:
        """Naming status from the real NameRequest and NameResult lifecycle."""
        mode = reported.mode if reported is not None else "unknown"
        not_running = self._not_running(reported)
        if not_running is not None:
            return not_running
        last = max((t for t in (requested_at, result_at) if t is not None), default=None)
        waiting = (
            outstanding > 0
            and requested_at is not None
            and (result_at is None or result_at < requested_at)
        )
        if waiting and now - requested_at > NAMING_NO_ANSWER_SECONDS:
            return _entry(
                "degraded", f"No naming answer for {_seconds(now - requested_at)}", last, mode
            )
        if result_ok is None:
            if waiting:
                return _entry("active", "Waiting for the first name", last, mode)
            if reported is not None and reported.status != "starting":
                return _entry(reported.status, reported.detail, reported.ts, mode)
            if reported is not None and now - reported.received_at <= STARTUP_GRACE_SECONDS:
                return _entry("starting", "Started; no naming requests yet", reported.ts, mode)
            # Quiet is normal: nothing to name. With no evidence either way, say so.
            return _entry("unknown", "Idle: no naming requests yet", None, mode)
        if result_ok:
            return _entry("active", "Last naming request answered", last, mode)
        return _entry(
            "degraded",
            "Last naming request failed or timed out; class labels are used",
            last,
            mode,
        )

    def _reported_only(self, reported: _Reported | None, what: str) -> dict[str, Any]:
        """A module that reports its own status; unknown until it does."""
        if reported is None:
            return _entry("unknown", f"{what} has not reported a status", None)
        return _entry(reported.status, reported.detail, reported.ts, reported.mode)

    def _hazard(self, reported: _Reported | None) -> dict[str, Any]:
        """Hazard checks publish no health, so only 'not running' can be known."""
        entry = self._not_running(reported)
        if entry is not None:
            return entry
        mode = reported.mode if reported is not None else "unknown"
        detail = "Hazard checks do not report health. No warning does not mean the way is clear"
        return _entry("unknown", detail, None, mode)
