"""Speech telemetry from the real audio manager and correlated answers from storage."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from audio.audio import AudioManager
from audio.backends import LogSpeaker
from contracts import (
    HazardEvent,
    LastSeenQuery,
    LastSeenResult,
    ModuleStatus,
    SpeakRequest,
    SpeechStatus,
    TouchEvent,
)
from fakes.storage.fake_store import FakeStore
from storage import db
from storage.last_seen import NOT_SEEN, UNAVAILABLE
from storage.writer import Store

BOX = (100.0, 80.0, 200.0, 240.0)


def wait_for(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    """Poll until predicate() is true or the timeout passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class GatedSpeaker:
    """Speaks until its gate opens or it is told to stop; declares itself real."""

    mode = "real"

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.started: list[str] = []

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        self.started.append(text)
        while not self.gate.is_set() and not should_stop():
            time.sleep(0.002)


class BrokenSpeaker:
    """A speech engine that raises while speaking."""

    mode = "real"

    def say(self, text: str, should_stop: Callable[[], bool]) -> None:
        raise OSError("device gone")


class Alarm:
    """Records plays; declares itself a real alarm."""

    duration = 0.0
    mode = "real"

    def __init__(self) -> None:
        self.plays = 0

    def play(self) -> None:
        self.plays += 1

    def close(self) -> None:
        pass


def _touch(object_id: int = 1, name: str = "Heinz ketchup") -> TouchEvent:
    return TouchEvent(time.time(), object_id, "bottle", name, "touch", BOX)


def _statuses(published: list[Any], speech_id: int | None = None) -> list[str]:
    return [
        m.status
        for m in published
        if isinstance(m, SpeechStatus) and (speech_id is None or m.speech_id == speech_id)
    ]


@pytest.fixture
def published() -> list[Any]:
    return []


def test_touch_speech_reports_queued_speaking_completed(published: list[Any]) -> None:
    """One phrase: queued, speaking, completed, all with the same id and mode real."""
    speaker = GatedSpeaker()
    manager = AudioManager(lambda: speaker, Alarm(), publish=published.append)
    try:
        manager.on_touch(_touch())
        assert wait_for(lambda: "speaking" in _statuses(published))
        speaker.gate.set()
        assert wait_for(lambda: "completed" in _statuses(published))
    finally:
        manager.stop()
    steps = [m for m in published if isinstance(m, SpeechStatus)]
    assert [m.status for m in steps] == ["queued", "speaking", "completed"]
    assert {m.speech_id for m in steps} == {steps[0].speech_id}
    # The factory is a lambda, so until the speaker exists the mode is not "real".
    assert steps[-1].mode == "real" and steps[-1].kind == "touch" and steps[-1].object_id == 1
    ready = [m for m in published if isinstance(m, ModuleStatus)]
    assert ready and ready[0].status == "active" and ready[0].mode == "real"


def test_hazard_interrupts_speech_and_still_plays_first(published: list[Any]) -> None:
    """The alarm plays at once; the speaking phrase ends interrupted; the hazard phrase follows."""
    speaker = GatedSpeaker()
    alarm = Alarm()
    manager = AudioManager(lambda: speaker, alarm, publish=published.append)
    try:
        manager.on_touch(_touch())
        assert wait_for(lambda: "speaking" in _statuses(published))
        touch_id = next(m.speech_id for m in published if isinstance(m, SpeechStatus))
        manager.on_hazard(HazardEvent(time.time(), "stairs_down", "grok", 0.9))
        assert alarm.plays == 1  # synchronously, before anything else
        assert wait_for(lambda: "interrupted" in _statuses(published, touch_id))
        assert wait_for(lambda: speaker.started[-1:] == ["Stop. Stairs."])
        speaker.gate.set()
        assert wait_for(
            lambda: any(
                isinstance(m, SpeechStatus) and m.kind == "hazard" and m.status == "completed"
                for m in published
            )
        )
    finally:
        manager.stop()
    interrupted = [m for m in published if isinstance(m, SpeechStatus) and m.status == "interrupted"]
    assert interrupted[0].speech_id == touch_id and "hazard" in interrupted[0].detail


