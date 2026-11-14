# Verification of the integrated dashboard

Branch `design/light-dashboard-integration`, base `a5ea3afb5871ea636829e34b4a9b45e6f735a26a`.
Merged in order: Agent 1 `399db3222ee99900e76d384131207001241cd039`,
Agent 2 `fb2e1ca536aac05a3bf4fb17d4e6f34fb39eb589`,
Agent 3 `a43b64d4af2202cd2518dab1664cb9df1f06759e`. The final commit is given in
[agent-4-handoff.md](agent-4-handoff.md).

## 1. Software verification (done)

Everything below ran on macOS, Python 3.11.18, Node 26.13, Chromium (Playwright
1.64), with fakes only at the hardware and network edges: recorded camera clip,
fake namer, in-memory store (or the real storage module with no database),
printed speech, scripted hazards. The bus, scene, `app.start`/`python -m app`,
dashboard services, HTTP server, WebSocket, shell and feature modules are real.

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` (repo root) | all pass except 1 skip: the live Tiger Data test (no `TIGER_DATABASE_URL`). Count in the handoff |
| `.venv/bin/python -m ruff check .` | clean |
| `node --test tests/ui/agent1/js/` / `agent2/` / `agent3/` / `agent4/` | 42 / 21 / 16 / 12, all passing (also run inside pytest) |
| `python -m app --fake vision namer storage audio` + `node tests/ui/agent4/integrated-check.mjs normal` | 49/49 |
| `python -m app --fake vision namer storage audio hazard` + `... hazard` | 8/8 |
| `python -m app --only dashboard --fake scene` + `... unavailable` | 4/4 |
| `... disconnect` (server stopped, then restarted, with the page open) | 6/6 |

What the live checks prove, end to end:

- **Engine → page:** a real scene `TouchEvent` reaches the touch card through the read model, `/ws` and the store; the card text matches `/api/state`. The touch screenshot shows the engine's TOUCHING overlay, the "Touching now" card and "Speaking now" at the same moment.
- **Page → engine → page:** the find form's search goes through `POST /api/last-seen` → `LastSeenService` → bus → store → `SpeakRequest` + `LastSeenResult` → "Found in touch history", recorded time and recorded neighbours.
- **Spoken and shown agree:** with the real storage module and no database, the page and the spoken phrase are both "Touch history is unavailable right now." (`test_unavailable_history_is_spoken_and_shown_the_same`); "I have not seen that." appears only for a query that ran and matched nothing.
- **Hanging requests:** a POST or GET that never answers ends at the 10 s search deadline in the real UI (Playwright holds the request open). A response whose body never finishes was tested against the real `core/api-client.js` in Node (`tests/ui/agent4/last-seen.test.mjs`); Playwright cannot stream a never-ending body.
- **Themes:** in light and high-contrast, feature colours equal the shell's resolved tokens (`--color-text`, `--color-accent`, `--color-border-control`) and text contrast is at least 4.5:1. With the pre-fix stylesheets this check fails in high contrast (verified), because the features had fallen back to light values.
- **Warning emphasis:** `#warning-panel[data-emphasis]` is `urgent` for an active real warning (also after a later simulation), `simulated` for a simulation alone, absent when nothing is active, and removed by the page's cleanup.
- **Announcements:** on disconnect and reconnect the live regions receive exactly one "Dashboard connection lost. Reconnecting." and one "Dashboard connection restored.", both from the shell; no feature repeats them.
- **First fake hazard:** with deferred fake publishers the first scripted hazard (vehicle, yolo) reaches audio (live log and `test_first_scripted_hazard_reaches_audio`, which fails without the fix).
- Two clients keep separate view-only controls; light mode is the default; no horizontal scroll at 360/768/1440 px or 720 CSS px at 2× scale; reduced motion; no console errors.

## 2. Hardware and service checks (outstanding)

