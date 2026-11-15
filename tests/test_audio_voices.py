"""Voice presets and matching them to installed pyttsx3 voices (audio/voices.py)."""

from __future__ import annotations

import logging

import pytest

from audio.voices import (
    PRESETS,
    installed_keys,
    resolve_voice,
    startup_voice_key,
)

SAMANTHA = ("com.apple.voice.compact.en-US.Samantha", "Samantha")
INSTALLED = [
    ("com.apple.voice.compact.en-US.Ava", "Ava"),
    ("com.apple.voice.premium.en-US.Ava", "Ava (Premium)"),
    ("com.apple.voice.premium.en-US.Zoe", "Zoe"),
    ("com.apple.voice.enhanced.en-US.Evan", "Evan (Enhanced)"),
    ("com.apple.voice.premium.en-GB.Jamie", "Jamie"),
    ("com.apple.voice.premium.en-AU.Matilda", "Matilda (Premium)"),
    SAMANTHA,
]


def test_five_presets_in_order() -> None:
    """The presets are ava, zoe, evan, jamie and matilda, in that order."""
    assert [p.key for p in PRESETS] == ["ava", "zoe", "evan", "jamie", "matilda"]
    assert [p.label for p in PRESETS] == ["Ava", "Zoe", "Evan", "Jamie", "Matilda"]


def test_premium_beats_compact() -> None:
    """With both a compact and a premium Ava installed, premium is used."""
    resolved = resolve_voice("ava", INSTALLED)
    assert resolved.voice_id == "com.apple.voice.premium.en-US.Ava"
    assert resolved.quality == "premium"
    assert resolved.label == "Ava"


def test_enhanced_quality_is_reported() -> None:
    """An enhanced voice is reported as enhanced."""
    resolved = resolve_voice("evan", INSTALLED)
    assert resolved.voice_id == "com.apple.voice.enhanced.en-US.Evan"
    assert resolved.quality == "enhanced"


def test_name_with_parenthetical_matches() -> None:
    """A name reported as "Zoe (Premium)" still matches the zoe preset."""
    resolved = resolve_voice(
        "zoe", [("com.apple.voice.premium.en-US.Zoe", "Zoe (Premium)")]
    )
    assert resolved.voice_id == "com.apple.voice.premium.en-US.Zoe"
    assert resolved.quality == "premium"


def test_locale_must_match() -> None:
    """An en-GB Ava does not satisfy the en-US ava preset."""
    resolved = resolve_voice(
        "ava", [("com.apple.voice.premium.en-GB.Ava", "Ava"), SAMANTHA]
    )
    assert resolved.voice_id == SAMANTHA[0]
    assert resolved.quality == "fallback"


def test_missing_voice_falls_back_to_samantha() -> None:
    """With only Samantha installed, jamie speaks with Samantha, reported as fallback."""
    resolved = resolve_voice("jamie", [SAMANTHA])
    assert resolved.voice_id == SAMANTHA[0]
    assert resolved.quality == "fallback"
    assert resolved.key == "jamie"
    assert resolved.label == "Jamie"


def test_nothing_installed_uses_system_default() -> None:
    """With no voices listed, the system default voice is used."""
    resolved = resolve_voice("ava", [])
    assert resolved.voice_id is None
    assert resolved.quality == "fallback"


def test_installed_keys_lists_only_real_matches() -> None:
    """Samantha standing in does not count as a preset being installed."""
    assert installed_keys([("com.apple.voice.premium.en-US.Ava", "Ava"), SAMANTHA]) == [
        "ava"
    ]
    assert installed_keys(INSTALLED) == ["ava", "zoe", "evan", "jamie", "matilda"]


def test_startup_key_from_env(caplog: pytest.LogCaptureFixture) -> None:
    """AUDIO_VOICE is trimmed and lowercased; blank or unknown means ava."""
    assert startup_voice_key({"AUDIO_VOICE": " Evan "}) == "evan"
    assert startup_voice_key({}) == "ava"
    assert startup_voice_key({"AUDIO_VOICE": ""}) == "ava"
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="audio"):
        assert startup_voice_key({"AUDIO_VOICE": "bob"}) == "ava"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "bob" in warnings[0].getMessage()
