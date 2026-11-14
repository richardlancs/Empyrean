"""Questions use real contract messages and keep stale views out of answers."""

import time

from fastapi.testclient import TestClient
from test_dashboard import TestBus

from contracts import LastSeenQuery, SceneObject, SceneSnapshot, SpeakRequest
from dashboard import DashboardState, create_app, register
from dashboard.questions import ask_question


def test_scene_answer_speaks_once_and_reaches_page() -> None:
    """Scene summaries use current names and exclude lost objects."""
    bus = TestBus()
    dashboard = register(bus, serve=False)
    now = time.time()
    bus.publish(
        SceneSnapshot(
            now,
            1,
            [
                SceneObject(
                    1, "bottle", "Heinz ketchup", "touching", (0, 0, 50, 50), now
                ),
                SceneObject(2, "cup", "", "lost", (60, 0, 100, 50), now),
            ],
        )
    )
    client = TestClient(create_app(dashboard.state, publish=bus.publish))
    reply = client.post("/api/question", json={"text": "What do you see?"}).json()
    assert reply["answer"] == "I can detect Heinz ketchup."
    spoken = [msg for msg in bus.published if isinstance(msg, SpeakRequest)]
    assert len(spoken) == 1
    assert dashboard.state.snapshot()["answer"] == reply["answer"]


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


def test_stale_scene_and_missing_history_are_honest() -> None:
    """Unavailable inputs do not masquerade as a successful lookup."""
    state = DashboardState()
    state.on_scene(SceneSnapshot(1, 1, []))
    published = []
    result = ask_question("What am I touching?", state, published.append, False)
    assert "current camera view" in result["answer"]
    result = ask_question("Find my bottle", state, published.append, False)
    assert "unavailable" in result["answer"]
    assert all(isinstance(msg, SpeakRequest) for msg in published)


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


def test_this_item_identifies_touch_instead_of_other_visible_objects() -> None:
    """A spoken this-item question answers with the touched object directly."""
    state = DashboardState()
    now = time.time()
    state.on_scene(
        SceneSnapshot(
            now,
            1,
            [
                SceneObject(1, "bottle", "Heinz ketchup", "held", (0, 0, 50, 50), now),
                SceneObject(2, "cup", "Coffee cup", "idle", (60, 0, 100, 50), now),
            ],
        )
    )
    spoken = []
    for question in ("What is this item?", "What's this?", "Identify this item"):
        reply = ask_question(question, state, spoken.append, False)
        assert reply["answer"] == "You are touching Heinz ketchup."
    assert len(spoken) == 3
    assert all(isinstance(message, SpeakRequest) for message in spoken)
