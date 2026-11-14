"""Standalone pyttsx3 speech test; no bus, alarm or hazard is involved.

Speaks one sentence through the system's default audio output, offline.

Setup, from the repository root, in Windows PowerShell:

    py -3.11 -m pip install -r audio/requirements.txt

Run:

    py -3.11 -m audio.speak_test "Heinz ketchup"
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

LOGGER = logging.getLogger("audio")


def speak(text: str) -> None:
    """Say text once with pyttsx3 and wait until it has finished playing."""
    import pyttsx3

    engine = pyttsx3.init()
    try:
        engine.say(text)
        engine.runAndWait()
    finally:
        engine.stop()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the sentence from the command line and speak it; return an exit code."""
    parser = argparse.ArgumentParser(description="Speak one sentence with pyttsx3.")
    parser.add_argument("text", help='Sentence to say, for example "Heinz ketchup"')
    args = parser.parse_args(argv)
    text = args.text.strip()
    if not text:
        parser.error("Please supply a sentence that is not empty.")

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    raise SystemExit(main())
