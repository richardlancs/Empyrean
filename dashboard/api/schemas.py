"""Request and response shapes for the dashboard API (see docs/dashboard-redesign/api.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The service trims and checks the real limit; this only stops absurd bodies early.
MAX_QUERY_BODY_CHARS = 200


class LastSeenRequest(BaseModel):
    """POST /api/last-seen body."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=MAX_QUERY_BODY_CHARS)


class LastSeenAccepted(BaseModel):
    """POST /api/last-seen reply (HTTP 202)."""

    request_id: str
    status: Literal["pending"] = "pending"


class LastSeenStatus(BaseModel):
    """GET /api/last-seen/{request_id} reply."""

    request_id: str
    status: Literal["pending", "found", "not_found", "unavailable"]
    answer: str | None
    matched_at: float | None  # Unix seconds of the matching recorded touch
    query: str
    label: str | None
    neighbours: list[str]
    detail: str
    submitted_at: float


class QuestionRequest(BaseModel):
    """POST /api/question body (main's shape): {"text": "What am I touching?"}."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)


class QuestionStatus(BaseModel):
    """One question's record: POST /api/question reply and GET /api/question/{id}.

    status: answered, looking_up (a history lookup is waiting for storage) or
    unavailable (no current camera view, or history could not be reached; never
    a "not found"). speech_requested only means a SpeakRequest was published.
    """

    question_id: str
    text: str
    intent: Literal["scene", "touch", "history", "help"]
    target: str | None
    status: Literal["answered", "looking_up", "unavailable"]
    answer: str | None
    answered_by: Literal["dashboard", "storage"] | None
    speech_requested: bool
    history_status: Literal["found", "not_found", "unavailable"] | None
    history_request_id: str | None
    detail: str
    asked_at: float
    answered_at: float | None


class ErrorBody(BaseModel):
    """Every error reply: one plain sentence the page can show."""

    detail: str


class ModeRequest(BaseModel):
    """POST /api/mode body (main's shape): {"mode": "actual" | "demo"}."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["actual", "demo"]
