"""Fixed offline phrases audio speaks itself, per language (SPEC.md section 4.8).

Hazard phrases and the voice sample line, keyed by the language codes in
contracts/languages.py. Machine-drafted; a native speaker should review them.
"""

from __future__ import annotations

from contracts.languages import DEFAULT_LANGUAGE

# Language -> hazard type -> spoken phrase.
HAZARD_PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "stairs_down": "Stop. Stairs.",
        "drop_off": "Stop. Drop ahead.",
        "vehicle": "Stop. Vehicle.",
        "obstacle": "Stop. Obstacle.",
    },
    "zh": {
        "stairs_down": "停。楼梯。",
        "drop_off": "停。前方有落差。",
        "vehicle": "停。车辆。",
        "obstacle": "停。障碍物。",
    },
    "es": {
        "stairs_down": "Alto. Escaleras.",
        "drop_off": "Alto. Desnivel adelante.",
        "vehicle": "Alto. Vehículo.",
        "obstacle": "Alto. Obstáculo.",
    },
    "fr": {
        "stairs_down": "Stop. Escalier.",
        "drop_off": "Stop. Dénivelé devant.",
        "vehicle": "Stop. Véhicule.",
        "obstacle": "Stop. Obstacle.",
    },
    "hi": {
        "stairs_down": "रुकिए। सीढ़ियाँ।",
        "drop_off": "रुकिए। आगे गड्ढा।",
        "vehicle": "रुकिए। वाहन।",
        "obstacle": "रुकिए। रुकावट।",
    },
}
# Spoken for a hazard type missing from the table above.
FALLBACK_HAZARD_PHRASES: dict[str, str] = {
    "en": "Stop.",
    "zh": "停。",
    "es": "Alto.",
    "fr": "Stop.",
    "hi": "रुकिए।",
}
# Spoken once a voice switch is applied; {label} is the preset's label.
SAMPLE_LINES: dict[str, str] = {
    "en": "This is {label}.",
    "zh": "我是{label}。",
    "es": "Soy {label}.",
    "fr": "Je suis {label}.",
    "hi": "मैं {label} हूँ।",
}


def _lang(language: str) -> str:
    """Return language if the phrase tables cover it, else the default language."""
    return language if language in HAZARD_PHRASES else DEFAULT_LANGUAGE


def hazard_phrase(hazard_type: str, language: str) -> str:
    """Return the spoken phrase for a hazard type in language."""
    lang = _lang(language)
    return HAZARD_PHRASES[lang].get(hazard_type, FALLBACK_HAZARD_PHRASES[lang])


def hazard_prerender(language: str) -> list[str]:
    """Return every hazard phrase of language plus its fallback, for pre-rendering."""
    lang = _lang(language)
    return [*HAZARD_PHRASES[lang].values(), FALLBACK_HAZARD_PHRASES[lang]]


def sample_line(label: str, language: str) -> str:
    """Return the voice sample line for a preset label in language."""
    return SAMPLE_LINES[_lang(language)].format(label=label)
