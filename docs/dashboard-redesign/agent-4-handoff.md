# Agent 4 handoff: runtime data, API, integration

**Status: READY** (integration complete; not merged into `main`)

| | |
|---|---|
| Base commit | `a5ea3afb5871ea636829e34b4a9b45e6f735a26a` (verified against `origin`, `richardlancs/Empyrean`) |
| Branch | `design/light-dashboard-integration` |
| Worktree | `../empyrean-design-4` |
| Agent | Claude Code (Claude Opus 5.5) |
| Merged | Agent 1 `399db3222ee99900e76d384131207001241cd039`, then Agent 2 `fb2e1ca536aac05a3bf4fb17d4e6f34fb39eb589`, then Agent 3 `a43b64d4af2202cd2518dab1664cb9df1f06759e`. No conflicts |

The implemented API is in [api.md](api.md); test results, screenshots and the
50-row coverage table are in [verification.md](verification.md).

## What Agent 4 changed

| Area | Files |
|---|---|
| Contracts (additive) | `contracts/messages.py`, `contracts/__init__.py`: `LastSeenQuery.request_id`, `LastSeenResult`, `SpeechStatus`, `ModuleStatus` |
| Config / spec | `config/thresholds.py` (3 dashboard values), `SPEC.md` sections 2.1, 4.9, 5, 9; `AGENTS.md` stack row |
| Audio | `audio/audio.py`, `audio/backends.py`, `fakes/audio/fake_audio.py`: speech and module telemetry, honest `mode` |
| Storage | `storage/writer.py`, `storage/__init__.py`, `storage/_deps.py`, `fakes/storage/fake_store.py`: correlated results, availability |
| App | `app/__main__.py`: lifecycle `ModuleStatus`, dashboard registered first |
| Dashboard backend | `dashboard/server.py`, `state.py`, `video.py`, `thumbnails.py`, `bus_adapter.py`, `api/{routes,realtime,schemas}.py`, `services/{health,last_seen,heartbeat,container}.py` |
| Tests | `tests/test_dashboard_{runtime,api,e2e}.py`, `tests/test_engine_telemetry.py`, `tests/ui/agent4/` (node tests and live browser check); edits to `test_contracts.py`, `test_dashboard.py`, `test_app_p1.py` (reasons in verification.md) |
| Docs | `docs/dashboard-redesign/{api,verification,agent-4-handoff}.md`, screenshots, `DEVLOG.md` |

### Edits to other agents' files after merging

| File | Change | Why |
|---|---|---|
| `dashboard/static/features/operations/selectors.js` (Agent 3) | `selectHealth` adds "(fake)" to fake modules and "N running as fakes" to the summary | The strip showed fake storage and audio as plain "Active" |
| `dashboard/static/features/experience/selectors.js` (Agent 2) | `selectCamera` titles a fake camera "Live (recorded clip, not a camera)" | The panel said "Live" for the test clip |

Both are covered by `tests/ui/agent4/integration.test.mjs`; the owners' own tests still pass.

## Answers to integration requests

- **Agent 1 A1** (`/static` mount, `/` serves `index.html`): done, with explicit JS/CSS MIME types and `no-store` on `/`. **A2** (page-text test): `test_page_has_button_and_both_areas` now follows the labels through `/` and the served modules. **A3** (DEVLOG): consolidated.
- **Agent 2**: every field and endpoint listed is implemented. `current_touch` is `null` when nothing is in a hand; the released object is in `last_touch`. `request_id` is a 32-character hex string. `/video` ignores unknown params. `thumbnail_url` changes at most every 5 s. The server search timeout is 8 s, so the page normally gets `unavailable` before its own 10 s timeout.
- **Agent 3**: `latest_real_warning`, `latest_simulated_warning` (each with `active`), `source` and `confidence` on every hazard entry, `event_log_size`, `diagnostics` with `camera.stale_after_seconds`; simulate still returns the full snapshot and publishes nothing. Idle naming is `starting` for the first 10 s and then `unknown` ("Idle: no naming requests yet"), never `failed`; it is not `active`, because the namer reports no health of its own.

## DEVLOG entry

Consolidated in `DEVLOG.md` (2026-11-14 14:00), with the contract changes row.

## Remaining limitations

- Not tested with the physical camera, an audible speaker, Grok, or Tiger Data (see verification.md).
- When the database is down, the spoken last-seen answer is still "I have not seen that." (existing behaviour kept). The page correctly shows `unavailable`. Changing the spoken sentence is a product decision.
- Hazard checks publish no health; the hazard entry is `unknown` unless not started.
- `--fake scene` uses 2025 timestamps, so its objects show as a year old.
- Still open in DEVLOG "Needs attention": with `--fake hazard`, the fake hazard starts before audio subscribes, so its first event can miss audio.
- The browser check needs a local or global Playwright with Chromium; it is not a project dependency and is not run by `pytest`.
