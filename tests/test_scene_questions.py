"""Current-view Grok QA runs independently and reports unavailable inputs honestly."""

import asyncio
import json
import threading
import time

import httpx
import numpy as np

from contracts import FrameResult, SceneQuestion
from namer.questions import SceneQuestions


def test_question_uses_full_image_and_real_reply(monkeypatch) -> None:
    """Keys need not be detected or touched for Grok to answer from the image."""
    monkeypatch.setenv("GROK_API_KEY", "test-only")
    monkeypatch.setenv("GROK_MODEL", "test-model")
    bodies = []
    answers = []
    ready = threading.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"output_text": "Your keys are to your right."})

    def publish(msg) -> None:
        answers.append(msg)
        ready.set()

    worker = SceneQuestions(
        publish, lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond))
    )
    try:
        worker.on_frame(
            FrameResult(time.time(), 1, np.zeros((360, 640, 3), dtype=np.uint8))
        )
        worker.on_question(SceneQuestion(time.time(), "Where are my keys?"))
        assert ready.wait(2)
        assert answers[0].text == "Your keys are to your right."
        assert answers[0].source == "namer"
        content = bodies[0]["input"][0]["content"]
        assert content[0]["image_url"].startswith("data:image/jpeg;base64,")
        assert "Where are my keys?" in content[1]["text"]
        assert "not visible" in content[1]["text"]
    finally:
        worker.stop()


def test_missing_and_stale_frame_never_call_grok() -> None:
    """Absent or stale images cannot produce invented locations."""
    ready = threading.Event()
    answers = []

    def publish(msg) -> None:
        answers.append(msg)
        ready.set()

    def unexpected(request: httpx.Request) -> httpx.Response:
        raise AssertionError("No network call expected")

    worker = SceneQuestions(
        publish, lambda: httpx.AsyncClient(transport=httpx.MockTransport(unexpected))
    )
    try:
        for frame in (None, FrameResult(1, 1, None)):
            if frame:
                worker.on_frame(frame)
            ready.clear()
            worker.on_question(SceneQuestion(time.time(), "Where are my keys?"))
            assert ready.wait(2)
            assert "current camera view" in answers[-1].text
    finally:
        worker.stop()


def test_slow_question_does_not_block_frames_and_failure_is_spoken(monkeypatch) -> None:
    """Frame delivery continues during a failed call, and the user gets an answer."""
    monkeypatch.setenv("GROK_API_KEY", "test-only")
    monkeypatch.setenv("GROK_MODEL", "test-model")
    entered = threading.Event()
    release = threading.Event()
    ready = threading.Event()
    answers = []

    def respond(request: httpx.Request) -> httpx.Response:
        entered.set()
        release.wait(2)
        return httpx.Response(503)

    def publish(msg) -> None:
        answers.append(msg)
        ready.set()

    worker = SceneQuestions(
        publish, lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond))
    )
    try:
        worker.on_frame(
            FrameResult(time.time(), 1, np.zeros((360, 640, 3), dtype=np.uint8))
        )
        worker.on_question(SceneQuestion(time.time(), "Where are my keys?"))
        assert entered.wait(2)
        worker.on_frame(FrameResult(time.time(), 2, None))
        assert worker._frame.frame_id == 2
        release.set()
        assert ready.wait(2)
        assert "could not answer" in answers[0].text
    finally:
        release.set()
        worker.stop()


def test_question_timeout_is_spoken(monkeypatch) -> None:
    """A hung Grok call has a bounded timeout and an audible failure answer."""
    import namer.questions as module

    monkeypatch.setattr(module, "QUESTION_TIMEOUT_SECONDS", 0.02)
    ready = threading.Event()
    answers = []

    async def hang(self, client, frame, text, language="en") -> str:
        await asyncio.Event().wait()
        return "unreachable"

    def publish(msg) -> None:
        answers.append(msg)
        ready.set()

    monkeypatch.setattr(SceneQuestions, "_answer", hang)
    worker = SceneQuestions(publish)
    try:
        worker.on_frame(FrameResult(time.time(), 1, None))
        worker.on_question(SceneQuestion(time.time(), "Where are my keys?"))
        assert ready.wait(2)
        assert "could not answer" in answers[0].text
    finally:
        worker.stop()


def test_fake_pipeline_announces_touch_and_answers_independently() -> None:
    """Real bus wiring with a fake namer supports both paths without a camera."""
    from test_audio import RecordingAlarm, RecordingSpeaker, settle

    from app.bus import Bus
    from audio.audio import AudioManager
    from contracts import TouchEvent
    from dashboard import register as register_dashboard
    from fakes.namer.fake_namer import register

    bus = Bus()
    speaker = RecordingSpeaker()
    audio = AudioManager(lambda: speaker, RecordingAlarm())
    from contracts import SpeakRequest

    bus.subscribe(TouchEvent, audio.on_touch)
    bus.subscribe(SpeakRequest, audio.on_speak)
    namer = register(bus)
    dashboard = register_dashboard(bus, serve=False)
    try:
        bus.publish(
            TouchEvent(
                time.time(), 1, "bottle", "Heinz ketchup", "touch", (0, 0, 50, 50)
            )
        )
        assert settle(speaker, 1) == ["Heinz ketchup"]
        record = dashboard.questions.ask("Where are my keys?")
        assert record["status"] == "looking_up"
        assert settle(speaker, 2)[-1] == "Demo answer: your keys are to your right."
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            done = dashboard.questions.get(record["question_id"])
            if done and done["status"] != "looking_up":
                break
            time.sleep(0.01)
        assert done is not None and done["answered_by"] == "namer"
        assert done["answer"] == "Demo answer: your keys are to your right."
    finally:
        namer.stop()
        bus.stop()
        audio.stop()


