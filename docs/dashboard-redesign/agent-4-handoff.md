# Agent 4 handoff: runtime data, API, integration

**Status: READY** for review. Software verification is complete; hardware and
external-service checks are outstanding (section 4). Not merged into `main`.

| | |
|---|---|
| Base commit | `a5ea3afb5871ea636829e34b4a9b45e6f735a26a` (verified against `origin`, `richardlancs/Empyrean`) |
| Branch | `design/light-dashboard-integration` |
| Verified commit | `b03372329426897b69325181eb164773d965a872` (code and tests; this handoff is committed on top of it) |
| Worktree | `../empyrean-design-4` |
| Agent | Claude Code (Claude Opus 5.5) |
| Merged | Agent 1 `399db3222ee99900e76d384131207001241cd039`, then Agent 2 `fb2e1ca536aac05a3bf4fb17d4e6f34fb39eb589`, then Agent 3 `a43b64d4af2202cd2518dab1664cb9df1f06759e`. No conflicts |

The API is in [api.md](api.md). Test detail, screenshots and the 50-row audit are
in [verification.md](verification.md).

## 1. What Agent 4 changed

| Area | Files |
|---|---|
| Contracts (additive) | `contracts/messages.py`, `contracts/__init__.py`: `LastSeenQuery.request_id`, `LastSeenResult`, `SpeechStatus`, `ModuleStatus` |
| Config / spec | `config/thresholds.py` (3 dashboard values), `SPEC.md` 2.1, 4.9, 4.10, 5, 9; `AGENTS.md` stack row |
| Audio | `audio/audio.py`, `audio/backends.py`, `fakes/audio/fake_audio.py`: speech and module telemetry, honest `mode` |
| Storage | `storage/writer.py`, `storage/last_seen.py`, `storage/__init__.py`, `storage/_deps.py`, `fakes/storage/fake_store.py`: correlated results, availability, spoken outage sentence |
| App and fakes | `app/__main__.py` (lifecycle status, dashboard first, deferred fake start); `fakes/hazard`, `fakes/vision` (`register(bus, start=False)`); `fakes/scene/script.py` (current timestamps) |
| Dashboard backend | `dashboard/server.py`, `state.py`, `video.py`, `thumbnails.py`, `bus_adapter.py`, `api/{routes,realtime,schemas}.py`, `services/{health,last_seen,heartbeat,container}.py` |
| Tests | `tests/test_dashboard_{runtime,api,e2e}.py`, `tests/test_engine_telemetry.py`, `tests/test_fake_start_order.py`, `tests/ui/agent4/` (node tests, live browser check); edits to `test_contracts.py`, `test_dashboard.py`, `test_app_p1.py`, `test_storage.py`, `test_register.py`, `test_scene.py` |
| Docs | `api.md`, `verification.md`, this file, screenshots, `DEVLOG.md` |

### Edits to Agents 1–3's files after integration

| File (owner) | Change | Why |
|---|---|---|
| `core/api-client.js` (A1) | Timeout and caller signal stay armed while the body is read | A response whose body never finished hung forever |
| `features/experience/last-seen.js` (A2) | Normalised ids; one overall deadline that aborts in-flight requests; settled guard; neighbours | Numeric ids never matched; hanging requests never timed out; late answers could replace a timeout |
| `features/experience/find-panel.js` (A2) | "Recorded next to: …" | Prompt asks for the known neighbours |
| `features/experience/index.js` (A2) | Camera does not announce a lost dashboard connection | Shell owns connection announcements |
| `features/experience/selectors.js` (A2) | "Live (recorded clip, not a camera)" | Fake clip shown as live camera |
| `features/experience/experience.css` (A2) | Shell token names; control border width token | Features ignored high contrast |
| `features/operations/index.js` (A3) | Connection announcements removed; warning emphasis set and cleared | Duplicate announcements; emphasis hook unused |
| `features/operations/selectors.js` (A3) | `warningEmphasis()`; "(fake)" labels and fake count | Hook logic; fakes shown as plain "Active" |
| `features/operations/operations.css` (A3) | Shell token names; `data-theme="high-contrast"`; OS media query removed (the shell decides) | Features ignored high contrast or contradicted the user's choice |
| `tests/ui/agent3/fixture-tokens.css`, `harness.js` (A3) | Harness uses the real tokens and `data-theme` | Harness exercised names production does not define |

Every change has a regression test in `tests/ui/agent4/` or the live browser
check, and the owners' own tests still pass.

## 2. Answers to integration requests

- **Agent 1:** A1 static mount with JS/CSS MIME types and `no-store` on `/`; A2 page-text test follows the served modules; A3 DEVLOG consolidated; A5's emphasis hook and "do not announce connection changes" are now implemented in the operations feature.
- **Agent 2:** all fields and endpoints. `current_touch` is null when nothing is in a hand (`last_touch` holds the released object); ids may be strings or numbers (now normalised); `/video` ignores unknown params; thumbnails change at most every 5 s; the server search timeout (8 s) is shorter than the page deadline (10 s).
- **Agent 3:** `latest_real_warning`/`latest_simulated_warning` with `active`, `source` and `confidence`, `event_log_size`, `camera.stale_after_seconds`; simulate publishes nothing. Idle naming is `starting` then `unknown`, never `failed`.

## 3. Software verification (complete)

On `b03372329426897b69325181eb164773d965a872`:

| Check | Result |
|---|---|
| `pytest -q` | 281 passed, 1 skipped (live Tiger Data test; no `TIGER_DATABASE_URL`) |
| `ruff check .` | clean |
| `node --test` agent1 / agent2 / agent3 / agent4 | 42 / 21 / 16 / 12 passed |
| Live Chromium, real shell and feature modules, `python -m app` with fakes | normal 49/49, hazard 8/8, unavailable 4/4, disconnect and reconnect 6/6 |

New regression tests were run against the pre-fix code and fail there (search
deadline and ids, first hazard to audio, theme colours).

## 4. Hardware and service checks (outstanding)

Not done: the physical camera with real YOLO and MediaPipe; audible speech and
alarm on the JBL Go 3; Grok naming and hazard calls; Tiger Data writes and
queries; screen readers, Firefox, Safari and real browser zoom. Suggested order on
the real laptop: `python -m app` with `.env` set, confirm the camera chip shows
"Active" without "(fake)", touch an object and listen, search for it, then stop
the database to confirm "Touch history is unavailable right now." is both spoken
and shown.

## 5. Remaining limitations

- #13 and #29 are partial: where fullscreen is unsupported, the fallback opens raw `/video` without stale-frame labelling.
- Hazard checks report no health, so the hazard entry is `unknown` unless not started.
- A camera sending identical frames still reads as current (only timestamps are checked).
- The browser check needs a local or global Playwright with Chromium; it is not a project dependency and pytest does not run it.
