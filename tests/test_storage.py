"""Smoke tests for storage/ (SPEC.md section 4.10)."""

from __future__ import annotations

import logging
import os
import re
import socket
import time
import uuid
from typing import Any

import psycopg
import pytest

from contracts import LastSeenResult, VoiceStatus
from contracts.languages import LANGUAGES
from storage import db
from storage._deps import HazardEvent, LastSeenQuery, SpeakRequest, TouchEvent
from storage.last_seen import (
    NOT_SEEN,
    NOT_SEEN_BY_LANGUAGE,
    UNAVAILABLE,
    UNAVAILABLE_BY_LANGUAGE,
    format_answer,
    not_seen,
    unavailable,
)
from storage.writer import QUEUE_MAX_ITEMS, Store

UNREACHABLE_URL = "postgresql://127.0.0.1:1/x"
NOW = 1_800_000_000.0


def _row(age: float, name: str = "Heinz ketchup", neighbours: list[str] | None = None,
         class_label: str = "bottle") -> dict[str, Any]:
    """Build a last_seen-shaped row of the given age."""
    return {"ts": NOW - age, "name": name, "class_label": class_label,
            "neighbours": neighbours or []}


def _touch(i: int = 0) -> TouchEvent:
    """Build a scripted TouchEvent."""
    return TouchEvent(ts=NOW + i, object_id=i, class_label="bottle", name="Heinz ketchup",
                      kind="touch", box=(300.0, 160.0, 340.0, 200.0), neighbours=["mug"])


def _wait_for(cond: Any, timeout: float = 3.0) -> bool:
    """Poll cond() until true or timeout."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


# 1. format_answer --------------------------------------------------------

@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, "just now"),
        (59.9, "just now"),
        (60, "1 minute ago"),
        (4 * 60 + 30, "4 minutes ago"),
        (3599, "59 minutes ago"),
        (3600, "1 hour ago"),
        (2 * 3600 + 59, "2 hours ago"),
        (-5, "just now"),
    ],
)
def test_format_answer_time_buckets(age: float, expected: str) -> None:
    """Each age bucket renders as SPEC 4.10 describes."""
    assert format_answer(_row(age), NOW) == f"Heinz ketchup, {expected}."


@pytest.mark.parametrize(
    ("neighbours", "suffix"),
    [
        ([], "."),
        (["mug"], ", next to mug."),
        (["mug", "cereal box"], ", next to mug and cereal box."),
        (["mug", "cereal box", "spoon"], ", next to mug, cereal box and spoon."),
    ],
)
def test_format_answer_neighbours(neighbours: list[str], suffix: str) -> None:
    """Zero to three neighbours are joined naturally."""
    assert format_answer(_row(240, neighbours=neighbours), NOW) == f"Heinz ketchup, 4 minutes ago{suffix}"


def test_format_answer_spec_example_and_fallbacks() -> None:
    """Spec example, class_label fallback, and no match."""
    assert (format_answer(_row(240, neighbours=["mug", "cereal box"]), NOW)
            == "Heinz ketchup, 4 minutes ago, next to mug and cereal box.")
    assert format_answer(_row(10, name=""), NOW) == "bottle, just now."
    assert format_answer(None, NOW) == "I have not seen that."
    assert NOT_SEEN == "I have not seen that."


# 2. unreachable database -------------------------------------------------

def _feed_100(store: Store) -> float:
    """Send 50 touch and 50 hazard events; return the slowest handler call in seconds."""
    worst = 0.0
    for i in range(100):
        ev: Any = _touch(i) if i % 2 else HazardEvent(
            ts=NOW + i, type="vehicle", source="yolo", confidence=0.9)
        t0 = time.perf_counter()
        if i % 2:
            store.on_touch_event(ev)
        else:
            store.on_hazard_event(ev)
        worst = max(worst, time.perf_counter() - t0)
    return worst


def test_unreachable_db_never_blocks_and_warns_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """100 events with the DB down: each call is fast, exactly one warning, nothing raised.

    The connection failure is mocked so this is deterministic on every OS. How
    long a real refused or silent connection takes is tested separately below.
    """
    attempts: list[str] = []

    def refuse(url: str) -> Any:
        attempts.append(url)
        raise psycopg.OperationalError("connection refused (mocked)")

    monkeypatch.setattr(db, "connect", refuse)
    published: list[Any] = []
    caplog.set_level(logging.WARNING, logger="storage")
    store = Store(published.append, UNREACHABLE_URL)
    try:
        worst = _feed_100(store)
        assert worst < 0.005, f"slowest call {worst * 1000:.2f} ms"
        assert _wait_for(lambda: store.dropped == 100)

        store.on_last_seen_query(LastSeenQuery(ts=NOW, text="ketchup"))
        assert _wait_for(lambda: len(published) == 1)
    finally:
        store.stop()
    # One connect attempt covers all 101 items: retries wait RETRY_INTERVAL_SECONDS.
    assert len(attempts) == 1
    assert store.written == 0
    warnings = [r for r in caplog.records if r.name == "storage" and r.levelno == logging.WARNING]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert "OperationalError" in warnings[0].getMessage()
    assert "127.0.0.1" not in caplog.text and "postgresql://" not in caplog.text
    answer = published[0]
    assert isinstance(answer, SpeakRequest)
    # Database down: say so, never "I have not seen that."
    assert (answer.text, answer.priority, answer.source) == (UNAVAILABLE, "normal", "storage")


@pytest.fixture
def silent_server() -> Any:
    """A local TCP port that accepts connections and never answers, like a hung database."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)  # the kernel completes the handshake; nothing is ever read or sent
    try:
        yield f"postgresql://u@127.0.0.1:{srv.getsockname()[1]}/x?sslmode=disable"
    finally:
        srv.close()


