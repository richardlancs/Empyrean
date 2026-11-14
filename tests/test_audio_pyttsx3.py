"""Pyttsx3Speaker uses a fresh engine per phrase (pyttsx3 2.99 on Windows goes silent otherwise)."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import Any

import pytest

from audio import backends


class FakeEngine:
    """Records what it was asked to say; fires started-word once per say."""

    def __init__(self, log: list[tuple[int, str]]) -> None:
        """Share a log with every other engine made by the fake module."""
        self.log = log
        self.stopped = False
        self._on_word: Callable[..., None] | None = None
        self._text = ""

    def connect(self, topic: str, callback: Callable[..., None]) -> None:
        """Keep the started-word callback."""
        assert topic == "started-word"
        self._on_word = callback

    def say(self, text: str) -> None:
        """Queue text."""
        self._text = text

    def runAndWait(self) -> None:
        """Pretend to speak: fire one word event, then log unless stopped."""
        if self._on_word is not None:
            self._on_word("utterance", 0, 1)
        if not self.stopped:
            self.log.append((id(self), self._text))

    def stop(self) -> None:
        """Cut speech off."""
        self.stopped = True


@pytest.fixture
def fake_pyttsx3(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[tuple[int, str]], list[Any]]:
    """Install a fake pyttsx3 whose init() always builds a new engine."""
    spoken: list[tuple[int, str]] = []
    engines: list[Any] = []

    def init() -> FakeEngine:
        """Build a new engine, like pyttsx3.init() after the old one is collected."""
        engine = FakeEngine(spoken)
        engines.append(engine)
        return engine

    module = types.ModuleType("pyttsx3")
    module.init = init  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyttsx3", module)
    monkeypatch.setattr(backends, "_init_com_for_thread", lambda: None)
    return spoken, engines


def test_each_phrase_gets_its_own_engine(
    fake_pyttsx3: tuple[list[tuple[int, str]], list[Any]],
) -> None:
    """Three phrases use three new engines, after the one made at startup."""
    spoken, engines = fake_pyttsx3
    speaker = backends.Pyttsx3Speaker()
    for text in ("Coca-Cola bottle", "Dell laptop", "Stop. Obstacle."):
        speaker.say(text, lambda: False)
    assert [text for _, text in spoken] == [
        "Coca-Cola bottle",
        "Dell laptop",
        "Stop. Obstacle.",
    ]
    assert len(engines) == 4  # one startup check plus one per phrase


def test_interrupted_phrase_does_not_silence_the_next(
    fake_pyttsx3: tuple[list[tuple[int, str]], list[Any]],
) -> None:
    """An alarm cut-off stops that engine only; the next phrase still plays."""
    spoken, _ = fake_pyttsx3
    speaker = backends.Pyttsx3Speaker()
    speaker.say("ASUS laptop", lambda: True)  # should_stop already true: nothing said
    calls = {"n": 0}

    def alarm_arrives_mid_phrase() -> bool:
        """False for say()'s own check, True from the first spoken word on."""
        calls["n"] += 1
        return calls["n"] > 1

    speaker.say("Heinz ketchup", alarm_arrives_mid_phrase)
    speaker.say("Stop. Stairs.", lambda: False)
    assert [text for _, text in spoken] == ["Stop. Stairs."]