| Check | Status |
|---|---|
| Physical camera (Logitech webcam) with real YOLO and MediaPipe | **Not done.** Only the recorded/scripted clip |
| Audible speech and alarm on the JBL Go 3 (pyttsx3, pygame) | **Not done.** Speech was printed by the fake; `audio/` telemetry was tested with stand-in speakers |
| Grok naming and Grok hazard calls | **Not done.** No API key; fake namer and scripted hazards |
| Tiger Data writes and last-seen queries | **Not done.** In-memory fake store, mocked psycopg, and the real storage module with no database (outage path) |
| Screen readers (VoiceOver, NVDA), Firefox, Safari, real browser zoom | **Not done.** Live-region DOM content and Chromium only; 200 % zoom approximated by a 2× device scale |

## 3. Screenshots (live app, fakes at the edges)

`screenshots/`: `normal-touch-1440.png`, `last-touch-found-1440.png`,
`simulated-warning-1440.png`, `high-contrast-1440.png`, `hazard-active-1440.png`,
`hazard-active-360.png`, `unavailable-1440.png`, `disconnected-1440.png`,
`mobile-360.png`. Agents 1–3 keep their fixture screenshots under
`tests/ui/agent*/screenshots/`.

## 4. Coverage of the 50 recommendations, audited against the original prompts

Owners come from the original Agent 1–3 prompts (Agent 1: 1, 7, 8, 11, 12, 14–18,
46–49; Agent 2: 3, 6, 13, 19–33, 50; Agent 3: 2, 4, 5, 9, 10, 34–45); together they
cover all 50. Agent 4 supplied the data for 5, 6, 9, 25–28, 30, 32, 33 and 50.
"Complete" means every requirement in the prompt's item is implemented;
"Partial" names exactly what is missing. Verification gaps that apply to all rows
(hardware, screen readers, other browsers) are in section 2.

