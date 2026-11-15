"""Question wording: which questions go to history and how the dashboard answers.

Pure functions, no state and no bus. dashboard/services/questions.py decides
when to call them and what to publish. Routing follows main's independent voice
questions (SPEC 4.9.1): only an explicit "Where did I last touch X?" goes to
history; every other question is a SceneQuestion that namer/ answers from the
current camera view with Grok.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from contracts.languages import DEFAULT_LANGUAGE

Intent = Literal["scene", "history"]

HISTORY = re.compile(
    r"^(?:where (?:did i|have i) last (?:touch|see)|when did i last (?:touch|see))"
    r"\s+(?:(?:the|my|a|an)\s+)?(.+)$"
)
SCENE_PENDING_ANSWER = "Checking the current camera view…"
# The same sentences namer/ speaks when it is busy or cannot answer.
SCENE_BUSY_ANSWER = "Please wait for the current question to finish."
SCENE_UNAVAILABLE_ANSWER = "I could not answer that right now. Please try again."
HISTORY_UNAVAILABLE_ANSWER = "Touch history is unavailable right now."

# Every sentence the dashboard itself may speak, per language (SPEC 4.8). Fixed
# and offline; English is the constant above, byte for byte. Machine-drafted, so
# a native speaker should review them before real use.
SPOKEN_ANSWERS: dict[str, dict[str, str]] = {
    SCENE_BUSY_ANSWER: {
        "zh": "请等待当前问题回答完毕。",
        "es": "Por favor, espera a que termine la pregunta actual.",
        "fr": "Veuillez attendre la fin de la question en cours.",
        "hi": "कृपया मौजूदा सवाल पूरा होने तक प्रतीक्षा करें।",
    },
    SCENE_UNAVAILABLE_ANSWER: {
        "zh": "我现在无法回答。请再试一次。",
        "es": "No pude responder a eso ahora. Inténtalo de nuevo.",
        "fr": "Je n'ai pas pu répondre pour le moment. Veuillez réessayer.",
        "hi": "मैं अभी इसका जवाब नहीं दे सका। कृपया फिर से कोशिश करें।",
    },
    HISTORY_UNAVAILABLE_ANSWER: {
        "zh": "触摸记录现在无法使用。",
        "es": "El historial de toques no está disponible ahora.",
        "fr": "L'historique des contacts n'est pas disponible pour le moment.",
        "hi": "छूने का इतिहास अभी उपलब्ध नहीं है।",
    },
}


@dataclass(frozen=True)
class ParsedQuestion:
    """What a question asks for. target is the object name for history questions."""

    intent: Intent
    target: str = ""


def normalize(text: str) -> str:
    """Lower-case, collapse spaces and drop surrounding punctuation."""
    return re.sub(r"\s+", " ", text.lower()).strip(" .?!")


def spoken(answer: str, language: str) -> str:
    """Return one of the dashboard's fixed answers in language (English if untranslated)."""
    if language == DEFAULT_LANGUAGE:
        return answer
    return SPOKEN_ANSWERS.get(answer, {}).get(language, answer)


def parse_question(text: str) -> ParsedQuestion:
    """Classify one transcript or typed question as history or scene."""
    match = HISTORY.fullmatch(normalize(text))
    if match:
        target = match.group(1).strip(" .?!")
        if target:
            return ParsedQuestion("history", target)
    return ParsedQuestion("scene")