def test_real_connect_timeout_is_bounded(silent_server: str) -> None:
    """A real connect to a silent server gives up after about CONNECT_TIMEOUT_SECONDS."""
    t0 = time.monotonic()
    with pytest.raises(psycopg.OperationalError):
        db.connect(silent_server)
    elapsed = time.monotonic() - t0
    assert db.CONNECT_TIMEOUT_SECONDS - 0.5 <= elapsed < db.CONNECT_TIMEOUT_SECONDS + 3


def test_hung_db_does_not_block_handlers(
    silent_server: str, caplog: pytest.LogCaptureFixture
) -> None:
    """While the worker sits in a real connect timeout, handlers still return at once."""
    caplog.set_level(logging.WARNING, logger="storage")
    published: list[Any] = []
    store = Store(published.append, silent_server)
    try:
        worst = _feed_100(store)  # the worker is stuck connecting for most of this
        # 50 ms, not 5 ms: with the worker busy in a real connect, a handler can
        # wait one GIL switch interval (5 ms by default) just to run. Blocking on
        # the DB would cost the whole CONNECT_TIMEOUT_SECONDS, far above this.
        assert worst < 0.05, f"slowest call {worst * 1000:.2f} ms"
        store.on_last_seen_query(LastSeenQuery(ts=NOW, text="ketchup"))
        # Wait well past the connect timeout, never just up to it.
        settle = db.CONNECT_TIMEOUT_SECONDS + 5
        assert _wait_for(lambda: store.dropped == 100 and len(published) == 1, settle)
    finally:
        store.stop()
    warnings = [r for r in caplog.records if r.name == "storage" and r.levelno == logging.WARNING]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert "127.0.0.1" not in caplog.text and "postgresql://" not in caplog.text
    assert published[0].text == UNAVAILABLE


# 3. queue full -----------------------------------------------------------

def test_queue_full_drops_instead_of_raising() -> None:
    """Past QUEUE_MAX_ITEMS, events are counted and dropped, not raised."""
    store = Store(lambda _m: None, UNREACHABLE_URL, start=False)
    for i in range(QUEUE_MAX_ITEMS + 5):
        store.on_touch_event(_touch(i))
    store.on_last_seen_query(LastSeenQuery(ts=NOW, text="mug"))
    assert store.dropped == 6
    store.stop()


# 4. LIKE escaping --------------------------------------------------------

def _like_to_regex(pattern: str, escape: str = db.LIKE_ESCAPE) -> re.Pattern[str]:
    """Translate a SQL LIKE pattern with an escape char into a case-insensitive regex."""
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == escape and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "%" else "." if ch == "_" else re.escape(ch))
        i += 1
    return re.compile("".join(out), re.IGNORECASE | re.DOTALL)