def test_waiting_phrase_replaced_or_cut_by_hazard_reports_interrupted(published: list[Any]) -> None:
    """A phrase that never played is reported interrupted, never completed."""
    speaker = GatedSpeaker()
    manager = AudioManager(lambda: speaker, Alarm(), publish=published.append)
    try:
        manager.on_touch(_touch(1))
        assert wait_for(lambda: "speaking" in _statuses(published))
        manager.on_touch(_touch(2, "Starbucks cup"))  # waits in the one-item slot
        manager.on_touch(_touch(3, "Penguin paperback"))  # replaces it
        waiting = [m for m in published if isinstance(m, SpeechStatus) and m.object_id == 2]
        assert [m.status for m in waiting] == ["queued", "interrupted"]
        assert "Replaced" in waiting[-1].detail
        manager.on_hazard(HazardEvent(time.time(), "vehicle", "yolo", 0.9))
        third = [m for m in published if isinstance(m, SpeechStatus) and m.object_id == 3]
        assert [m.status for m in third] == ["queued", "interrupted"]
    finally:
        speaker.gate.set()
        manager.stop()


def test_log_only_speech_is_failed_not_completed(published: list[Any]) -> None:
    """When TTS cannot start, phrases are logged and reported failed with mode unavailable."""

    def no_tts() -> Any:
        raise RuntimeError("no voice")

    manager = AudioManager(no_tts, Alarm(), publish=published.append)
    try:
        manager.on_touch(_touch())
        assert wait_for(lambda: "failed" in _statuses(published))
    finally:
        manager.stop()
    final = [m for m in published if isinstance(m, SpeechStatus)][-1]
    assert final.mode == "unavailable" and "logged" in final.detail
    assert "completed" not in _statuses(published)
    status = next(m for m in published if isinstance(m, ModuleStatus))
    assert status.status == "degraded" and status.mode == "unknown"


def test_engine_error_reports_failed_and_degraded(published: list[Any]) -> None:
    """A speech engine that raises gives a failed phrase and a degraded audio module."""
    manager = AudioManager(BrokenSpeaker, Alarm(), publish=published.append)
    try:
        manager.on_touch(_touch())
        assert wait_for(lambda: "failed" in _statuses(published))
    finally:
        manager.stop()
    statuses = [m for m in published if isinstance(m, ModuleStatus)]
    assert [s.status for s in statuses] == ["active", "degraded"]
    assert "OSError" in statuses[-1].detail


def test_fake_audio_is_labelled_fake_never_real(capsys: pytest.CaptureFixture[str]) -> None:
    """fakes.audio publishes the same telemetry with mode fake."""
    from fakes.audio import register as fake_register

    class Bus:
        def __init__(self) -> None:
            self.published: list[Any] = []

        def subscribe(self, *_: Any) -> None:
            pass

        def publish(self, message: Any) -> None:
            self.published.append(message)

    bus = Bus()
    manager = fake_register(bus)
    try:
        manager.on_touch(_touch(name="Heinz"))
        assert wait_for(lambda: "completed" in _statuses(bus.published))
    finally:
        manager.stop()
    modes = {m.mode for m in bus.published if isinstance(m, SpeechStatus | ModuleStatus)}
    assert modes == {"fake"}


def test_old_audio_constructor_publishes_nothing() -> None:
    """AudioManager(speaker_factory, alarm) without publish behaves exactly as before."""
    speaker = GatedSpeaker()
    speaker.gate.set()
    manager = AudioManager(lambda: speaker, Alarm())
    try:
        manager.on_touch(_touch())
        assert wait_for(lambda: speaker.started == ["Heinz ketchup"])
    finally:
        manager.stop()
    assert manager._outbox == []


def test_log_speaker_declares_unavailable() -> None:
    """The logging stand-in is never labelled as real playback."""
    assert LogSpeaker.mode == "unavailable"


# Storage --------------------------------------------------------------------


class FakeConn:
    """Enough of a psycopg connection for Store: last_seen is patched separately."""

    closed = False
    broken = False

    def close(self) -> None:
        pass


def _store_with_rows(monkeypatch: pytest.MonkeyPatch, rows: dict[str, dict[str, Any]],
                     fail: set[str] | None = None) -> tuple[Store, list[Any]]:
    monkeypatch.setattr(db, "connect", lambda url: FakeConn())
    monkeypatch.setattr(db, "ensure_schema", lambda conn: None)

    def last_seen(conn: Any, text: str) -> dict[str, Any] | None:
        if fail and text in fail:
            raise RuntimeError("statement failed")
        return rows.get(text)

    monkeypatch.setattr(db, "last_seen", last_seen)
    published: list[Any] = []
    return Store(published.append, "postgresql://unused", status_publish=published.append), published


