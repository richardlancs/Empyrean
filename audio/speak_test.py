"""Standalone speech test; no bus, alarm or hazard is involved.

Speaks through the system's default audio output, offline, at SPEECH_RATE_WPM.
Plain TEXT uses the pyttsx3 system voice. --voice, --all and --list-voices use
the same speaker as the app (Piper neural voices, pyttsx3 for system voices), to
check the five presets by ear.

Setup, from the repository root, on macOS:

    .venv/bin/python -m pip install -r audio/requirements.txt
    .venv/bin/python -m audio.fetch_voices    # once, with internet

Run:

    .venv/bin/python -m audio.speak_test "Heinz ketchup"
    .venv/bin/python -m audio.speak_test --voice alba "Heinz ketchup"
    .venv/bin/python -m audio.speak_test --list-voices
    .venv/bin/python -m audio.speak_test --all

On Windows PowerShell, use `py -3.11` in place of `.venv/bin/python`.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from audio.backends import HybridSpeaker
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


def _never() -> bool:
    """A should_stop that never stops: the test speaks each phrase to the end."""
    return False


def _say_preset(speaker: HybridSpeaker, text: str, voice_id: str | None) -> None:
    """Switch the app's speaker to voice_id and say text to the end."""
    speaker.set_voice(voice_id)
    speaker.say(text, _never)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line, then speak, list or play the presets; return an exit code."""
    parser = argparse.ArgumentParser(
        description="Speak with pyttsx3 or Piper and check voice presets."
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

    uses_presets = bool(args.voice or args.all or args.list_voices)
    if not uses_presets:
        try:
            import pyttsx3  # noqa: F401
        except ImportError:
            LOGGER.error(
                "pyttsx3 is missing. Install audio/requirements.txt with Python 3.11."
            )
            return 1
        try:
            LOGGER.info("Speaking: %s", text)
            speak(text)
        except Exception:
            LOGGER.exception("Audio test failed")
            return 1
        return 0

    try:
        speaker = HybridSpeaker()
    except Exception:
        LOGGER.exception(
            "No speech engine. Install audio/requirements.txt with Python 3.11 "
            "and run python -m audio.fetch_voices."
        )
        return 1

    try:
        voices = speaker.installed_voices()
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
                _say_preset(
                    speaker, SAMPLE_TEXT.format(label=preset.label), resolved.voice_id
                )
            return 0
        resolved = resolve_voice(args.voice, voices) if args.voice else None
        LOGGER.info("Speaking: %s", text)
        _say_preset(speaker, text, resolved.voice_id if resolved else None)
    except Exception:
        LOGGER.exception("Audio test failed")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    raise SystemExit(main())
