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


@dataclass(frozen=True)
class ParsedQuestion:
    """What a question asks for. target is the object name for history questions."""

    intent: Intent
    target: str = ""


def normalize(text: str) -> str:
    """Lower-case, collapse spaces and drop surrounding punctuation."""
    return re.sub(r"\s+", " ", text.lower()).strip(" .?!")


def parse_question(text: str) -> ParsedQuestion:
    """Classify one transcript or typed question as history or scene."""
    match = HISTORY.fullmatch(normalize(text))
    if match:
        target = match.group(1).strip(" .?!")
        if target:
            return ParsedQuestion("history", target)
    return ParsedQuestion("scene")
