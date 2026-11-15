"""Smoke tests for audio/ (SPEC.md 4.5 late names and 4.8 audio rules).

No sound device is used: the speaker and alarm are recording stand-ins.
"""

from __future__ import annotations

import threading
import time
import wave
from collections.abc import Callable, Iterator
from typing import Any, get_args, get_type_hints

import numpy as np
import pytest

from audio import audio as audio_module
from audio.audio import HAZARD_PHRASES, AudioManager
from audio.backends import ALARM_WAV
from contracts import HazardEvent, NameResult, SpeakRequest, TouchEvent, VoiceChange

BOX = (100.0, 100.0, 200.0, 200.0)


class Clock:
    """Controlled monotonic clock for the late-name window."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        """Return the controlled time."""
        return self.now


class RecordingSpeaker:
    """Records phrases. While gated, holds each phrase until released or cut off."""

    def __init__(self) -> None:
        self.started: list[str] = []
        self.finished: list[str] = []
        self.cut_off: list[str] = []
        self.gate = threading.Event()
        self.gate.set()
        self.lock = threading.Lock()

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Record text, waiting on the gate while honouring should_stop."""
        with self.lock:
            self.started.append(text)
        while not self.gate.wait(0.005):
            if should_stop():
                with self.lock:
                    self.cut_off.append(text)
                return
        with self.lock:
            self.finished.append(text)


class RecordingAlarm:
    """Records when the alarm started."""

    def __init__(self, duration: float = 0.0) -> None:
        self.duration = duration
        self.played_at: list[float] = []
        self.closed = False

    def play(self) -> None:
        """Record the start time."""
        self.played_at.append(time.monotonic())

    def close(self) -> None:
        """Record shutdown."""
        self.closed = True