def _results(published: list[Any]) -> dict[str, LastSeenResult]:
    return {m.request_id: m for m in published if isinstance(m, LastSeenResult)}


def test_store_correlates_found_and_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each request_id gets its own answer, with the matching touch time and neighbours."""
    row = {"ts": time.time() - 240, "name": "Heinz ketchup", "class_label": "bottle",
           "neighbours": ["mug", "cereal box"]}
    store, published = _store_with_rows(monkeypatch, {"ketchup": row})
    try:
        store.on_last_seen_query(LastSeenQuery(time.time(), "ketchup", request_id="a"))
        store.on_last_seen_query(LastSeenQuery(time.time(), "umbrella", request_id="b"))
        assert wait_for(lambda: len(_results(published)) == 2)
    finally:
        store.stop()
    results = _results(published)
    assert results["a"].status == "found" and results["a"].matched_at == row["ts"]
    assert results["a"].label == "Heinz ketchup" and results["a"].neighbours == ["mug", "cereal box"]
    assert results["a"].answer == "Heinz ketchup, 4 minutes ago, next to mug and cereal box."
    assert results["b"].status == "not_found" and results["b"].matched_at is None
    # The spoken answers are unchanged and still go out first.
    spoken = [m.text for m in published if isinstance(m, SpeakRequest)]
    assert spoken == [results["a"].answer, NOT_SEEN]
    assert results["b"].answer == NOT_SEEN  # spoken and shown agree for a real miss
    status = [m for m in published if isinstance(m, ModuleStatus)]
    assert status[-1].status == "active"


def test_store_error_is_unavailable_never_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing statement gives status unavailable with no answer text."""
    store, published = _store_with_rows(monkeypatch, {}, fail={"keys"})
    try:
        store.on_last_seen_query(LastSeenQuery(time.time(), "keys", request_id="x"))
        assert wait_for(lambda: "x" in _results(published))
    finally:
        store.stop()
    result = _results(published)["x"]
    assert result.status == "unavailable" and result.matched_at is None
    spoken = [m.text for m in published if isinstance(m, SpeakRequest)]
    # What the wearer hears and what the page shows are the same sentence.
    assert spoken == [UNAVAILABLE] and result.answer == UNAVAILABLE


def test_store_without_url_is_unavailable_and_reports_offline() -> None:
    """No TIGER_DATABASE_URL: lookups are unavailable and storage says offline."""
    published: list[Any] = []
    store = Store(published.append, None, status_publish=published.append)
    try:
        store.on_last_seen_query(LastSeenQuery(time.time(), "keys", request_id="y"))
        assert wait_for(lambda: "y" in _results(published))
    finally:
        store.stop()
    assert _results(published)["y"].status == "unavailable"
    assert [m.text for m in published if isinstance(m, SpeakRequest)] == [UNAVAILABLE]
    assert _results(published)["y"].answer == UNAVAILABLE
    status = next(m for m in published if isinstance(m, ModuleStatus))
    assert status.status == "offline" and "TIGER_DATABASE_URL" in status.detail
    assert "postgresql" not in status.detail


def test_query_without_request_id_publishes_only_the_spoken_answer() -> None:
    """Old LastSeenQuery(ts, text): exactly one SpeakRequest, as before the redesign."""
    published: list[Any] = []
    store = Store(published.append, None)
    try:
        store.on_last_seen_query(LastSeenQuery(time.time(), "keys"))
        assert wait_for(lambda: len(published) == 1)
        time.sleep(0.05)
    finally:
        store.stop()
    assert len(published) == 1 and isinstance(published[0], SpeakRequest)


def test_fake_store_correlates_results() -> None:
    """The fake store answers with LastSeenResult for correlated queries too."""
    published: list[Any] = []
    store = FakeStore(published.append)
    store.on_touch_event(TouchEvent(time.time() - 65, 3, "book", "", "touch", BOX, ["laptop"]))
    store.on_last_seen_query(LastSeenQuery(time.time(), "book", request_id="q1"))
    store.on_last_seen_query(LastSeenQuery(time.time(), "zebra", request_id="q2"))
    results = _results(published)
    assert results["q1"].status == "found" and results["q1"].neighbours == ["laptop"]
    assert results["q2"].status == "not_found"
