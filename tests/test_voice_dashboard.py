"""Voice switching through the dashboard: the service, the snapshot, and /api/voice."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from config import VOICE_SWITCH_TIMEOUT_SECONDS
from contracts import VoiceChange, VoiceStatus
from dashboard import DashboardState, create_app, register

NOW = 1_800_000_000.0
VOICES = {
    "ava": "Ava",
    "zoe": "Zoe",
    "evan": "Evan",
    "jamie": "Jamie",
    "matilda": "Matilda",
}


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


class SyncBus:
    def __init__(self) -> None:
        self.handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.published: list[Any] = []

    def subscribe(self, t: type, h: Callable[[Any], None]) -> None:
        self.handlers[t].append(h)

    def publish(self, msg: Any) -> None:
        self.published.append(msg)
        for h in list(self.handlers.get(type(msg), [])):
            h(msg)


def status(
    active: str, request_id: str | None = None, state: str = "active", **kw: Any
) -> VoiceStatus:
    kw.setdefault("installed", list(VOICES))
    return VoiceStatus(
        ts=NOW,
        state=state,
        active_voice=active,
        label=VOICES[active],
        quality="premium",
        voices=dict(VOICES),
        request_id=request_id,
        **kw,
    )


@pytest.fixture
def setup() -> tuple[TestClient, SyncBus, Any, Clock]:
    clock = Clock()
    bus = SyncBus()
    dashboard = register(bus, DashboardState(clock=clock), serve=False)
    dashboard.voice._clock = clock
    return TestClient(create_app(dashboard.state)), bus, dashboard, clock


def voice(client: TestClient) -> dict[str, Any]:
    return client.get("/api/state").json()["voice"]


def changes(bus: SyncBus) -> list[VoiceChange]:
    return [m for m in bus.published if isinstance(m, VoiceChange)]


def test_unknown_voice_state_refuses_to_switch(setup: Any) -> None:
    client, bus, _, _ = setup
    v = voice(client)
    assert v["state"] == "unknown" and v["message"] == "Audio has not reported a voice."
    reply = client.post("/api/voice", json={"voice": "zoe"})
    assert (
        reply.status_code == 503
        and reply.json()["detail"] == "Audio has not reported a voice."
    )
    assert changes(bus) == []


def test_active_voice_changes_only_after_audio_confirms(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("ava"))
    reply = client.post("/api/voice", json={"voice": "zoe"})
    assert reply.status_code == 202
    body = reply.json()
    assert (body["state"], body["voice"]) == ("switching", "zoe")
    assert body["voice_view"]["switching_to"] == "zoe"
    (sent,) = changes(bus)
    assert (sent.voice, sent.request_id) == ("zoe", body["request_id"])
    v = voice(client)
    assert (v["state"], v["active_voice"], v["switching_to"]) == (
        "switching",
        "ava",
        "zoe",
    )
    bus.publish(status("zoe", body["request_id"], requested_voice="zoe"))
    v = voice(client)
    assert (v["state"], v["active_voice"], v["label"], v["switching_to"]) == (
        "active",
        "zoe",
        "Zoe",
        None,
    )


def test_second_request_while_switching_is_409(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("ava"))
    assert client.post("/api/voice", json={"voice": "zoe"}).status_code == 202
    for key in ("zoe", "evan"):
        reply = client.post("/api/voice", json={"voice": key})
        assert reply.status_code == 409
        assert reply.json()["detail"] == "A switch to Zoe is already in progress."
    assert len(changes(bus)) == 1


def test_requesting_active_voice_sends_nothing(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("ava"))
    reply = client.post("/api/voice", json={"voice": "ava"})
    assert reply.status_code == 200 and reply.json()["state"] == "active"
    assert changes(bus) == []


def test_unlisted_voice_is_422(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("ava"))
    reply = client.post("/api/voice", json={"voice": "bob"})
    assert (
        reply.status_code == 422
        and reply.json()["detail"] == "Choose one of the listed voices."
    )
    assert client.post("/api/voice", json={"nope": 1}).status_code == 422
    assert changes(bus) == []


def test_timeout_then_late_status_shows_truth(setup: Any) -> None:
    client, bus, dashboard, clock = setup
    bus.publish(status("ava"))
    rid = client.post("/api/voice", json={"voice": "jamie"}).json()["request_id"]
    clock.now = NOW + VOICE_SWITCH_TIMEOUT_SECONDS
    assert dashboard.voice.expire() is False
    assert voice(client)["state"] == "switching"
    clock.now = NOW + VOICE_SWITCH_TIMEOUT_SECONDS + 0.01
    assert dashboard.voice.expire() is True
    v = voice(client)
    assert (v["state"], v["active_voice"]) == ("failed", "ava")
    assert v["message"] == (
        "Audio did not confirm Jamie within 10 s. The page shows the voice audio last reported."
    )
    bus.publish(status("jamie", rid))
    v = voice(client)
    assert (v["state"], v["active_voice"], v["message"]) == ("active", "jamie", "")


def test_stale_request_id_never_shows_wrong_voice(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("ava"))
    rid = client.post("/api/voice", json={"voice": "evan"}).json()["request_id"]
    bus.publish(status("ava", "older-request"))
    v = voice(client)
    assert (v["state"], v["switching_to"], v["active_voice"], v["request_id"]) == (
        "switching",
        "evan",
        "ava",
        rid,
    )
    bus.publish(status("evan", rid))
    assert voice(client)["active_voice"] == "evan"


def test_audio_failure_is_shown(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("ava"))
    rid = client.post("/api/voice", json={"voice": "zoe"}).json()["request_id"]
    bus.publish(
        status(
            "ava",
            rid,
            state="failed",
            requested_voice="zoe",
            detail="Zoe could not be loaded.",
        )
    )
    v = voice(client)
    assert (v["state"], v["active_voice"], v["message"]) == (
        "failed",
        "ava",
        "Zoe could not be loaded.",
    )
    assert client.post("/api/voice", json={"voice": "zoe"}).status_code == 202


def test_without_engine_switching_is_unavailable() -> None:
    client = TestClient(create_app(DashboardState(clock=Clock())))
    reply = client.post("/api/voice", json={"voice": "zoe"})
    assert reply.status_code == 503
    assert (
        reply.json()["detail"]
        == "Switching voices needs the full app; this page has no engine attached."
    )
    assert client.get("/api/state").json()["capabilities"]["voice_switch"] is False


def test_snapshot_has_voice_and_capability(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("ava", installed=["ava", "zoe"]))
    snap = client.get("/api/state").json()
    v = snap["voice"]
    assert set(v) == {
        "state",
        "active_voice",
        "label",
        "quality",
        "options",
        "switching_to",
        "message",
        "request_id",
        "updated_ts",
        "language",
        "languages",
    }
    assert v["options"][0] == {
        "key": "ava",
        "label": "Ava",
        "installed": True,
        "language": "en",
    }
    assert [o["key"] for o in v["options"]] == list(VOICES)
    assert v["options"][2]["installed"] is False
    assert snap["capabilities"]["voice_switch"] is True


def test_api_voice_round_trip(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(status("ava"))
    reply = client.post("/api/voice", json={"voice": "matilda"})
    assert reply.status_code == 202
    (sent,) = changes(bus)
    assert sent.request_id == reply.json()["request_id"]
    assert client.get("/api/voice").json()["state"] == "switching"
    bus.publish(status("matilda", sent.request_id))
    got = client.get("/api/voice").json()
    assert (got["state"], got["active_voice"], got["updated_ts"]) == (
        "active",
        "matilda",
        NOW,
    )


# Languages (SPEC 4.8): the active language is the language of audio's confirmed voice.

MULTI = {"ava": "Ava", "zoe": "Zoe", "huayan": "Huayan", "claude": "Claude", "siwis": "Siwis"}
MULTI_LANGS = {"ava": "en", "zoe": "en", "huayan": "zh", "claude": "es", "siwis": "fr"}


def multi_status(active: str, language: str, **kw: Any) -> VoiceStatus:
    return VoiceStatus(
        ts=NOW,
        state="active",
        active_voice=active,
        label=MULTI[active],
        quality="premium",
        voices=dict(MULTI),
        installed=list(MULTI),
        language=language,
        voice_languages=dict(MULTI_LANGS),
        **kw,
    )


def test_view_reports_language_languages_and_option_languages(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(multi_status("claude", "es"))
    v = voice(client)
    assert v["language"] == "es"
    # LANGUAGES order; Hindi has no option here so it is not offered.
    assert v["languages"] == [
        {"code": "en", "label": "English"},
        {"code": "zh", "label": "中文"},
        {"code": "es", "label": "Español"},
        {"code": "fr", "label": "Français"},
    ]
    assert [o["language"] for o in v["options"]] == ["en", "en", "zh", "es", "fr"]
    assert v["options"][3] == {
        "key": "claude",
        "label": "Claude",
        "installed": True,
        "language": "es",
    }


def test_view_before_any_status_is_english(setup: Any) -> None:
    client, _, dashboard, _ = setup
    v = voice(client)
    assert (v["language"], v["languages"]) == ("en", [])
    assert dashboard.voice.language() == "en"


def test_unknown_language_code_shows_as_english(setup: Any) -> None:
    client, bus, dashboard, _ = setup
    bus.publish(
        VoiceStatus(
            ts=NOW, state="active", active_voice="ava", label="Ava", quality="premium",
            voices={"ava": "Ava", "x": "X"}, installed=["ava"], language="klingon",
            voice_languages={"ava": "en", "x": "tlh"},
        )
    )
    v = voice(client)
    assert v["language"] == "en" and dashboard.voice.language() == "en"
    assert [o["language"] for o in v["options"]] == ["en", "en"]
    assert v["languages"] == [{"code": "en", "label": "English"}]


def test_picking_a_language_is_a_plain_voice_change(setup: Any) -> None:
    client, bus, _, _ = setup
    bus.publish(multi_status("ava", "en"))
    reply = client.post("/api/voice", json={"voice": "siwis"})
    assert reply.status_code == 202
    (sent,) = changes(bus)
    assert sent.voice == "siwis"
    assert voice(client)["language"] == "en"  # unchanged until audio confirms
    bus.publish(multi_status("siwis", "fr", request_id=sent.request_id))
    assert voice(client)["language"] == "fr"
