"""Standalone Windows Piper test; no bus or real alerts are involved."""

import argparse
import logging
from pathlib import Path
import sys
import tempfile
import wave

LOGGER = logging.getLogger("audio")
DEFAULT_MODEL = Path(__file__).resolve().parent / "voices" / "en_US-lessac-medium.onnx"


def main() -> int:
    """Speak one supplied sentence through the Windows default audio output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help='Sentence to say, for example "Keys on the left"')
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    if not args.text.strip():
        parser.error("Please supply a sentence that is not empty.")
    if sys.platform != "win32":
        parser.error("This standalone playback test requires Windows.")
    for path in (args.model, Path(str(args.model) + ".json")):
        if not path.is_file():
            parser.error(f"Missing voice file: {path}. Download the voice first.")

    try:
        import winsound
        from piper import PiperVoice
    except ImportError:
        LOGGER.error("Piper is missing. Install audio/requirements.txt in your Python environment.")
        return 1

    try:
        voice = PiperVoice.load(str(args.model))
        with tempfile.TemporaryDirectory(prefix="sightline-audio-") as directory:
            output = Path(directory) / "speech.wav"
            with wave.open(str(output), "wb") as wav_file:
                voice.synthesize_wav(args.text, wav_file)
            LOGGER.info("Speaking: %s", args.text)
            winsound.PlaySound(str(output), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
    except Exception:
        LOGGER.exception("Audio test failed")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    raise SystemExit(main())
