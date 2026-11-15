"""Sound outputs for the audio manager: Piper or pyttsx3 speech and the pygame alarm.

Every library (piper, pyttsx3, pygame, numpy) is imported only when a backend is
created, so the manager, the fake and the tests run on machines without them.
"""

from __future__ import annotations

import gc
import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from audio import voices
from config import SPEECH_RATE_WPM

log = logging.getLogger("audio")

ALARM_WAV = Path(__file__).resolve().parent / "sounds" / "alarm.wav"

# Piper's natural pace at length_scale 1.0, in words a minute. length_scale is
# PIPER_NATURAL_WPM / rate, so SPEECH_RATE_WPM 165 gives about 1.09 (a bit slower).
PIPER_NATURAL_WPM = 180
POLL_SECONDS = 0.01  # how often playback checks should_stop()


def _init_mixer() -> Any:
    """Import pygame and open its mixer unless it is already open; return pygame."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    # SDL otherwise takes over SIGTERM when the mixer starts and swallows it,
    # so `kill` or a process manager could not stop the app. Ctrl+C was unaffected.
    os.environ.setdefault("SDL_NO_SIGNAL_HANDLERS", "1")
    import pygame

    if not pygame.mixer.get_init():
        pygame.mixer.init()
    return pygame


def _init_com_for_thread() -> None:
    """Initialise COM on the calling thread. SAPI5 speech needs it on Windows."""
    if sys.platform != "win32":
        return
    import comtypes

    comtypes.CoInitialize()


def _speak_once(
    pyttsx3: Any,
    text: str,
    should_stop: Callable[[], bool],
    voice_id: str | None,
    rate: int,
) -> None:
    """Speak text on a brand-new engine, cutting off at a word boundary on should_stop().

    The rate is set on every engine, and the voice too unless voice_id is None
    (None keeps the system default voice).
    """
    engine = pyttsx3.init()
    engine.setProperty("rate", rate)
    if voice_id is not None:
        engine.setProperty("voice", voice_id)

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

    mode = "real"  # drives a real speech engine; still does not prove anyone heard it

    def __init__(self, rate: int = SPEECH_RATE_WPM) -> None:
        """Check on the current thread that a pyttsx3 engine can start; list its voices."""
        _init_com_for_thread()
        import pyttsx3

        self._pyttsx3 = pyttsx3
        self._rate = rate
        self._voice_id: str | None = None
        engine = pyttsx3.init()  # raise now, so the manager falls back to logging
        try:
            voices = engine.getProperty("voices") or []
            self._voices = [(str(v.id), str(v.name)) for v in voices]
        except Exception:
            log.exception("Could not list installed voices; using the system voice")
            self._voices = []
        del engine
        gc.collect()

    def installed_voices(self) -> list[tuple[str, str]]:
        """Return the (voice_id, name) pairs the engine listed at startup."""
        return list(self._voices)

    def set_voice(self, voice_id: str | None) -> None:
        """Use voice_id on every later engine; None means the system default voice."""
        self._voice_id = voice_id

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Speak text, blocking until it ends or should_stop() turns true."""
        if should_stop():
            return
        try:
            _speak_once(self._pyttsx3, text, should_stop, self._voice_id, self._rate)
        finally:
            gc.collect()  # drop the used engine so the next init() builds a new one


_DONE = object()  # end-of-phrase marker on the streaming queue


# Piper pads every sentence with about 0.26 s of silence before and 0.28 s after.
# Trimming it makes speech start sooner; a short tail keeps a pause between sentences.
SILENCE_LEVEL = 500  # int16 amplitude, about -36 dBFS: above the medium voices' noise floor
LEAD_PAD_SECONDS = 0.02
TAIL_PAD_SECONDS = 0.12


def _trim_silence(np: Any, samples: Any, rate: int) -> Any:
    """Cut leading and trailing near-silence from mono int16 samples, keeping short pads."""
    loud = np.flatnonzero(np.abs(samples.astype(np.int32)) > SILENCE_LEVEL)
    if len(loud) == 0:
        return samples
    start = max(0, int(loud[0]) - int(LEAD_PAD_SECONDS * rate))
    end = min(len(samples), int(loud[-1]) + 1 + int(TAIL_PAD_SECONDS * rate))
    return samples[start:end]


