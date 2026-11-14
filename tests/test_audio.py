"""Smoke tests for audio/speak_test.py and fakes/audio. No speaker or pyttsx3 needed.

pyttsx3 is replaced with a stub module, so these run on any machine.
"""

from __future__ import annotations

import sys
import types
import typing
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import pytest

from audio import speak_test
from config import LATE_NAME_WINDOW_SECONDS
from contracts import HazardEvent, NameResult, SpeakRequest, TouchEvent
from fakes.audio import fake_audio
from fakes.audio.fake_audio import HAZARD_PHRASES, FakeAudio, Played

NOW = 1_800_000_000.0
BOX = (100.0, 80.0, 200.0, 240.0)


class StubEngine:
    """Records pyttsx3 engine calls instead of speaking."""

    def __init__(self, fail: bool = False) -> None:
        """Start with no calls; fail makes runAndWait raise."""
        self.calls: list[tuple[str, ...]] = []
        self._fail = fail

    def say(self, text: str) -> None:
        """Record the text."""
        self.calls.append(("say", text))

    def runAndWait(self) -> None:
        """Record the wait, or raise if this engine is set to fail."""
        self.calls.append(("runAndWait",))
        if self._fail:
            raise RuntimeError("no audio device")

    def stop(self) -> None:
        """Record the stop."""
        self.calls.append(("stop",))


def _stub_pyttsx3(monkeypatch: pytest.MonkeyPatch, engine: StubEngine) -> None:
    """Install a fake pyttsx3 module whose init() returns engine."""
    module = types.ModuleType("pyttsx3")
    module.init = lambda *args, **kwargs: engine  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyttsx3", module)


class TestBus:
    """Minimal in-process bus: subscribe(MessageType, handler) and publish(message)."""

    __test__ = False  # not a pytest test class

    def __init__(self) -> None:
        """Start with no subscribers and an empty publish log."""
        self.subscribers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.published: list[Any] = []

    def subscribe(self, msg_type: type, handler: Callable[[Any], None]) -> None:
        """Register handler for messages of exactly msg_type."""
        self.subscribers[msg_type].append(handler)

    def publish(self, msg: Any) -> None:
        """Record msg, then deliver it synchronously."""
        self.published.append(msg)
        for handler in list(self.subscribers.get(type(msg), [])):
            handler(msg)


def _touch(
    object_id: int, kind: str, name: str = "", ts: float = NOW, label: str = "bottle"
) -> TouchEvent:
    """Build a TouchEvent with a fixed box."""
    return TouchEvent(
        ts=ts, object_id=object_id, class_label=label, name=name, kind=kind, box=BOX
    )  # type: ignore[arg-type]


def _texts(audio: FakeAudio) -> list[tuple[str, str]]:
    """Return (kind, text) for everything the fake played."""
    return [(p.kind, p.text) for p in audio.played]


# --- audio/speak_test.py ----------------------------------------------------


def test_speak_test_says_text_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The manual test hands the trimmed sentence to pyttsx3 and waits for it."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    assert speak_test.main(["  Heinz ketchup  "]) == 0
    assert engine.calls == [("say", "Heinz ketchup"), ("runAndWait",), ("stop",)]


def test_speak_test_rejects_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty sentence is a usage error, and nothing is spoken."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    with pytest.raises(SystemExit) as exc:
        speak_test.main(["   "])
    assert exc.value.code == 2
    assert engine.calls == []


