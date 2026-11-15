"""Audio in five languages: presets, hazard phrases, sample lines and spoken names.

No sound device is used: the speaker and alarm are the recording stand-ins from
tests/test_audio_voice_switch.py.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
from test_audio_voice_switch import (
    PREMIUM,
    SAMANTHA,
    PreparingSpeaker,
    RecordingAlarm,
    VoiceSpeaker,
    statuses,
    wait_for,
)

from audio.audio import AudioManager
from audio.phrases import FALLBACK_HAZARD_PHRASES, HAZARD_PHRASES, hazard_phrase
from audio.voices import (
    PRESETS,
    active_language,
    default_voice_for,
    language_of,
    resolve_voice,
)
from contracts import HazardEvent, NameResult, TouchEvent, VoiceChange
from contracts.languages import LANGUAGES

BOX = (10.0, 10.0, 50.0, 50.0)
LANGUAGE_VOICES = {"zh": "huayan", "es": "claude", "fr": "siwis", "hi": "priyamvada"}


def touch(object_id: int, label: str, name: str = "") -> TouchEvent:
    """Build a touch TouchEvent."""
    return TouchEvent(time.time(), object_id, label, name, "touch", BOX, [])


def name_result(
    object_id: int, name: str, spoken: str = "", language: str = ""
) -> NameResult:
    """Build a successful NameResult."""
    return NameResult(time.time(), object_id, name, True, spoken, language)


@pytest.fixture
def published() -> list[Any]:
    """Everything the manager publishes."""
    return []


def start(speaker: VoiceSpeaker, published: list[Any], voice: str = "alba") -> AudioManager:
    """Start a manager on voice and wait for its startup VoiceStatus."""
    mgr = AudioManager(lambda: speaker, RecordingAlarm(), publish=published.append, voice=voice)
    assert wait_for(lambda: len(statuses(published)) == 1)
    return mgr


@pytest.fixture
def french(published: list[Any]) -> Iterator[tuple[AudioManager, VoiceSpeaker]]:
    """A manager already speaking French with Siwis, every preset installed."""
    speaker = VoiceSpeaker()
    mgr = start(speaker, published, voice="siwis")
    yield mgr, speaker
    speaker.gate.set()
    mgr.stop()


def test_presets_and_languages() -> None:
    """Each language has its preset, English first; default_voice_for picks the first."""
    assert [p.language for p in PRESETS if p.key in LANGUAGE_VOICES.values()] == list(
        LANGUAGE_VOICES
    )
    assert {p.language for p in PRESETS} == set(LANGUAGES)
    assert default_voice_for("en") == "alba"
    for language, key in LANGUAGE_VOICES.items():
        assert default_voice_for(language) == key
        assert language_of(key) == language
    assert language_of("bob") == "en"
    assert default_voice_for("xx") == "alba"
    hindi = next(p for p in PRESETS if p.key == "priyamvada")
    assert (hindi.locale, hindi.model) == ("hi-IN", "hi_IN-priyamvada-medium")


def test_fallback_voice_is_english() -> None:
    """A missing preset falls back to Samantha and its active language is English."""
    resolved = resolve_voice("priyamvada", [SAMANTHA])
    assert resolved.quality == "fallback"
    assert active_language(resolved) == "en"
    assert active_language(resolve_voice("siwis", [PREMIUM["siwis"]])) == "fr"


def test_status_reports_language_and_voice_languages(published: list[Any]) -> None:
    """VoiceStatus carries the active language and every preset's language."""
    speaker = VoiceSpeaker()
    mgr = start(speaker, published)
    try:
        first = statuses(published)[0]
        assert first.language == "en"
        assert first.voice_languages == {p.key: p.language for p in PRESETS}
        mgr.on_voice_change(VoiceChange(1.0, "claude", "r1"))
        assert wait_for(lambda: len(statuses(published)) == 2)
        assert statuses(published)[-1].language == "es"
        assert wait_for(lambda: speaker.finished == ["Soy Claude."])
    finally:
        mgr.stop()


