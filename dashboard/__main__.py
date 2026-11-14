"""Run the dashboard on its own, with no bus: `python -m dashboard`.

Real events need app/ to call dashboard.register(bus). On its own the page
shows only what the Simulate alert button adds.
"""

from __future__ import annotations

import argparse
import logging

import uvicorn

from config import DASHBOARD_PORT
from dashboard.server import create_app

LOGGER = logging.getLogger("dashboard")


def main() -> None:
    """Serve the dashboard until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Run the dashboard with no bus.")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Use 0.0.0.0 to allow other devices"
    )
    parser.add_argument("--port", type=int, default=DASHBOARD_PORT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    LOGGER.info("Open http://localhost:%d in a browser. Ctrl+C stops it.", args.port)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
