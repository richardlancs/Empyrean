# Verification of the integrated dashboard

Branch `design/light-dashboard-integration`, base `a5ea3afb5871ea636829e34b4a9b45e6f735a26a`.
Merged in order: Agent 1 `399db3222ee99900e76d384131207001241cd039`,
Agent 2 `fb2e1ca536aac05a3bf4fb17d4e6f34fb39eb589`,
Agent 3 `a43b64d4af2202cd2518dab1664cb9df1f06759e`.

## What was and was not tested

| Thing | Tested? | How |
|---|---|---|
| Physical camera (Logitech webcam) | **No** | Recorded/scripted clip only (`--fake vision`) |
| Audible speaker output (JBL Go 3) | **No** | `--fake audio` prints speech; the page labels it "Log-only audio". `audio/` telemetry was tested with stand-in speakers |
| Grok naming or hazard calls | **No** | `--fake namer`, `--fake hazard`; no API key in the environment |
| Tiger Data | **No** | `--fake storage` (in-memory) and a mocked psycopg connection in tests; the live round-trip test is skipped without `TIGER_DATABASE_URL` |
| Real app startup, bus, registration, HTTP, WebSocket, browser UI | **Yes** | `app.start(...)` / `python -m app` with fakes at the hardware and network edges, Chromium via Playwright |
| Screen readers, Firefox, Safari | **No** | Live-region behaviour checked in the DOM only; Chromium only |

