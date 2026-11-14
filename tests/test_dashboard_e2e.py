"""End to end through the real app/ startup, bus and registration, with fake hardware.

Fakes stand in only at the hardware and network edges (camera clip, namer,
store, printed audio, scripted hazards). The scene, the bus, the dashboard
services, the HTTP server and the WebSocket are the real ones.
"""

from __future__ import annotations

import asyncio
import json
import socket
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
import websockets

import app.__main__ as app_main
from dashboard import server as dashboard_server

FAKES = ["vision", "namer", "storage", "audio", "hazard"]


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def running(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, int]]:
    """Start the whole app with fakes; the dashboard is served on a free port."""
    port = _free_port()
    original = dashboard_server.Dashboard.serve

    def serve_on_free_port(self: Any, host: str = "127.0.0.1", port_: int = port) -> bool:
        return original(self, host, port)

    monkeypatch.setattr(dashboard_server.Dashboard, "serve", serve_on_free_port)
    monkeypatch.delenv("TIGER_DATABASE_URL", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    started = app_main.start(fakes=FAKES)
    try:
        _wait(lambda: _get(port, "/api/state") is not None, 10)
        yield started, port
    finally:
        started.stop()


def _wait(predicate: Callable[[], Any], timeout: float) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def _get(port: int, path: str) -> Any:
    try:
        reply = httpx.get(f"http://127.0.0.1:{port}{path}", timeout=2)
    except httpx.HTTPError:
        return None
    return reply.json() if reply.status_code == 200 else None


async def _ws_until(port: int, predicate: Callable[[dict[str, Any]], bool], timeout: float) -> dict[str, Any]:
    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
        async def read() -> dict[str, Any]:
            while True:
                state = json.loads(await ws.recv())
                if predicate(state):
                    return state

        return await asyncio.wait_for(read(), timeout)


def test_engine_events_reach_the_page_over_the_real_websocket(running: tuple[Any, int]) -> None:
    """Scripted frames -> real scene -> touch, naming, fake speech and health over /ws."""
    _, port = running

    def ready(state: dict[str, Any]) -> bool:
        touch = state.get("current_touch")
        return bool(
            touch
            and state["diagnostics"]["camera"]["status"] == "active"
            and state.get("speech")
            and state["objects"]
        )

    state = asyncio.run(_ws_until(port, ready, 20))
    camera = state["diagnostics"]["camera"]
    assert camera["mode"] == "fake" and "fake" in camera["detail"]
    assert camera["width"] == 640 and camera["height"] == 360 and camera["fps"]
    assert state["current_touch"]["state"] in ("touching", "held")
    assert state["speech"]["mode"] == "fake"  # printed speech is never shown as real
    assert state["diagnostics"]["storage"]["mode"] == "fake"
    assert state["diagnostics"]["audio"]["mode"] == "fake"
    assert state["diagnostics"]["scene"]["mode"] == "real"
    assert state["capabilities"] == {
        "last_seen": True, "thumbnails": True, "overlays": True, "speech_status": True,
    }
    statuses = {o["naming_status"] for o in state["objects"]}
    assert statuses <= {"pending", "named", "fallback", "failed", "unknown"}


def test_last_touch_search_round_trip_and_concurrency(running: tuple[Any, int]) -> None:
    """API -> service -> bus -> fake store -> LastSeenResult -> correlated answers."""
    _, port = running
    touch = _wait(lambda: (_get(port, "/api/state") or {}).get("current_touch"), 20)
    base = f"http://127.0.0.1:{port}"
    ids = {
        query: httpx.post(f"{base}/api/last-seen", json={"query": query}).json()["request_id"]
        for query in (touch["class_label"], "zebra")
    }

    def finished(request_id: str) -> dict[str, Any] | None:
        body = _get(port, f"/api/last-seen/{request_id}")
        return body if body and body["status"] != "pending" else None

    found = _wait(lambda: finished(ids[touch["class_label"]]), 5)
    missing = _wait(lambda: finished(ids["zebra"]), 5)
    assert found["status"] == "found" and found["matched_at"] is not None
    assert found["matched_at"] >= touch["ts"] - 0.001
    assert found["answer"] and found["answer"].endswith(".")
    assert missing["status"] == "not_found" and missing["answer"] == "I have not seen that."


def test_simulated_alert_on_the_live_app_publishes_nothing(running: tuple[Any, int]) -> None:
    """POST /api/simulate-alert on the running app: no HazardEvent, no stored hazard row.

    The scripted hazard fake keeps publishing real HazardEvents, so the check is
    that every stored hazard row matches a real bus HazardEvent and none of them
    is the simulated warning.
    """
    started, port = running
    from contracts import HazardEvent
    from fakes.storage.fake_store import FakeStore

    store = next(i for i in started.instances if isinstance(i, FakeStore))
    seen: list[Any] = []
    started.bus.subscribe(HazardEvent, seen.append)
    time.sleep(0.2)
    reply = httpx.post(f"http://127.0.0.1:{port}/api/simulate-alert").json()
    simulated = reply["latest_simulated_warning"]
    assert simulated["simulated"] is True and simulated["source"] == "simulation"
    time.sleep(0.5)
    assert all(abs(m.ts - simulated["ts"]) > 1e-6 for m in seen)
    stored = {round(e.ts, 6) for e in store.hazard_events}
    assert round(simulated["ts"], 6) not in stored
    assert all(e.source in ("yolo", "grok") for e in store.hazard_events)
    real = reply["latest_real_warning"]
    assert real is None or real["simulated"] is False


def test_two_viewers_get_their_own_overlays_from_the_live_server(running: tuple[Any, int]) -> None:
    """Two concurrent /video streams with different options both stream JPEGs."""
    _, port = running
    _wait(lambda: (_get(port, "/api/state") or {}).get("objects"), 10)

    def first_jpeg(query: str) -> bytes:
        with httpx.stream("GET", f"http://127.0.0.1:{port}/video?{query}", timeout=5) as reply:
            assert reply.status_code == 200
            data = b""
            for chunk in reply.iter_bytes():
                data += chunk
                start = data.find(b"\xff\xd8")
                end = data.find(b"\xff\xd9", start)
                if start >= 0 and end > start:
                    return data[start:end + 2]
        raise AssertionError("no JPEG")

    plain = first_jpeg("boxes=0&hands=0&labels=0")
    selected = first_jpeg("selected_id=1")
    assert plain != selected
