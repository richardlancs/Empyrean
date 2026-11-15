"""Pyttsx3Speaker uses a fresh engine per phrase (pyttsx3 2.99 on Windows goes silent otherwise)."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from audio import backends
from config import SPEECH_RATE_WPM

ENGINE_VOICES = [
    SimpleNamespace(id="com.apple.voice.premium.en-US.Ava", name="Ava (Premium)"),
    SimpleNamespace(id="com.apple.voice.compact.en-US.Samantha", name="Samantha"),
]


class FakeEngine:
    """Records what it was asked to say; fires started-word once per say."""

    def __init__(self, log: list[tuple[int, str]]) -> None:
        """Share a log with every other engine made by the fake module."""
        self.log = log
        self.props: list[tuple[str, Any]] = []
        self.order: list[str] = []
        self.stopped = False
        self._on_word: Callable[..., None] | None = None
        self._text = ""

    def connect(self, topic: str, callback: Callable[..., None]) -> None:
        """Keep the started-word callback."""
        assert topic == "started-word"
        self._on_word = callback

    def setProperty(self, name: str, value: Any) -> None:
        """Record a property set on this engine."""
        self.props.append((name, value))
        self.order.append(f"set:{name}")

    def getProperty(self, name: str) -> Any:
        """Return the fake installed voices."""
        assert name == "voices"
        return list(ENGINE_VOICES)

    def say(self, text: str) -> None:
        """Queue text."""
        self.order.append("say")
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


def test_every_engine_gets_rate_and_voice(
    fake_pyttsx3: tuple[list[tuple[int, str]], list[Any]],
) -> None:
    """Each phrase's fresh engine gets the calm rate and chosen voice before say."""
    spoken, engines = fake_pyttsx3
    speaker = backends.Pyttsx3Speaker()
    speaker.set_voice("v1")
    speaker.say("Heinz ketchup", lambda: False)
    speaker.say("Stop. Stairs.", lambda: False)
    assert [text for _, text in spoken] == ["Heinz ketchup", "Stop. Stairs."]
    for engine in engines[1:]:
        assert ("rate", SPEECH_RATE_WPM) in engine.props
        assert ("voice", "v1") in engine.props
        assert engine.order.index("say") > engine.order.index("set:rate")
        assert engine.order.index("say") > engine.order.index("set:voice")
    assert SPEECH_RATE_WPM == 165


def test_no_voice_id_leaves_system_voice(
    fake_pyttsx3: tuple[list[tuple[int, str]], list[Any]],
) -> None:
    """Without set_voice the rate is still set, but the voice is left alone."""
    _, engines = fake_pyttsx3
    speaker = backends.Pyttsx3Speaker()
    speaker.say("Dell laptop", lambda: False)
    phrase_engine = engines[-1]
    assert ("rate", SPEECH_RATE_WPM) in phrase_engine.props
    assert all(name != "voice" for name, _ in phrase_engine.props)


def test_set_voice_none_returns_to_system_voice(
    fake_pyttsx3: tuple[list[tuple[int, str]], list[Any]],
) -> None:
    """set_voice(None) stops setting a voice on later engines."""
    _, engines = fake_pyttsx3
    speaker = backends.Pyttsx3Speaker()
    speaker.set_voice("v1")
    speaker.set_voice(None)
    speaker.say("Dell laptop", lambda: False)
    assert all(name != "voice" for name, _ in engines[-1].props)


def test_installed_voices_lists_engine_voices(
    fake_pyttsx3: tuple[list[tuple[int, str]], list[Any]],
) -> None:
    """installed_voices() returns the (id, name) pairs the engine reported at startup."""
    speaker = backends.Pyttsx3Speaker()
    assert speaker.installed_voices() == [
        ("com.apple.voice.premium.en-US.Ava", "Ava (Premium)"),
        ("com.apple.voice.compact.en-US.Samantha", "Samantha"),
    ]


def test_log_speaker_has_no_voices() -> None:
    """The logging stand-in lists no voices and accepts set_voice."""
    speaker = backends.LogSpeaker()
    assert speaker.installed_voices() == []
    speaker.set_voice("anything")
