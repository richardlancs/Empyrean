"""HybridSpeaker: Piper voices through the pygame mixer, pyttsx3 for system voices.

piper and pygame are replaced by fakes in sys.modules and pyttsx3 by a fake
speaker class, so nothing is played and no model is loaded.
"""

from __future__ import annotations

import sys
import threading
import time
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

from audio import backends, voices
from audio.audio import AudioManager
from config import SPEECH_RATE_WPM
from contracts import HazardEvent, ModuleStatus, SpeechStatus, VoiceChange, VoiceStatus

SAMANTHA = ("com.apple.voice.compact.en-US.Samantha", "Samantha")
SAMPLES = 100  # samples per fake sentence at 22050 Hz


class FakeChunk:
    """One sentence of Piper audio."""

    sample_rate = 22050
    sample_channels = 1

    def __init__(self, text: str) -> None:
        self.text = text
        self.audio_int16_bytes = np.arange(SAMPLES, dtype=np.int16).tobytes()


class FakeVoice:
    """A loaded Piper voice that yields one chunk per sentence."""

    def __init__(self, path: str, record: dict[str, Any]) -> None:
        self.path = path
        self.record = record

    def synthesize(self, text: str, syn_config: Any = None) -> Iterator[FakeChunk]:
        """Record the call, then yield each sentence."""
        self.record["synth"].append((Path(self.path).name, text, syn_config))
        for sentence in [s for s in text.split(". ") if s]:
            yield FakeChunk(sentence)


class FakeSynthesisConfig:
    """Keeps the keyword arguments it was built with."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.length_scale = kwargs.get("length_scale")


class FakeChannel:
    """Busy for a few polls, or until stopped when busy_polls is None."""

    def __init__(self, sound: FakeSound, busy_polls: int | None) -> None:
        self.sound = sound
        self.remaining = busy_polls
        self.stopped = False

    def get_busy(self) -> bool:
        """Count down one poll; never ends by itself when remaining is None."""
        if self.stopped:
            return False
        if self.remaining is None:
            return True
        self.remaining -= 1
        return self.remaining >= 0

    def stop(self) -> None:
        """Cut the sound off."""
        self.stopped = True


class FakeSound:
    """A Sound made from an array; records each play."""

    def __init__(self, array: Any, record: dict[str, Any]) -> None:
        self.array = array
        self.record = record

    def play(self) -> FakeChannel:
        """Start a channel and return it."""
        channel = FakeChannel(self, self.record["busy_polls"])
        self.record["channels"].append(channel)
        return channel


def new_record() -> dict[str, Any]:
    """Return an empty record of everything the fakes see."""
    return {
        "synth": [],
        "loads": [],
        "channels": [],
        "sounds": [],
        "busy_polls": 2,
        "mixer_inits": 0,
        "mixer": (44100, -16, 2),
    }


def install_fake_piper(
    monkeypatch: pytest.MonkeyPatch, record: dict[str, Any]
) -> types.ModuleType:
    """Install fake piper and pygame modules that log into record; return fake piper."""
    piper = types.ModuleType("piper")

    class PiperVoice:
        @staticmethod
        def load(path: str) -> FakeVoice:
            record["loads"].append(Path(path).name)
            return FakeVoice(path, record)

    piper.PiperVoice = PiperVoice  # type: ignore[attr-defined]
    piper.SynthesisConfig = FakeSynthesisConfig  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "piper", piper)

    pygame = types.ModuleType("pygame")
    state = {"init": True}

    def get_init() -> tuple[int, int, int] | None:
        return record["mixer"] if state["init"] else None

    def init() -> None:
        record["mixer_inits"] += 1
        state["init"] = True

    def make_sound(array: Any) -> FakeSound:
        sound = FakeSound(array, record)
        record["sounds"].append(sound)
        return sound

    pygame.mixer = types.SimpleNamespace(get_init=get_init, init=init)  # type: ignore[attr-defined]
    pygame.sndarray = types.SimpleNamespace(make_sound=make_sound)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pygame", pygame)
    return piper


@pytest.fixture
def record() -> dict[str, Any]:
    """Everything the fakes saw."""
    return new_record()


@pytest.fixture
def fake_piper(monkeypatch: pytest.MonkeyPatch, record: dict[str, Any]) -> types.ModuleType:
    """Install fake piper and pygame modules."""
    return install_fake_piper(monkeypatch, record)


class FakeSystemSpeaker:
    """Stands in for Pyttsx3Speaker."""

    instances: ClassVar[list[FakeSystemSpeaker]] = []

    def __init__(self, rate: int = SPEECH_RATE_WPM) -> None:
        self.rate = rate
        self.voice_calls: list[str | None] = []
        self.said: list[str] = []
        FakeSystemSpeaker.instances.append(self)

    def installed_voices(self) -> list[tuple[str, str]]:
        """List Samantha."""
        return [SAMANTHA]

    def set_voice(self, voice_id: str | None) -> None:
        """Record the switch."""
        self.voice_calls.append(voice_id)

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Record the text."""
        self.said.append(text)


