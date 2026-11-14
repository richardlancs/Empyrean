"""Question wording: which questions the dashboard understands and how it answers.

Pure functions, no state and no bus. dashboard/services/questions.py decides
when to call them and what to publish. The phrases and answers come from
main's microphone feature (commit 5ee1039) and are kept word for word.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

Intent = Literal["scene", "touch", "history", "help"]

HISTORY = re.compile(
    r"^(?:where (?:did i|have i) last (?:touch|see)|when did i last (?:touch|see)|"
    r"where (?:is|are)|find)\s+(?:(?:the|my|a|an)\s+)?(.+)$"
)
SCENE = frozenset(
    {
        "what do you see",
        "what can you see",
        "what is in front of me",
        "what's in front of me",
        "describe the scene",
        "what is around me",
        "what's around me",
    }
)
TOUCH = frozenset(
    {
        "what is this item",
        "what's this item",
        "what is this object",
        "what's this object",
        "what is this",
        "what's this",
        "identify this item",
        "what am i touching",
        "what am i holding",
        "what is in my hand",
        "what's in my hand",
    }
)
HELP_ANSWER = "Try: What do you see? What am I touching? Or: Where did I last touch the bottle?"
NO_VIEW_ANSWER = "I do not have a current camera view."
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
    """Classify one transcript or typed question."""
    normalized = normalize(text)
    match = HISTORY.fullmatch(normalized)
    if match:
        target = match.group(1).strip(" .?!")
        if target:
            return ParsedQuestion("history", target)
    if normalized in TOUCH:
        return ParsedQuestion("touch")
    if normalized in SCENE:
        return ParsedQuestion("scene")
    return ParsedQuestion("help")


def scene_answer(objects: Iterable[Mapping[str, Any]], touching: bool) -> str:
    """Answer a scene or touch question from the current object list.

    Touch questions count only touching and held objects. Scene questions also
    count idle ones. New and lost objects never count.
    """
    states = {"touching", "held"} if touching else {"idle", "touching", "held"}
    names = list(dict.fromkeys(str(obj["text"]) for obj in objects if obj.get("state") in states))
    if names:
        return ("You are touching " if touching else "I can detect ") + ", ".join(names) + "."
    if touching:
        return "I cannot detect what you are touching."
    return "I cannot detect any objects right now."
