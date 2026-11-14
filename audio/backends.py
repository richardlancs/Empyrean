"""Sound outputs for the audio manager: pyttsx3 speech and the pygame alarm.

Both libraries are imported only when a backend is created, so the manager, the
fake and the tests run on machines without them.
"""

from __future__ import annotations

import gc
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("audio")

ALARM_WAV = Path(__file__).resolve().parent / "sounds" / "alarm.wav"


def _init_com_for_thread() -> None:
    """Initialise COM on the calling thread. SAPI5 speech needs it on Windows."""
    if sys.platform != "win32":
        return
    import comtypes

    comtypes.CoInitialize()


def _speak_once(pyttsx3: Any, text: str, should_stop: Callable[[], bool]) -> None:
    """Speak text on a brand-new engine, cutting off at a word boundary on should_stop()."""
    engine = pyttsx3.init()

    def on_word(name: Any, location: int, length: int) -> None:
        """Cut speech off at the next word boundary once an alarm arrives."""
        if should_stop():
            engine.stop()

    engine.connect("started-word", on_word)
    engine.say(text)
    engine.runAndWait()


class Pyttsx3Speaker:
    """Offline text to speech. Create it and call it on one thread only.

    pyttsx3 2.99 on Windows (SAPI5) plays only the first runAndWait of an engine:
    later calls return in about 85 ms with no sound. So every phrase gets a fresh
    engine, which takes about 26 ms to start. pyttsx3.init() caches engines weakly,
    so the old one must be garbage collected before the next init() or the same
    broken engine comes back.
    """

    def __init__(self) -> None:
        """Check on the current thread that a pyttsx3 engine can start."""
        _init_com_for_thread()
        import pyttsx3

        self._pyttsx3 = pyttsx3
        pyttsx3.init()  # raise now, so the manager falls back to logging at startup
        gc.collect()

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Speak text, blocking until it ends or should_stop() turns true."""
        if should_stop():
            return
        try:
            _speak_once(self._pyttsx3, text, should_stop)
        finally:
            gc.collect()  # drop the used engine so the next init() builds a new one


class LogSpeaker:
    """Stand-in used when text to speech cannot start: logs instead of speaking."""

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Log the text that would have been spoken."""
        log.info("Would say: %s", text)


class PygameAlarm:
    """Plays the pre-made alarm WAV through the pygame mixer without blocking."""

    def __init__(self, path: Path = ALARM_WAV) -> None:
        """Open the mixer and load the alarm file."""
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        self._pygame = pygame
        self._sound = pygame.mixer.Sound(str(path))
        self.duration = float(self._sound.get_length())

    def play(self) -> None:
        """Start the beeps and return at once."""
        self._sound.play()

    def close(self) -> None:
        """Release the mixer."""
        self._pygame.mixer.quit()


class SilentAlarm:
    """Stand-in used when the mixer cannot start: hazards are still spoken."""

    duration = 0.0

    def play(self) -> None:
        """Log that the beeps were skipped."""
        log.warning("Alarm beeps skipped: no sound mixer")

    def close(self) -> None:
        """Nothing to release."""


def load_alarm() -> PygameAlarm | SilentAlarm:
    """Return the pygame alarm, or a silent stand-in if it cannot start."""
    try:
        return PygameAlarm()
    except Exception:
        log.exception("Alarm sound unavailable; hazards will be spoken without beeps")
        return SilentAlarm()
