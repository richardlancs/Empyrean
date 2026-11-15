"""Serve one consistent version of the dashboard's buildless browser assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

STATIC_DIR = Path(__file__).resolve().parent / "static"


def asset_revision(directory: Path) -> str:
    """Fingerprint asset paths and contents so updates get a fresh browser module graph."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


ASSET_PREFIX = f"/assets/{asset_revision(STATIC_DIR)}"


def page_html(path: Path, *, modules: bool = False) -> str:
    """Read a page with versioned assets and optional mappings for dynamic feature imports."""
    text = path.read_text(encoding="utf-8").replace("/static/", f"{ASSET_PREFIX}/")
    if modules:
        imports = json.dumps({"imports": {"/static/": f"{ASSET_PREFIX}/"}})
        text = text.replace(
            '<script type="module"',
            f'<script type="importmap">{imports}</script>\n<script type="module"',
            1,
        )
    return text


class RevalidatedStaticFiles(StaticFiles):
    """Keep unversioned local pages and assets from retaining stale code after updates."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve a file with explicit revalidation, including conditional responses."""
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response
