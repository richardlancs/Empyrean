"""The camera demo button exercises the real hazard/audio path."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from test_audio import RecordingAlarm, RecordingSpeaker, wait_for

from app.bus import Bus
from audio.audio import AudioManager
from config import HAZARD_COOLDOWN_SECONDS
from contracts import HazardEvent, SpeakRequest
from dashboard import create_app, register
from dashboard.services.demo_alert import DemoAlertRejected, DemoAlertService
from fakes.storage.fake_store import register as register_store


def test_demo_stairs_alarm_interrupts_speech_and_reaches_storage() -> None:
    """HTTP click fans out to the real audio manager, warning UI and storage."""
    bus = Bus()
    speaker, alarm = RecordingSpeaker(), RecordingAlarm()
    speaker.gate.clear()
    manager = AudioManager(lambda: speaker, alarm, publish=bus.publish)
    bus.subscribe(HazardEvent, manager.on_hazard)
    store = register_store(bus)
    dashboard = register(bus, serve=False)
    client = TestClient(create_app(dashboard.state))
    try:
        manager.on_speak(SpeakRequest(time.time(), "An ordinary answer", "normal", "namer"))
        assert wait_for(lambda: "An ordinary answer" in speaker.started)
        reply = client.post("/api/demo-alert")
        assert reply.status_code == 202
        assert reply.json()["type"] == "stairs_down"
        assert wait_for(lambda: len(alarm.played_at) == 1)
        assert wait_for(lambda: "An ordinary answer" in speaker.cut_off)
        speaker.gate.set()
        assert wait_for(lambda: "Stop. Stairs." in speaker.finished)
        assert wait_for(lambda: len(store.hazard_events) == 1)
        event = store.hazard_events[0]
        assert event.type == "stairs_down" and event.source == "grok"
        assert event.ts == reply.json()["ts"]
        assert wait_for(lambda: dashboard.state.snapshot()["latest_real_warning"] is not None)
        assert dashboard.state.snapshot()["latest_real_warning"]["type"] == "stairs_down"
        assert dashboard.state.snapshot()["latest_simulated_warning"] is None
        assert client.post("/api/demo-alert").status_code == 429
        assert len(alarm.played_at) == 1
        bus.publish(HazardEvent(time.time(), "vehicle", "yolo", 0.99))
        assert wait_for(lambda: len(alarm.played_at) == 2)
        assert wait_for(lambda: "Stop. Vehicle." in speaker.finished)
    finally:
        speaker.gate.set()
        manager.stop()
        dashboard.stop()
        bus.stop()


def test_demo_alarm_requires_a_bus() -> None:
    """A standalone dashboard cannot claim to have sent an audible alarm."""
    response = TestClient(create_app()).post("/api/demo-alert")
    assert response.status_code == 503
    assert "full app" in response.json()["detail"]


def test_demo_alarm_can_repeat_after_shared_cooldown() -> None:
    """A repeat request is accepted as soon as the configured cooldown expires."""
    now = [100.0]
    events: list[HazardEvent] = []
    service = DemoAlertService(events.append, clock=lambda: now[0])
    service.request()
    with pytest.raises(DemoAlertRejected) as rejected:
        service.request()
    assert rejected.value.status_code == 429
    now[0] += HAZARD_COOLDOWN_SECONDS
    service.request()
    assert [event.type for event in events] == ["stairs_down", "stairs_down"]