@pytest.fixture
def system(monkeypatch: pytest.MonkeyPatch) -> type[FakeSystemSpeaker]:
    """Replace pyttsx3 with the fake system speaker."""
    FakeSystemSpeaker.instances = []
    monkeypatch.setattr(backends, "Pyttsx3Speaker", FakeSystemSpeaker)
    return FakeSystemSpeaker


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point VOICE_MODEL_DIR at tmp_path with only alba and cori downloaded."""
    monkeypatch.setattr(voices, "VOICE_MODEL_DIR", tmp_path)
    for model in ("en_GB-alba-medium", "en_GB-cori-high"):
        (tmp_path / f"{model}.onnx").write_bytes(b"")
    return tmp_path


def pid(key: str) -> str:
    """Return the Piper voice id of a preset."""
    preset = voices.preset_for(key)
    assert preset is not None
    return voices.piper_voice_id(preset)


def wait_for(condition: Callable[[], bool], timeout: float = 2.0) -> bool:
    """Poll until condition() is true or timeout passes."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.005)
    return condition()


def test_installed_voices_lists_only_downloaded_models(
    fake_piper: Any, system: Any, models: Path
) -> None:
    """Presets with a model file come first, then the system voices."""
    speaker = backends.HybridSpeaker()
    assert speaker.installed_voices() == [
        (pid("alba"), "Alba"),
        (pid("cori"), "Cori"),
        SAMANTHA,
    ]
    assert voices.installed_keys(speaker.installed_voices()) == ["alba", "cori"]


