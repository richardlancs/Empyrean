"""Route dashboard questions through existing scene and speech messages."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from config import LOST_KEEP_SECONDS
from contracts import LastSeenQuery, SpeakRequest
from dashboard.state import DashboardState

HISTORY = re.compile(
    r"^(?:where (?:did i|have i) last (?:touch|see)|when did i last (?:touch|see)|"
    r"where (?:is|are)|find)\s+(?:(?:the|my|a|an)\s+)?(.+)$"
)
SCENE = {
    "what do you see",
    "what can you see",
    "what is in front of me",
    "what's in front of me",
    "describe the scene",
    "what is around me",
    "what's around me",
}
TOUCH = {
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


def ask_question(
    text: str,
    state: DashboardState,
    publish: Callable[[Any], None],
    history_available: bool,
) -> dict[str, str]:
    """Answer supported scene questions or publish a last-touch history query."""
    normalized = re.sub(r"\s+", " ", text.lower()).strip(" .?!")
    match = HISTORY.fullmatch(normalized)
    if match:
        target = match.group(1).strip(" .?!")
        if not target:
            raise ValueError("Name an object to search for.")
        if history_available:
            publish(LastSeenQuery(ts=time.time(), text=target))
            return {
                "kind": "history",
                "answer": f"Looking up the last touch of {target}…",
            }
        answer = "Touch history is unavailable. The database is not configured."
    elif normalized in SCENE or normalized in TOUCH:
        snapshot = state.snapshot()
        scene_ts = snapshot.get("scene_ts")
        if scene_ts is None or time.time() - scene_ts > LOST_KEEP_SECONDS:
            answer = "I do not have a current camera view."
        else:
            touching = normalized in TOUCH
            objects = [
                obj
                for obj in snapshot["objects"]
                if obj["state"]
                in ({"touching", "held"} if touching else {"idle", "touching", "held"})
            ]
            names = list(dict.fromkeys(obj["text"] for obj in objects))
            if names:
                answer = (
                    ("You are touching " if touching else "I can detect ")
                    + ", ".join(names)
                    + "."
                )
            else:
                answer = (
                    "I cannot detect what you are touching."
                    if touching
                    else "I cannot detect any objects right now."
                )
    else:
        answer = "Try: What do you see? What am I touching? Or: Where did I last touch the bottle?"
    publish(
        SpeakRequest(ts=time.time(), text=answer, priority="normal", source="dashboard")
    )
    return {"kind": "answer", "answer": answer}
