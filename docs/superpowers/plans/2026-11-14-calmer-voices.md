# Calmer Voices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the robotic, rushed default voice with five calmer Apple Premium/Enhanced English voices. Pick the default in `.env` and switch live from the dashboard.

**Architecture:** A new `audio/voices.py` holds five presets and the rule that matches each one to an installed pyttsx3 voice. `Pyttsx3Speaker` sets the voice id and `SPEECH_RATE_WPM` on every fresh engine. The dashboard asks for a switch with a new `VoiceChange` message. Audio's speech worker applies it between phrases and confirms with `VoiceStatus`, the same pattern as `ModeChange`/`DetectorStatus`.

**Tech Stack:** Python 3.11, `pyttsx3==2.99` (macOS NSSpeechSynthesizer driver), FastAPI, native ES modules, `pytest`, `node --test`, `ruff`. No new packages.

**Spec:** `docs/superpowers/specs/2026-11-14-calmer-voices-design.md` (read it first), plus `SPEC.md` §4.8, §4.9 and §5.

## Global Constraints

- No new dependency. `pyttsx3==2.99` and `pygame==2.6.1` stay as pinned in `audio/requirements.txt`.
- Speech never waits on the network. No network call anywhere in `audio/`.
- Nothing may delay, pause, queue behind, or disable the hazard path. A voice switch is applied only between phrases on the speech worker. Bus handlers only set state under the lock and return.
- Thresholds come from `config/`: `SPEECH_RATE_WPM = 165` (audio) and `VOICE_SWITCH_TIMEOUT_SECONDS = 10.0` (dashboard).
- Task 2 changes `contracts/`, `config/` and `SPEC.md`. That needs all four teammates to agree, recorded in `DEVLOG.md`, before it merges to `main`.
- Do not touch the `pointing-trigger` branch (PR #31). Branch from `main` as `p4-calmer-voices`.
- Never describe the hazard feature as a safety device in copy, comments or UI text.
- Type hints on every function, one docstring per public function, logger name `"audio"` or `"dashboard"`, no bare `print` outside `fakes/` and tests.
- Preset keys, labels and the default are exactly: `ava` "Ava" (default), `zoe` "Zoe", `evan` "Evan", `jamie` "Jamie", `matilda` "Matilda".
- Sample line after a switch: `f"This is {label}."`, spoken at answer priority with source `"audio"`.
- Run commands with `.venv/bin/python`.

## Review Focus

1. **A hazard arrives while a voice switch is pending or the sample line is playing.** The beeps start at once, the sample line is interrupted, and the hazard phrase is spoken in the new voice. Test in Task 5: `test_hazard_during_switch_outranks_sample`.
2. **The chosen preset's voice is not downloaded on the demo laptop.** Speech still works with Samantha, `VoiceStatus.quality == "fallback"`, `ModuleStatus` is `degraded` with a plain reason, and the picker shows "(not installed)". Tests in Tasks 3, 5 and 8.
3. **A switch requested while a long answer is speaking.** The answer is not cut off. The switch applies when it ends. If that takes longer than 10 s, the page shows "failed", then shows the truth when the late `VoiceStatus` arrives. Tests in Tasks 5 and 7.
4. **Two pages, or rapid clicks, ask for different voices.** The dashboard refuses a second request while one is pending (409). In audio, the newest pending switch wins. Tests in Tasks 5 and 7.
5. **Dashboard running without audio (`--only dashboard`) or with a typo in `AUDIO_VOICE`.** The picker is disabled with "Audio has not reported a voice." For the typo, audio logs one warning and uses `ava`. Tests in Tasks 3 and 7.

## Execution Split

The user asked for specialist agents wherever the parts are genuinely independent. No file has two owners.

| Order | Who | Tasks | Files owned | Why |
|---|---|---|---|---|
| 1 | Human and the main session | Task 1 (gate) | `DEVLOG.md` | Needs the human to download voices and listen. A `researcher` adds nothing: the engine choice is made and the open question is a hands-on check |
| 2 | Main session | Task 2 | `contracts/`, `config/`, `SPEC.md`, `.env.example` | Shared files are edited by the main session only, and both streams below need them first |
| 3a, in parallel | `backend-engineer` (audio) | Tasks 3 → 4 → 5 → 6, in sequence | `audio/`, `fakes/audio/`, `tests/test_audio_voices.py`, `tests/test_audio_pyttsx3.py`, `tests/test_audio_voice_switch.py`, `tests/test_speak_test.py` | These four are tightly coupled (each consumes the last one's interface), so one agent does them in order |
| 3b, in parallel | `backend-engineer` (dashboard) | Task 7 | `dashboard/services/voice_choice.py`, `dashboard/api/`, `dashboard/state.py`, `dashboard/server.py`, `dashboard/bus_adapter.py`, `tests/test_voice_dashboard.py` | Depends only on Task 2's messages |
| 3c, in parallel | `frontend-engineer` | Task 8 steps 1–4 | `dashboard/static/features/experience/*`, `tests/ui/toggle/voice.test.mjs` | Depends only on the `view()` shape pinned in Task 7's Interfaces. Step 5 (live check) waits for 3a and 3b |
| 4 | `qa-engineer`, then the main session with the human | Task 8 step 5, Task 9 steps 2–4 automated parts; the human does the listening in Task 9 steps 1–3 | none (reports only); the main session writes `DEVLOG.md` | Integration and regression check once all streams are merged; the by-ear judgement is the human's |
| 5 | One read-only reviewer | Whole branch | none | Final review, with hazard priority as the main focus |

Each parallel agent works in its own git worktree on a branch off `p4-calmer-voices`. The main session merges them in order: 3a, then 3b, then 3c.

---

### Task 1: Check that pyttsx3 can use Apple Premium voices (gate)

No code. This decides whether the plan continues or falls back to Piper (a new package, so team agreement first).

**Files:**
- Modify: `DEVLOG.md` (results only)

- [ ] **Step 1: Download the voices.** On the demo Mac go to System Settings → Accessibility → Spoken Content → System Voice → Manage Voices. Download English (US) Ava (Premium), Zoe (Premium) and Evan (Enhanced), English (UK) Jamie (Premium), and English (Australia) Matilda (Premium). The human does this; it needs no password.
- [ ] **Step 2: List what pyttsx3 sees.**

Run: `.venv/bin/python -c "import pyttsx3;e=pyttsx3.init();[print(v.id,'|',v.name,v.languages) for v in e.getProperty('voices') if '.premium.' in v.id or '.enhanced.' in v.id]"`
Expected: five lines, with ids shaped like `com.apple.voice.premium.en-US.Ava`. Write down the exact `id` and `name` strings. Task 3 matches on them.

- [ ] **Step 3: Speak with one at a calm rate.**

Run: `.venv/bin/python -c "import pyttsx3;e=pyttsx3.init();e.setProperty('voice','<Ava id from step 2>');e.setProperty('rate',165);e.say('Heinz ketchup. Stop. Stairs.');e.runAndWait()"`
Expected: a natural female US voice, clearly slower than today, out of the JBL Go 3.

- [ ] **Step 4: Decide.** If step 2 lists none of the voices, or step 3 plays the old voice: **stop**. Tell the human that the Piper fallback in the design doc needs all four teammates' agreement. Otherwise record the five ids in `DEVLOG.md` and continue. If only some presets are listed, swap each missing one for another listed Premium/Enhanced English voice. Tell the human which, and update the preset table in Task 3.

### Task 2: Shared contract and thresholds (needs team agreement)

**Files:**
- Modify: `contracts/messages.py` (after `DetectorStatus`), `contracts/__init__.py` (exports)
- Modify: `config/thresholds.py` (two constants and `__all__`)
- Modify: `SPEC.md` §4.8, §4.9, §5, §9
- Modify: `.env.example` (add `AUDIO_VOICE=`)
- Test: `tests/test_contracts.py`

**Interfaces:**
- Produces:

```python
@dataclass
class VoiceChange:
    """Dashboard to audio: a request to switch the spoken voice. Never a confirmation."""
    ts: float
    voice: str  # preset key, e.g. "ava"
    request_id: str | None = None  # echoed in the VoiceStatus that answers it

@dataclass
class VoiceStatus:
    """Audio to dashboard: the voice speech really uses now. The only confirmation of a switch."""
    ts: float
    state: Literal["active", "failed"]
    active_voice: str  # preset key in use now
    label: str  # e.g. "Ava"
    quality: Literal["premium", "enhanced", "compact", "fallback"]
    voices: dict[str, str] = field(default_factory=dict)  # key -> label, menu order
    installed: list[str] = field(default_factory=list)  # keys whose own voice is installed
    requested_voice: str | None = None  # set on a failed or answered request
    request_id: str | None = None
    detail: str = ""
```

  `SPEECH_RATE_WPM = 165  # audio` and `VOICE_SWITCH_TIMEOUT_SECONDS = 10.0  # dashboard`.

- [ ] **Step 1: Write the failing test** `test_voice_messages_have_spec_fields`. It builds `VoiceChange(ts=1.0, voice="ava")` and asserts `request_id is None`. It builds `VoiceStatus(ts=1.0, state="active", active_voice="ava", label="Ava", quality="premium")` and asserts `voices == {}`, `installed == []` and `detail == ""`. It asserts both names are in `contracts.__all__`, and that `config.SPEECH_RATE_WPM == 165` and `config.VOICE_SWITCH_TIMEOUT_SECONDS == 10.0`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_contracts.py -v`. Expected: FAIL with ImportError.
- [ ] **Step 3: Add the two dataclasses and two constants exactly as above.** Add `AUDIO_VOICE=` to `.env.example` with a comment listing the five keys.
- [ ] **Step 4: Update `SPEC.md`.**
  - §4.8: add a rule. "Speech uses one of five voice presets (`ava` default, `zoe`, `evan`, `jamie`, `matilda`) at `SPEECH_RATE_WPM`. `AUDIO_VOICE` in `.env` picks the startup voice. A `VoiceChange` is applied between phrases, never mid-phrase and never ahead of a hazard. Audio answers with `VoiceStatus`, then says 'This is <label>.' at priority 3."
  - §4.9: one row for the voice picker.
  - §5: the two message tables.
  - §9: the two thresholds.
- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/test_contracts.py -v`. Expected: PASS.
- [ ] **Step 6: Commit** `contracts, config, SPEC: VoiceChange/VoiceStatus and calmer speech rate`. Add a `DEVLOG.md` "Needs attention" line: "Shared change: needs all four teammates' OK before merge to main."

### Task 3: Voice presets and matching

**Files:**
- Create: `audio/voices.py`
- Test: `tests/test_audio_voices.py`

**Interfaces:**
- Produces:

```python
Quality = Literal["premium", "enhanced", "compact", "fallback"]

@dataclass(frozen=True)
class VoicePreset:
    key: str
    label: str
    apple_name: str  # name as pyttsx3 reports it, without " (Premium)"/" (Enhanced)"
    locale: str  # "en-US"; also the hook for languages later

@dataclass(frozen=True)
class ResolvedVoice:
    key: str
    label: str
    voice_id: str | None  # None means the system default voice
    quality: Quality

PRESETS: tuple[VoicePreset, ...]  # ava, zoe, evan, jamie, matilda in that order
DEFAULT_VOICE_KEY = "ava"
FALLBACK_NAME, FALLBACK_LOCALE = "Samantha", "en-US"

def preset_for(key: str) -> VoicePreset | None: ...
def voice_quality(voice_id: str) -> Literal["premium", "enhanced", "compact"]: ...
def resolve_voice(key: str, installed: Sequence[tuple[str, str]]) -> ResolvedVoice: ...
def installed_keys(installed: Sequence[tuple[str, str]]) -> list[str]: ...
def startup_voice_key(env: Mapping[str, str]) -> str: ...
```

`installed` is a list of `(voice_id, name)` pairs. A voice matches a preset when its name, with any trailing parenthetical removed, equals `apple_name`, and its id contains `locale`. Among matches, the order is premium, then enhanced, then compact, judged by `.premium.` or `.enhanced.` in the id; anything else counts as compact. With no match, use the Samantha/en-US match, then `voice_id=None`, both reported as `quality="fallback"`. `startup_voice_key` reads `AUDIO_VOICE`, strips it and lowercases it. A blank or unknown key logs one warning and returns `"ava"`.

- [ ] **Step 1: Write the failing tests** with fixture `INSTALLED` built from the ids recorded in Task 1, plus `("com.apple.voice.compact.en-US.Samantha", "Samantha")` and `("com.apple.voice.compact.en-US.Ava", "Ava")`:
  - `test_five_presets_in_order`: `[p.key for p in PRESETS] == ["ava","zoe","evan","jamie","matilda"]`.
  - `test_premium_beats_compact`: `resolve_voice("ava", INSTALLED).voice_id == "com.apple.voice.premium.en-US.Ava"` and `.quality == "premium"`.
  - `test_name_with_parenthetical_matches`: `("com.apple.voice.premium.en-US.Zoe", "Zoe (Premium)")` resolves for `zoe`.
  - `test_locale_must_match`: an `en-GB` Ava does not satisfy `ava`.
  - `test_missing_voice_falls_back_to_samantha`: with only Samantha installed, `resolve_voice("jamie", ...)` gives `voice_id` Samantha's id and `quality == "fallback"`.
  - `test_nothing_installed_uses_system_default`: `resolve_voice("ava", [])` gives `voice_id is None` and `quality == "fallback"`.
  - `test_installed_keys_lists_only_real_matches`: with only Ava Premium plus Samantha, the result is `["ava"]`.
  - `test_startup_key_from_env`: `{"AUDIO_VOICE": " Evan "}` gives `"evan"`, `{}` gives `"ava"`, and `{"AUDIO_VOICE": "bob"}` gives `"ava"` and logs one warning (`caplog`).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_audio_voices.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `audio/voices.py`** as specified.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `audio: five voice presets and installed-voice matching`.

### Task 4: Speaker sets voice and rate on every engine

**Files:**
- Modify: `audio/backends.py` (`_speak_once`, `Pyttsx3Speaker`, `LogSpeaker`)
- Modify: `fakes/audio/fake_audio.py` (`PrintSpeaker`)
- Test: `tests/test_audio_pyttsx3.py`

**Interfaces:**
- Consumes: `config.SPEECH_RATE_WPM`.
- Produces, on every speaker (the `Speaker` protocol gains them, and `AudioManager` calls them through `getattr` so older doubles still work):
  - `installed_voices(self) -> list[tuple[str, str]]`. Pyttsx3 reads `engine.getProperty("voices")` once in `__init__` and returns `(v.id, v.name)` pairs. `LogSpeaker` returns `[]`. `PrintSpeaker` returns a premium id for each of the five presets, e.g. `("fake.premium.en-US.Ava", "Ava")`, so the fake dashboard can switch.
  - `set_voice(self, voice_id: str | None) -> None`. Stores the id for later engines. `PrintSpeaker` prints `[fake audio] voice: <id>`.
- `Pyttsx3Speaker.__init__(self, rate: int = SPEECH_RATE_WPM)`.
- `_speak_once(pyttsx3, text, should_stop, voice_id: str | None, rate: int) -> None` calls `engine.setProperty("rate", rate)`, and `engine.setProperty("voice", voice_id)` only when `voice_id` is not None, before `say`.

- [ ] **Step 1: Extend `FakeEngine`** in `tests/test_audio_pyttsx3.py` with `setProperty`, which records into the shared log, and `getProperty("voices")`, which returns two `SimpleNamespace(id=..., name=...)`. Write the failing tests:
  - `test_every_engine_gets_rate_and_voice`: `set_voice("v1")`, then two `say` calls. Both engines recorded `("rate", 165)` and `("voice", "v1")` before `say`.
  - `test_no_voice_id_leaves_system_voice`: with no `set_voice`, `("rate", 165)` is set and no `"voice"` property is set.
  - `test_installed_voices_lists_engine_voices`: returns the two `(id, name)` pairs.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_audio_pyttsx3.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the interfaces above. Keep the fresh-engine-per-phrase and `gc.collect()` behaviour unchanged.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_audio_pyttsx3.py tests/test_audio.py -v`. Expected: PASS, with no change to the existing tests.
- [ ] **Step 5: Commit** `audio: set calmer rate and chosen voice on every speech engine`.

### Task 5: AudioManager applies voice switches between phrases

**Files:**
- Modify: `audio/audio.py` (`_State`, `AudioManager.__init__`, new `on_voice_change`, `_next_item`, `_report_ready`, `_run`, `register`)
- Modify: `fakes/audio/fake_audio.py` (`register` subscribes `VoiceChange`)
- Test: `tests/test_audio_voice_switch.py` (new; reuse the helpers and fixtures pattern from `tests/test_audio.py`)

**Interfaces:**
- Consumes: Task 3's `resolve_voice`, `installed_keys`, `preset_for`, `PRESETS`, `startup_voice_key`. Task 4's `installed_voices` and `set_voice`. Task 2's `VoiceChange` and `VoiceStatus`.
- Produces:
  - `AudioManager(..., voice: str = DEFAULT_VOICE_KEY)`.
  - `AudioManager.on_voice_change(msg: VoiceChange) -> None`. An unknown `msg.voice` queues `VoiceStatus(state="failed", requested_voice=msg.voice, request_id=msg.request_id, detail="Unknown voice ...")` and returns. Otherwise it sets `_State.pending_voice = (msg.voice, msg.request_id)`, replacing any older pending one, notifies, and returns. It never touches `slot` or `generation`.
  - `register(bus)` passes `voice=startup_voice_key(os.environ)` and subscribes `VoiceChange` after the existing four, so hazard stays first.
- Worker behaviour:
  - `_next_item` also wakes when `pending_voice` is set. Before returning an item, the worker applies any pending voice: resolve, `speaker.set_voice(voice_id)`, publish `VoiceStatus(state="active", ...)` with `voices` from `PRESETS`, `installed` from `installed_keys` and the echoed `request_id`, then `_offer` the sample line (`PRIORITY_ANSWER`, source `"audio"`).
  - A switch is never applied while `speaker.say` is running.
  - A hazard phrase waiting out its beeps (`not_before`) does not block applying a switch.
  - At startup, `_report_ready` resolves the startup voice, calls `set_voice`, and publishes one `VoiceStatus(state="active", request_id=None)` with no sample line. If the quality is `"fallback"`, the `ModuleStatus` is `degraded`, with detail `f"Voice {label} is not installed; using {fallback} instead"` appended to the existing text.

- [ ] **Step 1: Write the failing tests.** `RecordingSpeaker` gets `installed_voices()` returning premium ids for all five presets and `set_voice` recording ids. `publish` collects messages.
  - `test_startup_publishes_active_voice_without_sample`: one `VoiceStatus` with `active_voice == "ava"`, `quality == "premium"`, `list(voices) == ["ava","zoe","evan","jamie","matilda"]`, and nothing spoken.
  - `test_switch_confirms_then_says_sample`: `on_voice_change(VoiceChange(1.0, "jamie", "r1"))` gives `VoiceStatus` with `active_voice == "jamie"` and `request_id == "r1"`, `set_voice` called with Jamie's id, then spoken `["This is Jamie."]`.
  - `test_switch_waits_for_current_phrase`: speaker blocks on an event while saying an answer. Switch to `zoe`. Assert the answer is not cut off and `set_voice` is not called until the event is released, then the sample plays.
  - `test_hazard_during_switch_outranks_sample`: switch to `evan`, then `on_hazard` before the sample is spoken. The alarm `play` count is 1, the sample is `interrupted` or never spoken, and the next spoken text is `"Stop. Stairs."` with `set_voice` already called with Evan's id.
  - `test_newest_pending_switch_wins`: with the speaker blocked, request `zoe` then `matilda`, then release. Only `matilda` is confirmed and only `"This is Matilda."` is spoken.
  - `test_unknown_voice_fails_without_change`: `VoiceChange(1.0, "bob", "r2")` gives `VoiceStatus(state="failed", requested_voice="bob", request_id="r2", active_voice="ava")`, and `set_voice` is not called again.
  - `test_missing_voice_reports_fallback`: the speaker lists only Samantha. Startup `VoiceStatus.quality == "fallback"`, `installed == []`, and `ModuleStatus.status == "degraded"` with `"not installed"` in its detail.
  - `test_voice_handler_never_waits_on_speech`: with the speaker blocked, `on_voice_change` returns in under 50 ms (same style as `test_handlers_never_wait_on_speech`).
  - `test_register_subscribes_voice_change_after_hazard`: extends the existing ordering check.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_audio_voice_switch.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** as specified. Keep all `VoiceStatus` publishing in the existing outbox and `_flush`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_audio.py tests/test_audio_voice_switch.py tests/test_audio_shutdown.py -v`. Expected: PASS.
- [ ] **Step 5: Run** `.venv/bin/python -m app --fake vision` for about 20 s. Expected: it starts and logs one `VoiceStatus`. With `--fake audio`, the console shows `[fake audio] voice: fake.premium.en-US.Ava`.
- [ ] **Step 6: Commit** `audio: switch voice between phrases on VoiceChange, confirm with VoiceStatus`.

### Task 6: `speak_test` for checking voices by ear

**Files:**
- Modify: `audio/speak_test.py`
- Test: `tests/test_speak_test.py`

**Interfaces:**
- Consumes: `PRESETS` and `resolve_voice` (Task 3), `SPEECH_RATE_WPM`.
- Produces CLI: `python -m audio.speak_test [--voice KEY | --all] [--list-voices] [TEXT]`. `speak(text: str, voice_id: str | None = None, rate: int = SPEECH_RATE_WPM) -> None`.
  - `--list-voices` prints one line per preset: key, label, resolved id, quality. It is allowed to print because this is a CLI tool.
  - `--all` speaks each preset saying `f"This is {label}. Heinz ketchup. Stop. Stairs."`.
  - TEXT is required unless `--list-voices` or `--all` is given.

- [ ] **Step 1: Write the failing tests** (monkeypatch a fake `pyttsx3` as the file already does): `test_voice_flag_sets_voice_and_rate`, `test_list_voices_prints_five_presets` (5 lines, `ava` first), `test_all_speaks_each_preset_once` (5 `say` calls, the first containing "This is Ava."), `test_unknown_voice_flag_is_an_error` (exit code 2 from argparse `choices`).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_speak_test.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** Update the module docstring so its run lines use macOS `.venv/bin/python` and keep the Windows line as an alternative.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `audio: speak_test can list and play each voice preset`.

### Task 7: Dashboard voice service and API

**Files:**
- Create: `dashboard/services/voice_choice.py`
- Modify: `dashboard/api/schemas.py` (add `VoiceRequest`), `dashboard/api/routes.py` (add `POST /api/voice`, `GET /api/voice`), `dashboard/state.py` (snapshot `"voice"` and capability `"voice_switch"`), `dashboard/server.py` (construct, `tick` → `expire`, listener), `dashboard/bus_adapter.py` (subscribe `VoiceStatus`)
- Test: `tests/test_voice_dashboard.py` (mirror `tests/test_demo_toggle_dashboard.py`)

**Interfaces:**
- Consumes: `VoiceChange`, `VoiceStatus`, `VOICE_SWITCH_TIMEOUT_SECONDS`.
- Produces: `VoiceService(publish, clock=time.time, timeout=VOICE_SWITCH_TIMEOUT_SECONDS)`, with the same method set and semantics as `DetectorModeService`: `available`, `add_listener`, `request(voice: str) -> dict`, `on_status(msg: VoiceStatus) -> None`, `expire() -> bool`, `view() -> dict`. Errors raise `VoiceRejected(status_code, message)`.
  - Valid keys are the keys of the last `VoiceStatus.voices`. The dashboard never imports `audio/`.
  - `view()` keys: `state` (`"unknown"|"active"|"switching"|"failed"`), `active_voice`, `label`, `quality`, `options` (list of `{"key","label","installed"}` in order), `switching_to`, `message`, `request_id`, `updated_ts`.
  - Messages:
    - no status yet: "Audio has not reported a voice."
    - 503 with no bus: "Switching voices needs the full app; this page has no engine attached."
    - 409: f"A switch to {label} is already in progress."
    - 422: "Choose one of the listed voices."
    - timeout: f"Audio did not confirm {label} within {timeout:.0f} s. The page shows the voice audio last reported."
- `POST /api/voice {"voice": "zoe"}` returns 202 `{state:"switching", voice, request_id, voice_view}`. It returns 200 when that voice is already active.

- [ ] **Step 1: Write the failing tests:** `test_unknown_voice_state_refuses_to_switch` (503 before any status), `test_active_voice_changes_only_after_audio_confirms`, `test_second_request_while_switching_is_409`, `test_requesting_active_voice_sends_nothing`, `test_unlisted_voice_is_422`, `test_timeout_then_late_status_shows_truth` (clock fixture; 10.0 s boundary: 10.0 still pending, 10.01 failed), `test_stale_request_id_never_shows_wrong_voice`, `test_without_engine_switching_is_unavailable`, `test_snapshot_has_voice_and_capability` (`snapshot()["voice"]["options"][0] == {"key":"ava","label":"Ava","installed":True}` and `capabilities["voice_switch"] is True`), and `test_api_voice_round_trip` (FastAPI `TestClient`: POST returns 202, a published `VoiceChange` has the same `request_id`, feeding `VoiceStatus` makes GET show `active`).
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_voice_dashboard.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement**, copying `DetectorModeService`'s locking and expiry structure.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_voice_dashboard.py tests/test_demo_toggle_dashboard.py tests/test_dashboard_api.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `dashboard: voice switch service and /api/voice`.

### Task 8: Dashboard voice picker

**Files:**
- Create: `dashboard/static/features/experience/voice-switch.js`
- Modify: `dashboard/static/features/experience/selectors.js` (add `selectVoice`), `dashboard/static/features/experience/index.js` (mount next to the detector switch; request flow copied from `detectorLocal`), `dashboard/static/features/experience/experience.css`
- Test: `tests/ui/toggle/voice.test.mjs`

**Interfaces:**
- Consumes: snapshot `state.voice` (Task 7 `view()`), `capabilities.voice_switch`, `POST /api/voice`.
- Produces: `selectVoice(snapshot, local = { sending: null, error: null }) -> { options: [{key,label,text}], value, locked, statusText, tone }`.
  - `text` is the label, plus `" (not installed)"` when `installed` is false.
  - `value` is the confirmed `active_voice`, never the requested one.
  - `locked` is true while switching, while sending, when the capability is false, or when the state is `"unknown"`.
  - `statusText` is: "Voice: Ava" when active; "Voice: Ava (fallback voice)" when quality is `"fallback"`; "Switching to Zoe…" while switching; the service `message` when unknown or failed.
- `createVoiceSwitch(root, { onChoose }) -> { update(vm), destroy() }`. It renders a labelled native `<select>` ("Voice") and a polite live-region status. A locked select uses `aria-disabled` and keeps focus, the same as the detector switch.

- [ ] **Step 1: Write the failing node tests** in `voice.test.mjs`: `value stays on confirmed voice while switching`, `not installed voices are marked`, `fallback quality shows in status`, `unknown state is locked with audio message`, `no capability locks the picker`.
- [ ] **Step 2: Run** `node --test tests/ui/toggle/voice.test.mjs`. Expected: FAIL (export missing).
- [ ] **Step 3: Implement** the selector, the view and the wiring.
- [ ] **Step 4: Run** `node --test tests/ui/toggle/` and `.venv/bin/python -m pytest tests/test_dashboard*.py -v`. Expected: PASS.
- [ ] **Step 5: Run** `.venv/bin/python -m app --fake vision audio`, open `http://localhost:8000`, check the picker in the browser pane at 320 px and desktop width, pick Zoe, and confirm the console shows `[fake audio] voice: fake.premium.en-US.Zoe` and `say: This is Zoe.`.
- [ ] **Step 6: Commit** `dashboard: voice picker confirmed by audio`.

### Task 9: Verify by ear, full checks, log

**Files:**
- Modify: `DEVLOG.md`

- [ ] **Step 1: Listen to each voice.** With the JBL Go 3 as system output, run `.venv/bin/python -m audio.speak_test --list-voices`. Expected: 5 lines, none `fallback`. Then run `.venv/bin/python -m audio.speak_test --all`. The human scores each voice against the three complaints (robotic, rushed, flat) and picks the default. If a different default wins, change `DEFAULT_VOICE_KEY` and the tests that name `ava`, and tell the team.
- [ ] **Step 2: Listen to the whole system.** `.venv/bin/python -m app --fake vision hazard`. The hazard fake publishes real `HazardEvent`s; the dashboard's "Simulate alert" button never reaches audio. With the dashboard open: switch to each voice and hear "This is <name>."; let the scripted bottle point be announced; wait for a fake hazard to land during speech. Expected: beeps first, speech cut off, then the hazard phrase (for example "Stop. Obstacle.") in the chosen voice at the calmer rate.
- [ ] **Step 3: Check the fallback.** In System Settings, temporarily remove Matilda, restart, and choose Matilda. Expected: Samantha speaks, the picker says "(not installed)", and Status shows audio degraded. Re-download afterwards.
- [ ] **Step 4: Run the full checks.** `.venv/bin/python -m pytest`, `node --test tests/ui/` and `.venv/bin/ruff check .`. Expected: all pass. Report the real counts.
- [ ] **Step 5: Add a `DEVLOG.md` entry.** Include:
  - what changed;
  - the exact voice ids from Task 1;
  - the by-ear results;
  - the shared-file change awaiting all four teammates' agreement;
  - the setup step for teammates ("download the five voices in System Settings");
  - which agent did the work.

Then commit `devlog: calmer voices`.
