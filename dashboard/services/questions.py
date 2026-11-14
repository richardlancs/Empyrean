"""Questions from the page (typed or browser speech recognition), answered over the bus.

The route calls ask() and get(); neither blocks on the camera, a model, the
database or the speaker.

- Every question that is not an explicit history question is published as a
  SceneQuestion. namer/ answers it from the current camera view with Grok and
  speaks the answer itself (a SpeakRequest with source "namer"); the dashboard
  shows that answer and does not speak it again. Only one scene question is
  outstanding at a time, so the next namer answer belongs to it: a second
  question meanwhile is told to wait. If namer is not running, or no answer
  arrives within SCENE_ANSWER_TIMEOUT_SECONDS, the question is unavailable.
- History questions ("Where did I last touch the keys?") go through
  LastSeenService, which publishes a LastSeenQuery with a request_id. The
  question stays "looking_up" until storage's LastSeenResult with that id
  arrives. storage/ speaks its own answer, so the dashboard does not speak it
  again. If storage is not running or never answers, the answer says history is
  unavailable (never "not found") and the dashboard speaks that itself.

"speech_requested" only means a SpeakRequest was published. Whether audio
spoke it, and on what device, is reported separately by SpeechStatus.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from config import LAST_SEEN_TIMEOUT_SECONDS, QUESTION_TIMEOUT_SECONDS
from contracts import SceneQuestion, SpeakRequest
from dashboard.questions import (
    HISTORY_UNAVAILABLE_ANSWER,
    SCENE_BUSY_ANSWER,
    SCENE_PENDING_ANSWER,
    SCENE_UNAVAILABLE_ANSWER,
    parse_question,
)
from dashboard.services.last_seen import LastSeenService, QueryRejected

MAX_QUESTION_CHARS = 500  # main's /api/question limit
MAX_KEPT = 32  # questions kept for polling and for other open pages
RECENT_IN_STATE = 5  # newest questions sent to every page over /ws
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")
# namer/ bounds each Grok call by QUESTION_TIMEOUT_SECONDS; wait longer than that
# before giving up, reusing the dashboard's existing wait for storage answers.
SCENE_ANSWER_TIMEOUT_SECONDS = LAST_SEEN_TIMEOUT_SECONDS
assert SCENE_ANSWER_TIMEOUT_SECONDS > QUESTION_TIMEOUT_SECONDS


class QuestionRejected(Exception):
    """A question that was not accepted; status_code says which HTTP error fits."""

    def __init__(self, status_code: int, message: str) -> None:
        """Keep the HTTP status and a plain message for the page."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def clean_question(text: str) -> str:
    """Return the question trimmed with whitespace collapsed; raise if unusable."""
    if not isinstance(text, str):
        raise QuestionRejected(422, "The question must be text.")
    text = _SPACES.sub(" ", _CONTROL.sub(" ", text)).strip()
    if not text:
        raise QuestionRejected(422, "Please enter a question.")
    if len(text) > MAX_QUESTION_CHARS:
        raise QuestionRejected(422, f"Keep the question under {MAX_QUESTION_CHARS} characters.")
    return text