def _to_mixer_array(np: Any, samples: Any, src_rate: int, mixer_init: tuple[int, int, int]) -> Any:
    """Convert mono int16 samples to the open mixer's rate, sample format and channels."""
    freq, size, channels = mixer_init
    data = samples.astype(np.float32)
    if src_rate != freq and len(data) > 1:
        n_out = max(1, round(len(data) * freq / src_rate))
        positions = np.linspace(0, len(data) - 1, n_out)
        data = np.interp(positions, np.arange(len(data)), data).astype(np.float32)
    if abs(size) == 32:
        out = (data / 32768.0).astype(np.float32)
    elif size == 8:
        out = np.clip(data / 256.0 + 128.0, 0, 255).astype(np.uint8)
    elif size == -8:
        out = np.clip(data / 256.0, -128, 127).astype(np.int8)
    elif size == 16:
        out = np.clip(data + 32768.0, 0, 65535).astype(np.uint16)
    else:
        out = np.clip(data, -32768, 32767).astype(np.int16)
    if channels > 1:
        out = np.repeat(out[:, None], channels, axis=1)
    return np.ascontiguousarray(out)


class HybridSpeaker:
    """Piper neural voices played through the pygame mixer, with pyttsx3 for system voices.

    Create it and call say/set_voice on one thread (the speech worker). prepare()
    renders phrases on its own background thread. Piper ids come from
    voices.piper_voice_id; any other id (or None) goes to pyttsx3.
    """

    mode = "real"  # drives a real speech engine; still does not prove anyone heard it

    def __init__(self, rate: int = SPEECH_RATE_WPM, preload: bool = True) -> None:
        """Start pyttsx3 and Piper where possible; raise if neither can speak.

        preload loads every downloaded model in the background (the app wants
        this; a one-shot command line does not).
        """
        self._rate = rate
        self._system: Pyttsx3Speaker | None = None
        try:
            self._system = Pyttsx3Speaker(rate)
        except Exception:
            log.exception("System voices (pyttsx3) unavailable; using Piper voices only")
        self._piper: Any = None
        self._pygame: Any = None
        self._np: Any = None
        try:
            import numpy as np
            import piper

            self._pygame = _init_mixer()
            self._piper, self._np = piper, np
        except ImportError as exc:
            log.warning("Piper voices unavailable (%s); using system voices only", exc)
        except Exception:
            log.exception("Piper voices could not start; using system voices only")
        if self._piper is None and self._system is None:
            raise RuntimeError("No speech engine: neither Piper nor pyttsx3 could start")
        self._active: voices.VoicePreset | None = None  # None means pyttsx3 speaks
        self._loaded: dict[str, Any] = {}  # Piper model stem -> PiperVoice
        self._sounds: dict[tuple[str, str], Any] = {}  # (model, text) -> Sound
        self._cache_lock = threading.Lock()
        # espeak-ng phonemisation inside Piper is not known to be thread-safe, so
        # the worker and prepare() take turns, one sentence at a time.
        self._synth_lock = threading.Lock()
        # Live speech outranks pre-rendering: while it is set, prepare() pauses
        # between sentences. A newer prepare() cancels the older one.
        self._live = threading.Event()
        self._live_count = 0
        self._live_lock = threading.Lock()
        self._prepare_cancel = threading.Event()
        # Loading a model takes about 1 s. Every downloaded model is loaded once on
        # a background thread at startup, so a later switch does not hold up the
        # speech worker (and the hazard phrase behind it). Costs RAM per model.
        self._load_lock = threading.Lock()
        if preload and self._piper is not None:
            threading.Thread(target=self._preload, name="audio-preload", daemon=True).start()

    def installed_voices(self) -> list[tuple[str, str]]:
        """Return Piper presets whose model file exists, then the pyttsx3 system voices."""
        found: list[tuple[str, str]] = []
        if self._piper is not None:
            found = [
                (voices.piper_voice_id(p), p.voice_name)
                for p in voices.PRESETS
                if p.model and voices.piper_model_path(p).is_file()
            ]
        if self._system is not None:
            found += self._system.installed_voices()
        return found

    def set_voice(self, voice_id: str | None) -> None:
        """Use a Piper voice (loaded once, then cached) or route the id to pyttsx3.

        Raises if a Piper voice cannot be loaded, so the manager reports the
        switch as failed.
        """
        if voice_id is not None and voice_id.startswith(voices.PIPER_ID_PREFIX):
            preset = next(
                (p for p in voices.PRESETS if voices.piper_voice_id(p) == voice_id), None
            )
            if preset is None or self._piper is None:
                raise ValueError(f"Piper voice {voice_id!r} is not available")
            self._load(preset)
            self._active = preset
            return
        self._active = None
        if self._system is not None:
            self._system.set_voice(voice_id)

    def prepare(self, texts: Iterable[str]) -> None:
        """Render texts fully for the active Piper voice on a background thread.

        Returns at once. say() then plays the cached audio for those texts. Does
        nothing while a pyttsx3 voice is active.
        """
        preset = self._active
        if preset is None or self._piper is None:
            return
        voice = self._loaded[preset.model]
        wanted = [t for t in dict.fromkeys(texts) if t]
        self._prepare_cancel.set()  # stop an older prepare(), e.g. for the previous voice
        cancel = threading.Event()
        self._prepare_cancel = cancel

        def render() -> None:
            """Fill the cache one phrase at a time; stop at the first failure or on cancel."""
            for text in wanted:
                key = (preset.model, text)
                with self._cache_lock:
                    if key in self._sounds:
                        continue
                try:
                    chunks = list(self._synth_chunks(voice, text, cancel, yield_to_live=True))
                    if cancel.is_set():
                        return
                    sound = self._make_sound(chunks)
                except Exception:
                    log.exception("Pre-rendering %r failed; it will be synthesised live", text)
                    return
                with self._cache_lock:
                    self._sounds[key] = sound

        threading.Thread(target=render, name="audio-prepare", daemon=True).start()

    def is_prepared(self, text: str) -> bool:
        """Return True if text is cached for the active Piper voice."""
        preset = self._active
        if preset is None:
            return False
        with self._cache_lock:
            return (preset.model, text) in self._sounds

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Speak text, blocking until it ends; once should_stop() is true, cut off within ~10 ms."""
        if should_stop():
            return
        preset = self._active
        if preset is None:
            if self._system is None:
                raise RuntimeError("No system speech engine for this voice")
            self._system.say(text, should_stop)
            return
        with self._cache_lock:
            cached = self._sounds.get((preset.model, text))
        if cached is not None:
            self._play_cached(cached, should_stop)
            return
        self._stream(self._loaded[preset.model], text, should_stop)

    # Internals.

    def _load(self, preset: voices.VoicePreset) -> Any:
        """Return this preset's PiperVoice, loading it once; waits if the preloader has it."""
        with self._load_lock:
            if preset.model not in self._loaded:
                path = voices.piper_model_path(preset)
                self._loaded[preset.model] = self._piper.PiperVoice.load(str(path))
            return self._loaded[preset.model]

    def _preload(self) -> None:
        """Load every downloaded Piper model in the background, one at a time."""
        for preset in voices.PRESETS:
            if preset.model and voices.piper_model_path(preset).is_file():
                try:
                    self._load(preset)
                except Exception:
                    log.exception("Preloading voice %s failed", preset.label)

    def _synth_config(self) -> Any:
        """Build the SynthesisConfig that matches the calm speech rate."""
        return self._piper.SynthesisConfig(length_scale=PIPER_NATURAL_WPM / self._rate)

    def _synth_chunks(
        self,
        voice: Any,
        text: str,
        cancel: threading.Event | None = None,
        yield_to_live: bool = False,
    ) -> Iterable[Any]:
        """Yield Piper AudioChunks one sentence at a time, holding the synth lock per step.

        With yield_to_live (pre-rendering), wait before each sentence while live
        speech is synthesising, so a live hazard phrase never queues behind it.
        """
        stream = iter(voice.synthesize(text, syn_config=self._synth_config()))
        while cancel is None or not cancel.is_set():
            while yield_to_live and self._live.is_set():
                if cancel is not None and cancel.is_set():
                    return
                time.sleep(POLL_SECONDS)
            with self._synth_lock:
                chunk = next(stream, None)
            if chunk is None:
                return
            yield chunk

    def _make_sound(self, chunks: list[Any]) -> Any:
        """Turn AudioChunks into one pygame Sound in the mixer's own format."""
        np = self._np
        mixer_init = self._pygame.mixer.get_init()
        if not mixer_init:
            raise RuntimeError("The pygame mixer is closed")
        if not chunks:
            samples = np.zeros(1, dtype=np.int16)
            rate = mixer_init[0]
        else:
            parts = []
            for chunk in chunks:
                part = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                if chunk.sample_channels > 1:
                    part = part.reshape(-1, chunk.sample_channels)[:, 0]
                parts.append(_trim_silence(np, part, chunk.sample_rate))
            samples = np.concatenate(parts)
            rate = chunks[0].sample_rate
        array = _to_mixer_array(np, samples, rate, mixer_init)
        return self._pygame.sndarray.make_sound(array)

    def _play_cached(self, sound: Any, should_stop: Callable[[], bool]) -> None:
        """Play one Sound to the end, stopping its channel as soon as should_stop() is true."""
        channel = sound.play()
        if channel is None:
            log.warning("No free mixer channel; a phrase was skipped")
            return
        while channel.get_busy():
            if should_stop():
                channel.stop()
                return
            time.sleep(POLL_SECONDS)

    def _mark_live(self, delta: int) -> None:
        """Count live syntheses; pre-rendering pauses while any is running."""
        with self._live_lock:
            self._live_count += delta
            if self._live_count > 0:
                self._live.set()
            else:
                self._live.clear()

    def _stream(self, voice: Any, text: str, should_stop: Callable[[], bool]) -> None:
        """Synthesise on a helper thread and play each sentence as soon as it is ready.

        The next sentence is rendered while the current one plays. This thread
        only polls, so a cut-off never waits for synthesis.
        """
        chunks: queue.Queue[Any] = queue.Queue()
        cancel = threading.Event()

        def produce() -> None:
            """Render sentences into the queue until done, failed or cancelled."""
            self._mark_live(+1)
            try:
                for chunk in self._synth_chunks(voice, text, cancel):
                    chunks.put(self._make_sound([chunk]))
            except Exception as exc:  # noqa: BLE001 - re-raised by say() on the worker
                chunks.put(exc)
            finally:
                self._mark_live(-1)
            chunks.put(_DONE)

        threading.Thread(target=produce, name="audio-piper", daemon=True).start()
        channel: Any = None
        try:
            while True:
                if should_stop():
                    if channel is not None:
                        channel.stop()
                    return
                if channel is not None and channel.get_busy():
                    time.sleep(POLL_SECONDS)
                    continue
                try:
                    item = chunks.get(timeout=POLL_SECONDS)
                except queue.Empty:
                    continue
                if item is _DONE:
                    return
                if isinstance(item, Exception):
                    raise item
                channel = item.play()
                if channel is None:
                    log.warning("No free mixer channel; a sentence was skipped")
        finally:
            cancel.set()


class LogSpeaker:
    """Stand-in used when text to speech cannot start: logs instead of speaking."""

    mode = "unavailable"

    def installed_voices(self) -> list[tuple[str, str]]:
        """No engine, so no voices."""
        return []

    def set_voice(self, voice_id: str | None) -> None:
        """Nothing to switch: speech is only logged."""

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        """Log the text that would have been spoken."""
        log.info("Would say: %s", text)


class PygameAlarm:
    """Plays the pre-made alarm WAV through the pygame mixer without blocking."""

    mode = "real"

    def __init__(self, path: Path = ALARM_WAV) -> None:
        """Open the mixer and load the alarm file."""
        pygame = _init_mixer()
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
    mode = "unavailable"

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
