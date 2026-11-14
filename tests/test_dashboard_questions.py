"""Questions use real contract messages and keep stale views out of answers."""

import time

from fastapi.testclient import TestClient
from test_dashboard import TestBus

from contracts import LastSeenQuery, SpeakRequest
from dashboard import DashboardState, create_app, register
from dashboard.questions import ask_question


def test_scene_question_is_independent_and_answer_reaches_page() -> None:
    """Open questions use Grok messages, with no touch or database prerequisite."""
    from contracts import SceneQuestion

    bus = TestBus()
    dashboard = register(bus, serve=False)
    client = TestClient(create_app(dashboard.state, publish=bus.publish))
    for text in (
        "Where are my keys?",
        "Find my bottle",
        "What is this item?",
        "What do you see?",
    ):
        reply = client.post("/api/question", json={"text": text}).json()
        assert reply["kind"] == "question"
        assert isinstance(bus.published[-1], SceneQuestion)
        assert bus.published[-1].text == text
    assert not any(isinstance(msg, LastSeenQuery) for msg in bus.published)
    bus.publish(SpeakRequest(time.time(), "To your right.", "normal", "namer"))
    assert dashboard.state.snapshot()["answer"] == "To your right."


def test_history_extracts_object_and_publishes_query(monkeypatch) -> None:
    """History queries go to storage rather than inventing an answer."""
    monkeypatch.setenv("TIGER_DATABASE_URL", "configured-for-test")
    bus = TestBus()
    state = register(bus, serve=False).state
    client = TestClient(create_app(state, publish=bus.publish))
    assert (
        client.post(
            "/api/question", json={"text": "Where did I last touch the bottle?"}
        ).json()["kind"]
        == "history"
    )
    assert len(bus.published) == 1
    assert isinstance(bus.published[0], LastSeenQuery)
    assert bus.published[0].text == "bottle"
    bus.publish(
        SpeakRequest(time.time(), "Bottle, 2 minutes ago.", "normal", "storage")
    )
    assert state.snapshot()["answer"] == "Bottle, 2 minutes ago."


def test_missing_history_is_honest() -> None:
    """Explicit history requests report unavailable storage."""
    published = []
    result = ask_question(
        "Where did I last touch my bottle?", DashboardState(), published.append, False
    )
    assert "unavailable" in result["answer"]
    assert isinstance(published[0], SpeakRequest)


def test_invalid_and_standalone_requests() -> None:
    """Empty/oversized inputs and dashboards without a bus are rejected."""
    client = TestClient(create_app(publish=lambda msg: None))
    for text in ("", "   ", "x" * 501):
        assert client.post("/api/question", json={"text": text}).status_code == 422
    assert (
        TestClient(create_app())
        .post("/api/question", json={"text": "What do you see?"})
        .status_code
        == 503
    )
