"""Route independent scene questions to Grok and explicit history to storage."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from contracts import LastSeenQuery, SceneQuestion, SpeakRequest
from dashboard.state import DashboardState

HISTORY = re.compile(
    r"^(?:where (?:did i|have i) last (?:touch|see)|when did i last (?:touch|see))"
    r"\s+(?:(?:the|my|a|an)\s+)?(.+)$"
)


def ask_question(
    text: str,
    state: DashboardState,
    publish: Callable[[Any], None],
    history_available: bool,
) -> dict[str, str]:
    """Publish a scene question, or an explicitly requested last-touch lookup."""
    normalized = re.sub(r"\s+", " ", text.lower()).strip(" .?!")
    match = HISTORY.fullmatch(normalized)
    if match:
        if history_available:
            publish(LastSeenQuery(ts=time.time(), text=match.group(1).strip(" .?!")))
            return {"kind": "history", "answer": "Looking up your touch history…"}
        answer = "Touch history is unavailable. The database is not configured."
        publish(SpeakRequest(time.time(), answer, "normal", "dashboard"))
        return {"kind": "answer", "answer": answer}
    publish(SceneQuestion(ts=time.time(), text=text.strip()))
    return {"kind": "question", "answer": "Checking the current camera view…"}