def test_like_escaping() -> None:
    """User % and _ are literal; the escape char itself is escaped."""
    assert db.escape_like("50%") == "50\\%"
    assert db.escape_like("a_b") == "a\\_b"
    assert db.escape_like("c:\\x") == "c:\\\\x"
    pat = _like_to_regex(db.contains_pattern("50%"))
    assert pat.fullmatch("Juice 50% off")
    assert not pat.fullmatch("500 ml water")
    assert not pat.fullmatch("50 cents")
    under = _like_to_regex(db.contains_pattern("a_b"))
    assert under.fullmatch("x A_B y") and not under.fullmatch("axb")


# 5. live round trip ------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("TIGER_DATABASE_URL"), reason="TIGER_DATABASE_URL not set")
def test_live_round_trip() -> None:
    """Insert a touch row and find it again case-insensitively."""
    url = os.environ["TIGER_DATABASE_URL"]
    tag = uuid.uuid4().hex[:8]
    session = f"pytest-{tag}"
    name = f"Pytest Ketchup {tag}"
    with db.connect(url) as conn:
        db.ensure_schema(conn)
        try:
            cx, cy = db.box_centre_fraction((300.0, 160.0, 340.0, 200.0))
            db.insert_touch(conn, {"ts": time.time(), "session_id": session, "object_id": 7,
                                   "class_label": "bottle", "name": name, "kind": "touch",
                                   "cx": cx, "cy": cy, "neighbours": ["mug", "cereal box"]})
            row = db.last_seen(conn, name.lower())
            assert row is not None and row["name"] == name
            assert list(row["neighbours"]) == ["mug", "cereal box"]
            assert format_answer(row, time.time()).startswith(f"{name}, just now")
        finally:
            conn.execute("DELETE FROM touch_events WHERE session_id = %s", (session,))


# 6. languages ------------------------------------------------------------

def _voice(language: str) -> VoiceStatus:
    """Build a VoiceStatus for a voice of the given language."""
    return VoiceStatus(ts=NOW, state="active", active_voice="x", label="X",
                       quality="compact", language=language)


# Expected sentences per language: (age bucket answers, neighbour answers).
_AGE_CASES = [(0, "now"), (60, "one_min"), (240, "min"), (3600, "one_hour"), (7300, "hour")]
_EXPECTED_AGES: dict[str, dict[str, str]] = {
    "en": {"now": "just now", "one_min": "1 minute ago", "min": "4 minutes ago",
           "one_hour": "1 hour ago", "hour": "2 hours ago"},
    "zh": {"now": "刚才", "one_min": "1分钟前", "min": "4分钟前",
           "one_hour": "1小时前", "hour": "2小时前"},
    "es": {"now": "hace un momento", "one_min": "hace 1 minuto", "min": "hace 4 minutos",
           "one_hour": "hace 1 hora", "hour": "hace 2 horas"},
    "fr": {"now": "à l'instant", "one_min": "il y a 1 minute", "min": "il y a 4 minutes",
           "one_hour": "il y a 1 heure", "hour": "il y a 2 heures"},
    "hi": {"now": "अभी-अभी", "one_min": "1 मिनट पहले", "min": "4 मिनट पहले",
           "one_hour": "1 घंटा पहले", "hour": "2 घंटे पहले"},
}
# Neighbours cup / cup, bowl / cup, bowl, spoon around the bottle, 4 minutes ago.
_EXPECTED_FULL: dict[str, list[str]] = {
    "en": ["bottle, 4 minutes ago, next to cup.",
           "bottle, 4 minutes ago, next to cup and bowl.",
           "bottle, 4 minutes ago, next to cup, bowl and spoon."],
    "zh": ["瓶子，4分钟前，在杯子旁边。",
           "瓶子，4分钟前，在杯子和碗旁边。",
           "瓶子，4分钟前，在杯子、碗和勺子旁边。"],
    "es": ["botella, hace 4 minutos, junto a taza.",
           "botella, hace 4 minutos, junto a taza y cuenco.",
           "botella, hace 4 minutos, junto a taza, cuenco y cuchara."],
    "fr": ["bouteille, il y a 4 minutes, à côté de tasse.",
           "bouteille, il y a 4 minutes, à côté de tasse et bol.",
           "bouteille, il y a 4 minutes, à côté de tasse, bol et cuillère."],
    "hi": ["बोतल, 4 मिनट पहले, कप के पास।",
           "बोतल, 4 मिनट पहले, कप और कटोरा के पास।",
           "बोतल, 4 मिनट पहले, कप, कटोरा और चम्मच के पास।"],
}
_END = {"en": ".", "zh": "。", "es": ".", "fr": ".", "hi": "।"}
_SEP = {"en": ", ", "zh": "，", "es": ", ", "fr": ", ", "hi": ", "}


