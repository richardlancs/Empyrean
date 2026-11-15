"""Regular/Demo switching through the dashboard: service, API, and the real app with fake vision."""

from __future__ import annotations

import socket
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import app.__main__ as app_main
from config import MODE_SWITCH_TIMEOUT_SECONDS
from contracts import DetectorStatus, ModeChange, SpeakRequest
from dashboard import DashboardState, create_app, register
from dashboard import server as dashboard_server

NOW = 1_800_000_000.0


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


class SyncBus:
    def __init__(self) -> None:
        self.handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.published: list[Any] = []

    def subscribe(self, t: type, h: Callable[[Any], None]) -> None:
        self.handlers[t].append(h)

    def publish(self, msg: Any) -> None:
        self.published.append(msg)
        for h in list(self.handlers.get(type(msg), [])):
            h(msg)


def status(state: str, active: str, request_id: str | None = None, **kw: Any) -> DetectorStatus:
    return DetectorStatus(ts=NOW, state=state, active_mode=active, detector=f"{active} detector",
                          request_id=request_id, **kw)


@pytest.fixture
def setup() -> tuple[TestClient, SyncBus, Any, Clock]:
    clock = Clock()
    bus = SyncBus()
    dashboard = register(bus, DashboardState(clock=clock), serve=False)
    dashboard.detector_mode._clock = clock
    return TestClient(create_app(dashboard.state)), bus, dashboard, clock


def detector(client: TestClient) -> dict[str, Any]:
    return client.get("/api/state").json()["detector"]


def modes(bus: SyncBus) -> list[ModeChange]:
    return [m for m in bus.published if isinstance(m, ModeChange)]


def test_unknown_detector_refuses_to_switch(setup: Any) -> None:
    """Before vision reports anything the page cannot know what is running."""
    client, bus, _, _ = setup
    assert detector(client)["state"] == "unknown"
    reply = client.post("/api/mode", json={"mode": "demo"})
    assert reply.status_code == 503 and "not reported" in reply.json()["detail"]
    assert modes(bus) == []


def test_active_label_changes_only_after_vision_confirms(setup: Any) -> None:
    """HTTP success means 'requested'; the active mode changes only with DetectorStatus."""
    client, bus, _, _ = setup
    bus.publish(status("active", "actual", demo_available=True))
    reply = client.post("/api/mode", json={"mode": "demo"})
    assert reply.status_code == 202
    request_id = reply.json()["request_id"]
    (sent,) = modes(bus)
    assert (sent.mode, sent.request_id) == ("demo", request_id)
    d = detector(client)
    assert (d["state"], d["active_mode"], d["switching_to"]) == ("switching", "actual", "demo")
    bus.publish(status("switching", "actual", request_id, requested_mode="demo"))
    assert detector(client)["active_mode"] == "actual"
    bus.publish(status("active", "demo", request_id, demo_kind="trained", checkpoint="demo-yolo11s.pt"))
    d = detector(client)
    assert (d["state"], d["active_mode"], d["switching_to"], d["can_switch"]) == ("active", "demo", None, True)


def test_duplicate_and_conflicting_requests_are_refused_while_switching(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("active", "actual"))
    assert client.post("/api/mode", json={"mode": "demo"}).status_code == 202
    for mode in ("demo", "actual"):
        reply = client.post("/api/mode", json={"mode": mode})
        assert reply.status_code == 409 and "already in progress" in reply.json()["detail"]
    assert len(modes(bus)) == 1


def test_requesting_the_active_mode_sends_nothing(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("active", "actual"))
    reply = client.post("/api/mode", json={"mode": "actual"})
    assert reply.status_code == 200 and reply.json()["state"] == "active"
    assert modes(bus) == []


def test_failure_keeps_regular_and_explains(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("active", "actual"))
    rid = client.post("/api/mode", json={"mode": "demo"}).json()["request_id"]
    bus.publish(status("failed", "actual", rid, requested_mode="demo", demo_available=False,
                       message="No demo-trained checkpoint is installed."))
    d = detector(client)
    assert (d["state"], d["active_mode"], d["failed_mode"]) == ("failed", "actual", "demo")
    assert "No demo-trained checkpoint" in d["message"] and d["can_switch"] is True


def test_timeout_then_a_late_acknowledgement_shows_the_truth(setup: Any) -> None:
    client, bus, dashboard, clock = setup
    bus.publish(status("active", "actual"))
    rid = client.post("/api/mode", json={"mode": "demo"}).json()["request_id"]
    clock.now += MODE_SWITCH_TIMEOUT_SECONDS + 1
    dashboard.detector_mode.expire()
    d = detector(client)
    assert (d["state"], d["active_mode"]) == ("failed", "actual") and "did not confirm" in d["message"]
    bus.publish(status("active", "demo", rid))  # the late answer is still the truth
    d = detector(client)
    assert (d["state"], d["active_mode"]) == ("active", "demo")


