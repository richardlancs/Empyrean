"""Questions from the page: real contract messages, honest answers, correlated history.

Ported from main's microphone feature (5ee1039) to the layered dashboard: the
same question wording and answers, now through QuestionService and
POST/GET /api/question. History goes through LastSeenService with a request_id.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_dashboard import TestBus

from contracts import (
    LastSeenQuery,
    LastSeenResult,
    ModuleStatus,
    SceneObject,
    SceneSnapshot,
    SpeakRequest,
)
from dashboard import DashboardState, create_app, register
from dashboard.questions import parse_question, scene_answer
from dashboard.services.last_seen import LastSeenService
from dashboard.services.questions import QuestionService


def scene(now: float, *objects: SceneObject) -> SceneSnapshot:
    """A snapshot of the given objects, describing a frame captured at now."""
    return SceneSnapshot(now, 1, list(objects))


def obj(object_id: int, label: str, name: str, state: str, now: float) -> SceneObject:
    """One scene object with a dummy box."""
    return SceneObject(object_id, label, name, state, (0, 0, 50, 50), now)  # type: ignore[arg-type]


def spoken(bus: TestBus) -> list[str]:
    """Texts the dashboard asked audio to speak."""
    return [m.text for m in bus.published if isinstance(m, SpeakRequest)]


@pytest.fixture
def engine() -> tuple[TestBus, Any, TestClient]:
    """A dashboard registered on a test bus, with storage counted as running."""
    bus = TestBus()
    dashboard = register(bus, serve=False)
    return bus, dashboard, TestClient(create_app(dashboard.state))


# Wording (main's router, unchanged).


@pytest.mark.parametrize(
    ("text", "intent", "target"),
    [
        ("What can you see?", "scene", ""),
        ("what do you see", "scene", ""),
        ("What am I touching?", "touch", ""),
        ("What am I holding?", "touch", ""),
        ("Identify this item", "touch", ""),
        ("Where did I last touch the bottle?", "history", "bottle"),
        ("Where did I last touch my keys", "history", "keys"),
        ("Find my phone.", "history", "phone"),
        ("Sing a song", "help", ""),
    ],
)
def test_parse_question(text: str, intent: str, target: str) -> None:
    """Main's phrases map to the same intents."""
    parsed = parse_question(text)
    assert (parsed.intent, parsed.target) == (intent, target)


def test_touch_answer_names_only_the_touched_object() -> None:
    """A this-item question answers with the touched object, not other visible ones."""
    objects = [
        {"text": "Heinz ketchup", "state": "held"},
        {"text": "Coffee cup", "state": "idle"},
        {"text": "Old cup", "state": "lost"},
    ]
    assert scene_answer(objects, touching=True) == "You are touching Heinz ketchup."
    assert scene_answer(objects, touching=False) == "I can detect Heinz ketchup, Coffee cup."


# Scene and touch questions.


def test_scene_answer_speaks_once_and_reaches_every_page(engine: Any) -> None:
    """Scene summaries use current names, exclude lost objects, and speak once."""
    bus, dashboard, client = engine
    now = time.time()
    bus.publish(scene(now, obj(1, "bottle", "Heinz ketchup", "touching", now),
                      obj(2, "cup", "", "lost", now)))
    reply = client.post("/api/question", json={"text": "What do you see?"})
    assert reply.status_code == 200
    body = reply.json()
    assert body["answer"] == "I can detect Heinz ketchup."
    assert body["status"] == "answered" and body["answered_by"] == "dashboard"
    assert body["speech_requested"] is True
    assert spoken(bus) == ["I can detect Heinz ketchup."]
    # Another open page sees the same question and answer over /ws.
    recent = dashboard.state.snapshot()["questions"]["recent"]
    assert recent[0]["question_id"] == body["question_id"]
    assert client.get(f"/api/question/{body['question_id']}").json()["answer"] == body["answer"]


def test_touch_then_ask_what_it_is(engine: Any) -> None:
    """Touch an object, then ask what it is: the touched object's name comes back."""
    bus, _dashboard, client = engine
    now = time.time()
    bus.publish(scene(now, obj(1, "bottle", "Heinz ketchup", "touching", now),
                      obj(2, "cup", "Coffee cup", "idle", now)))
    body = client.post("/api/question", json={"text": "What am I touching?"}).json()
    assert body["answer"] == "You are touching Heinz ketchup."


