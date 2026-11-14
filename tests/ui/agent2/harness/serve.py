"""Preview server for the experience feature, using artificial FIXTURE data only.

Run from the repository root:  python tests/ui/agent2/harness/serve.py [port]
Then open http://localhost:8765/. Standard library only; never used by the app.

Serves /static/* from dashboard/static, the harness page, a fixture /video image,
fixture thumbnails, and a fake asynchronous /api/last-seen with test words:
"slow" answers after 3 s, "never" stays pending, "down" is unavailable,
"zebra" is not found, "broken" returns HTTP 500.
"""

from __future__ import annotations

import itertools
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[4]
STATIC = ROOT / "dashboard" / "static"
HARNESS = Path(__file__).resolve().parent
TYPES = {
    ".js": "text/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".svg": "image/svg+xml",
}

_ids = itertools.count(1)
_requests: dict[str, dict] = {}
_lock = threading.Lock()


def _fixture_svg(title: str, query: dict[str, list[str]]) -> bytes:
    """An obviously artificial camera picture, with the overlay options written on it."""
    opts = (
        ", ".join(f"{k}={v[0]}" for k, v in sorted(query.items()) if k != "r")
        or "default overlays"
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<rect width="640" height="360" fill="#2B3A4F"/>
<rect x="250" y="120" width="120" height="170" fill="none" stroke="#3FB950" stroke-width="4"/>
<rect x="420" y="160" width="140" height="110" fill="none" stroke="#FFFFFF" stroke-width="2"/>
<circle cx="300" cy="150" r="5" fill="#58A6FF"/><circle cx="320" cy="140" r="5" fill="#58A6FF"/>
<text x="20" y="40" fill="#FFFFFF" font-family="sans-serif" font-size="22">{title}</text>
<text x="20" y="340" fill="#D8E1EB" font-family="sans-serif" font-size="14">{opts}</text>
</svg>"""
    return svg.encode()


class Handler(BaseHTTPRequestHandler):
    """Static files plus fixture endpoints."""

    def log_message(self, fmt: str, *args: object) -> None:  # quieter output
        sys.stderr.write("harness: " + fmt % args + "\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data: object) -> None:
        self._send(code, json.dumps(data).encode(), "application/json")

    def do_GET(self) -> None:
        url = urlparse(self.path)
        path = url.path
        query = parse_qs(url.query)
        if path in ("/", "/index.html"):
            return self._file(HARNESS / "index.html")
        if path.startswith("/harness/"):
            return self._file(HARNESS / path.removeprefix("/harness/"))
        if path.startswith("/static/"):
            return self._file(STATIC / path.removeprefix("/static/"))
        if path == "/video":
            if Path(HARNESS / ".video-down").exists():
                return self._send(503, b"fixture video down", "text/plain")
            return self._send(
                200,
                _fixture_svg("FIXTURE camera image (not live)", query),
                TYPES[".svg"],
            )
        if path.startswith("/api/objects/") and path.endswith("/thumbnail"):
            oid = path.split("/")[3]
            if oid == "404":
                return self._json(404, {"detail": "No recent picture of this object"})
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><rect width="96" height="96" fill="#E6F4F1"/><text x="10" y="55" font-size="16" fill="#0F766E">FIX {oid}</text></svg>'
            return self._send(200, svg.encode(), TYPES[".svg"])
        if path.startswith("/api/last-seen/"):
            rid = path.rsplit("/", 1)[1]
            with _lock:
                req = _requests.get(rid)
            if req is None:
                return self._json(404, {"detail": "Unknown or expired request"})
            return self._json(200, _resolve(rid, req))
        return self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/last-seen":
            return self._send(404, b"not found", "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            text = str(body.get("query", "")).strip()
        except (ValueError, AttributeError):
            return self._json(422, {"detail": "query is required"})
        if not text:
            return self._json(422, {"detail": "query is required"})
        if "broken" in text.lower():
            return self._json(500, {"detail": "fixture failure"})
        rid = f"fx-{next(_ids)}"
        with _lock:
            _requests[rid] = {"query": text, "at": time.time()}
        return self._json(202, {"request_id": rid})

    def _file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            if not (
                resolved.is_relative_to(STATIC) or resolved.is_relative_to(HARNESS)
            ):
                raise FileNotFoundError
            data = resolved.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            return self._send(404, b"not found", "text/plain")
        self._send(200, data, TYPES.get(resolved.suffix, "application/octet-stream"))


def _resolve(rid: str, req: dict) -> dict:
    """Fixture answers keyed on words in the query."""
    q = req["query"].lower()
    waited = time.time() - req["at"]
    base = {"request_id": rid, "answer": None, "matched_at": None}
    if "never" in q or ("slow" in q and waited < 3) or waited < 0.6:
        return {**base, "status": "pending"}
    if "down" in q:
        return {**base, "status": "unavailable"}
    if "zebra" in q:
        return {**base, "status": "not_found", "answer": "I have not seen that."}
    return {
        **base,
        "status": "found",
        "answer": f"FIXTURE {req['query']}, 4 minutes ago, next to mug and cereal box.",
        "matched_at": time.time() - 240,
    }


def main() -> None:
    """Serve until Ctrl+C."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Experience harness (FIXTURE data) at http://localhost:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