def test_mixer_left_alone_when_already_open(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """The alarm opens the mixer first; the speaker does not open it again."""
    backends.HybridSpeaker()
    assert record["mixer_inits"] == 0


def test_set_voice_loads_once_and_caches(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """Switching back to a loaded voice does not load its model again."""
    speaker = backends.HybridSpeaker(preload=False)
    speaker.set_voice(pid("alba"))
    speaker.set_voice(pid("cori"))
    speaker.set_voice(pid("alba"))
    assert record["loads"] == ["en_GB-alba-medium.onnx", "en_GB-cori-high.onnx"]


def test_set_voice_load_failure_raises(
    fake_piper: Any, system: Any, models: Path
) -> None:
    """A model that will not load raises, so the manager reports a failed switch."""

    def broken(path: str) -> Any:
        raise RuntimeError("bad model")

    fake_piper.PiperVoice.load = staticmethod(broken)
    speaker = backends.HybridSpeaker()
    with pytest.raises(RuntimeError):
        speaker.set_voice(pid("alba"))
    with pytest.raises(ValueError):
        speaker.set_voice("piper.premium.en-US.Nobody")


def test_say_uses_calm_length_scale_and_mixer_format(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """length_scale is 180/165 and every sentence is resampled to stereo int16 at 44.1 kHz."""
    speaker = backends.HybridSpeaker()
    speaker.set_voice(pid("alba"))
    speaker.say("Heinz ketchup. On the table.", lambda: False)
    [(_, text, config)] = record["synth"]
    assert text == "Heinz ketchup. On the table."
    assert config.length_scale == pytest.approx(180 / 165)
    assert backends.PIPER_NATURAL_WPM == 180
    assert len(record["sounds"]) == 2
    array = record["sounds"][0].array
    assert array.dtype == np.int16
    assert array.shape == (SAMPLES * 2, 2)
    assert np.array_equal(array[:, 0], array[:, 1])
    assert len(record["channels"]) == 2
    assert system.instances[0].said == []


def test_mono_float_mixer_format(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """A mono float32 mixer at 22050 Hz gets the samples unchanged in scale -1..1."""
    record["mixer"] = (22050, 32, 1)
    speaker = backends.HybridSpeaker()
    speaker.set_voice(pid("alba"))
    speaker.say("Heinz ketchup", lambda: False)
    array = record["sounds"][0].array
    assert array.dtype == np.float32 and array.shape == (SAMPLES,)
    assert array[1] == pytest.approx(1 / 32768)


def test_should_stop_mid_play_stops_channel(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """Once should_stop() turns true the playing channel is stopped and say returns."""
    record["busy_polls"] = None  # the sound would never end by itself
    speaker = backends.HybridSpeaker()
    speaker.set_voice(pid("alba"))
    alarm = threading.Event()
    done = threading.Event()

    def run() -> None:
        speaker.say("A long answer. With two sentences.", alarm.is_set)
        done.set()

    threading.Thread(target=run, daemon=True).start()
    assert wait_for(lambda: len(record["channels"]) == 1)
    start = time.monotonic()
    alarm.set()
    assert done.wait(1.0)
    assert time.monotonic() - start < 0.2
    assert record["channels"][0].stopped
    assert len(record["channels"]) == 1  # the second sentence never started


def test_should_stop_before_say_plays_nothing(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """should_stop() already true: nothing is synthesised or played."""
    speaker = backends.HybridSpeaker()
    speaker.set_voice(pid("alba"))
    speaker.say("Heinz ketchup", lambda: True)
    assert record["synth"] == [] and record["channels"] == []


def test_system_voice_routes_to_pyttsx3(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """A non-Piper id (or None) goes to pyttsx3 and switches Piper off."""
    speaker = backends.HybridSpeaker()
    speaker.set_voice(pid("alba"))
    speaker.set_voice(SAMANTHA[0])
    speaker.say("Dell laptop", lambda: False)
    fake_system = system.instances[0]
    assert fake_system.voice_calls == [SAMANTHA[0]]
    assert fake_system.said == ["Dell laptop"]
    assert record["synth"] == []
    speaker.set_voice(None)
    assert fake_system.voice_calls[-1] is None


def test_prepare_caches_and_say_uses_cache(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """prepare() renders in the background; say() then plays one cached Sound."""
    speaker = backends.HybridSpeaker()
    speaker.set_voice(pid("alba"))
    start = time.monotonic()
    speaker.prepare(["Stop. Stairs.", "Stop.", "Stop."])
    assert time.monotonic() - start < 0.05
    assert wait_for(lambda: speaker.is_prepared("Stop. Stairs.") and speaker.is_prepared("Stop."))
    assert [text for _, text, _ in record["synth"]] == ["Stop. Stairs.", "Stop."]
    cached = record["sounds"][0]
    assert cached.array.shape == (SAMPLES * 2 * 2, 2)  # both sentences in one Sound
    synth_before = len(record["synth"])
    speaker.say("Stop. Stairs.", lambda: False)
    assert len(record["synth"]) == synth_before
    assert record["channels"][-1].sound is cached
    # Another voice has its own cache.
    speaker.set_voice(pid("cori"))
    assert not speaker.is_prepared("Stop. Stairs.")


def test_cached_phrase_can_be_cut_off(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """A pre-rendered phrase still stops as soon as should_stop() is true."""
    speaker = backends.HybridSpeaker()
    speaker.set_voice(pid("alba"))
    speaker.prepare(["Stop. Vehicle."])
    assert wait_for(lambda: speaker.is_prepared("Stop. Vehicle."))
    record["busy_polls"] = None
    calls = {"n": 0}

    def stop_after_a_few() -> bool:
        calls["n"] += 1
        return calls["n"] > 3

    speaker.say("Stop. Vehicle.", stop_after_a_few)
    assert record["channels"][-1].stopped


def test_prepare_is_a_no_op_for_system_voice(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """With pyttsx3 speaking there is nothing to pre-render."""
    speaker = backends.HybridSpeaker()
    speaker.set_voice(SAMANTHA[0])
    speaker.prepare(["Stop."])
    time.sleep(0.05)
    assert record["synth"] == []


def test_missing_piper_falls_back_to_pyttsx3(
    monkeypatch: pytest.MonkeyPatch, system: Any, models: Path
) -> None:
    """Without piper only system voices are listed and pyttsx3 speaks."""
    monkeypatch.setitem(sys.modules, "piper", None)
    speaker = backends.HybridSpeaker()
    assert speaker.installed_voices() == [SAMANTHA]
    assert voices.resolve_voice("alba", speaker.installed_voices()).quality == "fallback"
    speaker.set_voice(SAMANTHA[0])
    speaker.say("Heinz ketchup", lambda: False)
    assert system.instances[0].said == ["Heinz ketchup"]
    with pytest.raises(ValueError):
        speaker.set_voice(pid("alba"))


def test_no_engine_at_all_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither piper nor pyttsx3: the constructor raises so the manager logs instead."""
    monkeypatch.setitem(sys.modules, "piper", None)

    def broken(rate: int = SPEECH_RATE_WPM) -> Any:
        raise RuntimeError("no pyttsx3")

    monkeypatch.setattr(backends, "Pyttsx3Speaker", broken)
    with pytest.raises(RuntimeError):
        backends.HybridSpeaker()


def test_piper_only_without_pyttsx3(
    fake_piper: Any, monkeypatch: pytest.MonkeyPatch, models: Path, record: dict[str, Any]
) -> None:
    """pyttsx3 failing still leaves Piper voices working."""

    def broken(rate: int = SPEECH_RATE_WPM) -> Any:
        raise RuntimeError("no pyttsx3")

    monkeypatch.setattr(backends, "Pyttsx3Speaker", broken)
    speaker = backends.HybridSpeaker()
    assert speaker.installed_voices() == [(pid("alba"), "Alba"), (pid("cori"), "Cori")]
    speaker.set_voice(pid("cori"))
    speaker.say("Heinz ketchup", lambda: False)
    assert len(record["channels"]) == 1


def test_hybrid_speaker_declares_real() -> None:
    """The manager reports HybridSpeaker as real playback."""
    assert backends.HybridSpeaker.mode == "real"


def test_trim_silence_cuts_piper_padding() -> None:
    """Leading and trailing silence is cut to short pads; all-quiet audio is kept."""
    import numpy as np

    rate = 1000
    speech = np.full(100, 5000, dtype=np.int16)
    padded = np.concatenate([np.zeros(260, np.int16), speech, np.zeros(280, np.int16)])
    trimmed = backends._trim_silence(np, padded, rate)
    lead = int(backends.LEAD_PAD_SECONDS * rate)
    tail = int(backends.TAIL_PAD_SECONDS * rate)
    assert len(trimmed) == lead + 100 + tail
    assert trimmed[lead] == 5000
    quiet = np.zeros(50, np.int16)
    assert len(backends._trim_silence(np, quiet, rate)) == 50


def test_prerender_waits_while_live_speech_synthesises() -> None:
    """Pre-rendering pauses between sentences while live speech is synthesising."""
    speaker = backends.HybridSpeaker.__new__(backends.HybridSpeaker)
    speaker._synth_lock = threading.Lock()
    speaker._live = threading.Event()
    speaker._live_count = 0
    speaker._live_lock = threading.Lock()
    speaker._rate = 165
    speaker._piper = types.SimpleNamespace(SynthesisConfig=lambda **kw: kw)
    voice = types.SimpleNamespace(synthesize=lambda text, syn_config=None: iter(["s1", "s2"]))
    speaker._mark_live(+1)
    got: list[str] = []
    worker = threading.Thread(
        target=lambda: got.extend(speaker._synth_chunks(voice, "x", yield_to_live=True))
    )
    worker.start()
    time.sleep(0.05)
    assert got == []  # held back while live speech runs
    speaker._mark_live(-1)
    worker.join(1.0)
    assert got == ["s1", "s2"]


def test_new_prepare_cancels_the_old_one() -> None:
    """A cancelled pre-render stops before its next sentence."""
    speaker = backends.HybridSpeaker.__new__(backends.HybridSpeaker)
    speaker._synth_lock = threading.Lock()
    speaker._live = threading.Event()
    speaker._rate = 165
    speaker._piper = types.SimpleNamespace(SynthesisConfig=lambda **kw: kw)
    voice = types.SimpleNamespace(synthesize=lambda text, syn_config=None: iter(["s1", "s2"]))
    cancel = threading.Event()
    cancel.set()
    assert list(speaker._synth_chunks(voice, "x", cancel, yield_to_live=True)) == []


def test_downloaded_models_preload_in_background(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any]
) -> None:
    """Every downloaded model is loaded off the speech worker, once; a switch then loads nothing."""
    speaker = backends.HybridSpeaker()
    assert wait_for(lambda: len(record["loads"]) == 2)
    speaker.set_voice(pid("cori"))
    assert sorted(record["loads"]) == sorted(set(record["loads"]))
    assert len(record["loads"]) == 2
    backends.HybridSpeaker(preload=False)
    time.sleep(0.05)
    assert len(record["loads"]) == 2


@pytest.mark.parametrize("fail_load", [False, True])
def test_hazard_speaks_while_requested_model_loads(
    fake_piper: Any, system: Any, models: Path, record: dict[str, Any], fail_load: bool
) -> None:
    """A switch loading on another thread cannot hold up hazard speech in the old voice."""
    speaker = backends.HybridSpeaker(preload=False)
    speaker.set_voice(pid("alba"))
    entered, release = threading.Event(), threading.Event()
    original_load = fake_piper.PiperVoice.load

    def gated_load(path: str) -> FakeVoice:
        entered.set()
        assert release.wait(5)
        if fail_load:
            raise RuntimeError("bad model")
        return original_load(path)

    fake_piper.PiperVoice.load = staticmethod(gated_load)
    beeps = threading.Event()
    alarm = types.SimpleNamespace(mode="fake", duration=0.0, play=beeps.set, close=lambda: None)
    published: list[Any] = []
    manager = AudioManager(lambda: speaker, alarm, publish=published.append)
    try:
        assert wait_for(lambda: any(isinstance(m, VoiceStatus) for m in published))
        manager.on_voice_change(VoiceChange(time.time(), "cori", "slow-switch"))
        assert entered.wait(2)
        manager.on_hazard(HazardEvent(time.time(), "stairs_down", "yolo", 1.0))
        assert beeps.is_set()
        assert wait_for(lambda: any(
            isinstance(m, SpeechStatus) and m.kind == "hazard" and m.status == "completed"
            for m in published
        ))
        assert not release.is_set()
        assert speaker._active == voices.preset_for("alba")
        assert record["channels"]  # actual fake-mixer playback, not just queued telemetry
        release.set()
        assert wait_for(lambda: any(
            isinstance(m, VoiceStatus) and m.request_id == "slow-switch" for m in published
        ))
        status = next(m for m in published if isinstance(m, VoiceStatus) and m.request_id == "slow-switch")
        assert status.state == ("failed" if fail_load else "active")
        assert status.active_voice == ("alba" if fail_load else "cori")
    finally:
        release.set()
        manager.stop()


def test_cached_switch_does_not_wait_for_unrelated_preload(
    fake_piper: Any, system: Any, models: Path
) -> None:
    """The speech worker can activate a cached model even while another model loads."""
    speaker = backends.HybridSpeaker(preload=False)
    speaker.set_voice(pid("alba"))
    switched = threading.Event()
    with speaker._load_lock:
        worker = threading.Thread(target=lambda: (speaker.try_set_voice(pid("alba")), switched.set()))
        worker.start()
        ready_without_lock = switched.wait(1)
    worker.join(2)
    assert ready_without_lock
    assert speaker._active == voices.preset_for("alba")


def test_new_request_supersedes_loading_voice(
    fake_piper: Any, system: Any, models: Path
) -> None:
    """Finishing a superseded load must not switch back from the user's latest choice."""
    speaker = backends.HybridSpeaker(preload=False)
    speaker.set_voice(pid("alba"))
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_load = fake_piper.PiperVoice.load

    def gated_load(path: str) -> FakeVoice:
        entered.set()
        assert release.wait(5)
        result = original_load(path)
        finished.set()
        return result

    fake_piper.PiperVoice.load = staticmethod(gated_load)
    published: list[Any] = []
    alarm = types.SimpleNamespace(mode="fake", duration=0.0, play=lambda: None, close=lambda: None)
    manager = AudioManager(lambda: speaker, alarm, publish=published.append)
    try:
        assert wait_for(lambda: any(isinstance(m, VoiceStatus) for m in published))
        manager.on_voice_change(VoiceChange(time.time(), "cori", "old"))
        assert entered.wait(2)
        manager.on_voice_change(VoiceChange(time.time(), "alba", "new"))
        assert wait_for(lambda: any(isinstance(m, VoiceStatus) and m.request_id == "new" for m in published))
        release.set()
        assert finished.wait(2)
        manager.on_hazard(HazardEvent(time.time(), "stairs_down", "yolo", 1.0))
        assert wait_for(lambda: any(isinstance(m, SpeechStatus) and m.kind == "hazard" and m.status == "completed" for m in published))
        assert speaker._active == voices.preset_for("alba")
        assert not any(isinstance(m, VoiceStatus) and m.request_id == "old" for m in published)
    finally:
        release.set()
        manager.stop()


@pytest.mark.parametrize("alarm_mode", ["fake", "unavailable"])
def test_startup_model_load_keeps_system_hazard_voice_available(
    fake_piper: Any, system: Any, models: Path, alarm_mode: str
) -> None:
    """Startup loading also leaves the worker able to speak hazards using the fallback."""
    entered, release = threading.Event(), threading.Event()
    original_load = fake_piper.PiperVoice.load

    def gated_load(path: str) -> FakeVoice:
        entered.set()
        assert release.wait(5)
        return original_load(path)

    fake_piper.PiperVoice.load = staticmethod(gated_load)
    speaker = backends.HybridSpeaker(preload=False)
    published: list[Any] = []
    alarm = types.SimpleNamespace(mode=alarm_mode, duration=0.0, play=lambda: None, close=lambda: None)
    manager = AudioManager(lambda: speaker, alarm, publish=published.append)
    try:
        assert entered.wait(2)
        assert wait_for(lambda: any(isinstance(m, ModuleStatus) for m in published))
        startup = next(m for m in published if isinstance(m, ModuleStatus))
        assert "loading Alba" in startup.detail
        assert "not installed" not in startup.detail
        assert next(m for m in published if isinstance(m, VoiceStatus)).state == "switching"
        manager.on_hazard(HazardEvent(time.time(), "stairs_down", "yolo", 1.0))
        assert wait_for(lambda: system.instances[0].said == ["Stop. Stairs."])
        release.set()
        assert wait_for(lambda: any(
            isinstance(m, VoiceStatus) and m.quality == "enhanced" for m in published
        ))
        health = [m for m in published if isinstance(m, ModuleStatus)][-1]
        assert health.status == ("active" if alarm_mode == "fake" else "degraded")
        assert "loading" not in health.detail and "not installed" not in health.detail
        assert ("alarm beeps unavailable" in health.detail) == (alarm_mode == "unavailable")
        assert not any(isinstance(m, SpeechStatus) and m.source == "audio" for m in published)
    finally:
        release.set()
        manager.stop()
