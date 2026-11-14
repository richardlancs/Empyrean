"""Hand-run naming eval: sends every JPEG in scratch/eval/ to Grok and prints a table.

Run from the repo root:  .venv/bin/python -m fakes.namer.eval_names [folder]

Uses the real namer.grok_client.name_crop (xAI Responses API), so it tests the
exact request the namer sends. Needs GROK_API_KEY and
GROK_MODEL in .env. Publishes nothing; it only prints file, reply, latency ms.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from config import NAME_MAX_CHARS

DEFAULT_FOLDER = Path("scratch/eval")


def find_jpegs(folder: Path) -> list[Path]:
    """Return the JPEG files in folder, sorted by name."""
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"})


def make_namer() -> Callable[[bytes], str]:
    """Return a sync function that names one JPEG with the real namer.grok_client."""
    import asyncio

    import httpx

    from namer.grok_client import name_crop

    async def _one(jpeg: bytes) -> str:
        async with httpx.AsyncClient() as client:
            return await name_crop(client, jpeg, "unknown")

    return lambda jpeg: asyncio.run(_one(jpeg))[:NAME_MAX_CHARS]


def main(argv: list[str]) -> int:
    """Run the eval over a folder and print the table; return an exit code."""
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_FOLDER
    files = find_jpegs(folder)
    if not files:
        print(f"No JPEG files in {folder}/. Put some .jpg crops there and run again.")
        return 1

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    missing = [v for v in ("GROK_API_KEY", "GROK_MODEL") if not os.environ.get(v)]
    if missing:
        print(f"Missing {', '.join(missing)} in the environment. Add them to .env and retry.")
        return 1

    name_fn = make_namer()
    print(f"Naming {len(files)} file(s) with namer.grok_client.name_crop\n")
    width = max(len(p.name) for p in files)
    print(f"{'file':<{width}}  {'reply':<{NAME_MAX_CHARS}}  latency ms")
    print(f"{'-' * width}  {'-' * NAME_MAX_CHARS}  ----------")
    for path in files:
        start = time.monotonic()
        try:
            reply = name_fn(path.read_bytes())
        except Exception as exc:  # noqa: BLE001 - eval keeps going on any failure
            reply = f"ERROR {type(exc).__name__}"
        ms = (time.monotonic() - start) * 1000
        print(f"{path.name:<{width}}  {reply:<{NAME_MAX_CHARS}}  {ms:10.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
