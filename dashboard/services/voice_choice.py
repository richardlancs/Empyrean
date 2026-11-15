"""Spoken-voice switching for the page: one shared request at a time.

The page asks; audio answers. A request publishes VoiceChange (an in-memory bus
enqueue) and is remembered as pending. Only a VoiceStatus from audio changes
which voice the page calls active. A request audio never answers expires as
failed after VOICE_SWITCH_TIMEOUT_SECONDS, and any later status still updates
the page to the voice audio really uses. The list of voices comes from the last
VoiceStatus, so the dashboard never imports audio/.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from config import VOICE_SWITCH_TIMEOUT_SECONDS
from contracts import VoiceChange, VoiceStatus
from contracts.languages import DEFAULT_LANGUAGE, LANGUAGES, known_language

NO_STATUS = "Audio has not reported a voice."
NO_ENGINE = "Switching voices needs the full app; this page has no engine attached."
UNLISTED = "Choose one of the listed voices."


class VoiceRejected(Exception):
    """A switch that was not sent; status_code says which HTTP error fits."""

    def __init__(self, status_code: int, message: str) -> None:
        """Keep the HTTP status and a plain message for the page."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class VoiceService:
    """Send voice switch requests over the bus and track audio's answers."""

    def __init__(
        self,
        publish: Callable[[Any], None] | None,
        clock: Callable[[], float] = time.time,
        timeout: float = VOICE_SWITCH_TIMEOUT_SECONDS,
    ) -> None:
        """publish is bus.publish, or None when the dashboard runs with no bus."""
        self._publish = publish
        self._clock = clock
        self._timeout = timeout
        self._lock = threading.Lock()
        self._status: VoiceStatus | None = None
        self._pending: dict[str, Any] | None = None
        self._note = (
            ""  # dashboard-side failure note (timeout), cleared by the next status
        )
        self._listeners: list[Callable[[], None]] = []

    @property
    def available(self) -> bool:
        """True when switch requests can reach audio over a bus."""
        return self._publish is not None

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Call listener after the voice state changes."""
        with self._lock:
            self._listeners.append(listener)

    def request(self, voice: str) -> dict[str, Any]:
        """Ask audio to switch voice. Returns the reply body; raises VoiceRejected."""
        if self._publish is None:
            raise VoiceRejected(503, NO_ENGINE)
        self.expire()
        with self._lock:
            if self._status is None:
                raise VoiceRejected(503, NO_STATUS)
            voices = self._status.voices
            if voice not in voices:
                raise VoiceRejected(422, UNLISTED)
            if self._pending is not None:
                raise VoiceRejected(
                    409, f"A switch to {self._pending['label']} is already in progress."
                )
            if self._status.active_voice == voice and self._status.state == "active":
                return {"state": "active", "voice": voice, "request_id": None}
            request_id = uuid.uuid4().hex
            self._pending = {
                "voice": voice,
                "label": voices[voice],
                "request_id": request_id,
                "at": self._clock(),
            }
            self._note = ""
        self._publish(VoiceChange(ts=self._clock(), voice=voice, request_id=request_id))
        self._notify()
        return {"state": "switching", "voice": voice, "request_id": request_id}

    def on_status(self, msg: VoiceStatus) -> None:
        """Bus handler: audio's report is the truth about the voice in use."""
        with self._lock:
            self._status = msg
            self._note = ""
            pending = self._pending
            if pending is not None:
                answered = msg.request_id == pending["request_id"]
                reached = msg.state == "active" and msg.active_voice == pending["voice"]
                if answered or reached:
                    self._pending = None
        self._notify()

    def expire(self) -> bool:
        """Fail a request audio has not answered in time; True if anything changed."""
        with self._lock:
            pending = self._pending
            if pending is None or self._clock() - pending["at"] <= self._timeout:
                return False
            self._pending = None
            self._note = (
                f"Audio did not confirm {pending['label']} within {self._timeout:.0f} s. "
                "The page shows the voice audio last reported."
            )
        self._notify()
        return True

    def language(self) -> str:
        """The active language code from audio's last VoiceStatus, or "en" before one."""
        with self._lock:
            status = self._status
        return known_language(status.language) if status is not None else DEFAULT_LANGUAGE

    def view(self) -> dict[str, Any]:
        """The voice state for the page snapshot (plain JSON)."""
        with self._lock:
            status, pending, note = self._status, self._pending, self._note
        if status is None:
            return {
                "state": "unknown",
                "active_voice": None,
                "label": None,
                "quality": None,
                "options": [],
                "switching_to": pending["voice"] if pending else None,
                "message": NO_STATUS,
                "request_id": None,
                "updated_ts": None,
                "language": DEFAULT_LANGUAGE,
                "languages": [],
            }
        if pending is not None:
            state, switching_to = "switching", pending["voice"]
        elif note or status.state == "failed":
            state, switching_to = "failed", None
        else:
            state, switching_to = "active", None
        installed = set(status.installed)
        option_languages = {
            key: known_language(status.voice_languages.get(key)) for key in status.voices
        }
        offered = set(option_languages.values())
        return {
            "state": state,
            "active_voice": status.active_voice,
            "label": status.label,
            "quality": status.quality,
            "options": [
                {
                    "key": key,
                    "label": label,
                    "installed": key in installed,
                    "language": option_languages[key],
                }
                for key, label in status.voices.items()
            ],
            "switching_to": switching_to,
            "message": note or status.detail,
            "request_id": pending["request_id"] if pending else status.request_id,
            "updated_ts": status.ts,
            "language": known_language(status.language),
            "languages": [
                {"code": code, "label": label}
                for code, label in LANGUAGES.items()
                if code in offered
            ],
        }

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener()