def test_stale_scene_is_not_answered_confidently(engine: Any) -> None:
    """A scene older than LOST_KEEP_SECONDS gives "no current camera view", not names."""
    bus, _dashboard, client = engine
    old = time.time() - 30
    bus.publish(scene(old, obj(1, "bottle", "Heinz ketchup", "touching", old)))
    body = client.post("/api/question", json={"text": "What am I touching?"}).json()
    assert body["answer"] == "I do not have a current camera view."
    assert body["status"] == "unavailable"
    assert "Heinz" not in "".join(spoken(bus))


def test_no_scene_yet_is_unavailable(engine: Any) -> None:
    """Before any scene, questions about the view are honestly unavailable."""
    _bus, _dashboard, client = engine
    body = client.post("/api/question", json={"text": "What can you see?"}).json()
    assert body["status"] == "unavailable"
    assert body["answer"] == "I do not have a current camera view."


def test_unknown_question_gets_help(engine: Any) -> None:
    """Unsupported questions get main's help sentence, spoken."""
    bus, _dashboard, client = engine
    body = client.post("/api/question", json={"text": "Sing a song"}).json()
    assert body["intent"] == "help" and body["answer"].startswith("Try: What do you see?")
    assert len(spoken(bus)) == 1


# History questions.


def test_history_waits_for_storage_and_does_not_speak_twice(engine: Any) -> None:
    """A history question is looking_up until storage's correlated result arrives."""
    bus, dashboard, client = engine
    reply = client.post("/api/question", json={"text": "Where did I last touch the bottle?"})
    assert reply.status_code == 202
    body = reply.json()
    assert body["status"] == "looking_up" and body["answer"].startswith("Looking up")
    queries = [m for m in bus.published if isinstance(m, LastSeenQuery)]
    assert len(queries) == 1 and queries[0].text == "bottle" and queries[0].request_id
    assert spoken(bus) == []  # "Looking up…" is shown, not spoken
    # storage speaks its sentence itself, then publishes the correlated result.
    bus.publish(SpeakRequest(time.time(), "Bottle, 2 minutes ago.", "normal", "storage"))
    bus.publish(LastSeenResult(time.time(), queries[0].request_id, "found",
                               "Bottle, 2 minutes ago.", time.time() - 120, "bottle", []))
    done = client.get(f"/api/question/{body['question_id']}").json()
    assert done["status"] == "answered" and done["answer"] == "Bottle, 2 minutes ago."
    assert done["answered_by"] == "storage" and done["history_status"] == "found"
    # Only storage's own SpeakRequest: the dashboard never repeats it.
    assert spoken(bus) == ["Bottle, 2 minutes ago."]
    assert dashboard.state.snapshot()["questions"]["recent"][0]["status"] == "answered"


def test_unavailable_history_is_never_reported_as_not_found(engine: Any) -> None:
    """A database outage stays "unavailable"; it is not "I have not seen that"."""
    bus, _dashboard, client = engine
    body = client.post("/api/question", json={"text": "Find my keys"}).json()
    request_id = next(m for m in bus.published if isinstance(m, LastSeenQuery)).request_id
    bus.publish(LastSeenResult(time.time(), request_id, "unavailable",
                               "Touch history is unavailable right now.", None, "", []))
    done = client.get(f"/api/question/{body['question_id']}").json()
    assert done["status"] == "unavailable" and done["history_status"] == "unavailable"
    assert done["answer"] == "Touch history is unavailable right now."


def test_storage_not_started_answers_unavailable_at_once() -> None:
    """With storage not running in this launch, history is unavailable and spoken once."""
    bus = TestBus()
    dashboard = register(bus, serve=False)
    bus.publish(
        ModuleStatus(time.time(), "storage", "offline", "unknown", "Not started in this run")
    )
    client = TestClient(create_app(dashboard.state))
    body = client.post("/api/question", json={"text": "Where did I last touch the bottle?"}).json()
    assert body["status"] == "unavailable"
    assert body["answer"] == "Touch history is unavailable right now."
    assert not [m for m in bus.published if isinstance(m, LastSeenQuery)]
    assert spoken(bus) == ["Touch history is unavailable right now."]


