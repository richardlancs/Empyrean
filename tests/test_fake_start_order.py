"""Scripted fakes publish only after every consumer has subscribed, with current times."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

import app.__main__ as app_main
from contracts import HazardEvent, SceneSnapshot
from fakes.hazard.fake_hazard import SCRIPT, FakeHazard
from fakes.scene.script import scripted_messages
from fakes.vision.fake_vision import FakeVision


def test_deferred_fakes_publish_nothing_until_started() -> None:
    """register(bus, start=False) creates the publisher without publishing."""
    published: list[Any] = []
    hazard = FakeHazard(published.append, start=False)
    vision = FakeVision(published.append, start=False)
    time.sleep(0.3)
    assert published == []
    hazard.start()
    deadline = time.monotonic() + 2
    while not published and time.monotonic() < deadline:
        time.sleep(0.01)
    hazard.stop()
    vision.stop()  # stopping a publisher that never started is safe
    assert isinstance(published[0], HazardEvent)


def test_first_scripted_hazard_reaches_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Through the real app.start: audio receives the script's very first hazard."""
    from audio.audio import AudioManager

    received: list[tuple[str, str]] = []
    first = threading.Event()
    original = AudioManager.on_hazard

    def record(self: AudioManager, msg: HazardEvent) -> None:
        received.append((msg.type, msg.source))
        first.set()
        original(self, msg)

    monkeypatch.setattr(AudioManager, "on_hazard", record)
    monkeypatch.setattr(app_main, "MODULES", ("hazard", "audio"))
    running = app_main.start(fakes=("hazard", "audio"))
    try:
        assert first.wait(5.0)
    finally:
        running.stop()
    kind, source, _confidence = SCRIPT[0]
    assert received[0] == (kind, source)


def test_fake_scene_uses_current_timestamps() -> None:
    """The scripted scene starts now, not at a fixed date in 2025."""
    before = time.time()
    messages = scripted_messages()
    snapshots = [m for _t, m in messages if isinstance(m, SceneSnapshot)]
    assert before - 1 <= snapshots[0].ts <= time.time() + 1
    assert all(m.ts >= snapshots[0].ts for _t, m in messages)
    fixed = scripted_messages(start_ts=1000.0)
    assert next(m for _t, m in fixed if isinstance(m, SceneSnapshot)).ts == 1000.0


def test_crop_recorder_subscribes_first_and_saves_crops(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--record-crops (from main): the recorder is registered before any module and saves crops."""
    from contracts import NameRequest
    from fakes.namer.crop_recorder import CropRecorder

    monkeypatch.setattr(app_main, "MODULES", ("hazard",))
    running = app_main.start(fakes=("hazard",), record_crops=tmp_path)
    try:
        assert isinstance(running.instances[0], CropRecorder)
        assert NameRequest in running.bus._subscribers
        running.bus.publish(NameRequest(time.time(), 7, "bottle", b"\xff\xd8fake-jpeg"))
        recorder = running.instances[0]
        deadline = time.monotonic() + 3
        while recorder.saved < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        running.stop()
    sessions = [p for p in tmp_path.iterdir() if p.name.startswith("session-")]
    assert len(sessions) == 1
    assert (sessions[0] / "7-1.jpg").read_bytes() == b"\xff\xd8fake-jpeg"
