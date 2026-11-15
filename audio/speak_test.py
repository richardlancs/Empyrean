"""Standalone pyttsx3 speech test; no bus, alarm or hazard is involved.

Speaks through the system's default audio output, offline, at SPEECH_RATE_WPM.
It can also list the five voice presets and play each one, to check them by ear.

Setup, from the repository root, on macOS:

    .venv/bin/python -m pip install -r audio/requirements.txt

Run:

    .venv/bin/python -m audio.speak_test "Heinz ketchup"
    .venv/bin/python -m audio.speak_test --voice jamie "Heinz ketchup"
    .venv/bin/python -m audio.speak_test --list-voices
    .venv/bin/python -m audio.speak_test --all

On Windows PowerShell, use `py -3.11` in place of `.venv/bin/python`.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from audio.voices import PRESETS, resolve_voice
from config import SPEECH_RATE_WPM

LOGGER = logging.getLogger("audio")
SAMPLE_TEXT = "This is {label}. Heinz ketchup. Stop. Stairs."


def speak(text: str, voice_id: str | None = None, rate: int = SPEECH_RATE_WPM) -> None:
    """Say text once with pyttsx3 at rate, in voice_id if given, and wait until it ends."""
    import pyttsx3

    engine = pyttsx3.init()
    try:
        engine.setProperty("rate", rate)
        if voice_id is not None:
            engine.setProperty("voice", voice_id)
        engine.say(text)
        engine.runAndWait()
    finally:
        engine.stop()


def installed_voices() -> list[tuple[str, str]]:
    """Return the (voice_id, name) pairs pyttsx3 can see."""
    import pyttsx3

    engine = pyttsx3.init()
    return [(str(v.id), str(v.name)) for v in engine.getProperty("voices") or []]


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line, then speak, list or play the presets; return an exit code."""
    parser = argparse.ArgumentParser(
        description="Speak with pyttsx3 and check voice presets."
    )
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument(
        "--voice", choices=[p.key for p in PRESETS], help="Preset to speak TEXT with"
    )
    choice.add_argument(
        "--all", action="store_true", help="Play a sample of every preset"
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print each preset and the voice it uses",
    )
    parser.add_argument(
        "text", nargs="?", help='Sentence to say, for example "Heinz ketchup"'
    )
    args = parser.parse_args(argv)
    text = (args.text or "").strip()
    if not text and not (args.list_voices or args.all):
        parser.error("Please supply a sentence that is not empty.")

    try:
        import pyttsx3  # noqa: F401
    except ImportError:
        LOGGER.error(
            "pyttsx3 is missing. Install audio/requirements.txt with Python 3.11."
        )
        return 1

    try:
        voices = (
            installed_voices() if (args.voice or args.all or args.list_voices) else []
        )
        if args.list_voices:
            for preset in PRESETS:
                resolved = resolve_voice(preset.key, voices)
                print(
                    f"{preset.key}\t{preset.label}\t"
                    f"{resolved.voice_id or '(system default)'}\t{resolved.quality}"
                )
            if not (args.all or text):
                return 0
        if args.all:
            for preset in PRESETS:
                resolved = resolve_voice(preset.key, voices)
                LOGGER.info("Speaking %s (%s)", preset.label, resolved.quality)
                speak(SAMPLE_TEXT.format(label=preset.label), resolved.voice_id)
            return 0
        voice_id = resolve_voice(args.voice, voices).voice_id if args.voice else None
        LOGGER.info("Speaking: %s", text)
        speak(text, voice_id)
    except Exception:
        LOGGER.exception("Audio test failed")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    raise SystemExit(main())
