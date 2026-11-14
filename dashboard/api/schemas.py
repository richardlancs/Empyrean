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


class ErrorBody(BaseModel):
    """Every error reply: one plain sentence the page can show."""

    detail: str
