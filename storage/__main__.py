"""`python -m storage --selftest`: write one touch row to Tiger Data and read it back."""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid

from dotenv import load_dotenv

from storage import db
from storage.last_seen import format_answer


def selftest() -> int:
    """Connect, ensure the schema, round-trip one touch row and print the answer."""
    load_dotenv()
    url = os.environ.get("TIGER_DATABASE_URL")
    if not url:
        print("TIGER_DATABASE_URL is not set", file=sys.stderr)
        return 2
    tag = uuid.uuid4().hex[:8]
    name = f"Selftest ketchup {tag}"
    try:
        with db.connect(url) as conn:
            db.ensure_schema(conn)
            cx, cy = db.box_centre_fraction((300.0, 160.0, 340.0, 200.0))
            db.insert_touch(
                conn,
                {
                    "ts": time.time() - 240,
                    "session_id": f"selftest-{tag}",
                    "object_id": 1,
                    "class_label": "bottle",
                    "name": name,
                    "kind": "touch",
                    "cx": cx,
                    "cy": cy,
                    "neighbours": ["mug", "cereal box"],
                },
            )
            row = db.last_seen(conn, name.upper())
    except Exception as exc:  # noqa: BLE001
        # Class name only: driver messages can include host or user details.
        print(f"selftest failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if row is None or row.get("name") != name:
        print("selftest failed: row not found", file=sys.stderr)
        return 1
    print(format_answer(row, time.time()))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested command."""
    parser = argparse.ArgumentParser(prog="python -m storage")
    parser.add_argument("--selftest", action="store_true", help="round-trip one row")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
