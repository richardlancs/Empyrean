"""Grok object naming and independent current-camera question answering."""

from __future__ import annotations

from typing import Any

from contracts import FrameResult, NameRequest, SceneQuestion
from namer.namer import Namer, clean_name
from namer.questions import SceneQuestions

__all__ = ["Namer", "clean_name", "register"]


def register(bus: Any) -> Namer:
    """Create a Namer wired to the app bus and return it so the caller can stop() it."""
    namer = Namer(publish=bus.publish)
    bus.subscribe(NameRequest, namer.on_name_request)
    namer.questions = SceneQuestions(bus.publish)
    bus.subscribe(FrameResult, namer.questions.on_frame)
    bus.subscribe(SceneQuestion, namer.questions.on_question)
    return namer
