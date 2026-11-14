"""Questions from the page: real contract messages, honest answers, correlated history.

Routing follows main's independent voice questions (SPEC 4.9.1): an explicit
"Where did I last touch X?" goes to storage as a correlated LastSeenQuery;
every other question is a SceneQuestion that namer answers and speaks itself.
Both run through QuestionService and POST/GET /api/question.
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
    SceneQuestion,
    SpeakRequest,
)
from dashboard import DashboardState, create_app, register
from dashboard.questions import (
    SCENE_BUSY_ANSWER,
    SCENE_PENDING_ANSWER,
    SCENE_UNAVAILABLE_ANSWER,
    parse_question,
)
from dashboard.services.last_seen import LastSeenService
from dashboard.services.questions import QuestionService


def spoken(bus: TestBus) -> list[str]:
    """Texts anyone asked audio to speak."""
    return [m.text for m in bus.published if isinstance(m, SpeakRequest)]


def spoken_by_dashboard(published: list[Any]) -> list[str]:
    """Texts the dashboard itself asked audio to speak."""
    return [m.text for m in published if isinstance(m, SpeakRequest) and m.source == "dashboard"]


def scene_questions(published: list[Any]) -> list[SceneQuestion]:
    """SceneQuestions sent to namer."""
    return [m for m in published if isinstance(m, SceneQuestion)]


def namer_says(text: str) -> SpeakRequest:
    """namer's spoken answer to a scene question."""
    return SpeakRequest(time.time(), text, "normal", "namer")


@pytest.fixture
def engine() -> tuple[TestBus, Any, TestClient]:
    """A dashboard registered on a test bus, with storage and namer counted as running."""
    bus = TestBus()
    dashboard = register(bus, serve=False)
    return bus, dashboard, TestClient(create_app(dashboard.state))


# Routing (main's 4.9.1 rule).


@pytest.mark.parametrize(
    ("text", "intent", "target"),
    [
        ("What can you see?", "scene", ""),
        ("What am I touching?", "scene", ""),
        ("Where are my keys?", "scene", ""),
        ("Find my phone.", "scene", ""),
        ("Sing a song", "scene", ""),
        ("Where did I last touch the bottle?", "history", "bottle"),
        ("Where did I last touch my keys", "history", "keys"),
        ("When did I last see my phone?", "history", "phone"),
    ],
)
def test_parse_question(text: str, intent: str, target: str) -> None:
    """Only explicit last-touch questions go to history; everything else asks the view."""
    parsed = parse_question(text)
    assert (parsed.intent, parsed.target) == (intent, target)


# Scene questions (answered by namer).


def test_scene_question_goes_to_namer_and_its_answer_is_shown_not_repeated(engine: Any) -> None:
    """The question is published as a SceneQuestion; namer's spoken answer is shown once."""
    bus, dashboard, client = engine
    reply = client.post("/api/question", json={"text": "Where are my keys?"})
    assert reply.status_code == 202
    body = reply.json()
    assert body["intent"] == "scene" and body["status"] == "looking_up"
    assert body["answer"] == SCENE_PENDING_ANSWER
    assert [q.text for q in scene_questions(bus.published)] == ["Where are my keys?"]
    assert spoken(bus) == []  # "Checking…" is shown, not spoken
    bus.publish(namer_says("Your keys are on the table to your left."))
    done = client.get(f"/api/question/{body['question_id']}").json()
    assert done["status"] == "answered" and done["answered_by"] == "namer"
    assert done["answer"] == "Your keys are on the table to your left."
    assert done["speech_requested"] is False
    # Only namer's own SpeakRequest: the dashboard never repeats it.
    assert spoken(bus) == ["Your keys are on the table to your left."]
    recent = dashboard.state.snapshot()["questions"]["recent"]
    assert recent[0]["question_id"] == body["question_id"] and recent[0]["status"] == "answered"


