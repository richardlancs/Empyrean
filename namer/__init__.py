"""Grok namer module: subscribes to NameRequest, publishes NameResult."""

from __future__ import annotations

from typing import Any

from contracts import NameRequest
from namer.namer import Namer, clean_name

__all__ = ["Namer", "clean_name", "register"]


def register(bus: Any) -> Namer:
    """Create a Namer wired to the app bus and return it so the caller can stop() it."""
    # TODO(app bus): app/ has no bus yet. Expected API, to confirm with Person 1:
    #   bus.publish(msg) and bus.subscribe(NameRequest, handler).
    namer = Namer(publish=bus.publish)
    bus.subscribe(NameRequest, namer.on_name_request)
    return namer
