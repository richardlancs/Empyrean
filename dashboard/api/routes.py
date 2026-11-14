"""HTTP routes. Each handler validates input, calls one service, and shapes the reply.

No handler touches the database, a model, or the speaker. Last-touch search goes
through LastSeenService, which publishes on the bus for storage/ to answer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from dashboard.api.schemas import (
    ErrorBody,
    LastSeenAccepted,
    LastSeenRequest,
    LastSeenStatus,
    ModeRequest,
    QuestionRequest,
    QuestionStatus,
)
from dashboard.services.container import DashboardServices
from dashboard.services.detector_mode import ModeRejected
from dashboard.services.last_seen import QueryRejected
from dashboard.services.questions import QuestionRejected
from dashboard.video import BOUNDARY, OverlayOptions, mjpeg_stream

LOGGER = logging.getLogger("dashboard")
INDEX_PATH = Path(__file__).resolve().parents[1] / "index.html"
NO_STORE = {"Cache-Control": "no-store"}

Flag = Annotated[int, Query(ge=0, le=1)]


def _error(status_code: int, detail: str) -> JSONResponse:
    """Return the shared error body."""
    return JSONResponse(ErrorBody(detail=detail).model_dump(), status_code=status_code)


def build_router(services: DashboardServices) -> APIRouter:
    """Return the router for the page, the video, the state and the page actions."""
    router = APIRouter()
    state, video = services.state, services.video
    last_seen, thumbnails = services.last_seen, services.thumbnails

    @router.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        """Serve the page's entry document."""
        return HTMLResponse(INDEX_PATH.read_text(encoding="utf-8"), headers=NO_STORE)

    @router.get("/video")
    async def video_stream(
        boxes: Flag = 1,
        hands: Flag = 1,
        labels: Flag = 1,
        selected_id: Annotated[int | None, Query(ge=0)] = None,
    ) -> StreamingResponse:
        """Stream the camera feed as MJPEG with this viewer's overlays (SPEC.md 4.9)."""
        options = OverlayOptions(bool(boxes), bool(hands), bool(labels), selected_id)
        return StreamingResponse(
            mjpeg_stream(video, options=options),
            media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
            headers=NO_STORE,
        )

    @router.get("/api/state")
    async def get_state() -> dict[str, Any]:
        """Return the current page state."""
        return state.snapshot()

    @router.post("/api/simulate-alert")
    async def simulate_alert() -> dict[str, Any]:
        """Add one simulated warning to the page only, and return the new state."""
        LOGGER.info("Simulated alert added to the dashboard (no bus message, no alarm)")
        return state.simulate_hazard()

    @router.post(
        "/api/last-seen",
        status_code=202,
        response_model=LastSeenAccepted,
        responses={422: {"model": ErrorBody}, 429: {"model": ErrorBody}, 503: {"model": ErrorBody}},
    )
    async def post_last_seen(body: LastSeenRequest) -> Any:
        """Start a last-touch search; poll GET /api/last-seen/{request_id} for the answer."""
        try:
            request_id = last_seen.submit(body.query)
        except QueryRejected as exc:
            return _error(exc.status_code, exc.message)
        return JSONResponse(
            LastSeenAccepted(request_id=request_id).model_dump(), status_code=202
        )

    @router.get(
        "/api/last-seen/{request_id}",
        response_model=LastSeenStatus,
        responses={404: {"model": ErrorBody}},
    )
    async def get_last_seen(
        request_id: Annotated[str, PathParam(min_length=1, max_length=64)],
    ) -> Any:
        """Return one search's status: pending, found, not_found or unavailable."""
        record = last_seen.get(request_id)
        if record is None:
            return _error(404, "That search is unknown or has expired. Search again.")
        return LastSeenStatus(**{k: record[k] for k in LastSeenStatus.model_fields})

    @router.post(
        "/api/question",
        response_model=QuestionStatus,
        responses={
            202: {"model": QuestionStatus, "description": "History lookup started"},
            422: {"model": ErrorBody},
            503: {"model": ErrorBody},
        },
    )
    async def post_question(body: QuestionRequest) -> Any:
        """Answer a typed or recognized question; 202 while a history lookup is pending."""
        try:
            record = services.questions.ask(body.text)
        except QuestionRejected as exc:
            return _error(exc.status_code, exc.message)
        reply = QuestionStatus(**{k: record[k] for k in QuestionStatus.model_fields})
        return JSONResponse(
            reply.model_dump(), status_code=202 if record["status"] == "looking_up" else 200
        )

    @router.get(
        "/api/question/{question_id}",
        response_model=QuestionStatus,
        responses={404: {"model": ErrorBody}},
    )
    async def get_question(
        question_id: Annotated[str, PathParam(min_length=1, max_length=64)],
    ) -> Any:
        """Return one question's record; poll it while status is looking_up."""
        record = services.questions.get(question_id)
        if record is None:
            return _error(404, "That question is unknown or has expired. Ask again.")
        return QuestionStatus(**{k: record[k] for k in QuestionStatus.model_fields})

    @router.post(
        "/api/mode",
        responses={202: {"description": "Switch requested"}, 409: {"model": ErrorBody}, 503: {"model": ErrorBody}},
    )
    async def set_mode(body: ModeRequest) -> Any:
        """Ask vision to switch detector (Regular "actual" or Demo "demo").

        202 means only "requested": the page shows the new mode as active after
        vision confirms it with DetectorStatus. 200 means it is already active.
        """
        try:
            reply = services.detector_mode.request(body.mode)
        except ModeRejected as exc:
            return _error(exc.status_code, exc.message)
        LOGGER.info("Detector switch to %s requested from the dashboard", body.mode)
        return JSONResponse(
            {**reply, "detector": services.detector_mode.view()},
            status_code=202 if reply["state"] == "switching" else 200,
        )

    @router.get("/api/mode")
    async def get_mode() -> dict[str, Any]:
        """Return the detector state as vision last reported it."""
        return services.detector_mode.view()

    @router.get(
        "/api/objects/{object_id}/thumbnail",
        responses={200: {"content": {"image/jpeg": {}}}, 404: {"model": ErrorBody}},
    )
    async def object_thumbnail(object_id: Annotated[int, PathParam(ge=0)]) -> Response:
        """Return a recent JPEG crop of one object, or 404 if none is held."""
        jpeg = thumbnails.get(object_id)
        if jpeg is None:
            return _error(404, "No recent picture of this object.")
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "max-age=5"})

    return router