def wait_for(condition: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Poll until condition() is true or timeout passes."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


def touch(
    object_id: int, label: str, name: str = "", kind: str = "touch"
) -> TouchEvent:
    """Build a TouchEvent."""
    return TouchEvent(time.time(), object_id, label, name, kind, BOX, [])  # type: ignore[arg-type]


def named(object_id: int, name: str, ok: bool = True) -> NameResult:
    """Build a NameResult."""
    return NameResult(time.time(), object_id, name, ok)


@pytest.fixture
def speaker() -> RecordingSpeaker:
    """A recording speaker that speaks instantly unless its gate is cleared."""
    return RecordingSpeaker()


@pytest.fixture
def alarm() -> RecordingAlarm:
    """An alarm with no beep length."""
    return RecordingAlarm()


@pytest.fixture
def clock() -> Clock:
    """A controlled clock."""
    return Clock()


@pytest.fixture
def manager(
    speaker: RecordingSpeaker, alarm: RecordingAlarm, clock: Clock
) -> Iterator[AudioManager]:
    """An audio manager wired to the recording stand-ins."""
    mgr = AudioManager(lambda: speaker, alarm, clock=clock, announce_touches=True)
    yield mgr
    speaker.gate.set()
    mgr.stop()


def settle(speaker: RecordingSpeaker, count: int) -> list[str]:
    """Wait until count phrases have finished and return them."""
    assert wait_for(lambda: len(speaker.finished) >= count), speaker.finished
    time.sleep(0.05)  # catch anything extra that should not have been said
    return list(speaker.finished)


def test_touch_speaks_name(manager: AudioManager, speaker: RecordingSpeaker) -> None:
    """A touch with a known name speaks that name."""
    manager.on_touch(touch(1, "bottle", "Heinz ketchup"))
    assert settle(speaker, 1) == ["Heinz ketchup"]


def test_release_is_silent(manager: AudioManager, speaker: RecordingSpeaker) -> None:
    """A release is never spoken."""
    manager.on_touch(touch(1, "bottle", "Heinz ketchup", kind="release"))
    time.sleep(0.1)
    assert speaker.started == []


def test_retouch_speaks_again(manager: AudioManager, speaker: RecordingSpeaker) -> None:
    """Letting go and touching again gives a new announcement, no cooldown."""
    manager.on_touch(touch(1, "bottle", "Heinz ketchup"))
    settle(speaker, 1)
    manager.on_touch(touch(1, "bottle", "Heinz ketchup", kind="release"))
    manager.on_touch(touch(1, "bottle", "Heinz ketchup"))
    assert settle(speaker, 2) == ["Heinz ketchup", "Heinz ketchup"]


def test_unnamed_touch_then_late_name_spoken_once(
    manager: AudioManager, speaker: RecordingSpeaker, clock: Clock
) -> None:
    """Class label first, then the late name once if it arrives within the window."""
    manager.on_touch(touch(2, "cup"))
    settle(speaker, 1)
    clock.now += 1.0
    manager.on_name(named(2, "Starbucks coffee cup"))
    manager.on_name(named(2, "Starbucks coffee cup"))
    assert settle(speaker, 2) == ["cup", "Starbucks coffee cup"]


def test_late_name_outside_window_not_spoken(
    manager: AudioManager, speaker: RecordingSpeaker, clock: Clock
) -> None:
    """A name that arrives after the late-name window is not spoken."""
    manager.on_touch(touch(2, "cup"))
    settle(speaker, 1)
    clock.now += 1.6
    manager.on_name(named(2, "Starbucks coffee cup"))
    assert settle(speaker, 1) == ["cup"]


def test_late_name_after_release_not_spoken(
    manager: AudioManager, speaker: RecordingSpeaker, clock: Clock
) -> None:
    """A late name is spoken only while the object is still touched."""
    manager.on_touch(touch(2, "cup"))
    settle(speaker, 1)
    manager.on_touch(touch(2, "cup", kind="release"))
    clock.now += 0.5
    manager.on_name(named(2, "Starbucks coffee cup"))
    assert settle(speaker, 1) == ["cup"]


def test_failed_name_not_spoken(
    manager: AudioManager, speaker: RecordingSpeaker
) -> None:
    """A NameResult with ok=False or an empty name is ignored."""
    manager.on_touch(touch(2, "cup"))
    settle(speaker, 1)
    manager.on_name(named(2, "", ok=False))
    manager.on_name(named(2, "Starbucks", ok=False))
    assert settle(speaker, 1) == ["cup"]


def test_late_name_replaces_waiting_label(
    manager: AudioManager, speaker: RecordingSpeaker
) -> None:
    """If the label has not been spoken yet, the name replaces it: one announcement."""
    speaker.gate.clear()
    manager.on_speak(SpeakRequest(time.time(), "busy", "normal", "storage"))
    assert wait_for(lambda: speaker.started == ["busy"])
    manager.on_touch(touch(2, "cup"))
    manager.on_name(named(2, "Starbucks coffee cup"))
    speaker.gate.set()
    assert settle(speaker, 2) == ["busy", "Starbucks coffee cup"]


def test_name_before_touch_is_used(
    manager: AudioManager, speaker: RecordingSpeaker
) -> None:
    """A NameResult delivered before its TouchEvent still gives the name, not the label."""
    manager.on_name(named(3, "Pringles Original"))
    manager.on_touch(touch(3, "bottle"))
    assert settle(speaker, 1) == ["Pringles Original"]


def test_queue_holds_one_newest_wins(
    manager: AudioManager, speaker: RecordingSpeaker
) -> None:
    """A newer item replaces a waiting older one of the same priority."""
    speaker.gate.clear()
    manager.on_touch(touch(1, "bottle", "A"))
    assert wait_for(lambda: speaker.started == ["A"])
    manager.on_touch(touch(2, "cup", "B"))
    manager.on_touch(touch(3, "book", "C"))
    speaker.gate.set()
    assert settle(speaker, 2) == ["A", "C"]


def test_answer_does_not_replace_waiting_touch(
    manager: AudioManager, speaker: RecordingSpeaker
) -> None:
    """A spoken answer (priority 3) never replaces a waiting touch name (priority 2)."""
    speaker.gate.clear()
    manager.on_touch(touch(1, "bottle", "A"))
    assert wait_for(lambda: speaker.started == ["A"])
    manager.on_touch(touch(2, "cup", "B"))
    manager.on_speak(SpeakRequest(time.time(), "answer", "normal", "storage"))
    speaker.gate.set()
    assert settle(speaker, 2) == ["A", "B"]


def test_alarm_cuts_off_and_empties_queue(
    manager: AudioManager, speaker: RecordingSpeaker, alarm: RecordingAlarm
) -> None:
    """A hazard starts the beeps, cuts off speech, drops the queue, then speaks."""
    speaker.gate.clear()
    manager.on_speak(SpeakRequest(time.time(), "long answer", "normal", "storage"))
    assert wait_for(lambda: speaker.started == ["long answer"])
    manager.on_touch(touch(1, "bottle", "waiting"))
    manager.on_hazard(HazardEvent(time.time(), "stairs_down", "grok", 0.9))
    assert len(alarm.played_at) == 1
    assert wait_for(lambda: speaker.cut_off == ["long answer"])
    assert wait_for(lambda: "Stop. Stairs." in speaker.started)
    speaker.gate.set()
    assert settle(speaker, 1) == ["Stop. Stairs."]
    assert "waiting" not in speaker.started


def test_phrase_waits_for_beeps_and_outranks_touch(speaker: RecordingSpeaker) -> None:
    """The hazard phrase follows the beeps; a touch during the beeps cannot replace it."""
    alarm = RecordingAlarm(duration=0.2)
    mgr = AudioManager(lambda: speaker, alarm)
    try:
        mgr.on_hazard(HazardEvent(time.time(), "vehicle", "yolo", 0.95))
        mgr.on_touch(touch(1, "bottle", "Heinz ketchup"))
        assert settle(speaker, 1) == ["Stop. Vehicle."]
        assert time.monotonic() - alarm.played_at[0] >= 0.2
    finally:
        mgr.stop()


def test_handlers_never_wait_on_speech(
    manager: AudioManager, speaker: RecordingSpeaker
) -> None:
    """Every handler returns at once while the speaker is busy."""
    speaker.gate.clear()
    manager.on_touch(touch(1, "bottle", "A"))
    assert wait_for(lambda: speaker.started == ["A"])
    calls: list[Callable[[], None]] = [
        lambda: manager.on_touch(touch(2, "cup")),
        lambda: manager.on_name(named(2, "Starbucks")),
        lambda: manager.on_speak(SpeakRequest(time.time(), "x", "normal", "storage")),
        lambda: manager.on_hazard(HazardEvent(time.time(), "obstacle", "grok", 0.7)),
    ]
    for call in calls:
        start = time.monotonic()
        call()
        assert time.monotonic() - start < 0.05


def test_every_hazard_type_has_its_phrase() -> None:
    """Each HazardEvent type in contracts maps to the phrase in SPEC.md 4.8."""
    types = set(get_args(get_type_hints(HazardEvent)["type"]))
    assert set(HAZARD_PHRASES) == types
    assert HAZARD_PHRASES == {
        "stairs_down": "Stop. Stairs.",
        "drop_off": "Stop. Drop ahead.",
        "vehicle": "Stop. Vehicle.",
        "obstacle": "Stop. Obstacle.",
    }


def test_alarm_wav_is_three_880_hz_beeps() -> None:
    """The committed alarm is a short WAV whose tone is 880 Hz, in three bursts."""
    with wave.open(str(ALARM_WAV)) as wav:
        rate = wav.getframerate()
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(
            float
        )
    assert 0.3 < len(samples) / rate < 1.5
    spectrum = np.abs(np.fft.rfft(samples))
    peak_hz = np.fft.rfftfreq(len(samples), 1 / rate)[int(np.argmax(spectrum))]
    assert abs(peak_hz - 880) < 10
    loud = np.abs(samples) > 1000
    # Smooth over 10 ms so the zero crossings inside one beep do not count as gaps.
    smoothed = np.convolve(loud.astype(float), np.ones(rate // 100), "same") > 0
    bursts = int(np.sum(smoothed[1:] & ~smoothed[:-1])) + int(smoothed[0])
    assert bursts == 3


def test_speaker_failure_falls_back_to_logging(alarm: RecordingAlarm) -> None:
    """If text to speech cannot start, the manager keeps running."""

    def broken() -> Any:
        raise RuntimeError("no voice")

    mgr = AudioManager(broken, alarm)
    try:
        mgr.on_touch(touch(1, "bottle", "Heinz ketchup"))
        time.sleep(0.05)
        assert mgr._thread.is_alive()
    finally:
        mgr.stop()
    assert alarm.closed


class RecordingBus:
    """Records subscriptions in order."""

    def __init__(self) -> None:
        self.subscriptions: list[tuple[type, Callable[[Any], None]]] = []

    def subscribe(self, message_type: type, handler: Callable[[Any], None]) -> None:
        """Record one subscription."""
        self.subscriptions.append((message_type, handler))

    def publish(self, message: Any) -> None:
        """Deliver inline to matching handlers."""
        for message_type, handler in self.subscriptions:
            if type(message) is message_type:
                handler(message)


def test_register_subscribes_hazard_first(
    monkeypatch: pytest.MonkeyPatch, speaker: RecordingSpeaker
) -> None:
    """register(bus) subscribes the five input types, HazardEvent first, VoiceChange last."""
    monkeypatch.setattr(audio_module, "Pyttsx3Speaker", lambda: speaker)
    monkeypatch.setattr(audio_module, "load_alarm", RecordingAlarm)
    bus = RecordingBus()
    mgr = audio_module.register(bus)
    try:
        types = [t for t, _ in bus.subscriptions]
        assert types == [HazardEvent, TouchEvent, NameResult, SpeakRequest, VoiceChange]
        bus.publish(touch(1, "bottle", "Heinz ketchup"))
        assert settle(speaker, 1) == ["Heinz ketchup"]
        bus.publish(named(1, "New ketchup name"))
        bus.publish(
            SpeakRequest(time.time(), "Requested ketchup answer", "normal", "dashboard")
        )
        assert settle(speaker, 2) == ["Heinz ketchup", "Requested ketchup answer"]
    finally:
        mgr.stop()


def test_fake_audio_register_prints(capsys: pytest.CaptureFixture[str]) -> None:
    """The fake subscribes to the same types and prints what it would say."""
    from fakes.audio import register as fake_register

    bus = RecordingBus()
    mgr = fake_register(bus)
    try:
        assert [t for t, _ in bus.subscriptions] == [
            HazardEvent,
            TouchEvent,
            NameResult,
            SpeakRequest,
            VoiceChange,
        ]
        bus.publish(touch(1, "bottle", "Heinz"))
        bus.publish(named(1, "Heinz ketchup"))
        bus.publish(SpeakRequest(time.time(), "Heinz", "normal", "dashboard"))
        printed: list[str] = []
        assert wait_for(
            lambda: (
                printed.append(capsys.readouterr().out)
                or "say: Heinz" in "".join(printed)
            )
        )
    finally:
        mgr.stop()


def test_default_audio_announces_without_question(speaker: RecordingSpeaker) -> None:
    """Touch and retouch announce independently; requested answers also play."""
    alarm = RecordingAlarm()
    mgr = AudioManager(lambda: speaker, alarm)
    try:
        mgr.on_touch(touch(1, "bottle", "Heinz ketchup"))
        assert settle(speaker, 1) == ["Heinz ketchup"]
        mgr.on_touch(touch(1, "bottle", kind="release"))
        mgr.on_touch(touch(1, "bottle", "Heinz ketchup"))
        assert settle(speaker, 2) == ["Heinz ketchup", "Heinz ketchup"]
        mgr.on_speak(
            SpeakRequest(time.time(), "Your keys are to your right.", "normal", "namer")
        )
        assert settle(speaker, 3)[-1] == "Your keys are to your right."
        mgr.on_hazard(HazardEvent(time.time(), "vehicle", "yolo", 0.9))
        assert settle(speaker, 4)[-1] == "Stop. Vehicle."
        assert len(alarm.played_at) == 1
    finally:
        mgr.stop()
