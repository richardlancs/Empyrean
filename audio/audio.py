"""Audio manager: speak requested answers and sound the alarm first.

Touches announce automatically; separately requested answers use lower priority.

Subscribes to: HazardEvent, TouchEvent, NameResult, SpeakRequest, VoiceChange.
Publishes: SpeechStatus, VoiceStatus and ModuleStatus when given a publish callback
(register() passes bus.publish). Output is sound on the system speaker (the JBL Go 3).
Telemetry describes what the speech engine did; it never proves anyone heard it.

Every bus handler only updates state under a lock and returns. Speech runs on
one worker thread that owns the text-to-speech engine. The alarm beeps start on
the hazard handler's own thread, so they never wait behind speech. A voice switch
is applied by that worker between phrases, never mid-phrase.
"""

from __future__ import annotations

import itertools
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from audio.backends import HybridSpeaker, LogSpeaker, load_alarm
from audio.voices import (
    DEFAULT_VOICE_KEY,
    FALLBACK_NAME,
    PRESETS,
    ResolvedVoice,
    installed_keys,
    preset_for,
    resolve_voice,
    startup_voice_key,
)
from config import LATE_NAME_WINDOW_SECONDS
from contracts import (
    HazardEvent,
    ModuleStatus,
    NameResult,
    SpeakRequest,
    SpeechStatus,
    TouchEvent,
    VoiceChange,
    VoiceStatus,
)

log = logging.getLogger("audio")

# Spoken hazard phrases, SPEC.md section 4.8.
HAZARD_PHRASES: dict[str, str] = {
    "stairs_down": "Stop. Stairs.",
    "drop_off": "Stop. Drop ahead.",
    "vehicle": "Stop. Vehicle.",
    "obstacle": "Stop. Obstacle.",
}
FALLBACK_HAZARD_PHRASE = "Stop."
# Rendered ahead after every voice change, so a hazard phrase starts at once.
HAZARD_PRERENDER: list[str] = [*HAZARD_PHRASES.values(), FALLBACK_HAZARD_PHRASE]

# Lower number wins, SPEC.md section 4.8.
PRIORITY_ALARM = 1
PRIORITY_TOUCH = 2
PRIORITY_ANSWER = 3

KIND_BY_PRIORITY = {
    PRIORITY_ALARM: "hazard",
    PRIORITY_TOUCH: "touch",
    PRIORITY_ANSWER: "answer",
}
SPEECH_MODES = ("real", "fake", "unavailable")
UNAVAILABLE_DETAIL = "No speech engine: the text was logged, not played"
VOICE_MENU: dict[str, str] = {p.key: p.label for p in PRESETS}


def speaker_mode(speaker: Any) -> str:
    """Return real, fake or unavailable as the speaker declares it; undeclared is fake.

    Only a backend that drives a real speech engine declares real, so a test
    double or a printing stand-in is never reported as real playback.
    """
    mode = getattr(speaker, "mode", "fake")
    return mode if mode in SPEECH_MODES else "fake"