class QuestionService:
    """Route page questions to namer (scene) or storage (history) and track answers."""

    def __init__(
        self,
        publish: Callable[[Any], None] | None,
        last_seen: LastSeenService,
        *,
        scene_running: Callable[[], bool],
        history_running: Callable[[], bool],
        clock: Callable[[], float] = time.time,
        scene_timeout: float = SCENE_ANSWER_TIMEOUT_SECONDS,
    ) -> None:
        """publish is bus.publish, or None when the dashboard runs without the engine.

        scene_running and history_running say whether namer/ and storage/ are
        running in this launch.
        """
        self._publish = publish
        self._last_seen = last_seen
        self._scene_running = scene_running
        self._history_running = history_running
        self._clock = clock
        self._scene_timeout = scene_timeout
        self._pending_scene: str | None = None  # question_id waiting for namer
        self._late_scene_answers = 0  # namer answers still due for timed-out questions
        self._lock = threading.Lock()
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._by_lookup: dict[str, str] = {}  # last-seen request_id -> question_id
        self._listeners: list[Callable[[], None]] = []
        last_seen.add_listener(self._on_lookup_changed)

    @property
    def available(self) -> bool:
        """True when answers can be spoken and history reached over a bus."""
        return self._publish is not None

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Call listener after a question is asked or answered."""
        with self._lock:
            self._listeners.append(listener)

    def ask(self, text: str) -> dict[str, Any]:
        """Accept one question and return its record. Raises QuestionRejected."""
        if self._publish is None:
            raise QuestionRejected(503, "Questions require the running app.")
        question = clean_question(text)
        parsed = parse_question(question)
        now = self._clock()
        record: dict[str, Any] = {
            "question_id": uuid.uuid4().hex,
            "text": question,
            "intent": parsed.intent,
            "target": parsed.target or None,
            "status": "answered",
            "answer": None,
            "answered_by": None,  # "dashboard", "namer" or "storage"
            "speech_requested": False,
            "history_status": None,  # found | not_found | unavailable, for history only
            "history_request_id": None,
            "detail": "",
            "asked_at": now,
            "answered_at": None,
        }
        self.expire()
        with self._lock:
            self._records[record["question_id"]] = record
            while len(self._records) > MAX_KEPT:
                old_id, _old = self._records.popitem(last=False)
                self._by_lookup = {k: v for k, v in self._by_lookup.items() if v != old_id}
                if self._pending_scene == old_id:
                    self._pending_scene = None
        if parsed.intent == "history":
            speak_now = self._ask_history(record, parsed.target)
        else:
            speak_now = self._ask_scene(record, question)
        with self._lock:
            reply = dict(record)
        if speak_now:
            self._speak(reply["answer"])
        self._notify()
        return reply

    def get(self, question_id: str) -> dict[str, Any] | None:
        """Return a copy of one question's record, or None if unknown."""
        self._last_seen.expire()  # a lookup that timed out is finished on read too
        self.expire()
        with self._lock:
            record = self._records.get(question_id)
            return dict(record) if record else None

    def view(self) -> dict[str, Any]:
        """The newest questions, newest first, for every open page."""
        with self._lock:
            recent = [dict(r) for r in reversed(self._records.values())][:RECENT_IN_STATE]
        return {"available": self.available, "recent": recent}

    def on_answer(self, msg: SpeakRequest) -> None:
        """Bus handler: a namer answer finishes the scene question waiting for it."""
        if msg.source != "namer":
            return
        now = self._clock()
        with self._lock:
            if self._late_scene_answers:
                self._late_scene_answers -= 1  # belongs to a question that already timed out
                return
            record = self._records.get(self._pending_scene or "")
            self._pending_scene = None
            if record is None or record["status"] != "looking_up":
                return
            # namer spoke this sentence itself; the dashboard only shows it.
            record.update(
                status="answered",
                answer=msg.text,
                answered_by="namer",
                speech_requested=False,
                detail="",
                answered_at=now,
            )
        self._notify()

    def expire(self) -> bool:
        """Finish a scene question namer did not answer in time; True if one changed."""
        now = self._clock()
        with self._lock:
            record = self._records.get(self._pending_scene or "")
            if record is None or now - record["asked_at"] <= self._scene_timeout:
                return False
            self._pending_scene = None
            self._late_scene_answers += 1
            # Nothing is spoken: namer may still answer late and speak for itself.
            record.update(
                status="unavailable",
                answer=SCENE_UNAVAILABLE_ANSWER,
                answered_by="dashboard",
                speech_requested=False,
                detail="No answer from the scene question worker in time",
                answered_at=now,
            )
        self._notify()
        return True

    # Internals.

    def _answer_now(self, record: dict[str, Any], answer: str, now: float) -> None:
        """Finish a question the dashboard answers and speaks itself."""
        record.update(
            status="answered",
            answer=answer,
            answered_by="dashboard",
            speech_requested=True,
            answered_at=now,
        )

    def _ask_scene(self, record: dict[str, Any], question: str) -> bool:
        """Send a scene question to namer, or answer at once that it cannot be.

        Returns True only when the caller must speak an immediate answer.
        """
        now = self._clock()
        running = self._scene_running()
        with self._lock:
            if not running:
                self._answer_now(record, SCENE_UNAVAILABLE_ANSWER, now)
                record.update(status="unavailable", detail="Namer is not running in this launch")
                return True
            if self._pending_scene is not None:
                self._answer_now(record, SCENE_BUSY_ANSWER, now)
                record.update(status="unavailable", detail="Another question is still being answered")
                return True
            self._pending_scene = record["question_id"]
            record.update(status="looking_up", answer=SCENE_PENDING_ANSWER, detail="Waiting for namer")
        assert self._publish is not None  # ask() refuses when there is no bus
        self._publish(SceneQuestion(ts=now, text=question))
        return False

    def _ask_history(self, record: dict[str, Any], target: str) -> bool:
        """Send a history question to storage, or answer honestly that it cannot be.

        The record is already stored, so a fast LastSeenResult finds it. Returns
        True only when the caller must speak an immediate "unavailable" answer;
        lookups that finish later are spoken by storage or _on_lookup_changed.
        """
        now = self._clock()
        reason = "Storage is not running in this launch"
        if self._history_running():
            with self._lock:
                record.update(
                    status="looking_up",
                    answer=f"Looking up the last touch of {target}…",
                    detail="Waiting for storage",
                )
            try:
                request_id = self._last_seen.submit(target)
            except QueryRejected as exc:
                reason = exc.message
            else:
                with self._lock:
                    record["history_request_id"] = request_id
                    self._by_lookup[request_id] = record["question_id"]
                # storage may already have answered before the mapping existed.
                self._on_lookup_changed()
                return False
        with self._lock:
            self._answer_now(record, HISTORY_UNAVAILABLE_ANSWER, now)
            record.update(status="unavailable", history_status="unavailable", detail=reason)
        return True

    def _on_lookup_changed(self) -> None:
        """LastSeenService listener: finish questions whose lookup has finished."""
        with self._lock:
            waiting = [
                (lookup_id, question_id)
                for lookup_id, question_id in self._by_lookup.items()
                if self._records.get(question_id, {}).get("status") == "looking_up"
            ]
        speak: list[str] = []
        changed = False
        for lookup_id, question_id in waiting:
            result = self._last_seen.get(lookup_id)
            if result is not None and result["status"] == "pending":
                continue
            now = self._clock()
            with self._lock:
                record = self._records.get(question_id)
                if record is None or record["status"] != "looking_up":
                    continue
                self._by_lookup.pop(lookup_id, None)
                if result is not None and result["answer"]:
                    # storage spoke this exact sentence before publishing the result.
                    record.update(
                        status="unavailable" if result["status"] == "unavailable" else "answered",
                        answer=result["answer"],
                        answered_by="storage",
                        speech_requested=False,
                        history_status=result["status"],
                        detail=result["detail"],
                        answered_at=now,
                    )
                else:
                    # Timed out or forgotten: storage never answered, so nothing was spoken.
                    record.update(
                        status="unavailable",
                        answer=HISTORY_UNAVAILABLE_ANSWER,
                        answered_by="dashboard",
                        speech_requested=True,
                        history_status="unavailable",
                        detail=result["detail"] if result else "The lookup expired",
                        answered_at=now,
                    )
                    speak.append(HISTORY_UNAVAILABLE_ANSWER)
                changed = True
        for text in speak:
            self._speak(text)
        if changed:
            self._notify()

    def _speak(self, text: str) -> None:
        """Ask audio/ to speak one answer (an in-memory enqueue)."""
        if self._publish is not None:
            self._publish(
                SpeakRequest(ts=self._clock(), text=text, priority="normal", source="dashboard")
            )

    def _notify(self) -> None:
        """Tell listeners a question changed."""
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener()