@pytest.mark.parametrize("language", list(LANGUAGE_VOICES))
def test_hazard_phrase_follows_language_after_switch(
    language: str, published: list[Any]
) -> None:
    """After a switch, the sample line and hazard phrase are in the new language."""
    speaker = VoiceSpeaker()
    mgr = start(speaker, published)
    try:
        key = LANGUAGE_VOICES[language]
        mgr.on_voice_change(VoiceChange(1.0, key, "r1"))
        assert wait_for(lambda: len(speaker.finished) == 1)
        mgr.on_hazard(HazardEvent(time.time(), "stairs_down", "yolo", 0.9))
        assert wait_for(lambda: len(speaker.finished) == 2)
        assert speaker.finished[1] == HAZARD_PHRASES[language]["stairs_down"]
        assert speaker.voice_at_start[1] == PREMIUM[key][0]
    finally:
        mgr.stop()


def test_expected_phrases() -> None:
    """Spot-check the phrase tables against the plan."""
    assert hazard_phrase("stairs_down", "hi") == "रुकिए। सीढ़ियाँ।"
    assert hazard_phrase("drop_off", "zh") == "停。前方有落差。"
    assert hazard_phrase("unknown", "es") == "Alto."
    assert hazard_phrase("vehicle", "xx") == "Stop. Vehicle."
    assert FALLBACK_HAZARD_PHRASES["fr"] == "Stop."


def test_missing_hindi_speaks_english(published: list[Any]) -> None:
    """Hindi without its model: Samantha, language en, English sample, hazard and label."""
    speaker = VoiceSpeaker(voices=[PREMIUM["alba"], SAMANTHA])
    mgr = start(speaker, published)
    try:
        mgr.on_voice_change(VoiceChange(1.0, "priyamvada", "r1"))
        assert wait_for(lambda: len(statuses(published)) == 2)
        status = statuses(published)[-1]
        assert status.quality == "fallback" and status.language == "en"
        assert wait_for(lambda: speaker.finished == ["This is Priyamvada."])
        mgr.on_hazard(HazardEvent(time.time(), "vehicle", "yolo", 0.9))
        assert wait_for(lambda: len(speaker.finished) == 2)
        assert speaker.finished[1] == "Stop. Vehicle."
        mgr.on_name(name_result(4, "Dasani water", "दसानी पानी", "hi"))
        mgr.on_touch(touch(4, "bottle"))
        assert wait_for(lambda: len(speaker.finished) == 3)
        assert speaker.finished[2] == "Dasani water"
        assert speaker.voice_at_start[2] == SAMANTHA[0]
    finally:
        mgr.stop()


def test_translated_label_without_spoken_name(
    french: tuple[AudioManager, VoiceSpeaker],
) -> None:
    """In French, a touch with only an English name speaks the translated class label."""
    mgr, speaker = french
    mgr.on_touch(touch(1, "bottle", name="Heinz ketchup"))
    assert wait_for(lambda: speaker.finished == ["bouteille"])


def test_matching_spoken_name_is_spoken(french: tuple[AudioManager, VoiceSpeaker]) -> None:
    """A French spoken_name that arrived first is spoken on touch."""
    mgr, speaker = french
    mgr.on_name(name_result(2, "Heinz ketchup", "ketchup Heinz", "fr"))
    mgr.on_touch(touch(2, "bottle", name="Heinz ketchup"))
    assert wait_for(lambda: speaker.finished == ["ketchup Heinz"])


def test_wrong_language_spoken_name_is_not_spoken(
    french: tuple[AudioManager, VoiceSpeaker],
) -> None:
    """A Spanish spoken_name is never spoken in French, early or late."""
    mgr, speaker = french
    mgr.on_name(name_result(3, "Heinz ketchup", "salsa de tomate Heinz", "es"))
    mgr.on_touch(touch(3, "bottle"))
    assert wait_for(lambda: speaker.finished == ["bouteille"])
    mgr.on_name(name_result(3, "Heinz ketchup", "salsa de tomate Heinz", "es"))
    time.sleep(0.1)
    assert speaker.finished == ["bouteille"]