class Speaker(Protocol):
    """Blocking text to speech that can be cut off between words."""

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Speak text, returning early once should_stop() is true."""

    def installed_voices(self) -> list[tuple[str, str]]:
        """Return (voice_id, name) pairs; optional, read through getattr."""

    def set_voice(self, voice_id: str | None) -> None:
        """Use voice_id for later phrases; optional, read through getattr."""

    def prepare(self, texts: list[str]) -> None:
        """Pre-render texts in the background without blocking; optional, via getattr."""


class Alarm(Protocol):
    """Non-blocking alarm sound."""

    duration: float

    def play(self) -> None:
        """Start the alarm and return at once."""

    def close(self) -> None:
        """Release the sound device."""


@dataclass
class _Item:
    """One thing waiting to be spoken."""

    priority: int
    text: str
    generation: int  # alarm count when queued; a newer alarm cancels it
    created_at: float
    not_before: float = 0.0  # the hazard phrase waits for the beeps to end
    speech_id: int = 0  # telemetry id, the same for every SpeechStatus of this item
    object_id: int | None = None
    source: str = ""


@dataclass
class _Touch:
    """An object that is being touched right now."""

    received_at: float
    spoke_label: bool  # True when the class label was used because no name was known
    late_name_done: bool = False


@dataclass
class _State:
    """Everything the handlers and the worker share, guarded by one condition."""

    slot: _Item | None = None  # the speech queue holds one item
    generation: int = 0
    closed: bool = False
    touches: dict[int, _Touch] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)
    pending_voice: tuple[str, str | None] | None = None  # (preset key, request id)


@dataclass
class _VoiceSwitch:
    """A pending voice switch handed from the queue to the worker."""

    key: str
    request_id: str | None


class AudioManager:
    """Turns bus messages into speech and alarms, alarm first."""

    def __init__(
        self,
        speaker_factory: Callable[[], Speaker],
        alarm: Alarm,
        *,
        clock: Callable[[], float] = time.monotonic,
        late_name_window: float = LATE_NAME_WINDOW_SECONDS,
        announce_touches: bool = True,
        publish: Callable[[Any], None] | None = None,
        module_name: str = "audio",
        voice: str = DEFAULT_VOICE_KEY,
    ) -> None:
        """Start the speech worker. speaker_factory runs on that worker thread.

        announce_touches (on by default) speaks touched objects and late names
        automatically; False leaves only requested answers and alarms.
        publish, if given, receives SpeechStatus, VoiceStatus and ModuleStatus
        messages. It must not block (bus.publish only enqueues). voice is the
        preset key to start with.
        """
        self._announce_touches = announce_touches
        self._speaker_factory = speaker_factory
        self._alarm = alarm
        self._clock = clock
        self._late_name_window = late_name_window
        self._publish = publish
        self._module_name = module_name
        self._cond = threading.Condition()
        self._state = _State()
        self._ids = itertools.count(1)
        # Until the worker builds the speaker, trust only what the factory declares.
        self._mode = speaker_mode(speaker_factory)
        self._outbox: list[Any] = []
        self._publish_lock = threading.Lock()
        self._speech_failed = False
        self._startup_voice = voice if preset_for(voice) is not None else DEFAULT_VOICE_KEY
        self._active_voice: ResolvedVoice = resolve_voice(self._startup_voice, [])
        self._installed: list[str] = []
        self._thread = threading.Thread(
            target=self._run, name="audio-speech", daemon=True
        )
        self._thread.start()

    # Bus handlers. Each returns without waiting on sound.

    def on_hazard(self, msg: HazardEvent) -> None:
        """Start the beeps, cut off speech, empty the queue, then queue the phrase."""
        try:
            self._alarm.play()
        except Exception:
            log.exception("Alarm sound failed")
        phrase = HAZARD_PHRASES.get(msg.type, FALLBACK_HAZARD_PHRASE)
        with self._cond:
            state = self._state
            if state.slot is not None:
                self._status(state.slot, "interrupted", "Cut off by a hazard alarm")
            state.generation += 1
            now = self._clock()
            state.slot = self._new_item(
                PRIORITY_ALARM,
                phrase,
                state.generation,
                now,
                not_before=now + self._alarm.duration,
                source="hazard",
            )
            self._status(state.slot, "queued")
            self._cond.notify_all()
        self._flush()
        log.info("Alarm: %s (%s, confidence %.2f)", phrase, msg.source, msg.confidence)

    def on_touch(self, msg: TouchEvent) -> None:
        """Announce the touched object automatically when announcements are enabled."""
        if not self._announce_touches:
            return
        with self._cond:
            state = self._state
            if msg.kind != "touch":
                state.touches.pop(msg.object_id, None)
                return
            # A NameResult can reach audio just before the TouchEvent that it beat.
            name = msg.name.strip() or state.names.get(msg.object_id, "")
            now = self._clock()
            state.touches[msg.object_id] = _Touch(now, spoke_label=not name)
            self._offer(
                self._new_item(
                    PRIORITY_TOUCH,
                    name or msg.class_label,
                    state.generation,
                    now,
                    object_id=msg.object_id,
                    source="scene",
                )
            )
        self._flush()

    def on_name(self, msg: NameResult) -> None:
        """Speak a late name while the object is still being touched."""
        if not self._announce_touches:
            return
        name = msg.name.strip()
        if not msg.ok or not name:
            return
        with self._cond:
            state = self._state
            state.names[msg.object_id] = name
            touch = state.touches.get(msg.object_id)
            if touch is None or not touch.spoke_label or touch.late_name_done:
                return
            now = self._clock()
            if now - touch.received_at > self._late_name_window:
                return
            touch.late_name_done = True
            self._offer(
                self._new_item(
                    PRIORITY_TOUCH,
                    name,
                    state.generation,
                    now,
                    object_id=msg.object_id,
                    source="namer",
                )
            )
        self._flush()

    def on_speak(self, msg: SpeakRequest) -> None:
        """Speak an answer, such as the last-seen reply, at the lowest priority."""
        text = msg.text.strip()
        if not text:
            return
        with self._cond:
            self._offer(
                self._new_item(
                    PRIORITY_ANSWER,
                    text,
                    self._state.generation,
                    self._clock(),
                    source=msg.source,
                )
            )
        self._flush()

    def on_voice_change(self, msg: VoiceChange) -> None:
        """Note a voice switch for the speech worker; refuse an unknown preset at once."""
        with self._cond:
            if preset_for(msg.voice) is None:
                self._voice_status(
                    "failed",
                    requested_voice=msg.voice,
                    request_id=msg.request_id,
                    detail=f"Unknown voice {msg.voice!r}",
                )
            else:
                # The newest pending switch wins; slot and generation are untouched.
                self._state.pending_voice = (msg.voice, msg.request_id)
                self._cond.notify_all()
        self._flush()

    def stop(self, timeout: float = 2.0) -> None:
        """Cut off speech, stop the worker and release the alarm."""
        with self._cond:
            self._state.closed = True
            self._state.slot = None
            self._cond.notify_all()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout)
        try:
            self._alarm.close()
        except Exception:
            log.exception("Alarm close failed")

    @property
    def mode(self) -> str:
        """real, fake or unavailable: what the current speaker really does."""
        return self._mode

    # Internals.

    def _new_item(
        self,
        priority: int,
        text: str,
        generation: int,
        created_at: float,
        *,
        not_before: float = 0.0,
        object_id: int | None = None,
        source: str = "",
    ) -> _Item:
        """Build a queue item with its own telemetry id."""
        return _Item(
            priority,
            text,
            generation,
            created_at,
            not_before,
            speech_id=next(self._ids),
            object_id=object_id,
            source=source,
        )

    def _status(self, item: _Item, status: str, detail: str = "") -> None:
        """Queue a SpeechStatus for publishing. Caller holds the lock."""
        if self._publish is None:
            return
        self._outbox.append(
            SpeechStatus(
                ts=time.time(),
                speech_id=item.speech_id,
                text=item.text,
                status=status,  # type: ignore[arg-type]
                mode=self._mode,  # type: ignore[arg-type]
                kind=KIND_BY_PRIORITY.get(item.priority, "answer"),  # type: ignore[arg-type]
                object_id=item.object_id,
                source=item.source,
                detail=detail,
            )
        )

    def _module_status(self, status: str, detail: str) -> None:
        """Queue a ModuleStatus for this module. Caller holds the lock."""
        if self._publish is None:
            return
        mode = {"real": "real", "fake": "fake"}.get(self._mode, "unknown")
        self._outbox.append(
            ModuleStatus(
                ts=time.time(),
                module=self._module_name,
                status=status,  # type: ignore[arg-type]
                mode=mode,  # type: ignore[arg-type]
                detail=detail,
            )
        )

    def _voice_status(
        self,
        state: str,
        *,
        requested_voice: str | None = None,
        request_id: str | None = None,
        detail: str = "",
    ) -> None:
        """Queue a VoiceStatus describing the active voice. Caller holds the lock."""
        if self._publish is None:
            return
        active = self._active_voice
        self._outbox.append(
            VoiceStatus(
                ts=time.time(),
                state=state,  # type: ignore[arg-type]
                active_voice=active.key,
                label=active.label,
                quality=active.quality,
                voices=dict(VOICE_MENU),
                installed=list(self._installed),
                requested_voice=requested_voice,
                request_id=request_id,
                detail=detail,
            )
        )

    def _apply_voice(self, speaker: Speaker, key: str) -> ResolvedVoice:
        """Resolve key against the speaker's voices and switch it. Worker thread only."""
        list_voices = getattr(speaker, "installed_voices", None)
        try:
            installed = list(list_voices()) if list_voices is not None else []
        except Exception:
            log.exception("Listing installed voices failed")
            installed = []
        resolved = resolve_voice(key, installed)
        set_voice = getattr(speaker, "set_voice", None)
        if set_voice is not None:
            set_voice(resolved.voice_id)
        prepare = getattr(speaker, "prepare", None)
        if prepare is not None:
            try:  # returns at once: rendering happens on the speaker's own thread
                prepare(list(HAZARD_PRERENDER))
            except Exception:
                log.exception("Pre-rendering the hazard phrases failed")
        with self._cond:
            self._active_voice = resolved
            self._installed = installed_keys(installed)
        if resolved.quality == "fallback":
            log.warning(
                "Voice %s is not installed; using %s instead",
                resolved.label,
                _fallback_name(resolved),
            )
        else:
            log.info("Voice %s (%s): %s", resolved.label, resolved.quality, resolved.voice_id)
        return resolved

    def _switch_voice(self, speaker: Speaker, switch: _VoiceSwitch) -> None:
        """Apply a requested switch between phrases, confirm it, then queue the sample."""
        try:
            resolved = self._apply_voice(speaker, switch.key)
        except Exception as exc:
            log.exception("Voice switch to %s failed", switch.key)
            with self._cond:
                self._voice_status(
                    "failed",
                    requested_voice=switch.key,
                    request_id=switch.request_id,
                    detail=f"Speech engine error ({type(exc).__name__})",
                )
            self._flush()
            return
        with self._cond:
            self._voice_status(
                "active",
                requested_voice=switch.key,
                request_id=switch.request_id,
                detail=_voice_detail(resolved),
            )
            # Answer priority: never displaces a waiting touch or hazard phrase.
            self._offer(
                self._new_item(
                    PRIORITY_ANSWER,
                    f"This is {resolved.label}.",
                    self._state.generation,
                    self._clock(),
                    source="audio",
                )
            )
        self._flush()

    def _flush(self) -> None:
        """Publish queued telemetry in order, outside the state lock."""
        if self._publish is None:
            return
        with self._publish_lock:  # one flusher at a time keeps the order
            with self._cond:
                pending, self._outbox = self._outbox, []
            for message in pending:
                try:
                    self._publish(message)
                except Exception:
                    log.exception("Publishing audio telemetry failed")

    def _offer(self, item: _Item) -> None:
        """Put item in the one-item queue. Caller holds the lock.

        A newer item replaces a waiting older one unless the waiting one has a
        higher priority. Stale speech is worse than no speech.
        """
        waiting = self._state.slot
        if waiting is not None and waiting.priority < item.priority:
            log.info("Dropped %r: %r is waiting", item.text, waiting.text)
            self._status(item, "interrupted", "Not queued: more urgent speech is waiting")
            return
        if waiting is not None:
            log.info("Replaced %r with %r", waiting.text, item.text)
            self._status(waiting, "interrupted", "Replaced by newer speech before it played")
        self._state.slot = item
        self._status(item, "queued")
        self._cond.notify_all()

    def _next_item(self) -> _Item | _VoiceSwitch | None:
        """Block until a voice switch is pending or an item is due. None once stopped.

        A pending switch is returned first, so it is applied before the next
        phrase, including a hazard phrase still waiting out its beeps.
        """
        with self._cond:
            state = self._state
            while True:
                while (
                    state.slot is None and state.pending_voice is None and not state.closed
                ):
                    self._cond.wait()
                if state.closed:
                    return None
                if state.pending_voice is not None:
                    key, request_id = state.pending_voice
                    state.pending_voice = None
                    return _VoiceSwitch(key, request_id)
                item = state.slot
                assert item is not None
                remaining = item.not_before - self._clock()
                if remaining <= 0:
                    state.slot = None
                    return item
                # Leave the phrase in the slot while the beeps play, so nothing
                # of lower priority can replace it and a newer alarm can.
                self._cond.wait(remaining)

    def _make_speaker(self) -> Speaker:
        """Create the speaker on this thread, or fall back to logging."""
        try:
            return self._speaker_factory()
        except Exception:
            log.exception("Text to speech unavailable; speech will be logged only")
            return LogSpeaker()

    def _report_ready(self, speaker: Speaker) -> None:
        """Set the startup voice and publish what this manager can really play."""
        alarm_ok = getattr(self._alarm, "mode", "fake") != "unavailable"
        lists_voices = getattr(speaker, "installed_voices", None) is not None
        try:
            resolved: ResolvedVoice | None = self._apply_voice(speaker, self._startup_voice)
        except Exception:
            log.exception("Setting the startup voice failed; using the system voice")
            resolved = None
        with self._cond:
            if self._mode == "real":
                status, detail = "active", "Speech engine ready"
            elif self._mode == "fake":
                status, detail = "active", "Fake audio: speech is printed, not played"
            else:
                status = "degraded"
                detail = "Text to speech could not start; speech is logged only"
            if not alarm_ok:
                status = "degraded"
                detail += "; alarm beeps unavailable (hazards are still spoken)"
            # Only a speaker that can list voices can say a preset is missing.
            if (
                resolved is not None
                and resolved.quality == "fallback"
                and lists_voices
                and self._mode != "unavailable"
            ):
                status = "degraded"
                detail += (
                    f"; Voice {resolved.label} is not installed; "
                    f"using {_fallback_name(resolved)} instead"
                )
            self._voice_status(
                "active", detail=_voice_detail(resolved) if resolved is not None else ""
            )
            self._module_status(status, detail)
        self._flush()

    def _run(self) -> None:
        """Speech worker: speak one item at a time until stopped."""
        speaker = self._make_speaker()
        with self._cond:
            self._mode = speaker_mode(speaker)
        self._report_ready(speaker)
        failed_logged = False
        while True:
            item = self._next_item()
            if item is None:
                return
            if isinstance(item, _VoiceSwitch):
                self._switch_voice(speaker, item)
                continue
            generation = item.generation

            def should_stop(generation: int = generation) -> bool:
                state = self._state
                return state.closed or state.generation != generation

            if should_stop():
                with self._cond:
                    self._status(item, "interrupted", "Cut off by a hazard alarm")
                self._flush()
                continue
            log.info(
                "Speaking %r, %.0f ms after the event",
                item.text,
                (self._clock() - item.created_at) * 1000,
            )
            with self._cond:
                self._status(item, "speaking")
            self._flush()
            try:
                speaker.say(item.text, should_stop)
            except Exception as exc:
                if not failed_logged:
                    log.exception("Speech failed for %r", item.text)
                    failed_logged = True
                with self._cond:
                    self._status(item, "failed", f"Speech engine error ({type(exc).__name__})")
                    if not self._speech_failed:
                        self._speech_failed = True
                        self._module_status(
                            "degraded", f"Speech engine error ({type(exc).__name__})"
                        )
                self._flush()
                continue
            with self._cond:
                if should_stop():
                    reason = "Audio stopped" if self._state.closed else "Cut off by a hazard alarm"
                    self._status(item, "interrupted", reason)
                elif self._mode == "unavailable":
                    self._status(item, "failed", UNAVAILABLE_DETAIL)
                else:
                    self._status(item, "completed")
                    if self._speech_failed:
                        self._speech_failed = False
                        self._module_status("active", "Speech engine recovered")
            self._flush()


def _fallback_name(resolved: ResolvedVoice) -> str:
    """Name the voice standing in for a preset that is not installed."""
    return FALLBACK_NAME if resolved.voice_id is not None else "the system default voice"


def _voice_detail(resolved: ResolvedVoice) -> str:
    """Say which voice stands in when the preset's own voice is missing."""
    if resolved.quality != "fallback":
        return ""
    return f"Voice {resolved.label} is not installed; using {_fallback_name(resolved)} instead"


def register(bus: Any) -> AudioManager:
    """Subscribe the audio manager to the bus, HazardEvent first, and return it."""
    manager = AudioManager(
        HybridSpeaker,
        load_alarm(),
        publish=bus.publish,
        voice=startup_voice_key(os.environ),
    )
    bus.subscribe(HazardEvent, manager.on_hazard)
    bus.subscribe(TouchEvent, manager.on_touch)
    bus.subscribe(NameResult, manager.on_name)
    bus.subscribe(SpeakRequest, manager.on_speak)
    bus.subscribe(VoiceChange, manager.on_voice_change)
    return manager
