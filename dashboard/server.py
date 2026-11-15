"""Compose the dashboard: services, bus wiring, routes, static files and the web server.

Layers, outermost first:
  api/ (routes.py, realtime.py, schemas.py)  HTTP and WebSocket, validation, errors
  services/ and state.py                     read model, queries, health, heartbeat
  bus_adapter.py                             the only place that subscribes to the bus
  video.py, thumbnails.py                    the camera picture pipeline
The frontend lives in index.html and static/ and only talks to the api layer.
"""

from __future__ import annotations

import logging
import mimetypes
import socket
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import DASHBOARD_PORT
from dashboard import bus_adapter
from dashboard.api.realtime import ClientHub, build_realtime_router
from dashboard.api.routes import INDEX_PATH, build_router
from dashboard.services.container import DashboardServices
from dashboard.services.detector_mode import DetectorModeService
from dashboard.services.heartbeat import Heartbeat
from dashboard.services.last_seen import LastSeenService
from dashboard.services.questions import QuestionService
from dashboard.state import DashboardState
from dashboard.thumbnails import ThumbnailCache
from dashboard.video import VideoFeed

LOGGER = logging.getLogger("dashboard")
STATIC_DIR = Path(__file__).resolve().parent / "static"
HOW_DIR = Path(__file__).resolve().parents[1] / "howitworks"
DEFAULT_HOST = "127.0.0.1"
SERVER_STOP_SECONDS = 3.0  # how long stop() waits for the web server thread

# Native ES modules need a JavaScript MIME type; some OS registries map .js wrongly.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

__all__ = ["INDEX_PATH", "STATIC_DIR", "Dashboard", "create_app", "register"]


class Dashboard:
    """The dashboard as app/ runs it: bus-fed services plus the web page on a thread."""

    def __init__(
        self,
        state: DashboardState,
        video: VideoFeed | None = None,
        *,
        last_seen: LastSeenService | None = None,
        thumbnails: ThumbnailCache | None = None,
        detector_mode: DetectorModeService | None = None,
        questions: QuestionService | None = None,
    ) -> None:
        """Hold the services; call serve() to start the web page."""
        self.state = state
        # "is None", not "or": an empty ThumbnailCache has len 0 and is falsy.
        self.video = video if video is not None else VideoFeed()
        self.thumbnails = thumbnails if thumbnails is not None else ThumbnailCache()
        self.last_seen = last_seen if last_seen is not None else LastSeenService(None)
        self.detector_mode = detector_mode if detector_mode is not None else DetectorModeService(None)
        self.state.thumbnails = self.thumbnails
        self.state.last_seen = self.last_seen
        self.state.detector_mode = self.detector_mode
        self.questions = questions if questions is not None else _questions(None, self.state, self.last_seen)
        self.state.questions = self.questions
        self.heartbeat = Heartbeat(self.tick)
        self._server: Any = None
        self._thread: threading.Thread | None = None

    @property
    def services(self) -> DashboardServices:
        """The services the routes call into."""
        return DashboardServices(
            self.state, self.video, self.last_seen, self.thumbnails, self.detector_mode,
            self.questions,
        )

    def tick(self) -> None:
        """Expire old searches and pictures, then push the state to open pages."""
        self.last_seen.expire()
        self.questions.expire()
        self.detector_mode.expire()
        self.thumbnails.expire()
        self.state.tick()

    def serve(self, host: str = DEFAULT_HOST, port: int = DASHBOARD_PORT) -> bool:
        """Start the web page on a background thread; return False if the port is busy."""
        if not _port_is_free(host, port):
            LOGGER.warning(
                "Port %d is already in use, so the dashboard page was not started", port
            )
            return False
        import uvicorn

        config = uvicorn.Config(
            _build_app(self.services), host=host, port=port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="dashboard-server", daemon=True
        )
        self._thread.start()
        self.heartbeat.start()  # only pages need the push; queries expire on read too
        LOGGER.info("Dashboard page at http://localhost:%d", port)
        return True

    def stop(self) -> None:
        """End open video streams, stop the heartbeat and the web server, and wait briefly."""
        self.heartbeat.stop()
        self.video.close()
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(SERVER_STOP_SECONDS)


