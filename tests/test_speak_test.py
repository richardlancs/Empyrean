"""Smoke tests for audio/speak_test.py. No speaker or pyttsx3 needed.

pyttsx3 is replaced with a stub module, so these run on any machine. The audio
manager's own tests are in tests/test_audio.py.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from audio import speak_test
from config import SPEECH_RATE_WPM

VOICES = [
    SimpleNamespace(id="com.apple.voice.premium.en-US.Ava", name="Ava (Premium)"),
    SimpleNamespace(id="com.apple.voice.premium.en-GB.Jamie", name="Jamie"),
    SimpleNamespace(id="com.apple.voice.compact.en-US.Samantha", name="Samantha"),
]


class StubEngine:
    """Records pyttsx3 engine calls instead of speaking."""

    def __init__(self, fail: bool = False) -> None:
        """Start with no calls; fail makes runAndWait raise."""
        self.calls: list[tuple[str, ...]] = []
        self._fail = fail

    def setProperty(self, name: str, value: Any) -> None:
        """Record a property set."""
        self.calls.append(("set", name, value))

    def getProperty(self, name: str) -> Any:
        """Return the fake installed voices."""
        assert name == "voices"
        return list(VOICES)

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


def test_speak_test_says_text_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The manual test hands the trimmed sentence to pyttsx3 and waits for it."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    assert speak_test.main(["  Heinz ketchup  "]) == 0
    assert engine.calls == [
        ("set", "rate", SPEECH_RATE_WPM),
        ("say", "Heinz ketchup"),
        ("runAndWait",),
        ("stop",),
    ]


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


def _said(engine: StubEngine) -> list[str]:
    """Return the texts handed to say()."""
    return [call[1] for call in engine.calls if call[0] == "say"]


def test_voice_flag_sets_voice_and_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    """--voice jamie sets Jamie's id and the calm rate before speaking."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    assert speak_test.main(["--voice", "jamie", "Heinz ketchup"]) == 0
    assert ("set", "voice", "com.apple.voice.premium.en-GB.Jamie") in engine.calls
    assert ("set", "rate", SPEECH_RATE_WPM) in engine.calls
    assert _said(engine) == ["Heinz ketchup"]
    assert engine.calls.index(("say", "Heinz ketchup")) > engine.calls.index(
        ("set", "voice", "com.apple.voice.premium.en-GB.Jamie")
    )


def test_list_voices_prints_five_presets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--list-voices prints one line per preset, ava first, and speaks nothing."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    assert speak_test.main(["--list-voices"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 5
    assert lines[0].split()[0] == "ava"
    assert "com.apple.voice.premium.en-US.Ava" in lines[0] and "premium" in lines[0]
    assert "fallback" in lines[1]  # zoe is not installed in the stub
    assert _said(engine) == []


def test_all_speaks_each_preset_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """--all says one sample per preset, Ava first."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    assert speak_test.main(["--all"]) == 0
    said = _said(engine)
    assert len(said) == 5
    assert "This is Ava." in said[0]
    assert said[0] == "This is Ava. Heinz ketchup. Stop. Stairs."


def test_unknown_voice_flag_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown preset key is a usage error."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    with pytest.raises(SystemExit) as exc:
        speak_test.main(["--voice", "bob", "Heinz ketchup"])
    assert exc.value.code == 2
    assert _said(engine) == []


def test_text_required_without_list_or_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no TEXT and no --list-voices or --all, it is a usage error."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    with pytest.raises(SystemExit) as exc:
        speak_test.main([])
    assert exc.value.code == 2
