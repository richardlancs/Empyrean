"""CLI: `python -m namer path/to/image.jpg [--label bottle]` names one image."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

from namer import _pending as c
from namer.grok_client import name_crop
from namer.namer import clean_name


async def _name_file(jpeg: bytes, label: str) -> str:
    """Make one Grok call for a JPEG and return the raw reply."""
    async with httpx.AsyncClient(timeout=c.NAME_TIMEOUT_SECONDS) as client:
        return await asyncio.wait_for(
            name_crop(client, jpeg, label), c.NAME_TIMEOUT_SECONDS
        )


def main(argv: list[str] | None = None) -> int:
    """Name one image file with Grok and print the cleaned name."""
    parser = argparse.ArgumentParser(prog="python -m namer", description=__doc__)
    parser.add_argument("image", type=Path, help="JPEG file to name")
    parser.add_argument(
        "--label", default="object", help="class label hint, e.g. bottle"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        jpeg = args.image.read_bytes()
        raw = asyncio.run(_name_file(jpeg, args.label))
    except Exception as exc:  # noqa: BLE001 - CLI reports any failure and exits 1
        print(f"naming failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(clean_name(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
