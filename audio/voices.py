"""Voice presets and the rule that matches each one to an installed pyttsx3 voice.

Five calm English presets backed by Apple Premium or Enhanced voices. A preset
that is not installed falls back to compact Samantha (en-US), then to the
system default voice. Both are reported as quality "fallback".
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger("audio")

Quality = Literal["premium", "enhanced", "compact", "fallback"]


@dataclass(frozen=True)
class VoicePreset:
    """One selectable voice."""

    key: str
    label: str
    apple_name: str  # name as pyttsx3 reports it, without " (Premium)"/" (Enhanced)"
    locale: str  # "en-US"; also the hook for languages later


@dataclass(frozen=True)
class ResolvedVoice:
    """A preset matched to the voice speech will really use."""

    key: str
    label: str
    voice_id: str | None  # None means the system default voice
    quality: Quality


PRESETS: tuple[VoicePreset, ...] = (
    VoicePreset("ava", "Ava", "Ava", "en-US"),
    VoicePreset("zoe", "Zoe", "Zoe", "en-US"),
    VoicePreset("evan", "Evan", "Evan", "en-US"),
    VoicePreset("jamie", "Jamie", "Jamie", "en-GB"),
    VoicePreset("matilda", "Matilda", "Matilda", "en-AU"),
)
DEFAULT_VOICE_KEY = "ava"
FALLBACK_NAME, FALLBACK_LOCALE = "Samantha", "en-US"

_QUALITY_RANK = {"premium": 0, "enhanced": 1, "compact": 2}


def preset_for(key: str) -> VoicePreset | None:
    """Return the preset with this key, or None."""
    return next((p for p in PRESETS if p.key == key), None)


def voice_quality(voice_id: str) -> Literal["premium", "enhanced", "compact"]:
    """Judge a voice's quality from its id; anything not premium or enhanced is compact."""
    if ".premium." in voice_id:
        return "premium"
    if ".enhanced." in voice_id:
        return "enhanced"
    return "compact"


def _base_name(name: str) -> str:
    """Strip a trailing parenthetical such as " (Premium)" or " (English (US))"."""
    return name.split("(", 1)[0].strip()


def _best_match(
    name: str, locale: str, installed: Sequence[tuple[str, str]]
) -> str | None:
    """Return the best installed voice id with this name and locale, or None."""
    matches = [
        voice_id
        for voice_id, voice_name in installed
        if _base_name(voice_name) == name and locale in voice_id
    ]
    if not matches:
        return None
    return min(matches, key=lambda voice_id: _QUALITY_RANK[voice_quality(voice_id)])


def resolve_voice(key: str, installed: Sequence[tuple[str, str]]) -> ResolvedVoice:
    """Match a preset key to the best installed voice, falling back to Samantha, then default."""
    preset = preset_for(key) or preset_for(DEFAULT_VOICE_KEY)
    assert preset is not None
    voice_id = _best_match(preset.apple_name, preset.locale, installed)
    if voice_id is not None:
        return ResolvedVoice(
            preset.key, preset.label, voice_id, voice_quality(voice_id)
        )
    fallback_id = _best_match(FALLBACK_NAME, FALLBACK_LOCALE, installed)
    return ResolvedVoice(preset.key, preset.label, fallback_id, "fallback")


def installed_keys(installed: Sequence[tuple[str, str]]) -> list[str]:
    """Return the preset keys, in menu order, whose own voice is installed."""
    return [
        p.key
        for p in PRESETS
        if _best_match(p.apple_name, p.locale, installed) is not None
    ]


def startup_voice_key(env: Mapping[str, str]) -> str:
    """Read AUDIO_VOICE; an unknown key logs one warning and gives the default."""
    raw = env.get("AUDIO_VOICE", "") or ""
    key = raw.strip().lower()
    if not key:
        return DEFAULT_VOICE_KEY
    if preset_for(key) is None:
        log.warning(
            "AUDIO_VOICE=%r is not a voice preset (%s); using %s",
            raw,
            ", ".join(p.key for p in PRESETS),
            DEFAULT_VOICE_KEY,
        )
        return DEFAULT_VOICE_KEY
    return key
