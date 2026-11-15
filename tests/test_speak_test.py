"""Smoke tests for audio/speak_test.py. No speaker, pyttsx3 or Piper needed.

pyttsx3 is replaced with a stub module, and piper and pygame with the fakes from
tests/test_audio_piper.py (or hidden), so these run on any machine and play
nothing. The audio manager's own tests are in tests/test_audio.py.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_audio_piper import install_fake_piper, new_record

from audio import backends, speak_test, voices
from config import SPEECH_RATE_WPM

SAMANTHA_ID = "com.apple.voice.compact.en-US.Samantha"
VOICES = [
    SimpleNamespace(id="com.apple.voice.compact.en-GB.Daniel", name="Daniel"),
    SimpleNamespace(id=SAMANTHA_ID, name="Samantha"),
]


class StubEngine:
    """Records pyttsx3 engine calls instead of speaking."""

    def __init__(self, fail: bool = False) -> None:
        """Start with no calls; fail makes runAndWait raise."""
        self.calls: list[tuple[str, ...]] = []
        self._fail = fail

    def connect(self, topic: str, callback: Callable[..., None]) -> None:
        """Accept the started-word callback Pyttsx3Speaker connects."""

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


@pytest.fixture
def presets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[StubEngine, dict[str, Any]]:
    """Stub pyttsx3, fake piper and pygame, with only the alba and cori models present."""
    engine = StubEngine()
    _stub_pyttsx3(monkeypatch, engine)
    monkeypatch.setattr(backends, "_init_com_for_thread", lambda: None)
    record = new_record()
    install_fake_piper(monkeypatch, record)
    monkeypatch.setattr(voices, "VOICE_MODEL_DIR", tmp_path)
    for model in ("en_GB-alba-medium", "en_GB-cori-high"):
        (tmp_path / f"{model}.onnx").write_bytes(b"")
    return engine, record


def _piper_texts(record: dict[str, Any]) -> list[str]:
    """Return the texts handed to the fake Piper voice."""
    return [text for _, text, _ in record["synth"]]


def test_voice_flag_speaks_with_piper(
    presets: tuple[StubEngine, dict[str, Any]],
) -> None:
    """--voice cori loads Cori's model and speaks through Piper at the calm rate."""
    engine, record = presets
    assert speak_test.main(["--voice", "cori", "Heinz ketchup"]) == 0
    assert record["loads"] == ["en_GB-cori-high.onnx"]
    assert _piper_texts(record) == ["Heinz ketchup"]
    assert record["synth"][0][2].length_scale == pytest.approx(180 / SPEECH_RATE_WPM)
    assert record["channels"]
    assert _said(engine) == []


def test_voice_flag_falls_back_to_samantha(
    presets: tuple[StubEngine, dict[str, Any]],
) -> None:
    """--voice lessac without its model speaks with Samantha at the calm rate."""
    _, record = presets
    phrase_engines: list[StubEngine] = []

    def init() -> StubEngine:
        """Build a fresh engine per phrase, like the real pyttsx3."""
        engine = StubEngine()
        phrase_engines.append(engine)
        return engine

    sys.modules["pyttsx3"].init = init  # type: ignore[attr-defined]
    assert speak_test.main(["--voice", "lessac", "Heinz ketchup"]) == 0
    assert _piper_texts(record) == []
    spoken = [e for e in phrase_engines if _said(e)]
    assert len(spoken) == 1
    calls = spoken[0].calls
    assert ("set", "voice", SAMANTHA_ID) in calls
    assert ("set", "rate", SPEECH_RATE_WPM) in calls
    assert calls.index(("say", "Heinz ketchup")) > calls.index(("set", "voice", SAMANTHA_ID))


def test_list_voices_prints_five_presets(
    presets: tuple[StubEngine, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    """--list-voices prints one line per preset, alba first, and speaks nothing."""
    engine, record = presets
    assert speak_test.main(["--list-voices"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 5
    assert lines[0].split()[0] == "alba"
    assert "piper.enhanced.en-GB.Alba" in lines[0] and "enhanced" in lines[0]
    assert "fallback" in lines[1] and SAMANTHA_ID in lines[1]  # kristin not downloaded
    assert "piper.premium.en-GB.Cori" in lines[3] and "premium" in lines[3]
    assert _said(engine) == [] and record["synth"] == []


def test_all_speaks_each_preset_once(
    presets: tuple[StubEngine, dict[str, Any]],
) -> None:
    """--all says one sample per preset, Alba first; missing models use Samantha."""
    _, record = presets
    phrase_engines: list[StubEngine] = []

    def init() -> StubEngine:
        """Build a fresh engine per phrase."""
        new = StubEngine()
        phrase_engines.append(new)
        return new

    sys.modules["pyttsx3"].init = init  # type: ignore[attr-defined]
    assert speak_test.main(["--all"]) == 0
    piper_said = _piper_texts(record)
    system_said = [text for e in phrase_engines for text in _said(e)]
    assert piper_said == [
        "This is Alba. Heinz ketchup. Stop. Stairs.",
        "This is Cori. Heinz ketchup. Stop. Stairs.",
    ]
    assert len(system_said) == 3
    assert "This is Kristin." in system_said[0]


def test_voice_paths_report_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """With neither Piper nor pyttsx3, --voice exits 1 instead of crashing."""
    monkeypatch.setitem(sys.modules, "pyttsx3", None)
    monkeypatch.setitem(sys.modules, "piper", None)
    assert speak_test.main(["--voice", "alba", "Heinz ketchup"]) == 1


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
