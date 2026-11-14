"""Tiger Data store: logs touches and hazards, answers last-seen queries (SPEC.md 4.10)."""

from __future__ import annotations

import logging
import os
from typing import Any

from storage.writer import Store

log = logging.getLogger("storage")

__all__ = ["Store", "register"]


def register(bus: Any) -> Store:
    """Create the store, wire it to the bus, and return it so app/ can stop() it."""
    store = Store(bus.publish, os.environ.get("TIGER_DATABASE_URL"))
    # TODO(app/ bus): app/ has no bus yet. Once it does, wire these handlers, e.g.
    #   bus.subscribe(TouchEvent, store.on_touch_event)
    #   bus.subscribe(HazardEvent, store.on_hazard_event)
    #   bus.subscribe(LastSeenQuery, store.on_last_seen_query)
    # Handlers only enqueue and return, so they are safe on the delivering thread.
    # Answers are published with bus.publish(SpeakRequest(...)) from the worker thread.
    return store
