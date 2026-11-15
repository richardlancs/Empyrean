"""Development and test server for the How It Works page.

Serves howitworks/ and dashboard/static/ at the URLs the real dashboard uses,
without starting the engine. Run: uvicorn tests.howitworks_server:app --port 8010
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
HOW_DIR = ROOT / "howitworks"
STATIC_DIR = ROOT / "dashboard" / "static"


def build_dev_app() -> FastAPI:
    """Return an app that serves only the How It Works page and the shared styles."""
    dev = FastAPI(title="Empyrean How It Works (dev)")

    @dev.get("/dashboard", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        """Keep the walkthrough's return link available in its standalone preview."""
        return HTMLResponse((ROOT / "dashboard" / "index.html").read_text(encoding="utf-8"))

    dev.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    dev.mount("/how-it-works", StaticFiles(directory=HOW_DIR, html=True), name="how-it-works")
    return dev


app = build_dev_app()
