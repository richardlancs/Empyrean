"""Voice presets and the rule that matches each one to an installed voice.

Five calm English presets backed by offline Piper neural voices, downloaded once
into audio/voice_models/ by `python -m audio.fetch_voices`. Piper voices are
listed with ids like "piper.premium.en-GB.Cori": high-tier models count as
premium and medium-tier as enhanced. A preset whose model is missing falls back
to pyttsx3's compact Samantha (en-US), then to the system default voice. Both
are reported as quality "fallback".
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

log = logging.getLogger("audio")

Quality = Literal["premium", "enhanced", "compact", "fallback"]


@dataclass(frozen=True)
class VoicePreset:
    """One selectable voice."""

    key: str
    label: str
    voice_name: str  # name the speaker reports, without a trailing parenthetical
    locale: str  # "en-US"; also the hook for languages later
    model: str = ""  # Piper model file stem, e.g. "en_GB-cori-high"


@dataclass(frozen=True)
class ResolvedVoice:
    """A preset matched to the voice speech will really use."""

    key: str
    label: str
    voice_id: str | None  # None means the system default voice
    quality: Quality


# Medium models start speaking in about 50-100 ms on the demo Mac, high models
# in 200-450 ms. Dataset licences (Piper model cards): Cori public domain (LibriVox), Alba
# CC BY 4.0, Northern English male CC BY-SA 4.0, Lessac Blizzard 2013 licence,
# Kristin per its model card. Model files are never committed.
PRESETS: tuple[VoicePreset, ...] = (
    VoicePreset("alba", "Alba", "Alba", "en-GB", "en_GB-alba-medium"),
    VoicePreset("kristin", "Kristin", "Kristin", "en-US", "en_US-kristin-medium"),
    VoicePreset(
        "northern",
        "Northern English",
        "Northern English",
        "en-GB",
        "en_GB-northern_english_male-medium",
    ),
    VoicePreset("cori", "Cori", "Cori", "en-GB", "en_GB-cori-high"),
    VoicePreset("lessac", "Lessac", "Lessac", "en-US", "en_US-lessac-high"),
)
DEFAULT_VOICE_KEY = "alba"  # medium tier: first audio in about 60 ms on the demo Mac
VOICE_MODEL_DIR = Path(__file__).resolve().parent / "voice_models"
PIPER_ID_PREFIX = "piper."
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
    voice_id = _best_match(preset.voice_name, preset.locale, installed)
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
        if _best_match(p.voice_name, p.locale, installed) is not None
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


def piper_voice_id(preset: VoicePreset) -> str:
    """Return the id a Piper-backed speaker lists for this preset's model."""
    tier = preset.model.rsplit("-", 1)[-1]
    quality = "premium" if tier == "high" else "enhanced"
    return f"{PIPER_ID_PREFIX}{quality}.{preset.locale}.{preset.voice_name}"


def piper_model_path(preset: VoicePreset) -> Path:
    """Return where this preset's Piper .onnx model lives once downloaded."""
    return VOICE_MODEL_DIR / f"{preset.model}.onnx"
