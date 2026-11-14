"""Dashboard read model: touch, naming, speech, warnings and measured health."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

import numpy as np

from config import (
    CAMERA_STALE_SECONDS,
    HAZARD_COOLDOWN_SECONDS,
    PROCESS_HEIGHT,
    PROCESS_WIDTH,
)
from contracts import (
    FrameResult,
    HazardEvent,
    ModuleStatus,
    NameRequest,
    NameResult,
    SceneObject,
    SceneSnapshot,
    SpeechStatus,
    TouchEvent,
)
from dashboard import DashboardState, register

NOW = 1_800_000_000.0
BOX = (100.0, 80.0, 200.0, 240.0)
CUP = (320.0, 150.0, 420.0, 290.0)
ORIGINAL_KEYS = {"now", "hazard_active_seconds", "latest_warning", "events", "objects"}
ADDED_KEYS = {
    "latest_real_warning",
    "latest_simulated_warning",
    "current_touch",
    "last_touch",
    "speech",
    "diagnostics",
    "capabilities",
}


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, start: float = NOW) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class SyncBus:
    """Deliver each message straight to its subscribers and record it."""

    def __init__(self) -> None:
        self.handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.published: list[Any] = []

    def subscribe(self, msg_type: type, handler: Callable[[Any], None]) -> None:
        self.handlers[msg_type].append(handler)

    def publish(self, msg: Any) -> None:
        self.published.append(msg)
        for handler in list(self.handlers.get(type(msg), [])):
            handler(msg)


def _touch(kind: str, object_id: int = 1, name: str = "", label: str = "bottle",
           ts: float = NOW) -> TouchEvent:
    return TouchEvent(ts, object_id, label, name, kind, BOX)  # type: ignore[arg-type]


def _scene(*objects: SceneObject, frame_id: int = 1) -> SceneSnapshot:
    return SceneSnapshot(NOW, frame_id, list(objects))


def _frame(frame_id: int, ts: float) -> FrameResult:
    image = np.zeros((PROCESS_HEIGHT, PROCESS_WIDTH, 3), dtype=np.uint8)
    return FrameResult(ts=ts, frame_id=frame_id, image=image)


def _speech(speech_id: int, status: str, object_id: int | None = 1, ts: float = NOW,
            mode: str = "real", text: str = "Heinz ketchup") -> SpeechStatus:
    kind = "touch" if object_id is not None else "hazard"
    return SpeechStatus(ts, speech_id, text, status, mode, kind, object_id, "scene", "")  # type: ignore[arg-type]


def test_snapshot_keeps_original_fields_and_adds_the_agreed_ones() -> None:
    """Old keys are still there with the same meaning; the new ones are present and empty."""
    snap = DashboardState(clock=Clock()).snapshot()
    assert ORIGINAL_KEYS | ADDED_KEYS <= set(snap)
    assert snap["latest_warning"] is None and snap["events"] == [] and snap["objects"] == []
    assert snap["current_touch"] is None and snap["speech"] is None
    assert set(snap["diagnostics"]) >= {"camera", "scene", "naming", "storage", "audio"}
    for entry in snap["diagnostics"].values():
        assert {"status", "detail", "last_update_ts"} <= set(entry)
    camera = snap["diagnostics"]["camera"]
    assert camera["last_frame_ts"] is None and camera["fps"] is None
    assert camera["width"] is None and camera["height"] is None
    assert set(snap["capabilities"]) == {"last_seen", "thumbnails", "overlays", "speech_status", "mode_switch"}
    # Nothing was instrumented, so nothing claims to be healthy.
    assert all(e["status"] != "active" for e in snap["diagnostics"].values())
    assert snap["capabilities"]["speech_status"] is False


def test_touch_hold_release_retouch_drives_current_touch() -> None:
    """touching -> held (from the scene) -> released (null) -> touching again."""
    clock = Clock()
    state = DashboardState(clock=clock)
    state.on_touch(_touch("touch", name="Heinz ketchup"))
    current = state.snapshot()["current_touch"]
    assert (current["object_id"], current["text"], current["state"]) == (1, "Heinz ketchup", "touching")
    assert current["ts"] == NOW

    state.on_scene(_scene(SceneObject(1, "bottle", "Heinz ketchup", "held", BOX, NOW)))
    assert state.snapshot()["current_touch"]["state"] == "held"

    state.on_touch(_touch("release", ts=NOW + 2))
    snap = state.snapshot()
    assert snap["current_touch"] is None
    assert snap["last_touch"]["state"] == "released" and snap["last_touch"]["released_ts"] == NOW + 2
    # A late snapshot still saying "held" does not resurrect a released touch.
    state.on_scene(_scene(SceneObject(1, "bottle", "Heinz ketchup", "held", BOX, NOW)))
    assert state.snapshot()["current_touch"] is None

    state.on_touch(_touch("touch", name="Heinz ketchup", ts=NOW + 5))
    snap = state.snapshot()
    assert snap["current_touch"]["state"] == "touching" and snap["current_touch"]["ts"] == NOW + 5
    assert [e["kind"] for e in snap["events"]] == ["touch", "touch"]  # releases not logged


def test_release_of_one_hand_keeps_the_other_touch_current() -> None:
    """Two touched objects: releasing the newer one shows the one still in a hand."""
    state = DashboardState(clock=Clock())
    state.on_touch(_touch("touch", object_id=1, name="Heinz ketchup"))
    state.on_touch(_touch("touch", object_id=2, label="cup", ts=NOW + 1))
    state.on_touch(_touch("release", object_id=2, label="cup", ts=NOW + 2))
    assert state.snapshot()["current_touch"]["object_id"] == 1


def test_delayed_name_and_naming_status_lifecycle() -> None:
    """Unnamed touch -> pending request -> late name; failed and generic answers stay distinct."""
    clock = Clock()
    state = DashboardState(clock=clock)
    state.on_scene(_scene(SceneObject(1, "bottle", "", "idle", BOX, NOW),
                          SceneObject(2, "cup", "", "idle", CUP, NOW),
                          SceneObject(3, "chair", "", "new", CUP, NOW)))
    statuses = {o["object_id"]: o["naming_status"] for o in state.snapshot()["objects"]}
    assert statuses == {1: "unknown", 2: "unknown", 3: "unknown"}  # no request seen yet

    state.on_name_request(NameRequest(NOW, 1, "bottle", b"\xff\xd8\xff\xd9"))
    state.on_name_request(NameRequest(NOW, 2, "cup", b"\xff\xd8\xff\xd9"))
    state.on_touch(_touch("touch", object_id=1))
    snap = state.snapshot()
    assert snap["current_touch"]["text"] == "bottle"
    assert snap["current_touch"]["naming_status"] == "pending"

    clock.now += 1.0
    state.on_name_result(NameResult(clock.now, 1, "Heinz ketchup", True))
    state.on_name_result(NameResult(clock.now, 2, "", False))
    snap = state.snapshot()
    assert snap["current_touch"]["text"] == "Heinz ketchup"
    assert snap["current_touch"]["naming_status"] == "named"
    by_id = {o["object_id"]: o for o in snap["objects"]}
    assert by_id[2]["naming_status"] == "failed" and by_id[2]["text"] == "cup"

    # The scene retries; a generic answer (ok, empty) is a fallback, not a failure.
    state.on_name_request(NameRequest(clock.now, 2, "cup", b"\xff\xd8\xff\xd9"))
    assert {o["object_id"]: o["naming_status"] for o in state.snapshot()["objects"]}[2] == "pending"
    state.on_name_result(NameResult(clock.now, 2, "", True))
    assert {o["object_id"]: o["naming_status"] for o in state.snapshot()["objects"]}[2] == "fallback"


def test_pending_name_with_no_answer_stops_claiming_pending() -> None:
    """A request that never got an answer is not shown as in progress forever."""
    clock = Clock()
    state = DashboardState(clock=clock)
    state.on_scene(_scene(SceneObject(1, "bottle", "", "idle", BOX, NOW)))
    state.on_name_request(NameRequest(NOW, 1, "bottle", b"\xff\xd8\xff\xd9"))
    assert state.snapshot()["objects"][0]["naming_status"] == "pending"
    clock.now += 60
    assert state.snapshot()["objects"][0]["naming_status"] == "unknown"


def test_speech_lifecycle_is_ordered_and_tied_to_the_current_touch() -> None:
    """queued -> speaking -> completed; a late out-of-order step does not move it back."""
    state = DashboardState(clock=Clock())
    state.on_touch(_touch("touch", name="Heinz ketchup"))
    state.on_speech(_speech(1, "queued"))
    state.on_speech(_speech(1, "speaking"))
    assert state.snapshot()["current_touch"]["speech"]["status"] == "speaking"
    state.on_speech(_speech(1, "completed"))
    state.on_speech(_speech(1, "speaking"))  # arrives late
    snap = state.snapshot()
    assert snap["speech"]["status"] == "completed"
    assert snap["current_touch"]["speech"]["status"] == "completed"
    assert snap["capabilities"]["speech_status"] is True
    assert snap["speech"]["mode"] == "real"


def test_hazard_phrase_becomes_latest_speech_and_interrupts_touch_speech() -> None:
    """The interrupted touch phrase stays on the touch; the hazard phrase is the latest speech."""
    state = DashboardState(clock=Clock())
    state.on_touch(_touch("touch", name="Heinz ketchup"))
    state.on_speech(_speech(1, "speaking"))
    state.on_hazard(HazardEvent(NOW, "stairs_down", "grok", 0.9))
    state.on_speech(_speech(1, "interrupted"))
    state.on_speech(_speech(2, "queued", object_id=None, text="Stop. Stairs."))
    snap = state.snapshot()
    assert snap["speech"]["text"] == "Stop. Stairs." and snap["speech"]["kind"] == "hazard"
    assert snap["current_touch"]["speech"]["status"] == "interrupted"
    assert snap["latest_real_warning"]["active"] is True


def test_simulated_warning_never_replaces_the_real_one() -> None:
    """A simulation after a real hazard leaves latest_real_warning active and unchanged."""
    clock = Clock()
    state = DashboardState(clock=clock)
    state.on_hazard(HazardEvent(NOW, "vehicle", "yolo", 0.91))
    clock.now += 1
    snap = state.simulate_hazard()
    assert snap["latest_real_warning"]["type"] == "vehicle"
    assert snap["latest_real_warning"]["simulated"] is False
    assert snap["latest_real_warning"]["active"] is True
    assert snap["latest_simulated_warning"]["simulated"] is True
    assert snap["latest_simulated_warning"]["source"] == "simulation"
    assert snap["latest_warning"]["simulated"] is True  # compatibility: newest of either
    assert [e["simulated"] for e in snap["events"]] == [True, False]  # both stay visible
    clock.now += HAZARD_COOLDOWN_SECONDS + 1
    assert state.snapshot()["latest_real_warning"]["active"] is False


def test_camera_health_starting_active_stale_offline_and_reconnect() -> None:
    """Camera status comes from frame arrival times and measured capture rate."""
    clock = Clock()
    state = DashboardState(clock=clock)
    state.on_module_status(ModuleStatus(NOW, "vision", "starting", "real", "Started"))
    assert state.snapshot()["diagnostics"]["camera"]["status"] == "starting"

    for i in range(10):  # 5 frames a second for two seconds
        clock.now = NOW + i * 0.2
        state.on_frame(_frame(i, clock.now))
    camera = state.snapshot()["diagnostics"]["camera"]
    assert camera["status"] == "active"
    assert camera["fps"] == 5.0
    assert (camera["width"], camera["height"]) == (PROCESS_WIDTH, PROCESS_HEIGHT)
    assert camera["last_frame_ts"] == NOW + 9 * 0.2

    clock.now += CAMERA_STALE_SECONDS + 0.5
    camera = state.snapshot()["diagnostics"]["camera"]
    assert camera["status"] == "degraded" and "No new frame" in camera["detail"]
    clock.now += 30
    camera = state.snapshot()["diagnostics"]["camera"]
    assert camera["status"] == "offline" and camera["fps"] == 0.0

    for i in range(10, 13):  # frames resume
        clock.now += 0.2
        state.on_frame(_frame(i, clock.now))
    assert state.snapshot()["diagnostics"]["camera"]["status"] == "active"


def test_quiet_scene_is_not_reported_as_failed() -> None:
    """With no frames to process the scene is idle (unknown), not degraded or offline."""
    clock = Clock()
    state = DashboardState(clock=clock)
    state.on_scene(_scene())
    assert state.snapshot()["diagnostics"]["scene"]["status"] == "active"
    clock.now += 60
    scene = state.snapshot()["diagnostics"]["scene"]
    assert scene["status"] == "unknown" and "Idle" in scene["detail"]


def test_module_status_from_app_never_overrides_the_module_itself() -> None:
    """app/'s 'starting' arrives after audio already said it is ready: audio's status wins."""
    state = DashboardState(clock=Clock())
    state.on_module_status(ModuleStatus(NOW, "audio", "active", "fake", "Fake audio"))
    state.on_module_status(ModuleStatus(NOW + 0.1, "audio", "starting", "fake", "Started"))
    audio = state.snapshot()["diagnostics"]["audio"]
    assert (audio["status"], audio["mode"]) == ("active", "fake")


def test_modules_not_started_are_offline_not_unknown() -> None:
    """With --only dashboard, app/ marks the rest 'Not started in this run'."""
    state = DashboardState(clock=Clock())
    for module in ("namer", "storage", "audio"):
        state.on_module_status(ModuleStatus(NOW, module, "offline", "unknown", "Not started in this run"))
    diagnostics = state.snapshot()["diagnostics"]
    for key in ("naming", "storage", "audio"):
        assert diagnostics[key]["status"] == "offline"
        assert diagnostics[key]["detail"] == "Not started in this run"


def test_register_routes_every_message_to_the_read_model() -> None:
    """Through register(bus): touch, naming, speech and status all reach the snapshot."""
    bus = SyncBus()
    dashboard = register(bus, DashboardState(clock=Clock()), serve=False)
    bus.publish(SceneSnapshot(NOW, 1, [SceneObject(1, "bottle", "", "idle", BOX, NOW)]))
    bus.publish(NameRequest(NOW, 1, "bottle", b"\xff\xd8\xff\xd9"))
    bus.publish(_touch("touch"))
    bus.publish(_speech(4, "speaking"))
    bus.publish(ModuleStatus(NOW, "storage", "offline", "real", "TIGER_DATABASE_URL is not set"))
    snap = dashboard.state.snapshot()
    assert snap["current_touch"]["naming_status"] == "pending"
    assert snap["speech"]["speech_id"] == 4
    assert snap["diagnostics"]["storage"]["status"] == "offline"
    assert snap["capabilities"]["last_seen"] is True
    assert bus.published[-1].module == "storage"  # the dashboard itself published nothing
    assert len(bus.published) == 5


def test_hazard_entries_carry_source_and_confidence_and_log_size() -> None:
    """Agent 3's request: source and confidence as fields, plus the server log size."""
    state = DashboardState(clock=Clock())
    state.on_hazard(HazardEvent(NOW, "drop_off", "grok", 0.82))
    state.simulate_hazard()
    snap = state.snapshot()
    real, simulated = snap["latest_real_warning"], snap["latest_simulated_warning"]
    assert (real["source"], real["confidence"], real["detail"]) == ("grok", 0.82, "grok, 82%")
    assert (simulated["source"], simulated["confidence"]) == ("simulation", None)
    assert snap["event_log_size"] == 10
    assert snap["diagnostics"]["camera"]["stale_after_seconds"] == CAMERA_STALE_SECONDS