def _status(language: str):
    from contracts import VoiceStatus

    return VoiceStatus(time.time(), "active", "x", "X", "enhanced", language=language)


def test_non_english_question_asks_grok_to_answer_in_that_language(monkeypatch) -> None:
    """The instruction gains "Answer in <language>." only outside English."""
    from namer.questions import INSTRUCTION, instruction_for

    assert instruction_for("en") == INSTRUCTION
    assert instruction_for("fr").endswith("Answer in French. Question: ")
    monkeypatch.setenv("GROK_API_KEY", "test-only")
    monkeypatch.setenv("GROK_MODEL", "test-model")
    bodies = []
    ready = threading.Event()

    def respond(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"output_text": "Tes clés sont à droite."})

    worker = SceneQuestions(
        lambda msg: ready.set(),
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    try:
        worker.on_voice_status(_status("fr"))
        worker.on_frame(
            FrameResult(time.time(), 1, np.zeros((360, 640, 3), dtype=np.uint8))
        )
        worker.on_question(SceneQuestion(time.time(), "Where are my keys?"))
        assert ready.wait(2)
        text = bodies[0]["input"][0]["content"][1]["text"]
        assert text == instruction_for("fr") + "Where are my keys?"
    finally:
        worker.stop()


def test_fixed_answers_in_hindi_and_english() -> None:
    """Namer's own answers come from the fixed table; English wording is unchanged."""
    from namer.questions import FIXED_ANSWERS, fixed_answer

    assert (
        fixed_answer("busy", "en") == "Please wait for the current question to finish."
    )
    assert fixed_answer("no_view", "en") == "I do not have a current camera view."
    assert fixed_answer("failed", "en") == (
        "I could not answer that right now. Please try again."
    )
    assert fixed_answer("no_view", "hi") == "मेरे पास अभी कैमरे का दृश्य नहीं है।"
    assert fixed_answer("failed", "xx") == fixed_answer("failed", "en")
    assert set(FIXED_ANSWERS) == {"en", "zh", "es", "fr", "hi"}
    assert all(set(t) == set(FIXED_ANSWERS["en"]) for t in FIXED_ANSWERS.values())

    answers = []
    ready = threading.Event()

    def publish(msg) -> None:
        answers.append(msg)
        ready.set()

    worker = SceneQuestions(publish)
    try:
        worker.on_voice_status(_status("hi"))
        worker.on_question(SceneQuestion(time.time(), "Where are my keys?"))
        assert ready.wait(2)
        assert answers[0].text == fixed_answer("no_view", "hi")
    finally:
        worker.stop()


def test_question_language_is_captured_when_asked(monkeypatch) -> None:
    """A switch while a question is in flight does not change its answer language."""
    import namer.questions as module

    monkeypatch.setattr(module, "QUESTION_TIMEOUT_SECONDS", 0.2)
    entered = threading.Event()
    ready = threading.Event()
    answers = []
    seen_languages = []

    async def hang(self, client, frame, text, language) -> str:
        seen_languages.append(language)
        entered.set()
        await asyncio.Event().wait()
        return "unreachable"

    def publish(msg) -> None:
        answers.append(msg)
        ready.set()

    monkeypatch.setattr(SceneQuestions, "_answer", hang)
    worker = SceneQuestions(publish)
    try:
        worker.on_voice_status(_status("es"))
        worker.on_frame(FrameResult(time.time(), 1, None))
        worker.on_question(SceneQuestion(time.time(), "Where are my keys?"))
        assert entered.wait(2)
        worker.on_voice_status(_status("en"))
        assert ready.wait(2)
        assert seen_languages == ["es"]
        assert answers[0].text == module.fixed_answer("failed", "es")
    finally:
        worker.stop()


def test_fake_namer_speaks_the_active_language() -> None:
    """The fake namer translates its class label into spoken_name outside English."""
    from contracts import NameRequest, SpeakRequest
    from fakes.namer.fake_namer import FakeNamer

    results = []
    done = threading.Event()

    def publish(msg) -> None:
        results.append(msg)
        if len(results) == 4:
            done.set()

    fake = FakeNamer(publish, seed=1, delay_range=(0.0, 0.01))
    try:
        fake.on_name_request(NameRequest(time.time(), 1, "bottle", b""))
        fake.on_voice_status(_status("es"))
        fake.on_name_request(NameRequest(time.time(), 1, "bottle", b""))
        fake.on_name_request(NameRequest(time.time(), 2, "keyboard", b""))
        fake.on_question(SceneQuestion(time.time(), "Where are my keys?"))
        assert done.wait(2)
    finally:
        fake.stop()
    names = [r for r in results if not isinstance(r, SpeakRequest)]
    [answer] = [r for r in results if isinstance(r, SpeakRequest)]
    assert [(r.name, r.spoken_name, r.language) for r in names] == [
        ("Heinz ketchup", "", ""),
        ("Heinz ketchup", "botella", "es"),
        ("keyboard", "teclado", "es"),
    ]
    assert answer.text.startswith("Respuesta de demostración")
