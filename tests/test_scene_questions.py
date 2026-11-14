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

    async def hang(self, client, frame, text) -> str:
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
    from dashboard.questions import ask_question
    from dashboard.state import DashboardState
    from fakes.namer.fake_namer import register

    bus = Bus()
    speaker = RecordingSpeaker()
    audio = AudioManager(lambda: speaker, RecordingAlarm())
    from contracts import SpeakRequest

    bus.subscribe(TouchEvent, audio.on_touch)
    bus.subscribe(SpeakRequest, audio.on_speak)
    namer = register(bus)
    try:
        bus.publish(
            TouchEvent(
                time.time(), 1, "bottle", "Heinz ketchup", "touch", (0, 0, 50, 50)
            )
        )
        assert settle(speaker, 1) == ["Heinz ketchup"]
        ask_question("Where are my keys?", DashboardState(), bus.publish, False)
        assert settle(speaker, 2)[-1] == "Demo answer: your keys are to your right."
    finally:
        namer.stop()
        bus.stop()
        audio.stop()
