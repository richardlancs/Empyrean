"""FastAPI app: the page, the camera feed at /video, state over /ws, Simulate alert, Demo mode."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from config import DASHBOARD_PORT
from contracts import (
    FrameResult,
    HazardEvent,
    ModeChange,
    SceneSnapshot,
    SpeakRequest,
    TouchEvent,
)
from dashboard.questions import ask_question
from dashboard.state import DashboardState
from dashboard.video import BOUNDARY, VideoFeed, mjpeg_stream

LOGGER = logging.getLogger("dashboard")
INDEX_PATH = Path(__file__).resolve().parent / "index.html"
DEFAULT_HOST = "127.0.0.1"
SERVER_STOP_SECONDS = 3.0  # how long stop() waits for the web server thread


class Question(BaseModel):
    """One recognized or typed question."""

    text: str = Field(min_length=1, max_length=500)


class Dashboard:
    """The dashboard as app/ runs it: bus-fed state plus the web page on a thread."""

    def __init__(
        self,
        state: DashboardState,
        video: VideoFeed | None = None,
        publish: Callable[[Any], None] | None = None,
    ) -> None:
        """Hold state, the camera feed and the bus publish; call serve() to start the page."""
        self.state = state
        self.video = video or VideoFeed()
        self.publish = publish
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
            create_app(self.state, self.video, self.publish),
            host=host,
            port=port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="dashboard-server", daemon=True
        )
        self._thread.start()
        LOGGER.info("Dashboard page at http://localhost:%d", port)
        return True

    def stop(self) -> None:
        """End open video streams, ask the web server to finish, and wait briefly."""
        self.video.close()
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(SERVER_STOP_SECONDS)


def _port_is_free(host: str, port: int) -> bool:
    """Return True if nothing is listening on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # Match Uvicorn: a previous connection in TIME_WAIT is safe to reuse.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def register(
    bus: Any, state: DashboardState | None = None, serve: bool = True
) -> Dashboard:
    """Feed bus messages to the dashboard and, if serve, start the page.

    FrameResult and SceneSnapshot drive the camera feed, SceneSnapshot also
    drives the object list, and HazardEvent and TouchEvent drive the warning
    and event log. The Demo mode button publishes ModeChange, and ModeChange
    from the bus sets the mode shown on the page.
    """
    dashboard = Dashboard(state or DashboardState(), publish=bus.publish)
    bus.subscribe(ModeChange, dashboard.state.on_mode)
    bus.subscribe(SpeakRequest, dashboard.state.on_answer)
    bus.subscribe(HazardEvent, dashboard.state.on_hazard)
    bus.subscribe(TouchEvent, dashboard.state.on_touch)
    bus.subscribe(FrameResult, dashboard.video.on_frame)
    bus.subscribe(SceneSnapshot, dashboard.video.on_scene)
    bus.subscribe(SceneSnapshot, dashboard.state.on_scene)
    if serve:
        dashboard.serve()
    return dashboard


def _put_latest(queue: asyncio.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
    """Replace whatever is waiting in a one-slot queue; stale state is useless."""
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(item)


def create_app(
    state: DashboardState | None = None,
    video: VideoFeed | None = None,
    publish: Callable[[Any], None] | None = None,
) -> FastAPI:
    """Build the dashboard web app around state and a camera feed (new empty ones if not given).

    publish is the bus publish used by the Demo mode button; without it the
    button only changes the page.
    """
    state = state or DashboardState()
    video = video or VideoFeed()
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

    @app.get("/video")
    async def video_stream() -> StreamingResponse:
        """Stream the camera feed with overlays as MJPEG (SPEC.md 4.9)."""
        return StreamingResponse(
            mjpeg_stream(video),
            media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/state")
    async def get_state() -> dict[str, Any]:
        """Return the current page state."""
        return state.snapshot()

    @app.post("/api/question")
    async def question(body: Question) -> dict[str, str]:
        """Route a transcript without blocking camera or hazard processing."""
        if publish is None:
            raise HTTPException(503, "Questions require the running app.")
        if not body.text.strip():
            raise HTTPException(422, "Please enter a question.")
        return ask_question(
            body.text, state, publish, bool(os.environ.get("TIGER_DATABASE_URL"))
        )

    @app.post("/api/simulate-alert")
    async def simulate_alert() -> dict[str, Any]:
        """Add one simulated warning to the page only, and return the new state."""
        LOGGER.info("Simulated alert added to the dashboard (no bus message, no alarm)")
        return state.simulate_hazard()

    @app.post("/api/mode")
    async def set_mode(
        mode: Literal["actual", "demo"] = Body(embed=True),
    ) -> dict[str, Any]:
        """Ask the app to switch mode, show it on the page, and return the new state."""
        message = ModeChange(ts=time.time(), mode=mode)
        state.on_mode(message)
        if publish is not None:
            publish(message)  # the bus only queues it; nothing here waits on vision
        LOGGER.info("Mode set to %s from the dashboard", mode)
        return state.snapshot()

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