def test_a_stale_acknowledgement_never_shows_the_wrong_mode(setup: Any) -> None:
    """An older request's answer arriving during a newer switch does not end the newer one."""
    client, bus, _, _ = setup
    bus.publish(status("active", "demo"))
    rid2 = client.post("/api/mode", json={"mode": "actual"}).json()["request_id"]
    bus.publish(status("active", "demo", "older-request"))
    d = detector(client)
    assert (d["state"], d["switching_to"], d["active_mode"]) == ("switching", "actual", "demo")
    bus.publish(status("active", "actual", rid2))
    assert detector(client)["active_mode"] == "actual"


def test_two_clients_share_the_engine_state(setup: Any) -> None:
    client, bus, dashboard, _ = setup
    other = TestClient(create_app(dashboard.state))
    bus.publish(status("active", "actual"))
    client.post("/api/mode", json={"mode": "demo"})
    assert detector(other)["state"] == "switching"
    assert other.post("/api/mode", json={"mode": "demo"}).status_code == 409
    with other.websocket_connect("/ws") as ws:
        assert ws.receive_json()["detector"]["switching_to"] == "demo"


def test_without_an_engine_switching_is_unavailable() -> None:
    client = TestClient(create_app(DashboardState(clock=Clock())))
    reply = client.post("/api/mode", json={"mode": "demo"})
    assert reply.status_code == 503
    assert client.get("/api/state").json()["capabilities"]["mode_switch"] is False


def test_bad_mode_is_rejected(setup: Any) -> None:
    client, _, _, _ = setup
    assert client.post("/api/mode", json={"mode": "regular"}).status_code == 422


# ----------------------- real app, fake vision (no model runs) -----------------------


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _run(monkeypatch: pytest.MonkeyPatch, outcome: str) -> Iterator[tuple[Any, int]]:
    port = _free_port()
    original = dashboard_server.Dashboard.serve
    monkeypatch.setattr(dashboard_server.Dashboard, "serve", lambda self, host="127.0.0.1", port_=port: original(self, host, port))
    monkeypatch.setenv("FAKE_DEMO_DETECTOR", outcome)
    # Long enough that the "not yet confirmed" read cannot lose the race: one local
    # HTTP round trip took about 0.35 s on a Windows laptop, longer than 0.3 s.
    monkeypatch.setenv("FAKE_DETECTOR_SWITCH_SECONDS", "2.0")
    monkeypatch.delenv("TIGER_DATABASE_URL", raising=False)
    running = app_main.start(fakes=["vision", "namer", "storage", "audio"])
    try:
        _wait(lambda: _state(port) is not None, 10)
        yield running, port
    finally:
        running.stop()


def _state(port: int) -> Any:
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/api/state", timeout=2)
    except httpx.HTTPError:
        return None
    return r.json() if r.status_code == 200 else None


def _wait(predicate: Callable[[], Any], timeout: float) -> Any:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


@pytest.fixture
def app_ok(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, int]]:
    yield from _run(monkeypatch, "ok")


@pytest.fixture
def app_missing(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, int]]:
    yield from _run(monkeypatch, "missing")


def test_live_regular_demo_regular_through_the_engine(app_ok: tuple[Any, int]) -> None:
    """API -> service -> bus -> fake vision -> DetectorStatus -> page; source stays the fake clip."""
    running, port = app_ok
    spoken: list[Any] = []
    running.bus.subscribe(SpeakRequest, spoken.append)
    _wait(lambda: (_state(port) or {}).get("detector", {}).get("state") == "active", 5)
    before = _state(port)
    assert before["detector"]["active_mode"] == "actual" and before["detector"]["fake"] is True
    reply = httpx.post(f"http://127.0.0.1:{port}/api/mode", json={"mode": "demo"})
    assert reply.status_code == 202
    pending = _state(port)["detector"]
    assert pending["active_mode"] == "actual"  # not yet confirmed
    assert pending["state"] == "switching" and pending["switching_to"] == "demo"
    after = _wait(lambda: (s := _state(port)) and s["detector"]["active_mode"] == "demo" and s, 5)
    assert after["detector"]["state"] == "active" and after["detector"]["demo_kind"] == "fake"
    assert "No detector" in after["detector"]["detector"]  # never called the trained model
    assert after["diagnostics"]["camera"]["mode"] == "fake"  # the camera source did not change
    assert httpx.post(f"http://127.0.0.1:{port}/api/mode", json={"mode": "actual"}).status_code == 202
    _wait(lambda: (_state(port) or {})["detector"]["active_mode"] == "actual", 5)
    assert spoken == []  # switching never speaks
    assert len(_state(port)["events"]) >= len(before["events"])  # history is untouched


def test_live_missing_checkpoint_fails_and_stays_regular(app_missing: tuple[Any, int]) -> None:
    _, port = app_missing
    _wait(lambda: (_state(port) or {}).get("detector", {}).get("state") == "active", 5)
    assert httpx.post(f"http://127.0.0.1:{port}/api/mode", json={"mode": "demo"}).status_code == 202
    failed = _wait(lambda: (s := _state(port)) and s["detector"]["state"] == "failed" and s, 5)
    assert failed["detector"]["active_mode"] == "actual"
    assert "No demo-trained checkpoint" in failed["detector"]["message"]