def test_storage_that_never_answers_times_out_as_unavailable() -> None:
    """A lookup storage never answers becomes unavailable and is spoken by the dashboard."""
    clock = [1000.0]
    published: list[Any] = []
    last_seen = LastSeenService(published.append, clock=lambda: clock[0], timeout=8.0)
    service = QuestionService(
        published.append, last_seen, objects=list, scene_age=lambda: None,
        history_running=lambda: True, clock=lambda: clock[0],
    )
    record = service.ask("Where did I last touch the remote?")
    assert record["status"] == "looking_up"
    clock[0] += 9.0
    done = service.get(record["question_id"])
    assert done is not None and done["status"] == "unavailable"
    assert done["detail"] == "History storage did not answer in time"
    assert [m.text for m in published if isinstance(m, SpeakRequest)] == [
        "Touch history is unavailable right now."
    ]


def test_delayed_history_cannot_overwrite_a_newer_answer(engine: Any) -> None:
    """Two lookups in flight: each result lands on its own question, in any order."""
    bus, dashboard, client = engine
    first = client.post("/api/question", json={"text": "Find my keys"}).json()
    second = client.post("/api/question", json={"text": "Find my phone"}).json()
    q1, q2 = [m for m in bus.published if isinstance(m, LastSeenQuery)]
    bus.publish(LastSeenResult(time.time(), q2.request_id, "found", "Phone, just now.",
                               time.time(), "phone", []))
    bus.publish(LastSeenResult(time.time(), q1.request_id, "not_found",
                               "I have not seen keys.", None, "", []))
    a1 = client.get(f"/api/question/{first['question_id']}").json()
    a2 = client.get(f"/api/question/{second['question_id']}").json()
    assert (a1["answer"], a1["history_status"]) == ("I have not seen keys.", "not_found")
    assert (a2["answer"], a2["history_status"]) == ("Phone, just now.", "found")
    newest = dashboard.state.snapshot()["questions"]["recent"][0]
    assert newest["question_id"] == second["question_id"]


def test_concurrent_questions_from_many_threads(engine: Any) -> None:
    """Questions asked at once each get their own record and exactly one speech request."""
    bus, dashboard, _client = engine
    now = time.time()
    bus.publish(scene(now, obj(1, "bottle", "Heinz ketchup", "touching", now)))
    replies: list[dict[str, Any]] = []
    lock = threading.Lock()

    def ask() -> None:
        reply = dashboard.questions.ask("What am I touching?")
        with lock:
            replies.append(reply)

    threads = [threading.Thread(target=ask) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({r["question_id"] for r in replies}) == 12
    assert len(spoken(bus)) == 12


def test_result_arriving_before_mapping_is_not_lost() -> None:
    """storage may answer before ask() has mapped the lookup; the answer still lands."""
    published: list[Any] = []
    holder: dict[str, Any] = {}

    def publish(msg: Any) -> None:
        published.append(msg)
        if isinstance(msg, LastSeenQuery):  # storage answers synchronously, inside submit()
            holder["last_seen"].on_result(
                LastSeenResult(time.time(), msg.request_id, "found", "Keys, just now.",
                               time.time(), "keys", [])
            )

    last_seen = LastSeenService(publish)
    holder["last_seen"] = last_seen
    service = QuestionService(publish, last_seen, objects=list, scene_age=lambda: None,
                              history_running=lambda: True)
    record = service.ask("Find my keys")
    assert record["status"] == "answered" and record["answer"] == "Keys, just now."
    assert not [m for m in published if isinstance(m, SpeakRequest)]


# Input and availability.


def test_invalid_and_standalone_requests() -> None:
    """Empty/oversized inputs are 422, and a dashboard with no engine says 503."""
    bus = TestBus()
    client = TestClient(create_app(register(bus, serve=False).state))
    for text in ("", "   ", "x" * 501):
        assert client.post("/api/question", json={"text": text}).status_code == 422
    standalone = TestClient(create_app(DashboardState()))
    reply = standalone.post("/api/question", json={"text": "What do you see?"})
    assert reply.status_code == 503
    assert reply.json()["detail"] == "Questions require the running app."
    assert standalone.get("/api/state").json()["capabilities"]["questions"] is False
    assert client.get("/api/question/unknown").status_code == 404