def test_every_language_has_every_template() -> None:
    """The tables cover exactly the five contract languages."""
    assert set(NOT_SEEN_BY_LANGUAGE) == set(LANGUAGES) == set(UNAVAILABLE_BY_LANGUAGE)
    assert set(_EXPECTED_AGES) == set(LANGUAGES)


@pytest.mark.parametrize("lang", list(LANGUAGES))
@pytest.mark.parametrize(("age", "bucket"), _AGE_CASES)
def test_time_phrase_in_every_language(lang: str, age: float, bucket: str) -> None:
    """Each age bucket in each language; a brand name is spoken as stored."""
    expected = f"Heinz ketchup{_SEP[lang]}{_EXPECTED_AGES[lang][bucket]}{_END[lang]}"
    assert format_answer(_row(age), NOW, lang) == expected


@pytest.mark.parametrize("lang", list(LANGUAGES))
@pytest.mark.parametrize("count", [1, 2, 3])
def test_class_label_and_neighbours_in_every_language(lang: str, count: int) -> None:
    """Class labels (object and neighbours) are translated and joined per language."""
    row = _row(240, name="", neighbours=["cup", "bowl", "spoon"][:count])
    assert format_answer(row, NOW, lang) == _EXPECTED_FULL[lang][count - 1]


def test_fixed_sentences_in_every_language() -> None:
    """Not-seen and unavailable in every language; English is the SPEC wording."""
    assert not_seen("en") == NOT_SEEN == "I have not seen that."
    assert unavailable("en") == UNAVAILABLE == "Touch history is unavailable right now."
    assert not_seen("zh") == "我没有见过它。"
    assert not_seen("es") == "No lo he visto."
    assert not_seen("fr") == "Je ne l'ai pas vu."
    assert not_seen("hi") == "मैंने वह नहीं देखा।"
    assert unavailable("zh") == "暂时无法查看触摸记录。"
    assert unavailable("es") == "El historial de toques no está disponible ahora."
    assert unavailable("fr") == "L'historique des contacts est indisponible pour le moment."
    assert unavailable("hi") == "छूने का इतिहास अभी उपलब्ध नहीं है।"
    for lang in LANGUAGES:
        assert format_answer(None, NOW, lang) == not_seen(lang)
    assert format_answer(None, NOW, "de") == NOT_SEEN  # unknown code falls back to English


def test_english_default_is_unchanged() -> None:
    """Omitting the language and passing "en" give the same SPEC sentence."""
    row = _row(240, neighbours=["mug", "cereal box"])
    expected = "Heinz ketchup, 4 minutes ago, next to mug and cereal box."
    assert format_answer(row, NOW) == format_answer(row, NOW, "en") == expected


class _Conn:
    """A connection the store treats as open."""

    closed = False
    broken = False

    def close(self) -> None:
        """Do nothing."""


