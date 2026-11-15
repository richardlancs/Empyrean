"""Voice presets and matching them to installed voices (audio/voices.py)."""

from __future__ import annotations

import logging

import pytest

from audio.voices import (
    PRESETS,
    VOICE_MODEL_DIR,
    installed_keys,
    piper_model_path,
    piper_voice_id,
    preset_for,
    resolve_voice,
    startup_voice_key,
)

KEYS = ["alba", "kristin", "northern", "cori", "lessac"]
SAMANTHA = ("com.apple.voice.compact.en-US.Samantha", "Samantha")


def piper(key: str) -> tuple[str, str]:
    """Return the (voice_id, name) pair a Piper speaker lists for this preset."""
    preset = preset_for(key)
    assert preset is not None
    return piper_voice_id(preset), preset.voice_name


INSTALLED = [piper(key) for key in KEYS] + [SAMANTHA]


def test_five_presets_in_order() -> None:
    """The presets are alba, kristin, northern, cori and lessac, in that order."""
    assert [p.key for p in PRESETS] == KEYS
    assert [p.label for p in PRESETS] == [
        "Alba",
        "Kristin",
        "Northern English",
        "Cori",
        "Lessac",
    ]


def test_piper_ids_and_model_paths() -> None:
    """High models list as premium, medium as enhanced; models live in VOICE_MODEL_DIR."""
    assert piper("cori")[0] == "piper.premium.en-GB.Cori"
    assert piper("alba")[0] == "piper.enhanced.en-GB.Alba"
    preset = preset_for("lessac")
    assert preset is not None
    assert piper_model_path(preset) == VOICE_MODEL_DIR / "en_US-lessac-high.onnx"


def test_premium_beats_compact() -> None:
    """With both a compact and a premium Cori installed, premium is used."""
    resolved = resolve_voice(
        "cori", [("system.compact.en-GB.Cori", "Cori"), piper("cori"), SAMANTHA]
    )
    assert resolved.voice_id == "piper.premium.en-GB.Cori"
    assert resolved.quality == "premium"
    assert resolved.label == "Cori"


def test_enhanced_quality_is_reported() -> None:
    """A medium Piper voice is reported as enhanced."""
    resolved = resolve_voice("alba", INSTALLED)
    assert resolved.voice_id == "piper.enhanced.en-GB.Alba"
    assert resolved.quality == "enhanced"


def test_name_with_parenthetical_matches() -> None:
    """A name reported as "Lessac (Premium)" still matches the lessac preset."""
    voice_id = piper("lessac")[0]
    resolved = resolve_voice("lessac", [(voice_id, "Lessac (Premium)")])
    assert resolved.voice_id == voice_id
    assert resolved.quality == "premium"


def test_locale_must_match() -> None:
    """An en-US Alba does not satisfy the en-GB alba preset."""
    resolved = resolve_voice(
        "alba", [("piper.enhanced.en-US.Alba", "Alba"), SAMANTHA]
    )
    assert resolved.voice_id == SAMANTHA[0]
    assert resolved.quality == "fallback"


def test_missing_voice_falls_back_to_samantha() -> None:
    """With only Samantha installed, cori speaks with Samantha, reported as fallback."""
    resolved = resolve_voice("cori", [SAMANTHA])
    assert resolved.voice_id == SAMANTHA[0]
    assert resolved.quality == "fallback"
    assert resolved.key == "cori"
    assert resolved.label == "Cori"


def test_nothing_installed_uses_system_default() -> None:
    """With no voices listed, the system default voice is used."""
    resolved = resolve_voice("alba", [])
    assert resolved.voice_id is None
    assert resolved.quality == "fallback"


def test_installed_keys_lists_only_real_matches() -> None:
    """Samantha standing in does not count as a preset being installed."""
    assert installed_keys([piper("alba"), SAMANTHA]) == ["alba"]
    assert installed_keys(INSTALLED) == KEYS


def test_startup_key_from_env(caplog: pytest.LogCaptureFixture) -> None:
    """AUDIO_VOICE is trimmed and lowercased; blank or unknown means alba."""
    assert startup_voice_key({"AUDIO_VOICE": " Cori "}) == "cori"
    assert startup_voice_key({}) == "alba"
    assert startup_voice_key({"AUDIO_VOICE": ""}) == "alba"
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="audio"):
        assert startup_voice_key({"AUDIO_VOICE": "bob"}) == "alba"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "bob" in warnings[0].getMessage()