| # | Requirement (original prompt) | Implementation | Verification | Status / limitation |
|---|---|---|---|---|
| 1 | Shared light tokens; teal touch, red urgent, purple simulation | `styles/tokens.css` | A1 contrast tests; live: light default, features resolve shell tokens | Complete. Features followed the tokens only after this pass (item 3) |
| 2 | Compact neutral inactive warning; prominent active real hazard, no permanent empty card | `operations/warning-panel.js` | Live hazard and normal runs | Complete |
| 3 | Object name is the largest text; Touching/Holding; no stale object as current; "Last touched" separate | `experience/touch-card.js`, `current_touch` null after release | `test_touch_hold_release_retouch_drives_current_touch`; live | Complete |
| 4 | Simulate alert inside a secondary "Demo tools" disclosure with the given explanation | `operations/demo-tools.js` | A3 tests; live | Complete |
| 5 | Connection shown separately from camera freshness and module health; no ambiguous "Live" | `status-strip.js`, `diagnostics` | Live disconnect; camera says "Live (recorded clip, not a camera)" for the fake | Complete |
| 6 | Camera startup, first frame, current, disconnected, stale from real frame times | `camera-panel.js`, `services/health.py` | `test_camera_health_*`; live unavailable and reconnect | Complete. Identical frames that keep arriving still count as current (not detectable from timestamps) |
| 7 | Mobile order: header, health, warning, touch, camera, objects, search, activity, demo; desktop camera + 360–420 px column; active warning stays visible | `layout.css`, emphasis hook | A1 checks; live widths; `urgent` pins the warning slot | Complete. The pin was not wired until this pass (item 2) |
| 8 | 17–18 px body text | `tokens.css` (17 px) | A1 checks | Complete |
| 9 | Compact module summary (camera, scene, naming, storage, audio) from telemetry; unknown states; idle naming not failed | `status-strip.js`, `health.py`, `ModuleStatus` | `test_dashboard_runtime.py`; live; fakes labelled "(fake)" | Complete |
| 10 | New warnings announced once; ages never re-announce; reconnect replays deduplicated | announcer keys in A3 | A3 tests; live announcement log | Complete. Duplicate connection announcements removed this pass (item 1) |
| 11 | "Touch an object. Hear its name." and a restrained Prototype label | `app-shell.js` | Screenshots | Complete |
| 12 | About 1440 px max width, gutters, flexible columns | `layout.css` | A1 checks | Complete |
| 13 | Preserve aspect ratio; fit and fullscreen with fallback | `camera-panel.js` | A2 checks | **Partial:** where fullscreen is unsupported the fallback opens raw `/video` in a new tab, which has no stale-frame labelling |
| 14 | No large unproductive empty panels | `layout.css` (`.app-slot:empty`) | A1 checks | Complete. Page background can show beside a shorter column; no empty panels |
| 15 | Shared spacing, surface, border, radius, button, chip, field, empty and loading primitives | `components.css` | A1 checks | Complete. Features use their own scoped classes on the same tokens |
| 16 | Ornament subordinate to the task | `components.css` | Screenshots | Complete |
| 17 | Sentence-case titles, readable badges (≥ 13 px) | `tokens.css`, `components.css` | A1 checks | Complete |
| 18 | Object name more prominent than the brand | `--text-display` | Screenshots | Complete |
| 19 | Long names: two-line summary and accessible full name | `object-list.js` | A2 checks at 360 px | Complete |
| 20 | User-facing states New, In view, Touching, Holding, Temporarily lost; raw state kept in data | `selectors.js` | A2 tests | Complete |
| 21 | Meaningful in-view count; lost items not counted as visible without explanation | `selectors.js` | A2 tests; live "2 in view" | Complete |
| 22 | "Last seen" label | `object-list.js` | A2 tests | Complete. Fake scene now uses current times, so ages are realistic |
| 23 | Calm human intervals, no changing decimals | `selectors.js` | A2 tests | Complete |
| 24 | Lost items remain readable | `object-list.js` | A2 checks; unavailable screenshot | Complete |
| 25 | Naming in progress, specific, generic fallback and failure from naming status | `naming_status` in `state.py`, `namingInfo` | `test_delayed_name_and_naming_status_lifecycle` | Complete |
| 26 | Bounded recent crops; alternatives; no per-frame downloads or leaks | `thumbnails.py`, `/api/objects/{id}/thumbnail`, `object-list.js` | `test_thumbnail_*`; live thumbnails load | Complete. A crop refreshes at most every 5 s |
| 27 | Selecting an object highlights its box by stable id; no detection rerun | `OverlayOptions.selected_id` | `test_selected_object_*`, `test_two_viewers_*` | Complete |
| 28 | Speech status only from audio telemetry; "Last speech completed"; fake/log-only distinguished; "Audio status unavailable" without telemetry | `SpeechStatus` from `audio/`, `selectSpeech` | `test_engine_telemetry.py`; live "Log-only audio" | Complete. Never observed on a real speaker |
| 29 | Fit and fullscreen controls, keyboard access | `camera-panel.js` | A2 checks | **Partial:** same fullscreen fallback gap as #13 |
| 30 | Toggles for boxes, hand markers and labels, presentation only | `/video?boxes&hands&labels` | `test_overlay_flags_*`; live two-client check | Complete |
| 31 | Small understandable legend | `camera-panel.js` | A2 checks | Complete |
| 32 | Footer with measured fps, frame age and size; unknown stays unknown | `diagnostics.camera` | `test_camera_health_*`; live "5.0 fps · under 1 s · 640 × 360" | Complete |
| 33 | Stale image marked; touch and object data flagged when frames stop | `last_frame_ts`, A2 freshness | A2 tests; `test_camera_health_*` | Complete (same identical-frame caveat as #6) |
| 34 | Distinct hazard text and icons | `selectors.js` | A3 tests | Complete |
| 35 | Active vs "Previous warning"; expiry never claims the hazard is gone | `warning-panel.js`, `active` flag | A3 tests | Complete |
| 36 | Simulated purple with persistent label; never displaces an active real warning | `latest_real_warning`/`latest_simulated_warning`, warning panel | `test_simulation_never_reaches_hazard_audio_or_storage`; live priority and emphasis checks | Complete |
| 37 | Description first; source and confidence in a disclosure; confidence not presented as safety probability | `source`/`confidence` fields, disclosure | `test_hazard_entries_carry_source_and_confidence_and_log_size` | Complete |
| 38 | Group repeats with count and occurrence times; underlying events and cooldown untouched | HistoryModel | A3 tests; live "× N" | Complete |
| 39 | Relative time with exact time on focus, click and hover | `dom.js` | A3 tests | Complete |
| 40 | All / Touch / Warning filters with selected state and empty messages | `event-history.js` | A3 tests | Complete |
| 41 | Pause freezes only this panel | `event-history.js` | Live: other client and detection unaffected | Complete |
| 42 | Reliable new-event count while paused, or say it is inexact | HistoryModel, `event_log_size` | A3 tests | Complete. Inexact (and said so) past 10 events |
| 43 | Clear this view affects only this browser | `event-history.js` | A3 tests | Complete |
| 44 | Progress, success, HTTP and network failure; controls re-enable | `demo-tools.js` | A3 tests | Complete |
| 45 | Result through the same renderer, deduplicated; never a real HazardEvent | simulate route unchanged | `test_simulation_never_reaches_*`; e2e | Complete |
| 46 | Visible focus, landmarks, skip link, button types, labels | `app-shell.js`, `base.css` | Live: first Tab is the skip link, focus ring `#1D4ED8` | Complete |
| 47 | Generous targets | `components.css` (44 px) | A1 checks | Complete |
| 48 | Persisted light / high-contrast-light; storage failures; no flash | `preferences.js`, `theme-boot.js` | A1 checks; live theme check | Complete. Before this pass the features ignored high contrast (item 3) |
| 49 | 200 % zoom and narrow screens without clipping or page scroll | `layout.css` | Live widths and 2× scale | Complete (real browser zoom not used) |
| 50 | Discoverable search; explanation; loading, found, not found, unavailable, timeout, retry; correlation; recorded time and neighbours; no invented location | `LastSeenService`, `LastSeenResult`, `last-seen.js`, `find-panel.js` | `tests/ui/agent4/last-seen.test.mjs`, `test_last_seen_*`, e2e; live found with neighbours | Complete. Id normalisation, the overall deadline and the neighbours line were added this pass (item 4) |

Partial: **#13 and #29** (fullscreen fallback without stale labelling). All other
recommendations are complete in software; none is verified on hardware.

## 5. Fixes made during integration

| Problem | Where | Fix |
|---|---|---|
| Module status sent while registering was lost | `app/__main__.py` | Dashboard registers first |
| Empty thumbnail cache replaced (`len` 0 is falsy) | `dashboard/server.py` | Explicit `is None` |
| A released object looked touched | `dashboard/state.py` | `current_touch` null after release; `last_touch` |
| Fakes shown as plain "Active"; test clip shown as "Live" | A3/A2 selectors | "(fake)", "running as fakes", "Live (recorded clip, not a camera)" |
| Search offered with storage not started | `dashboard/state.py` | `capabilities.last_seen` false |
| Dashboard refused to start after a restart with a page open | `dashboard/server.py` | `SO_REUSEADDR` port probe (not Windows) |
| CLI test flake | `tests/test_app_p1.py` | Waits for the first frame |
| Connection announced by shell, operations and camera | A3 `index.js`, A2 `index.js` | Shell only |
| Warning emphasis hook never set | A3 `index.js`, `selectors.js` | `urgent` / `simulated` / none; cleared on cleanup |
| Features used token names the shell does not define, so high contrast never applied | A2/A3 CSS, A3 harness | Shell names and `data-theme="high-contrast"` |
| Numeric `request_id` never matched; hanging requests never timed out; late answers could replace a timeout | A2 `last-seen.js`, A1 `api-client.js` | Normalised ids, overall deadline with abort, settled guard; timeout covers body reading |
| Storage outage spoken as "I have not seen that." | `storage/writer.py` | "Touch history is unavailable right now."; result answer equals speech |
| First scripted hazard missed audio; fake scene dated 2025 | `app/`, `fakes/` | Deferred fake start; current timestamps |
| Neighbours of a found item not shown | A2 `last-seen.js`, `find-panel.js` | "Recorded next to: …" |
