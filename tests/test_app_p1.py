"""Person 1 smoke tests for bus isolation and fake-vision startup."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from app.__main__ import start
from app.bus import Bus
from contracts import FrameResult, HazardEvent


def test_bus_delivers_without_waiting_for_slow_frame_handler() -> None:
    """A blocked subscriber cannot delay publishing or a hazard callback."""
    bus = Bus()
    slow_started = threading.Event()
    release_slow = threading.Event()
    hazard_delivered = threading.Event()

    def slow(_: FrameResult) -> None:
        slow_started.set()
        release_slow.wait(timeout=2.0)

    def fast(_: FrameResult) -> None:
        hazard_delivered.set()

    bus.subscribe(FrameResult, slow)
    bus.subscribe(FrameResult, fast)
    try:
        message = FrameResult(time.time(), 0, None)
        start_time = time.monotonic()
        bus.publish(message)
        assert time.monotonic() - start_time < 0.1
        assert slow_started.wait(timeout=1.0)
        assert hazard_delivered.wait(timeout=1.0)
    finally:
        release_slow.set()
        bus.stop()


def test_fake_vision_starts_on_bus() -> None:
    """The app starts a fake camera without opening a real device."""
    app = start(only="vision", fakes=("vision",))
    arrived = threading.Event()
    frames: list[FrameResult] = []

    def receive(msg: FrameResult) -> None:
        frames.append(msg)
        arrived.set()

    app.bus.subscribe(FrameResult, receive)
    try:
        assert arrived.wait(timeout=2.0)
        assert frames[0].image.shape == (360, 640, 3)
    finally:
        app.stop()


def test_cli_fake_vision_starts() -> None:
    """The documented CLI boots and reports fake camera frames."""
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "app", "--only", "scene", "--fake", "vision"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    ready = threading.Event()
    lines: list[str] = []

    def read_output() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if "Published synthetic FrameResult" in line:
                ready.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        assert ready.wait(timeout=15.0), "".join(lines)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
        reader.join(timeout=5.0)
        proc.stdout.close()



def test_bus_preserves_hazard_event_delivery() -> None:
    """A hazard event gets its own worker, independent of frames."""
    bus = Bus()
    reached = threading.Event()
    bus.subscribe(HazardEvent, lambda _: reached.set())
    try:
        bus.publish(HazardEvent(time.time(), "vehicle", "yolo", 0.8))
        assert reached.wait(timeout=1.0)
    finally:
        bus.stop()


def test_first_fake_hazard_reaches_late_subscriber(monkeypatch: Any) -> None:
    """Registration completes before the first scripted hazard is published."""
    import app.__main__ as entry

    original = entry._register
    received = threading.Event()
    events = []

    def register(name: str, fake: bool, bus: Bus) -> Any:
        if name == "scene":
            def on_hazard(message: HazardEvent) -> None:
                events.append(message)
                received.set()
            bus.subscribe(HazardEvent, on_hazard)
            return None
        return original(name, fake, bus)

    monkeypatch.setattr(entry, "_register", register)
    running = entry.start(only="scene", fakes=("hazard",))
    try:
        assert received.wait(1.0)
        assert (events[0].type, events[0].source) == ("vehicle", "yolo")
    finally:
        running.stop()


def test_crop_recording_uses_separate_sessions(tmp_path: Path) -> None:
    """Repeated app runs preserve earlier crops and stop the writer."""
    from contracts import NameRequest

    for payload in (b"first crop", b"second crop"):
        running = start(only="scene", record_crops=tmp_path)
        recorder = running.instances[0]
        running.bus.publish(NameRequest(time.time(), 1, "bottle", payload))
        deadline = time.monotonic() + 2.0
        while recorder.saved == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        running.stop()
        assert recorder.saved == 1
        assert not recorder._thread.is_alive()
    assert {p.read_bytes() for p in tmp_path.glob("session-*/*.jpg")} == {
        b"first crop", b"second crop",
    }