def test_a_second_scene_question_while_waiting_is_told_to_wait(engine: Any) -> None:
    """One scene question at a time, so namer's next answer is known to be the first one's."""
    bus, _dashboard, client = engine
    first = client.post("/api/question", json={"text": "What can you see?"}).json()
    second = client.post("/api/question", json={"text": "What am I holding?"}).json()
    assert len(scene_questions(bus.published)) == 1
    assert second["status"] == "unavailable" and second["answer"] == SCENE_BUSY_ANSWER
    assert spoken_by_dashboard(bus.published) == [SCENE_BUSY_ANSWER]
    bus.publish(namer_says("A desk with a laptop."))
    assert client.get(f"/api/question/{first['question_id']}").json()["answer"] == "A desk with a laptop."
    assert client.get(f"/api/question/{second['question_id']}").json()["answer"] == SCENE_BUSY_ANSWER


def test_other_speech_does_not_answer_a_scene_question(engine: Any) -> None:
    """Only a SpeakRequest from namer finishes a scene question."""
    bus, _dashboard, client = engine
    body = client.post("/api/question", json={"text": "What can you see?"}).json()
    bus.publish(SpeakRequest(time.time(), "Bottle, 2 minutes ago.", "normal", "storage"))
    bus.publish(SpeakRequest(time.time(), "Something else.", "normal", "dashboard"))
    assert client.get(f"/api/question/{body['question_id']}").json()["status"] == "looking_up"


def test_namer_not_started_answers_unavailable_at_once() -> None:
    """With namer not running in this launch, a scene question is unavailable and spoken once."""
    bus = TestBus()
    dashboard = register(bus, serve=False)
    bus.publish(ModuleStatus(time.time(), "namer", "offline", "unknown", "Not started in this run"))
    client = TestClient(create_app(dashboard.state))
    body = client.post("/api/question", json={"text": "What can you see?"}).json()
    assert body["status"] == "unavailable" and body["answer"] == SCENE_UNAVAILABLE_ANSWER
    assert not scene_questions(bus.published)
    assert spoken(bus) == [SCENE_UNAVAILABLE_ANSWER]


def test_namer_that_never_answers_times_out_and_a_late_answer_is_not_misattributed() -> None:
    """A timed-out question is unavailable; namer's late answer does not land on the next one."""
    clock = [1000.0]
    published: list[Any] = []
    service = QuestionService(
        published.append, LastSeenService(published.append), scene_running=lambda: True,
        history_running=lambda: True, clock=lambda: clock[0], scene_timeout=8.0,
    )
    first = service.ask("What can you see?")
    clock[0] += 9.0
    timed_out = service.get(first["question_id"])
    assert timed_out is not None and timed_out["status"] == "unavailable"
    assert timed_out["answer"] == SCENE_UNAVAILABLE_ANSWER
    assert spoken_by_dashboard(published) == []  # namer may still speak late; never twice
    second = service.ask("What am I holding?")
    assert second["status"] == "looking_up" and len(scene_questions(published)) == 2
    service.on_answer(namer_says("A late answer to the first question."))
    assert service.get(second["question_id"])["status"] == "looking_up"  # type: ignore[index]
    service.on_answer(namer_says("You are holding a phone."))
    done = service.get(second["question_id"])
    assert done is not None and done["answer"] == "You are holding a phone."


def test_concurrent_scene_questions_from_many_threads(engine: Any) -> None:
    """Questions asked at once get their own records; only one reaches namer."""
    bus, dashboard, _client = engine
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
    assert len(scene_questions(bus.published)) == 1
    assert [r["status"] for r in replies].count("looking_up") == 1
    assert spoken_by_dashboard(bus.published) == [SCENE_BUSY_ANSWER] * 11


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
    body = client.post("/api/question", json={"text": "Where did I last touch my keys?"}).json()
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
        published.append, last_seen, scene_running=lambda: True,
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
    first = client.post("/api/question", json={"text": "Where did I last touch my keys?"}).json()
    second = client.post("/api/question", json={"text": "Where did I last touch my phone?"}).json()
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
    service = QuestionService(publish, last_seen, scene_running=lambda: True,
                              history_running=lambda: True)
    record = service.ask("Where did I last touch my keys?")
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
