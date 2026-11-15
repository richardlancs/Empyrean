"""Download the nine Piper voice files into audio/voice_models/ (git-ignored).

Run once per laptop, with internet, before the demo. After that speech is
fully offline. Files come from the rhasspy/piper-voices repository on Hugging
Face; a file that is already present is skipped.

    python -m audio.fetch_voices          # all nine voices
    python -m audio.fetch_voices cori     # one preset by key
"""

from __future__ import annotations

import argparse
import logging
import shutil
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from audio.voices import PRESETS, VOICE_MODEL_DIR

log = logging.getLogger("audio")

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def voice_urls(model: str) -> list[tuple[str, Path]]:
    """Return (url, local path) for a Piper model's .onnx and .onnx.json files."""
    lang = model.split("-", 1)[0]  # en_GB
    family = lang.split("_", 1)[0]  # en
    name, tier = model.split("-")[1], model.split("-")[2]
    folder = f"{BASE_URL}/{family}/{lang}/{name}/{tier}"
    return [
        (f"{folder}/{model}{ext}", VOICE_MODEL_DIR / f"{model}{ext}")
        for ext in (".onnx", ".onnx.json")
    ]


def fetch(model: str) -> None:
    """Download one model's two files unless they are already present."""
    VOICE_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for url, path in voice_urls(model):
        if path.exists() and path.stat().st_size > 0:
            log.info("Already have %s", path.name)
            continue
        partial = path.with_suffix(path.suffix + ".part")
        log.info("Downloading %s", url)
        with urllib.request.urlopen(url, timeout=60) as reply, partial.open("wb") as out:
            shutil.copyfileobj(reply, out)
        partial.rename(path)
        log.info("Saved %s (%.0f MB)", path.name, path.stat().st_size / 1e6)


def main(argv: Sequence[str] | None = None) -> int:
    """Download the requested presets' voices (all nine by default)."""
    keys = [p.key for p in PRESETS]
    parser = argparse.ArgumentParser(description="Download Piper voices for audio/.")
    parser.add_argument("keys", nargs="*", choices=keys, help="preset keys (default: all)")
    args = parser.parse_args(argv)
    wanted = args.keys or keys
    for preset in PRESETS:
        if preset.key in wanted:
            fetch(preset.model)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    raise SystemExit(main())