## Commands run and results

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` (repo root) | 277 passed, 1 skipped (`test_storage.py` live Tiger Data test, `TIGER_DATABASE_URL` unset) |
| `.venv/bin/python -m ruff check .` | clean |
| `node --test tests/ui/agent1/js/` / `agent2/` / `agent3/` / `agent4/` | 42 / 21 / 16 / 2 passed, 0 failed (also run inside pytest) |
| `python -m app --fake vision namer storage audio` + `node tests/ui/agent4/integrated-check.mjs normal` | 26/26 |
| `python -m app --fake vision namer storage audio hazard` + `... hazard` | 5/5 |
| `python -m app --only dashboard --fake scene` + `... unavailable` | 4/4 |
| `... disconnect` (server stopped, then restarted, with the page open) | 3/3 |

Key Python test files: `tests/test_dashboard_runtime.py` (read model),
`tests/test_engine_telemetry.py` (audio and storage telemetry),
`tests/test_dashboard_api.py` (HTTP, overlays, thumbnails, static, simulation),
`tests/test_dashboard_e2e.py` (real `app.start`, real server and WebSocket).

The end-to-end paths verified:

- **Engine → page:** scripted frames → real scene → `TouchEvent`/`SceneSnapshot` → `bus_adapter` → `DashboardState` → `/ws` → `core/socket-client.js` → store → touch card. The live check compares the touch card text with `/api/state.current_touch` (or `last_touch`), and the screenshot shows the engine's TOUCHING overlay, the touch card and "Speaking now" in the same frame.
- **Page → engine → page:** find form → `ctx.request` → `POST /api/last-seen` → `LastSeenService` → `LastSeenQuery(request_id)` on the bus → fake store → `SpeakRequest` (spoken through fake audio, visible as speech) and `LastSeenResult` → `GET /api/last-seen/{id}` → "Found in touch history, Recorded at …". Concurrent searches (found and not found) are tested in `test_dashboard_e2e.py` and with out-of-order results in `test_dashboard_api.py`.

## Screenshots

All taken from the live app (fakes at the edges), not fixtures, in `screenshots/`:

| File | State |
|---|---|
| `normal-touch-1440.png` | Touching now, TOUCHING overlay, speech "Speaking now" labelled log-only, fake modules labelled |
| `last-touch-found-1440.png` | Search found with recorded time and neighbours |
| `simulated-warning-1440.png` | Simulated warning, purple and labelled, no real warning |
| `hazard-active-1440.png`, `hazard-active-360.png` | Active real warning with the hazard phrase as current speech |
| `unavailable-1440.png` | `--only dashboard`: camera offline, modules not started, audio status unavailable, search disabled with a reason |
| `disconnected-1440.png` | Server stopped: "Dashboard disconnected, reconnecting", statuses "last known" |
| `mobile-360.png` | Full page at 360 px |

Agents 1–3 kept their fixture screenshots under `tests/ui/agent*/screenshots/`.

## Coverage of the 50 recommendations

The numbered list itself was not in Agent 4's brief and is not in the repository.
This table is built from the numbers and titles each agent reported in its
handoff, plus Agent 4's data-dependent items (5, 6, 9, 25, 26, 27, 28, 30, 32,
33, 50). Every number from 1 to 50 is claimed by exactly one feature agent.
"Live" means checked against the running app with `integrated-check.mjs`;
"Agent N" means the owning agent's fixture tests and browser checks.

| # | Recommendation (as reported) | Implementing file / feature | Verification | Unresolved limitation |
|---|---|---|---|---|
| 1 | Light palette, semantic state colours | `styles/tokens.css` (A1) | A1 WCAG contrast tests (both themes); live: light is default, body `#F5F7FA` | — |
| 2 | Warning prominence; neutral empty state that does not imply safety | `operations/warning-panel.js` (A3) | A3 browser checks; live hazard 5/5, screenshot | Active window is the 3 s cooldown; a physically present hazard reads as "Previous" after that |
| 3 | Current touch is the focal point | `experience/touch-card.js` (A2), `current_touch` (A4) | Live: "Touching now" matches backend `current_touch`; screenshot | — |
| 4 | Demo tools secondary and explained | `operations/demo-tools.js` (A3) | A3 checks; live: simulate via disclosure | — |
| 5 | Connection shown separately from module health | `status-strip.js` (A3), `diagnostics` (A4) | Live disconnect/reconnect 3/3; `test_dashboard_runtime.py` | — |
| 6 | Honest camera states (starting, waiting, live, stale, offline) | `camera-panel.js` (A2), `health.py` camera (A4) | `test_camera_health_starting_active_stale_offline_and_reconnect`; live unavailable 4/4, reconnect reopens video | Stale is judged from frame arrival; a frozen camera that keeps sending identical frames is still "live" |
| 7 | Responsive order of panels | `styles/layout.css` (A1) | A1 browser checks; live no horizontal scroll at 360/768/1440 | Some page-background gaps when columns differ in height |
| 8 | Readable type sizes | `tokens.css`, `base.css` (A1) | A1 checks | — |
| 9 | Module health chips from real telemetry; unknown when missing | `status-strip.js` (A3), `health.py` (A4), `ModuleStatus` | `test_dashboard_runtime.py` (quiet scene, not-started, app-vs-module precedence); live: fakes labelled "(fake)" | Hazard checks publish no health, so hazard is always "unknown" unless not started |
| 10 | Announcements once per real event | `core/announcer.js` (A1), keys in A2/A3 | A1/A3 tests (no timer announcements, dedupe) | No screen reader used |
| 11 | Explain the product in the header | `app-shell.js` (A1) | A1 checks; visible in screenshots | — |
| 12 | Layout width and spacing | `layout.css` (A1) | A1 checks | — |
| 13 | Camera presentation (16:9, actual size, full screen) | `camera-panel.js` (A2) | A2 checks | Full-screen fallback link opens raw `/video` without stale labelling |
| 14 | No empty oversized cards | `layout.css` (A1) | A1 checks | — |
| 15 | Consistent component primitives | `components.css` `ui-` (A1) | A1 checks | — |
| 16 | Consistent states and badges | `components.css` (A1) | A1 checks | — |
| 17 | Minimum badge size, sentence case | `tokens.css`/`components.css` (A1) | A1 checks | — |
| 18 | Hierarchy: object name larger than brand | `--text-display` (A1) | A1 checks; screenshot | — |
| 19 | Long object names readable | `object-list.js` (A2) | A2 checks (long names at 360) | — |
| 20 | Full-name toggle with `aria-expanded` | `object-list.js` (A2) | A2 checks | — |
| 21 | Object counts in plain words | `selectors.js` (A2) | A2 tests; live "2 in view" | — |
| 22 | Last-seen wording without decimals | `selectors.js` (A2) | A2 tests | Fake scene script uses 2025 timestamps, so `--fake scene` shows "366 days ago" |
| 23 | Object state labels | `selectors.js` (A2) | A2 tests | — |
| 24 | Lost objects visible but distinct | `object-list.js` (A2) | A2 checks; unavailable screenshot | — |
| 25 | Naming states: pending, named, fallback, failed | `naming_status` in `state.py` (A4), `namingInfo` (A2) | `test_delayed_name_and_naming_status_lifecycle`, `test_pending_name_with_no_answer_stops_claiming_pending` | — |
| 26 | Thumbnails of objects | `thumbnails.py`, `/api/objects/{id}/thumbnail` (A4), `object-list.js` (A2) | `test_thumbnail_*` (expiry, bound, frame match); live: thumbnails load | Thumbnails refresh at most every 5 s |
| 27 | Overlay toggles per view | `/video?boxes&hands&labels` (A4), `camera-panel.js` (A2) | `test_overlay_flags_*`, `test_two_viewers_*`; live two-client check | — |
| 28 | Speech activity from real telemetry | `SpeechStatus` from `audio/` (A4), `selectSpeech` (A2) | `test_engine_telemetry.py` (order, hazard interrupt, log-only = failed, fake mode); live "Log-only audio" | `completed` means the engine returned, not that anyone heard it; never verified on a real speaker |
| 29 | Fit and full-screen controls | `camera-panel.js` (A2) | A2 checks | — |
| 30 | Selected object emphasis on video | `OverlayOptions.selected_id`, `_draw_selected` (A4), selection (A2) | `test_selected_object_has_contrast_on_dark_and_light_frames` | — |
| 31 | Overlay legend | `camera-panel.js` (A2) | A2 checks | — |
| 32 | Camera measurement footer (fps, age, size) | `diagnostics.camera` (A4), footer (A2) | `test_camera_health_*` (fps 5.0, 640×360); live footer "5.0 fps, under 1 s, 640 × 360" | — |
| 33 | Stopped frames flag touch and object data | `last_frame_ts` (A4), freshness (A2) | A2 tests; `test_camera_health_*` | — |
| 34 | Hazard type labels and icons | `selectors.js` (A3) | A3 tests | — |
| 35 | Active vs previous warnings | `warning-panel.js` (A3), `active` flag (A4) | A3 tests; `test_simulated_warning_never_replaces_the_real_one` | — |
| 36 | Real vs simulated warnings, real keeps priority | `latest_real_warning`/`latest_simulated_warning` (A4), warning panel (A3) | `test_simulation_never_reaches_hazard_audio_or_storage`, e2e simulate test; live hazard priority check | — |
| 37 | Source and confidence explained | `source`/`confidence` fields (A4), disclosure (A3) | `test_hazard_entries_carry_source_and_confidence_and_log_size` | — |
| 38 | Group repeated events | `selectors.js` HistoryModel (A3) | A3 tests; live "× 10" grouping | Grouping window is a UI constant (120 s) |
| 39 | Relative time with exact time on demand | `dom.js`, `selectors.js` (A3) | A3 tests | — |
| 40 | Event filters | `event-history.js` (A3) | A3 tests | — |
| 41 | Pause activity view (browser only) | `event-history.js` (A3) | Live: pausing in one client does not affect the other or detection | — |
| 42 | Paused count of new events | `selectors.js` (A3), `event_log_size` (A4) | A3 tests | Inexact when more than 10 events arrive while paused |
| 43 | Clear this view (browser only) | `event-history.js` (A3) | A3 tests | — |
| 44 | Simulate alert progress and errors | `demo-tools.js` (A3) | A3 tests (HTTP 500, network) | — |
| 45 | Simulation is page-only | `POST /api/simulate-alert` unchanged (A4) | `test_simulation_never_reaches_hazard_audio_or_storage` (real Bus, alarm, speaker and store); e2e live | — |
| 46 | Keyboard access, skip link, focus ring | `app-shell.js`, `base.css` (A1) | A1 checks; live: first Tab is the skip link, focus ring `#1D4ED8` | — |
| 47 | 44 px touch targets | `components.css` (A1) | A1 checks | — |
| 48 | Light and high-contrast light themes | `preferences.js`, `theme-boot.js` (A1) | A1 checks (persisted, no flash, blocked storage) | High contrast changes hues to reach 7:1 |
| 49 | Reflow at 360 px and 200 % zoom | `layout.css` (A1) | Live: no horizontal scroll at 360/768/1440 and 720 CSS px at 2× | Real browser zoom not used; a 2× device scale was |
| 50 | Last-touch search: correlated, honest outcomes | `LastSeenService`, `LastSeenResult`, routes (A4), `find-panel.js`/`last-seen.js` (A2) | `test_last_seen_*`, `test_concurrent_searches_*`, `test_store_*`, e2e round trip; live found and not found | Storage-down speech still says "I have not seen that."; the page says unavailable |

## Fixes made during integration

| Problem found | Where | Fix |
|---|---|---|
| Storage and audio status sent while registering was lost | `app/__main__.py` | Dashboard registers first |
| Empty thumbnail cache replaced by a new one (`len` 0 is falsy) | `dashboard/server.py` | Explicit `is None` fallbacks |
| A released object would show as touched in Agent 2's card | `dashboard/state.py` | `current_touch` null after release; `last_touch` added |
| Status strip showed fakes as plain "Active", "5 of 5 modules active" | `operations/selectors.js` (A3 file) | "(fake)" label and "N running as fakes" |
| Camera panel said "Live" for the recorded clip | `experience/selectors.js` (A2 file) | "Live (recorded clip, not a camera)" |
| Search offered while storage was not started | `dashboard/state.py` | `capabilities.last_seen` false then |
| Dashboard refused to start after a restart with a page open | `dashboard/server.py` | Port probe uses `SO_REUSEADDR` (not Windows) |
| CLI test flaked on cold audio startup | `tests/test_app_p1.py` | Waits for the first frame line, 20 s deadline |