def test_speak_test_reports_missing_pyttsx3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without pyttsx3 installed the test exits 1 instead of crashing."""
    monkeypatch.setitem(sys.modules, "pyttsx3", None)  # makes the import fail
    assert speak_test.main(["Heinz ketchup"]) == 1


def test_speak_test_reports_engine_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """An engine error exits 1 and still stops the engine."""
    engine = StubEngine(fail=True)
    _stub_pyttsx3(monkeypatch, engine)
    assert speak_test.main(["Heinz ketchup"]) == 1
    assert engine.calls[-1] == ("stop",)


# --- fakes/audio --------------------------------------------------------------


def test_register_subscribes_everything_audio_consumes() -> None:
    """The fake listens to the four messages SPEC.md 3.1 lists for audio/."""
    bus = TestBus()
    fake_audio.register(bus)
    assert set(bus.subscribers) == {HazardEvent, TouchEvent, NameResult, SpeakRequest}


def test_every_hazard_type_has_its_spec_phrase() -> None:
    """Each HazardEvent type gives an alarm with the SPEC.md 4.8 phrase."""
    hazard_types = typing.get_args(typing.get_type_hints(HazardEvent)["type"])
    assert set(HAZARD_PHRASES) == set(hazard_types)
    bus = TestBus()
    audio = fake_audio.register(bus)
    for i, hazard in enumerate(hazard_types):
        bus.publish(HazardEvent(ts=NOW + i, type=hazard, source="yolo", confidence=0.9))
    assert _texts(audio) == [("alarm", HAZARD_PHRASES[h]) for h in hazard_types]
    assert HAZARD_PHRASES["stairs_down"] == "Stop. Stairs."


def test_scripted_sequence_through_bus() -> None:
    """Touch speaks the name, release is silent, answers are spoken, nothing is published."""
    bus = TestBus()
    heard: list[Played] = []
    audio = fake_audio.register(bus, on_play=heard.append)

    bus.publish(_touch(1, "touch", name="Heinz ketchup"))
    bus.publish(_touch(1, "release", name="Heinz ketchup", ts=NOW + 1))
    bus.publish(
        _touch(1, "touch", name="Heinz ketchup", ts=NOW + 2)
    )  # retouch speaks again
    bus.publish(
        SpeakRequest(
            ts=NOW + 3,
            text="Keys last seen 2 minutes ago.",
            priority="normal",
            source="storage",
        )
    )

    assert _texts(audio) == [
        ("speech", "Heinz ketchup"),
        ("speech", "Heinz ketchup"),
        ("speech", "Keys last seen 2 minutes ago."),
    ]
    assert heard == audio.played
    assert all(not isinstance(m, Played) for m in bus.published)
    assert len(bus.published) == 4  # only the four inputs; the fake publishes nothing


def test_late_name_within_window_is_spoken_once() -> None:
    """An unnamed touch speaks the class label, then the late name once (SPEC.md 4.5)."""
    bus = TestBus()
    audio = fake_audio.register(bus)
    bus.publish(_touch(2, "touch", label="cup"))
    late = NOW + LATE_NAME_WINDOW_SECONDS - 0.1
    bus.publish(NameResult(ts=late, object_id=2, name="Starbucks coffee cup", ok=True))
    bus.publish(NameResult(ts=late, object_id=2, name="Starbucks coffee cup", ok=True))
    assert _texts(audio) == [("speech", "cup"), ("speech", "Starbucks coffee cup")]


@pytest.mark.parametrize(
    "case",
    [
        "too_late",
        "released_first",
        "naming_failed",
    ],
)
def test_late_name_not_spoken(case: str) -> None:
    """A late name is dropped if it is too late, after release, or a failed name."""
    bus = TestBus()
    audio = fake_audio.register(bus)
    bus.publish(_touch(3, "touch", label="book"))
    if case == "too_late":
        bus.publish(
            NameResult(
                ts=NOW + LATE_NAME_WINDOW_SECONDS + 0.1,
                object_id=3,
                name="Penguin paperback",
                ok=True,
            )
        )
    elif case == "released_first":
        bus.publish(_touch(3, "release", label="book", ts=NOW + 0.5))
        bus.publish(
            NameResult(ts=NOW + 1.0, object_id=3, name="Penguin paperback", ok=True)
        )
    else:
        bus.publish(NameResult(ts=NOW + 1.0, object_id=3, name="", ok=False))
    assert _texts(audio) == [("speech", "book")]
