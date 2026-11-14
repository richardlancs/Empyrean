"""Agent 1 preview fixtures: dashboard states for every UI condition the foundation must hold.

Test and preview use only. Each scenario is a function of the server clock so
timestamps stay relative ("2 s ago") however long the preview runs. Shapes follow
the existing DashboardState.snapshot() plus the additive fields Agent 4 owns
(docs/dashboard-redesign: latest_real_warning, current_touch, speech, diagnostics,
capabilities, naming_status, thumbnail_url). None of this is real engine data.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

State = dict[str, Any]
HAZARD_ACTIVE_SECONDS = 5.0
LONG_NAME = "Kirkland Signature Organic Extra Virgin Olive Oil, two litre"


def _diag(now: float, **overrides: Any) -> dict[str, Any]:
    """Diagnostics with every module active unless overridden."""
    base: dict[str, Any] = {
        "camera": {
            "status": "active",
            "detail": "Logitech webcam",
            "last_update_ts": now - 0.1,
            "last_frame_ts": now - 0.1,
            "fps": 14.8,
            "width": 640,
            "height": 360,
        },
        "scene": {"status": "active", "detail": None, "last_update_ts": now - 0.1},
        "naming": {
            "status": "active",
            "detail": "Grok vision",
            "last_update_ts": now - 3,
        },
        "storage": {
            "status": "active",
            "detail": "Tiger Data",
            "last_update_ts": now - 2,
        },
        "audio": {"status": "active", "detail": "Speaker", "last_update_ts": now - 1},
    }
    for key, value in overrides.items():
        base[key] = {**base[key], **value}
    return base


def _caps() -> dict[str, bool]:
    return {
        "last_seen": True,
        "thumbnails": False,
        "overlays": True,
        "speech_status": True,
    }


def _obj(
    oid: int, text: str, cls: str, state: str, seen: float, **extra: Any
) -> dict[str, Any]:
    return {
        "object_id": oid,
        "text": text,
        "class_label": cls,
        "named": text != cls,
        "state": state,
        "last_seen_ts": seen,
        "naming_status": "named" if text != cls else "pending",
        **extra,
    }


def _event(
    eid: int,
    ts: float,
    kind: str,
    text: str,
    detail: str = "",
    simulated: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": eid,
        "ts": ts,
        "kind": kind,
        "type": extra.pop("type", None),
        "text": text,
        "detail": detail,
        "simulated": simulated,
        **extra,
    }


def _warning(
    eid: int, ts: float, text: str = "Stairs", simulated: bool = False
) -> dict[str, Any]:
    return _event(
        eid,
        ts,
        "hazard",
        text,
        "" if simulated else "grok, 82%",
        simulated,
        type="stairs_down",
    )


def _base(now: float, **fields: Any) -> State:
    state: State = {
        "now": now,
        "hazard_active_seconds": HAZARD_ACTIVE_SECONDS,
        "latest_warning": None,
        "latest_real_warning": None,
        "latest_simulated_warning": None,
        "events": [],
        "objects": [],
        "current_touch": None,
        "speech": None,
        "diagnostics": _diag(now),
        "capabilities": _caps(),
    }
    state.update(fields)
    return state


def empty(now: float) -> State:
    """Connected, camera running, nothing in view yet."""
    return _base(now)


def touch(now: float) -> State:
    """A named object is being touched and its name is being spoken."""
    objects = [
        _obj(7, "Heinz ketchup", "bottle", "touching", now),
        _obj(3, "Starbucks coffee cup", "cup", "idle", now),
        _obj(9, "laptop", "laptop", "idle", now - 1.2),
    ]
    return _base(
        now,
        objects=objects,
        current_touch={
            "object_id": 7,
            "text": "Heinz ketchup",
            "state": "touching",
            "ts": now - 0.6,
        },
        speech={
            "text": "Heinz ketchup",
            "status": "speaking",
            "ts": now - 0.4,
            "mode": "real",
            "object_id": 7,
            "source": "audio",
        },
        events=[_event(41, now - 0.6, "touch", "Heinz ketchup")],
    )


def held(now: float) -> State:
    """Still holding the object: no repeated speech."""
    state = touch(now)
    state["objects"][0]["state"] = "held"
    state["current_touch"] = {
        "object_id": 7,
        "text": "Heinz ketchup",
        "state": "held",
        "ts": now - 6,
    }
    state["speech"] = {
        "text": "Heinz ketchup",
        "status": "completed",
        "ts": now - 5,
        "mode": "real",
        "object_id": 7,
    }
    state["events"] = [_event(41, now - 6, "touch", "Heinz ketchup")]
    return state


def retouch(now: float) -> State:
    """Released and touched again: a new touch event, announced again."""
    state = touch(now)
    state["events"] = [
        _event(44, now - 0.5, "touch", "Heinz ketchup"),
        _event(41, now - 9, "touch", "Heinz ketchup"),
    ]
    state["current_touch"]["ts"] = now - 0.5
    return state


def naming_pending(now: float) -> State:
    """Touching an object whose specific name has not arrived yet."""
    return _base(
        now,
        objects=[_obj(12, "bottle", "bottle", "touching", now)],
        current_touch={
            "object_id": 12,
            "text": "bottle",
            "state": "touching",
            "ts": now - 0.3,
        },
        speech={
            "text": "bottle",
            "status": "queued",
            "ts": now - 0.2,
            "mode": "real",
            "object_id": 12,
        },
        events=[_event(50, now - 0.3, "touch", "bottle", "not named yet")],
    )


def naming_fallback(now: float) -> State:
    """Naming failed: the plain class label is the fallback."""
    state = naming_pending(now)
    state["objects"][0]["naming_status"] = "fallback"
    state["speech"] = {
        "text": "bottle",
        "status": "completed",
        "ts": now - 1,
        "mode": "real",
        "object_id": 12,
    }
    state["diagnostics"] = _diag(
        now, naming={"status": "degraded", "detail": "Grok timed out twice"}
    )
    return state


def speech_failed(now: float) -> State:
    """The speak request failed in the audio module."""
    state = touch(now)
    state["speech"] = {
        "text": "Heinz ketchup",
        "status": "failed",
        "ts": now - 0.5,
        "mode": "real",
        "object_id": 7,
    }
    state["diagnostics"] = _diag(
        now, audio={"status": "offline", "detail": "Speaker not connected"}
    )
    return state


def hazard_active(now: float) -> State:
    """A real warning inside its active window."""
    warning = _warning(60, now - 1)
    state = touch(now)
    state.update(latest_warning=warning, latest_real_warning=warning)
    state["events"] = [warning, *state["events"]]
    return state


def hazard_expired(now: float) -> State:
    """The last real warning is older than the active window."""
    warning = _warning(60, now - 40)
    state = empty(now)
    state.update(latest_warning=warning, latest_real_warning=warning, events=[warning])
    return state


def simulated(now: float) -> State:
    """A page-only simulated warning; no real warning."""
    warning = _warning(70, now - 1, simulated=True)
    state = empty(now)
    state.update(
        latest_warning=warning, latest_simulated_warning=warning, events=[warning]
    )
    return state


def real_and_simulated(now: float) -> State:
    """A real warning is still active although a simulation happened after it."""
    real = _warning(60, now - 2)
    sim = _warning(61, now - 1, simulated=True)
    state = touch(now)
    state.update(
        latest_warning=sim, latest_real_warning=real, latest_simulated_warning=sim
    )
    state["events"] = [sim, real, *state["events"]]
    return state


def stale_camera(now: float) -> State:
    """No new camera frame for 12 s."""
    state = touch(now)
    state["diagnostics"] = _diag(
        now,
        camera={
            "status": "degraded",
            "detail": "No new frame",
            "last_frame_ts": now - 12,
            "fps": 0.0,
        },
    )
    return state


def long_names(now: float) -> State:
    """Very long names and many objects, to check wrapping and reflow."""
    objects = [
        _obj(1, LONG_NAME, "bottle", "touching", now),
        *[
            _obj(
                10 + i,
                f"Object number {i} with a fairly long descriptive name",
                "cup",
                "idle",
                now - i,
            )
            for i in range(8)
        ],
        _obj(30, "chair", "chair", "lost", now - 20),
    ]
    return _base(
        now,
        objects=objects,
        current_touch={
            "object_id": 1,
            "text": LONG_NAME,
            "state": "touching",
            "ts": now - 0.5,
        },
        speech={
            "text": LONG_NAME,
            "status": "speaking",
            "ts": now - 0.3,
            "mode": "fake",
            "object_id": 1,
        },
        events=[
            _event(80 + i, now - i * 7, "touch", LONG_NAME if i == 0 else f"Thing {i}")
            for i in range(10)
        ],
    )


def legacy(now: float) -> State:
    """Only the fields today's backend sends; every new field missing."""
    return {
        "now": now,
        "hazard_active_seconds": HAZARD_ACTIVE_SECONDS,
        "latest_warning": None,
        "events": [_event(1, now - 3, "touch", "Heinz ketchup")],
        "objects": [
            {
                "object_id": 7,
                "text": "Heinz ketchup",
                "class_label": "bottle",
                "named": True,
                "state": "touching",
                "last_seen_ts": now,
            },
        ],
    }


SCENARIOS: dict[str, Callable[[float], State]] = {
    "empty": empty,
    "touch": touch,
    "held": held,
    "retouch": retouch,
    "naming-pending": naming_pending,
    "naming-fallback": naming_fallback,
    "speech-failed": speech_failed,
    "hazard-active": hazard_active,
    "hazard-expired": hazard_expired,
    "simulated": simulated,
    "real-and-simulated": real_and_simulated,
    "stale-camera": stale_camera,
    "long-names": long_names,
    "legacy": legacy,
}