def test_late_spoken_name_in_language(french: tuple[AudioManager, VoiceSpeaker]) -> None:
    """A matching spoken_name arriving after the label is spoken once."""
    mgr, speaker = french
    mgr.on_touch(touch(5, "cup"))
    assert wait_for(lambda: speaker.finished == ["tasse"])
    mgr.on_name(name_result(5, "Starbucks cup", "tasse Starbucks", "fr"))
    assert wait_for(lambda: speaker.finished == ["tasse", "tasse Starbucks"])
    mgr.on_name(name_result(5, "Starbucks cup", "tasse Starbucks", "fr"))
    time.sleep(0.1)
    assert speaker.finished == ["tasse", "tasse Starbucks"]


def test_switch_away_drops_old_spoken_name(published: list[Any]) -> None:
    """After switching French to Spanish, the French spoken_name gives way to the label."""
    speaker = VoiceSpeaker()
    mgr = start(speaker, published, voice="siwis")
    try:
        mgr.on_name(name_result(6, "Heinz ketchup", "ketchup Heinz", "fr"))
        mgr.on_voice_change(VoiceChange(1.0, "claude", "r1"))
        assert wait_for(lambda: speaker.finished == ["Soy Claude."])
        mgr.on_touch(touch(6, "bottle"))
        assert wait_for(lambda: speaker.finished == ["Soy Claude.", "botella"])
    finally:
        mgr.stop()


def test_english_touch_unchanged(published: list[Any]) -> None:
    """In English the Grok name is spoken and a spoken_name is ignored."""
    speaker = VoiceSpeaker()
    mgr = start(speaker, published)
    try:
        mgr.on_name(name_result(7, "Heinz ketchup", "ketchup Heinz", "fr"))
        mgr.on_touch(touch(7, "bottle"))
        assert wait_for(lambda: speaker.finished == ["Heinz ketchup"])
    finally:
        mgr.stop()


def test_prepare_gets_target_language_phrases(published: list[Any]) -> None:
    """prepare() receives the hazard phrases of the language being switched to."""
    speaker = PreparingSpeaker()
    mgr = start(speaker, published)
    try:
        assert wait_for(lambda: len(speaker.prepared) == 1)
        mgr.on_voice_change(VoiceChange(1.0, "huayan", "r1"))
        assert wait_for(lambda: len(speaker.prepared) == 2)
        assert speaker.prepared[1] == (
            PREMIUM["huayan"][0],
            [*HAZARD_PHRASES["zh"].values(), "停。"],
        )
    finally:
        mgr.stop()


class SlowSwitchSpeaker(VoiceSpeaker):
    """Holds set_voice for a switch until released, like a slow model load."""

    def __init__(self) -> None:
        super().__init__()
        self.switching = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def set_voice(self, voice_id: str | None) -> None:
        """Block until released, then record the switch."""
        self.switching.set()
        self.release.wait(2.0)
        super().set_voice(voice_id)


def test_hazard_during_switch_is_worded_for_loaded_voice(published: list[Any]) -> None:
    """A hazard queued mid-switch is spoken in the language of the voice then loaded."""
    speaker = SlowSwitchSpeaker()
    mgr = start(speaker, published)
    try:
        speaker.switching.clear()
        speaker.release.clear()
        mgr.on_voice_change(VoiceChange(1.0, "siwis", "r1"))
        assert speaker.switching.wait(2.0)
        mgr.on_hazard(HazardEvent(time.time(), "stairs_down", "yolo", 0.9))
        speaker.release.set()
        assert wait_for(lambda: len(speaker.finished) >= 1)
        assert speaker.finished[0] == "Stop. Escalier."
        assert speaker.voice_at_start[0] == PREMIUM["siwis"][0]
    finally:
        speaker.release.set()
        mgr.stop()