def test_language_is_captured_when_query_arrives(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each query is answered in the voice language it was asked in."""
    monkeypatch.setattr(db, "connect", lambda url: _Conn())
    monkeypatch.setattr(db, "ensure_schema", lambda conn: None)
    rows: dict[str, dict[str, Any] | None] = {
        "ketchup": {"ts": time.time() - 240, "name": "", "class_label": "bottle",
                    "neighbours": ["cup"]},
        "nothing": None,
    }
    monkeypatch.setattr(db, "last_seen", lambda conn, text: rows[text])
    published: list[Any] = []
    store = Store(published.append, UNREACHABLE_URL, start=False)
    assert store.language == "en"  # English until the first VoiceStatus
    store.start()
    try:
        for i, (lang, text, rid) in enumerate([("es", "ketchup", "a"), ("es", "nothing", "b"),
                                               ("fr", "nothing", "c"),
                                               ("xx", "nothing", "d")]):  # xx -> English
            store.on_voice_status(_voice(lang))
            store.on_last_seen_query(LastSeenQuery(ts=NOW, text=text, request_id=rid))
            assert _wait_for(lambda n=2 * (i + 1): len(published) == n)
    finally:
        store.stop()
    spoken = [m.text for m in published if isinstance(m, SpeakRequest)]
    results = {m.request_id: m for m in published if isinstance(m, LastSeenResult)}
    assert spoken == ["botella, hace 4 minutos, junto a taza.", "No lo he visto.",
                      "Je ne l'ai pas vu.", NOT_SEEN]
    assert [results[k].answer for k in "abcd"] == spoken  # exactly what was spoken
    assert [results[k].status for k in "abcd"] == ["found", "not_found", "not_found",
                                                   "not_found"]
    assert results["a"].label == "bottle"  # the stored value, not translated


def test_stale_language_answer_is_unavailable_in_current_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A switch while the query runs gives the unavailable sentence in the new language."""
    monkeypatch.setattr(db, "connect", lambda url: _Conn())
    monkeypatch.setattr(db, "ensure_schema", lambda conn: None)
    published: list[Any] = []
    store = Store(published.append, UNREACHABLE_URL, start=False)

    def last_seen(conn: Any, text: str) -> dict[str, Any]:
        store.on_voice_status(_voice("en"))  # the wearer switches mid-query
        return {"ts": time.time() - 240, "name": "", "class_label": "bottle",
                "neighbours": ["cup"]}

    monkeypatch.setattr(db, "last_seen", last_seen)
    store.on_voice_status(_voice("hi"))
    store.on_last_seen_query(LastSeenQuery(ts=NOW, text="ketchup", request_id="s"))
    store.on_last_seen_query(LastSeenQuery(ts=NOW, text="ketchup"))  # asked in Hindi too
    store.start()
    try:
        assert _wait_for(lambda: len(published) == 3)
    finally:
        store.stop()
    spoken = [m.text for m in published if isinstance(m, SpeakRequest)]
    results = [m for m in published if isinstance(m, LastSeenResult)]
    assert spoken == [UNAVAILABLE, UNAVAILABLE]
    assert len(results) == 1
    assert results[0].answer == UNAVAILABLE and results[0].status == "unavailable"
    assert results[0].matched_at is None and results[0].label == ""
    assert results[0].neighbours == []


def test_unavailable_answer_follows_language() -> None:
    """With no database the unavailable sentence is in the query's language."""
    published: list[Any] = []
    store = Store(published.append, None, start=False)
    store.on_voice_status(_voice("hi"))
    store.on_last_seen_query(LastSeenQuery(ts=NOW, text="ketchup", request_id="h"))
    store.start()
    try:
        assert _wait_for(lambda: len(published) == 2)
    finally:
        store.stop()
    assert [m.answer if isinstance(m, LastSeenResult) else m.text for m in published] == [
        "छूने का इतिहास अभी उपलब्ध नहीं है।"] * 2


def test_voice_status_handler_only_sets_a_field() -> None:
    """The handler returns at once and publishes and queues nothing."""
    published: list[Any] = []
    store = Store(published.append, None, start=False)
    t0 = time.perf_counter()
    store.on_voice_status(_voice("zh"))
    assert time.perf_counter() - t0 < 0.005
    assert store.language == "zh" and published == [] and store._queue.empty()


def test_fake_store_answers_in_the_voice_language() -> None:
    """The fake follows VoiceStatus too, and stays English by default."""
    from fakes.storage.fake_store import FakeStore

    published: list[Any] = []
    fake = FakeStore(published.append)
    fake.on_touch_event(TouchEvent(ts=time.time() - 240, object_id=1, class_label="bottle",
                                   name="", kind="touch", box=(0.0, 0.0, 1.0, 1.0),
                                   neighbours=["cup"]))
    fake.on_last_seen_query(LastSeenQuery(ts=NOW, text="bottle"))
    fake.on_voice_status(_voice("fr"))
    fake.on_last_seen_query(LastSeenQuery(ts=NOW, text="bottle"))
    fake.on_last_seen_query(LastSeenQuery(ts=NOW, text="umbrella"))
    assert [m.text for m in published] == ["bottle, 4 minutes ago, next to cup.",
                                           "bouteille, il y a 4 minutes, à côté de tasse.",
                                           "Je ne l'ai pas vu."]
