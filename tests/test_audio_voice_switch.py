"""AudioManager applies VoiceChange between phrases and confirms with VoiceStatus.

No sound device is used: the speaker and alarm are recording stand-ins.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from audio import audio as audio_module
from audio.audio import HAZARD_PRERENDER, AudioManager
from audio.voices import PRESETS, piper_voice_id
from contracts import (
    HazardEvent,
    ModuleStatus,
    NameResult,
    SpeakRequest,
    SpeechStatus,
    TouchEvent,
    VoiceChange,
    VoiceStatus,
)

PREMIUM = {p.key: (piper_voice_id(p), p.voice_name) for p in PRESETS}
KEYS = [
    "alba",
    "kristin",
    "northern",
    "cori",
    "lessac",
    "huayan",
    "claude",
    "siwis",
    "priyamvada",
]
SAMANTHA = ("com.apple.voice.compact.en-US.Samantha", "Samantha")


class VoiceSpeaker:
    """Records phrases and voice switches. While gated, holds each phrase."""

    mode = "real"

    def __init__(self, voices: list[tuple[str, str]] | None = None) -> None:
        self.voices = list(PREMIUM.values()) + [SAMANTHA] if voices is None else voices
        self.started: list[str] = []
        self.finished: list[str] = []
        self.cut_off: list[str] = []
        self.set_calls: list[str | None] = []
        self.voice_at_start: list[str | None] = []
        self.saying = threading.Event()
        self.gate = threading.Event()
        self.gate.set()
        self.lock = threading.Lock()

    def installed_voices(self) -> list[tuple[str, str]]:
        """Return the scripted voice list."""
        return list(self.voices)

    def set_voice(self, voice_id: str | None) -> None:
        """Record the switch; it must never happen mid-phrase."""
        assert not self.saying.is_set(), "voice switched while speaking"
        with self.lock:
            self.set_calls.append(voice_id)

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Record text, waiting on the gate while honouring should_stop."""
        self.saying.set()
        try:
            with self.lock:
                self.started.append(text)
                self.voice_at_start.append(
                    self.set_calls[-1] if self.set_calls else None
                )
            while not self.gate.wait(0.005):
                if should_stop():
                    with self.lock:
                        self.cut_off.append(text)
                    return
            with self.lock:
                self.finished.append(text)
        finally:
            self.saying.clear()


class RecordingAlarm:
    """Counts plays."""

    duration = 0.0
    mode = "real"

    def __init__(self) -> None:
        self.plays = 0

    def play(self) -> None:
        """Count one play."""
        self.plays += 1

    def close(self) -> None:
        """Nothing to release."""


