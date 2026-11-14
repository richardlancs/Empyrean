"""Person 1 smoke tests for bus isolation and fake-vision startup."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

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
        [sys.executable, "-m", "app", "--fake", "vision"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    # Wait for the line instead of a fixed 1.4 s sleep: cold pyttsx3/pygame
    # startup can take seconds (DEVLOG "Needs attention", Person 4, 2026-11-14).
    lines: list[str] = []
    found = threading.Event()

    def read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if "Published synthetic FrameResult" in line:
                found.set()
                return

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        found.wait(20.0)  # a silent hang still ends at the deadline
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
        reader.join(timeout=5.0)
    output = "".join(lines)
    assert "Published synthetic FrameResult" in output, output


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
