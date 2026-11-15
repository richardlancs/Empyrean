"""Tiger Data store: logs touches and hazards, answers last-seen queries (SPEC.md 4.10)."""

from __future__ import annotations

import logging
import os
from typing import Any

from storage._deps import HazardEvent, LastSeenQuery, TouchEvent, VoiceStatus
from storage.writer import Store

log = logging.getLogger("storage")

__all__ = ["Store", "register"]


def register(bus: Any) -> Store:
    """Create the store, subscribe it to the bus, and return it so app/ can stop() it.

    The bus needs bus.publish(message) and bus.subscribe(MessageType, handler).
    TIGER_DATABASE_URL is read here, once, so app/ must load .env before calling this.
    Handlers only enqueue and return. All database work, and every SpeakRequest
    answer published through bus.publish, happens on the store's worker thread.
    """
    store = Store(
        bus.publish, os.environ.get("TIGER_DATABASE_URL"), status_publish=bus.publish
    )
    bus.subscribe(TouchEvent, store.on_touch_event)
    bus.subscribe(HazardEvent, store.on_hazard_event)
    bus.subscribe(LastSeenQuery, store.on_last_seen_query)
    bus.subscribe(VoiceStatus, store.on_voice_status)
    return store