def wait_for(condition: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Poll until condition() is true or timeout passes."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


def statuses(published: list[Any]) -> list[VoiceStatus]:
    """Return the VoiceStatus messages published so far."""
    return [m for m in list(published) if isinstance(m, VoiceStatus)]


@pytest.fixture
def speaker() -> VoiceSpeaker:
    """A speaker with every preset installed."""
    return VoiceSpeaker()


@pytest.fixture
def alarm() -> RecordingAlarm:
    """An alarm with no beep length."""
    return RecordingAlarm()


@pytest.fixture
def published() -> list[Any]:
    """Everything the manager publishes."""
    return []


@pytest.fixture
def manager(
    speaker: VoiceSpeaker, alarm: RecordingAlarm, published: list[Any]
) -> Iterator[AudioManager]:
    """A manager that has reported its startup voice."""
    mgr = AudioManager(lambda: speaker, alarm, publish=published.append)
    assert wait_for(lambda: len(statuses(published)) == 1)
    yield mgr
    speaker.gate.set()
    mgr.stop()


def test_startup_publishes_active_voice_without_sample(
    manager: AudioManager, speaker: VoiceSpeaker, published: list[Any]
) -> None:
    """At startup: one active VoiceStatus for alba, the voice set, nothing spoken."""
    time.sleep(0.05)
    [status] = statuses(published)
    assert status.state == "active"
    assert status.active_voice == "alba" and status.label == "Alba"
    assert status.quality == "enhanced"  # alba is a medium Piper model
    assert list(status.voices) == KEYS
    assert status.voices["cori"] == "Cori"
    assert status.installed == KEYS
    assert status.request_id is None
    assert speaker.set_calls == [PREMIUM["alba"][0]]
    assert speaker.started == []
    module = [m for m in published if isinstance(m, ModuleStatus)]
    assert module and module[0].status == "active"


def test_startup_voice_from_constructor(
    speaker: VoiceSpeaker, alarm: RecordingAlarm, published: list[Any]
) -> None:
    """The voice argument picks the startup preset."""
    mgr = AudioManager(
        lambda: speaker, alarm, publish=published.append, voice="lessac"
    )
    try:
        assert wait_for(lambda: len(statuses(published)) == 1)
        assert statuses(published)[0].active_voice == "lessac"
        assert speaker.set_calls == [PREMIUM["lessac"][0]]
    finally:
        mgr.stop()


def test_switch_confirms_then_says_sample(
    manager: AudioManager, speaker: VoiceSpeaker, published: list[Any]
) -> None:
    """A switch sets the voice, confirms with the request id, then says the sample line."""
    manager.on_voice_change(VoiceChange(1.0, "cori", "r1"))
    assert wait_for(lambda: speaker.finished == ["This is Cori."])
    confirm = statuses(published)[-1]
    assert confirm.state == "active"
    assert confirm.active_voice == "cori" and confirm.label == "Cori"
    assert confirm.request_id == "r1" and confirm.requested_voice == "cori"
    assert speaker.set_calls[-1] == PREMIUM["cori"][0]
    assert speaker.voice_at_start == [PREMIUM["cori"][0]]
    sample = [
        m
        for m in published
        if isinstance(m, SpeechStatus) and m.text == "This is Cori."
    ]
    assert sample[0].kind == "answer" and sample[0].source == "audio"


def test_switch_waits_for_current_phrase(
    manager: AudioManager, speaker: VoiceSpeaker, published: list[Any]
) -> None:
    """A long answer is not cut off; the switch applies once it ends."""
    speaker.gate.clear()
    manager.on_speak(
        SpeakRequest(time.time(), "Your keys are on the table.", "normal", "namer")
    )
    assert wait_for(lambda: speaker.started == ["Your keys are on the table."])
    manager.on_voice_change(VoiceChange(1.0, "kristin", "r1"))
    time.sleep(0.1)
    assert speaker.set_calls == [PREMIUM["alba"][0]]
    assert len(statuses(published)) == 1
    speaker.gate.set()
    assert wait_for(
        lambda: speaker.finished == ["Your keys are on the table.", "This is Kristin."]
    )
    assert speaker.cut_off == []
    assert speaker.set_calls[-1] == PREMIUM["kristin"][0]
    assert statuses(published)[-1].active_voice == "kristin"


def test_hazard_during_switch_outranks_sample(
    manager: AudioManager, speaker: VoiceSpeaker, alarm: RecordingAlarm
) -> None:
    """A hazard during a pending switch beeps at once and is spoken before the switch runs.

    Applying a switch may load a voice model (about 1 s), so it never runs ahead
    of a waiting hazard phrase; the phrase uses the voice already loaded.
    """
    speaker.gate.clear()
    manager.on_speak(SpeakRequest(time.time(), "A long answer.", "normal", "namer"))
    assert wait_for(lambda: speaker.started == ["A long answer."])
    manager.on_voice_change(VoiceChange(1.0, "northern", "r1"))
    manager.on_hazard(HazardEvent(time.time(), "stairs_down", "grok", 0.9))
    assert alarm.plays == 1
    assert wait_for(lambda: len(speaker.started) == 2)
    assert speaker.started[1] == "Stop. Stairs."
    assert speaker.voice_at_start[1] == PREMIUM["alba"][0]
    speaker.gate.set()
    assert wait_for(lambda: "Stop. Stairs." in speaker.finished)
    assert speaker.cut_off == ["A long answer."]
    # The switch is applied once the hazard phrase is done.
    assert wait_for(lambda: speaker.set_calls[-1:] == [PREMIUM["northern"][0]])


def test_hazard_right_after_switch_cuts_sample(
    manager: AudioManager, speaker: VoiceSpeaker, alarm: RecordingAlarm
) -> None:
    """A hazard while the sample line plays cuts it off; the phrase follows in the new voice."""
    speaker.gate.clear()
    manager.on_voice_change(VoiceChange(1.0, "northern", "r1"))
    assert wait_for(lambda: speaker.started == ["This is Northern English."])
    manager.on_hazard(HazardEvent(time.time(), "vehicle", "yolo", 0.9))
    assert alarm.plays == 1
    assert wait_for(lambda: speaker.started[-1:] == ["Stop. Vehicle."])
    assert speaker.cut_off == ["This is Northern English."]
    assert speaker.voice_at_start[-1] == PREMIUM["northern"][0]


def test_newest_pending_switch_wins(
    manager: AudioManager, speaker: VoiceSpeaker, published: list[Any]
) -> None:
    """With speech busy, the newest of two requests is the one applied."""
    speaker.gate.clear()
    manager.on_speak(SpeakRequest(time.time(), "Busy.", "normal", "namer"))
    assert wait_for(lambda: speaker.started == ["Busy."])
    manager.on_voice_change(VoiceChange(1.0, "kristin", "r1"))
    manager.on_voice_change(VoiceChange(1.1, "lessac", "r2"))
    speaker.gate.set()
    assert wait_for(lambda: speaker.finished == ["Busy.", "This is Lessac."])
    time.sleep(0.05)
    confirmed = [s for s in statuses(published) if s.request_id is not None]
    assert [(s.active_voice, s.request_id) for s in confirmed] == [("lessac", "r2")]
    assert PREMIUM["kristin"][0] not in speaker.set_calls


def test_unknown_voice_fails_without_change(
    manager: AudioManager, speaker: VoiceSpeaker, published: list[Any]
) -> None:
    """An unknown key is refused with a failed VoiceStatus; the voice stays."""
    manager.on_voice_change(VoiceChange(1.0, "bob", "r2"))
    assert wait_for(lambda: len(statuses(published)) == 2)
    failed = statuses(published)[-1]
    assert failed.state == "failed"
    assert failed.requested_voice == "bob" and failed.request_id == "r2"
    assert failed.active_voice == "alba" and failed.label == "Alba"
    assert "Unknown voice" in failed.detail
    time.sleep(0.05)
    assert speaker.set_calls == [PREMIUM["alba"][0]]
    assert speaker.started == []


def test_missing_voice_reports_fallback(
    alarm: RecordingAlarm, published: list[Any]
) -> None:
    """Without the preset's voice: Samantha stands in, reported fallback and degraded."""
    speaker = VoiceSpeaker(voices=[SAMANTHA])
    mgr = AudioManager(lambda: speaker, alarm, publish=published.append)
    try:
        assert wait_for(lambda: len(statuses(published)) == 1)
        status = statuses(published)[0]
        assert status.quality == "fallback" and status.installed == []
        assert status.active_voice == "alba"
        assert "Samantha" in status.detail
        assert speaker.set_calls == [SAMANTHA[0]]
        module = [m for m in published if isinstance(m, ModuleStatus)]
        assert module[0].status == "degraded"
        assert "not installed" in module[0].detail
        assert "Samantha" in module[0].detail
    finally:
        mgr.stop()


def test_voice_handler_never_waits_on_speech(
    manager: AudioManager, speaker: VoiceSpeaker
) -> None:
    """on_voice_change returns at once while the speaker is busy."""
    speaker.gate.clear()
    manager.on_speak(SpeakRequest(time.time(), "Busy.", "normal", "namer"))
    assert wait_for(lambda: speaker.started == ["Busy."])
    for key in ("kristin", "bob"):
        start = time.monotonic()
        manager.on_voice_change(VoiceChange(time.time(), key, None))
        assert time.monotonic() - start < 0.05


class RecordingBus:
    """Records subscriptions in order."""

    def __init__(self) -> None:
        self.subscriptions: list[type] = []
        self.published: list[Any] = []

    def subscribe(self, message_type: type, handler: Callable[[Any], None]) -> None:
        """Record one subscription."""
        self.subscriptions.append(message_type)

    def publish(self, message: Any) -> None:
        """Record a published message."""
        self.published.append(message)


def test_register_subscribes_voice_change_after_hazard(
    monkeypatch: pytest.MonkeyPatch, speaker: VoiceSpeaker
) -> None:
    """register(bus) keeps HazardEvent first and adds VoiceChange last; AUDIO_VOICE picks."""
    monkeypatch.setattr(audio_module, "HybridSpeaker", lambda: speaker)
    monkeypatch.setattr(audio_module, "load_alarm", RecordingAlarm)
    monkeypatch.setenv("AUDIO_VOICE", "Cori")
    bus = RecordingBus()
    mgr = audio_module.register(bus)
    try:
        assert bus.subscriptions == [
            HazardEvent,
            TouchEvent,
            NameResult,
            SpeakRequest,
            VoiceChange,
        ]
        assert wait_for(lambda: len(statuses(bus.published)) == 1)
        assert statuses(bus.published)[0].active_voice == "cori"
    finally:
        mgr.stop()


def test_fake_audio_register_switches_voice(capsys: pytest.CaptureFixture[str]) -> None:
    """The fake subscribes VoiceChange last, lists every preset, and prints the switch."""
    from fakes.audio import register as fake_register

    bus = RecordingBus()
    mgr = fake_register(bus)
    try:
        assert bus.subscriptions[0] is HazardEvent
        assert bus.subscriptions[-1] is VoiceChange
        assert wait_for(lambda: len(statuses(bus.published)) == 1)
        first = statuses(bus.published)[0]
        assert first.installed == KEYS
        assert first.quality == "enhanced"
        mgr.on_voice_change(VoiceChange(1.0, "lessac", "r1"))
        assert wait_for(lambda: len(statuses(bus.published)) == 2)
        assert statuses(bus.published)[-1].active_voice == "lessac"
        out: list[str] = []
        assert wait_for(
            lambda: (
                out.append(capsys.readouterr().out)
                or "voice: piper.premium.en-US.Lessac" in "".join(out)
            )
        )
    finally:
        mgr.stop()


class PreparingSpeaker(VoiceSpeaker):
    """Also records prepare() calls, with the voice active at each call."""

    def __init__(self) -> None:
        super().__init__()
        self.prepared: list[tuple[str | None, list[str]]] = []

    def prepare(self, texts: list[str]) -> None:
        """Record the phrases to pre-render; returns at once like the real speaker."""
        with self.lock:
            self.prepared.append((self.set_calls[-1] if self.set_calls else None, list(texts)))


def test_prepare_hazard_phrases_after_startup_and_switch(
    alarm: RecordingAlarm, published: list[Any]
) -> None:
    """Every applied voice is followed by prepare() with all hazard phrases."""
    speaker = PreparingSpeaker()
    mgr = AudioManager(lambda: speaker, alarm, publish=published.append)
    try:
        assert wait_for(lambda: len(speaker.prepared) == 1)
        expected = [
            "Stop. Stairs.",
            "Stop. Drop ahead.",
            "Stop. Vehicle.",
            "Stop. Obstacle.",
            "Stop.",
        ]
        assert HAZARD_PRERENDER == expected
        assert speaker.prepared[0] == (PREMIUM["alba"][0], expected)
        mgr.on_voice_change(VoiceChange(1.0, "cori", "r1"))
        assert wait_for(lambda: len(speaker.prepared) == 2)
        assert speaker.prepared[1] == (PREMIUM["cori"][0], expected)
    finally:
        mgr.stop()


class FailingSwitchSpeaker(PreparingSpeaker):
    """set_voice raises for one voice, like a Piper model that will not load."""

    def set_voice(self, voice_id: str | None) -> None:
        """Fail for Cori; record the rest."""
        if voice_id == PREMIUM["cori"][0]:
            raise RuntimeError("model will not load")
        super().set_voice(voice_id)


def test_failed_voice_load_reports_failed_and_skips_prepare(
    alarm: RecordingAlarm, published: list[Any]
) -> None:
    """A set_voice error gives a failed VoiceStatus and no prepare for that voice."""
    speaker = FailingSwitchSpeaker()
    mgr = AudioManager(lambda: speaker, alarm, publish=published.append)
    try:
        assert wait_for(lambda: len(statuses(published)) == 1)
        mgr.on_voice_change(VoiceChange(1.0, "cori", "r9"))
        assert wait_for(lambda: len(statuses(published)) == 2)
        failed = statuses(published)[-1]
        assert failed.state == "failed" and failed.request_id == "r9"
        assert failed.active_voice == "alba"
        assert len(speaker.prepared) == 1
    finally:
        mgr.stop()
