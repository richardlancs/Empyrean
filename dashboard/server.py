"""FastAPI app: serves the page, pushes state over /ws, and handles Simulate alert."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from config import DASHBOARD_PORT
from contracts import HazardEvent, TouchEvent
from dashboard.state import DashboardState

LOGGER = logging.getLogger("dashboard")
INDEX_PATH = Path(__file__).resolve().parent / "index.html"
DEFAULT_HOST = "127.0.0.1"
SERVER_STOP_SECONDS = 3.0  # how long stop() waits for the web server thread


class Dashboard:
    """The dashboard as app/ runs it: bus-fed state plus the web page on a thread."""

    def __init__(self, state: DashboardState) -> None:
        """Hold state; call serve() to start the web page."""
        self.state = state
        self._server: Any = None
        self._thread: threading.Thread | None = None

    def serve(self, host: str = DEFAULT_HOST, port: int = DASHBOARD_PORT) -> bool:
        """Start the web page on a background thread; return False if the port is busy."""
        if not _port_is_free(host, port):
            LOGGER.warning(
                "Port %d is already in use, so the dashboard page was not started", port
            )
            return False
        import uvicorn

        config = uvicorn.Config(
            create_app(self.state), host=host, port=port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="dashboard-server", daemon=True
        )
        self._thread.start()
        LOGGER.info("Dashboard page at http://localhost:%d", port)
        return True

    def stop(self) -> None:
        """Ask the web server to finish and wait briefly for it."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(SERVER_STOP_SECONDS)


def _port_is_free(host: str, port: int) -> bool:
    """Return True if nothing is listening on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def register(
    bus: Any, state: DashboardState | None = None, serve: bool = True
) -> Dashboard:
    """Feed HazardEvent and TouchEvent to the dashboard and, if serve, start the page."""
    dashboard = Dashboard(state or DashboardState())
    bus.subscribe(HazardEvent, dashboard.state.on_hazard)
    bus.subscribe(TouchEvent, dashboard.state.on_touch)
    if serve:
        dashboard.serve()
    return dashboard


def _put_latest(queue: asyncio.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
    """Replace whatever is waiting in a one-slot queue; stale state is useless."""
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(item)


def create_app(state: DashboardState | None = None) -> FastAPI:
    """Build the dashboard web app around state (a new empty one if not given)."""
    state = state or DashboardState()
    app = FastAPI(title="Dashboard")
    app.state.dashboard = state
    clients: set[asyncio.Queue[dict[str, Any]]] = set()
    loop_ref: dict[str, asyncio.AbstractEventLoop] = {}

    def push_to_clients() -> None:
        """Queue the new state for every open page; safe to call from any thread."""
        loop = loop_ref.get("loop")
        if loop is None or not clients:
            return
        snapshot = state.snapshot()
        for queue in list(clients):
            with contextlib.suppress(RuntimeError):  # loop already closed at shutdown
                loop.call_soon_threadsafe(_put_latest, queue, snapshot)

    state.add_listener(push_to_clients)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        """Serve the single dashboard page."""
        return INDEX_PATH.read_text(encoding="utf-8")

    @app.get("/api/state")
    async def get_state() -> dict[str, Any]:
        """Return the current page state."""
        return state.snapshot()

    @app.post("/api/simulate-alert")
    async def simulate_alert() -> dict[str, Any]:
        """Add one simulated warning to the page only, and return the new state."""
        LOGGER.info("Simulated alert added to the dashboard (no bus message, no alarm)")
        return state.simulate_hazard()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """Send the state on connect and after every change until the page closes."""
        await websocket.accept()
        loop_ref["loop"] = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
        clients.add(queue)
        receiver = asyncio.create_task(_wait_for_close(websocket))
        try:
            await websocket.send_json(state.snapshot())
            while not receiver.done():
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {getter, receiver}, return_when=asyncio.FIRST_COMPLETED
                )
                if getter in done:
                    await websocket.send_json(getter.result())
                else:
                    getter.cancel()
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(queue)
            receiver.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                await receiver

    return app


async def _wait_for_close(websocket: WebSocket) -> None:
    """Read and ignore anything the page sends; return when it disconnects."""
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            await websocket.receive_text()