def test_idle_naming_is_not_failed_and_not_forever_starting() -> None:
    """A started namer with nothing to name: starting at first, then unknown (idle), never failed."""
    clock = Clock()
    state = DashboardState(clock=clock)
    state.on_module_status(ModuleStatus(NOW, "namer", "starting", "fake", "Started with a fake"))
    assert state.snapshot()["diagnostics"]["naming"]["status"] == "starting"
    clock.now += 60
    naming = state.snapshot()["diagnostics"]["naming"]
    assert naming["status"] == "unknown" and "Idle" in naming["detail"]
    state.on_name_request(NameRequest(clock.now, 1, "bottle", b"\xff\xd8\xff\xd9"))
    state.on_name_result(NameResult(clock.now, 1, "Heinz ketchup", True))
    assert state.snapshot()["diagnostics"]["naming"]["status"] == "active"


def test_search_capability_is_false_when_storage_is_not_running() -> None:
    """--only dashboard: the page can say search is unavailable instead of waiting 8 s."""
    bus = SyncBus()
    dashboard = register(bus, DashboardState(clock=Clock()), serve=False)
    assert dashboard.state.snapshot()["capabilities"]["last_seen"] is True
    bus.publish(ModuleStatus(NOW, "storage", "offline", "unknown", "Not started in this run"))
    assert dashboard.state.snapshot()["capabilities"]["last_seen"] is False
    # A running store that is merely offline (database down) still answers "unavailable".
    bus.publish(ModuleStatus(NOW, "storage", "offline", "real", "Tiger Data unavailable"))
    assert dashboard.state.snapshot()["capabilities"]["last_seen"] is True
