"""Agent 1 preview server: the real foundation files against fixture data.

Serves dashboard/index.html and dashboard/static/ as they are, with fixture
scenarios on /ws and /api/state. The feature modules are preview stubs from
tests/ui/agent1/stubs/ (Agents 2 and 3 own the real ones). Not production.

    python tests/ui/agent1/agent1_preview_server.py [--port 8765] [--missing-features]

Controls (for browser checks):
    POST /preview/scenario/{name}     switch scenario and push it to open pages
    POST /preview/drop?seconds=3      close sockets and refuse new ones for a while
    GET  /preview/scenarios           list scenario names
    GET  /preview/inventory           visual inventory of the foundation primitives
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import itertools
import logging
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from agent1_fixtures import SCENARIOS

LOGGER = logging.getLogger("dashboard")
PUSH_INTERVAL_SECONDS = 1.0
FEATURE_NAMES = ("experience", "operations")


def _video_svg(label: str) -> str:
    """A 640x360 stand-in for the MJPEG feed, clearly marked as a fixture."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<rect width="640" height="360" fill="#2B3A4F"/>
<rect x="250" y="120" width="110" height="170" rx="10" fill="none" stroke="#3FD1B5" stroke-width="5"/>
<rect x="250" y="94" width="96" height="24" fill="#3FD1B5"/>
<text x="258" y="112" font-family="sans-serif" font-size="15" font-weight="700" fill="#08241F">TOUCHING</text>
<rect x="420" y="160" width="120" height="110" rx="8" fill="none" stroke="#FFFFFF" stroke-width="2"/>
<circle cx="300" cy="210" r="7" fill="#FFD166"/><circle cx="318" cy="190" r="7" fill="#FFD166"/>
<text x="16" y="340" font-family="sans-serif" font-size="16" fill="#FFFFFF">Preview fixture: {label}</text>
</svg>"""


def create_preview_app(missing_features: bool = False) -> FastAPI:
    """Build the preview app. missing_features makes both feature modules 404."""
    app = FastAPI(title="Empyrean foundation preview")
    # Scenario timestamps are fixed when a scenario starts (like real events);
    # only `now` advances, so ages grow and warnings expire naturally.
    current: dict[str, Any] = {"name": "touch", "sim": None, "anchor": time.time()}
    sockets: set[WebSocket] = set()
    refuse_until = {"t": 0.0}
    lookups: dict[str, dict[str, Any]] = {}
    ids = itertools.count(1)

    def state() -> dict[str, Any]:
        snap = SCENARIOS[current["name"]](current["anchor"])
        snap["now"] = time.time()
        if current["sim"] is not None and "latest_simulated_warning" in snap:
            sim = dict(current["sim"])
            snap["latest_simulated_warning"] = sim
            snap["latest_warning"] = sim
            snap["events"] = [sim, *snap["events"]][:10]
        return snap

    async def broadcast() -> None:
        snap = state()
        for ws in list(sockets):
            with contextlib.suppress(Exception):
                await ws.send_json(snap)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            ROOT / "dashboard" / "index.html", headers={"Cache-Control": "no-store"}
        )

    @app.get("/static/features/{feature}/{path:path}")
    async def feature_file(feature: str, path: str) -> FileResponse:
        target = (HERE / "stubs" / "features" / feature / path).resolve()
        if missing_features or feature not in FEATURE_NAMES or not target.is_file():
            raise HTTPException(status_code=404, detail="Feature module not found")
        if (HERE / "stubs").resolve() not in target.parents:
            raise HTTPException(status_code=404, detail="Feature module not found")
        return FileResponse(target, headers={"Cache-Control": "no-store"})

    app.mount(
        "/static", StaticFiles(directory=ROOT / "dashboard" / "static"), name="static"
    )

    @app.get("/preview/inventory")
    async def inventory() -> FileResponse:
        return FileResponse(
            HERE / "preview" / "inventory.html", headers={"Cache-Control": "no-store"}
        )

    @app.get("/preview/scenarios")
    async def scenarios() -> dict[str, Any]:
        return {"current": current["name"], "names": list(SCENARIOS)}

    @app.post("/preview/scenario/{name}")
    async def set_scenario(name: str) -> dict[str, Any]:
        if name not in SCENARIOS:
            raise HTTPException(status_code=404, detail=f"No scenario named {name}")
        current.update(name=name, sim=None, anchor=time.time())
        await broadcast()
        return {"current": name}

    @app.post("/preview/drop")
    async def drop(seconds: float = 3.0) -> dict[str, Any]:
        refuse_until["t"] = time.time() + seconds
        for ws in list(sockets):
            with contextlib.suppress(Exception):
                await ws.close(code=1012)
        return {"refusing_for": seconds}

    @app.get("/video")
    async def video() -> Response:
        return Response(
            _video_svg(current["name"]),
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/state")
    async def get_state() -> dict[str, Any]:
        return state()

    @app.post("/api/simulate-alert")
    async def simulate_alert() -> dict[str, Any]:
        current["sim"] = {
            "id": 1000 + next(ids),
            "ts": time.time(),
            "kind": "hazard",
            "type": "stairs_down",
            "text": "Stairs",
            "detail": "",
            "simulated": True,
        }
        await broadcast()
        return state()

    @app.post("/api/last-seen", status_code=202)
    async def last_seen(body: dict[str, Any]) -> dict[str, Any]:
        query = str(body.get("query", "")).strip()
        if not query:
            raise HTTPException(status_code=422, detail="Type what to look for")
        request_id = f"preview-{next(ids)}"
        lookups[request_id] = {"query": query, "polls": 0}
        return {"request_id": request_id}

    @app.get("/api/last-seen/{request_id}")
    async def last_seen_result(request_id: str) -> JSONResponse:
        lookup = lookups.get(request_id)
        if lookup is None:
            return JSONResponse(
                {"detail": "Unknown or expired request"}, status_code=404
            )
        lookup["polls"] += 1
        if lookup["polls"] < 2:
            body = {
                "request_id": request_id,
                "status": "pending",
                "answer": None,
                "matched_at": None,
            }
        elif "ketchup" in lookup["query"].lower():
            body = {
                "request_id": request_id,
                "status": "found",
                "answer": "Heinz ketchup, 2 min ago, next to Starbucks coffee cup.",
                "matched_at": time.time() - 120,
            }
        else:
            body = {
                "request_id": request_id,
                "status": "not_found",
                "answer": None,
                "matched_at": None,
            }
        return JSONResponse(body)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        if time.time() < refuse_until["t"]:
            await websocket.close(code=1013)
            return
        await websocket.accept()
        sockets.add(websocket)
        try:
            await websocket.send_json(state())
            while True:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        websocket.receive_text(), PUSH_INTERVAL_SECONDS
                    )
                await websocket.send_json(state())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            sockets.discard(websocket)

    return app


def main() -> None:
    """Run the preview server."""
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--missing-features", action="store_true", help="serve no feature modules"
    )
    args = parser.parse_args()
    uvicorn.run(
        create_preview_app(args.missing_features),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