def _port_is_free(host: str, port: int) -> bool:
    """Return True if nothing is listening on host:port.

    SO_REUSEADDR matches what uvicorn sets, so connections left in TIME_WAIT by
    a page that was open before a restart do not block the new server. A live
    listener still makes bind() fail. Windows is left as is: there the option
    would let two servers share the port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if sys.platform != "win32":
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

    The subscriptions are listed in bus_adapter.connect. Last-touch searches are
    published on this bus for storage/ to answer.
    """
    state = state or DashboardState()
    last_seen = LastSeenService(bus.publish)
    dashboard = Dashboard(
        state,
        last_seen=last_seen,
        detector_mode=DetectorModeService(bus.publish),
        questions=_questions(bus.publish, state, last_seen),
    )
    bus_adapter.connect(bus, dashboard.services)
    if serve:
        dashboard.serve()
    return dashboard


def create_app(
    state: DashboardState | None = None,
    video: VideoFeed | None = None,
    *,
    last_seen: LastSeenService | None = None,
    thumbnails: ThumbnailCache | None = None,
    detector_mode: DetectorModeService | None = None,
    questions: QuestionService | None = None,
) -> FastAPI:
    """Build the dashboard web app (new empty services for anything not given)."""
    state = state if state is not None else DashboardState()
    thumbnails = _first(thumbnails, state.thumbnails, ThumbnailCache)
    last_seen = _first(last_seen, state.last_seen, lambda: LastSeenService(None))
    detector_mode = _first(detector_mode, state.detector_mode, lambda: DetectorModeService(None))
    state.thumbnails, state.last_seen, state.detector_mode = thumbnails, last_seen, detector_mode
    questions = _first(questions, state.questions, lambda: _questions(None, state, last_seen))
    state.questions = questions
    video = video if video is not None else VideoFeed()
    return _build_app(
        DashboardServices(state, video, last_seen, thumbnails, detector_mode, questions)
    )


def _questions(
    publish: Any, state: DashboardState, last_seen: LastSeenService
) -> QuestionService:
    """Build the question service over the read model; publish None means no engine."""
    return QuestionService(
        publish,
        last_seen,
        scene_running=lambda: not state.health.not_started("namer"),
        history_running=lambda: last_seen.available and not state.health.not_started("storage"),
    )


def _first(given: Any, attached: Any, make: Any) -> Any:
    """Return given, else attached, else make(); tested with "is None" (an empty cache is falsy)."""
    if given is not None:
        return given
    return attached if attached is not None else make()


def _build_app(services: DashboardServices) -> FastAPI:
    """Assemble routes, the WebSocket hub and static files around the services."""
    app = FastAPI(title="Empyrean dashboard")
    app.state.dashboard = services.state
    app.state.services = services
    hub = ClientHub(services.state.snapshot)
    services.state.add_listener(hub.push)
    services.last_seen.add_listener(hub.push)
    services.detector_mode.add_listener(hub.push)
    services.questions.add_listener(hub.push)
    app.include_router(build_router(services))
    app.include_router(build_realtime_router(hub))
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if HOW_DIR.is_dir():
        # The static How It Works page (howitworks/): no engine data, no routes.
        app.mount("/how-it-works", StaticFiles(directory=HOW_DIR, html=True), name="how-it-works")

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        """Translate validation errors into one plain sentence plus the field list."""
        fields = [".".join(str(p) for p in e.get("loc", ())[1:]) for e in exc.errors()]
        named = ", ".join(f for f in fields if f) or "request"
        return JSONResponse(
            {"detail": f"Invalid {named}.", "errors": _jsonable_errors(exc)}, status_code=422
        )

    return app


def _jsonable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Return validation errors with only JSON-safe fields."""
    return [
        {"loc": [str(p) for p in e.get("loc", ())], "msg": str(e.get("msg", ""))}
        for e in exc.errors()
    ]
