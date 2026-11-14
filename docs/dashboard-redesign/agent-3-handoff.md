# Agent 3 handoff: hazards, system status, activity, demo controls

**Status: READY**

| | |
|---|---|
| Base SHA | `a5ea3afb5871ea636829e34b4a9b45e6f735a26a` (verified as origin `richardlancs/Empyrean`) |
| Branch | `design/alerts-history` (no suffix needed) |
| Worktree | `../empyrean-design-3` |
| Agent | Claude Code (Claude Opus 5.5) |
| Date | 2026-11-14 |

## What is delivered

`dashboard/static/features/operations/` exports `mountOperations(ctx)` from `index.js` and returns a cleanup function. It renders only into `ctx.roots.health`, `.warning`, `.events` and `.demo`.

| File | Layer | Role |
|---|---|---|
| `index.js` | Controller | Subscribes to the store, folds snapshots into view state, announces, routes demo requests through `ctx.request`, builds models for the components, runs a 1 s relative-time tick (never announced). |
| `selectors.js` | Presenter (pure) | Event identity, warning selection, health model, `HistoryModel` (bounded, pause, clear), grouping, filters, time formatting, copy. No DOM, no network. |
| `status-strip.js` | Component | Connection line, five module chips, summary, "Status details" disclosure. |
| `warning-panel.js` | Component | Neutral "No recent warnings" line, active real card, simulated card (compact when beside a real one), "Previous warning" rows. |
| `event-history.js` | Component | All / Touch / Warning filters, Pause activity view, Clear this view, paused and cleared notices, keyed grouped list. |
| `demo-tools.js` | Component | "Demo tools" disclosure, explanation, Simulate alert, progress and result line. |
| `dom.js` | Helpers | `el()` (text only through `textContent`), icons, time toggle, focus preservation. |
| `operations.css` | Styles | Everything prefixed `operations-`. |

Components get data and callbacks only. No component opens a socket or calls `fetch`; a pytest guard enforces this.

## Recommendations completed

| # | How |
|---|---|
| 2 | When nothing is active the panel shows one line: "No recent warnings. This does not mean the path is clear." There is no reserved empty card. An active real warning gets a red card with a thick left border, an icon, an "Active warning" badge, a 28px title and a description. |
| 5 | The connection line ("Dashboard connected" / "Connecting to dashboard" / "Dashboard disconnected, reconnecting") is separate from the module chips. While disconnected, every module shows "(last known)" and loses its green tone. Status details state that a connection does not prove anyone heard anything. |
| 9 | Chips for Camera, Object tracking, Naming, Storage and Audio come from `state.diagnostics`. A missing entry or missing `diagnostics` shows "Unknown". Camera freshness comes from `last_frame_ts`. An idle naming service still shows Active ("quiet periods are normal"). Details list the backend `detail`, last update, fps and size. |
| 10 | Each warning is announced once, keyed by `hazard|real/sim|type|ts|source`. Real warnings are assertive and simulated ones polite. Warnings that are replayed or already expired (page load, reconnect) are shown but not announced. The announced-key memory is bounded at 300. Timer ticks never announce, and no `aria-live`/`role=status` exists inside the four roots (browser-tested). Focus is preserved with keyed reconciliation, and the time buttons' accessible names don't tick. |
| 34 | Each type has its own label, description and icon: Stairs down, Drop ahead, Vehicle, Obstacle. An unknown type degrades to "Warning". |
| 35 | Active cards are kept separate from the "Previous warning" / "Previous simulated warning" rows. Expiry wording says "Previous", never "cleared" or "safe". |
| 36 | Simulated warnings are purple with a dashed border and a persistent "Simulated" badge. The flask icon appears in the warning, history ("Simulated warning" kind) and announcement text. A real warning that is still active stays first and full size, and the simulation becomes a compact card under it. This also works on today's server, which keeps only one `latest_warning`: the real warning is recovered from the event log or from view memory. |
| 37 | The description comes first. "Source and confidence" is a disclosure. Confidence carries the note: "How sure the detector was about this report. It is not the chance that the area is safe or dangerous." |
| 38 | Consecutive repeats (same kind, same type or name, same real/sim flag, within 120 s) become one row with "× N" and a "Show all N times" list. Group identity follows the oldest occurrence, so the row doesn't remount as repeats arrive. Underlying events are kept, and nothing touches cooldown or the runtime. |
| 39 | Relative time ("12 s ago"). The exact time shows on hover, keyboard focus or click (pinned, `aria-expanded`). The accessible name is "At HH:MM:SS". |
| 40 | The All / Touch / Warning buttons use `aria-pressed` and a ✓ plus filled style. Each filter has its own empty message. |
| 41–43 | Pausing freezes only this list. The notice gives an exact new-event count, or "At least N … Some may have been missed" when a full server log arrives with no overlap. Resume returns focus to the pause button. "Clear this view" hides currently known events in this browser only. New events still appear, "Show cleared activity" restores them, and the warning panel is unaffected. Browser memory is capped at 100 events. Server history is untouched. |
| 4, 44, 45 | Simulate alert lives inside a "Demo tools" disclosure with the required explanation, which is also linked by `aria-describedby`. It shows progress ("Adding simulated warning…", `aria-busy`, `aria-disabled` so focus stays), success with time, HTTP failure ("The server refused the request (HTTP 500)…"), and network failure. The result is ingested through the same path as socket snapshots and deduplicated by key when the socket echoes it (browser-tested: one row, one announcement). The feature only POSTs `/api/simulate-alert`, which publishes nothing on the bus. |

## Tests run (in this worktree)

- `.venv/bin/python -m pytest -q` (whole repo): **188 passed, 1 skipped**. The skip is `tests/test_storage.py:236`, because TIGER_DATABASE_URL is not set, and it predates this change.
- `tests/ui/agent3/test_agent3_operations_ui.py` (part of the above, 6 tests): files exist, no `WebSocket`/`fetch`/`innerHTML`/`speechSynthesis` in the feature, CSS fully scoped, no safety claims, required demo text present, and the node unit tests pass.
- `node --test tests/ui/agent3/`: **16/16** for the selectors (identity, real-vs-sim priority on old and new server shapes, expiry, confidence wording, unknown telemetry, last-known while disconnected, camera freshness, replay dedupe, bounded memory, exact and inexact pause counts, clear and restore, grouping, filters, time).
- `node tests/ui/agent3/e2e.mjs` against the fixture harness in headless Chromium 1248: **24/24**. Covered: real and simulated together; replay and reconnect not re-announcing; expired warnings on load; quiet expiry; simulate success with socket echo; HTTP 500; network failure; a real warning staying first while demo tools are used; pause, count and focus; inexact count; clear, new and restore; grouping; filters; exact time on focus and click; unknown telemetry; partial failure; no live regions; keyboard reach with a visible focus outline; 44px targets; no horizontal overflow at 360, 720 (1440 at 200%), 768 and 1440 with long names; text contrast ≥ 4.5:1 for every visible text node in default and `prefers-contrast: more`; and cleanup.
- `ruff check` / `ruff format` on the new Python test file: clean.

How to rerun the browser checks. Neither package is a project dependency.

```
python3 -m http.server 8793 --bind 127.0.0.1            # repo root
PLAYWRIGHT_CORE=<path>/playwright-core/index.mjs CHROMIUM=<chrome binary> node tests/ui/agent3/e2e.mjs
```

Screenshots were taken locally (not committed): real+simulated, expired, repeated, paused, partial failure, simulate success and HTTP failure at 1440, long names at 360/720/768/1440, and both contrast modes.

**Not verified:** the real shell (Agent 1), the real store, socket and announcer, the real backend fields from Agent 4, hardware, audio and the database. Everything above ran against fixtures. Reduced motion: the feature has no animations or transitions, and a reduced-motion guard is included.

## Fixture harness

Open `tests/ui/agent3/harness.html` (see the command above). It has a striped "FIXTURE HARNESS" banner, a dashed fixture-control area, "FIXTURE …" object names and a visible log of every `ctx.announce` call. It covers nine scenarios plus push, burst, replay and reconnect actions, connection and request-failure modes, and a high-contrast toggle. `fixture-tokens.css` is a stand-in for Agent 1's tokens and is not production code.

## API assumptions (shared contract)

- `ctx.subscribe(cb)` calls `cb({state, connection, receivedAt})` immediately and on every update. The same state may be delivered again; the feature dedupes by key.
- `ctx.request(path, {method})` resolves with the JSON body.
- `ctx.announce(text, {priority, key})` dedupes by key. Keys I send:
  - warnings: `hazard|real|stairs_down|<ts>|<source>`
  - user-action and connection keys: `activity-pause-N`, `connection-lost-N`, …
  - module transitions: `module|<id>|<status>|<last_update_ts>`
- State fields used (all optional, all degrade):
  - `now`, `hazard_active_seconds`, `latest_warning`, `latest_real_warning`, `latest_simulated_warning`, `events[]` (`ts, kind, type, text, detail, simulated`, optional `source`, `confidence`, `object_id`)
  - `event_log_size` (optional; defaults to 10)
  - `diagnostics.{camera,scene,naming,storage,audio}.{status, detail, last_update_ts}`, plus camera `last_frame_ts, fps, width, height` and optional `stale_after_seconds` (default 2 s)
- Token names used, with spec hex fallbacks:
  - colours: `--color-bg`, `--color-surface`, `--color-text`, `--color-text-secondary`, `--color-border`, `--color-border-strong`, `--color-primary(-soft)`, `--color-caution(-soft)`, `--color-danger(-soft)`, `--color-demo(-soft)`, `--color-focus`
  - other: `--radius`, `--radius-sm`, `--space-1..3`, `--font-size-body`
- High contrast responds to `prefers-contrast: more` and `:root[data-contrast="high"]`.

## Integration requests

**Agent 1 (shell / core):**
1. Link `/static/features/operations/operations.css`, then call `mountOperations(ctx)` and keep the returned cleanup.
2. Either use the token names above, or tell the integrator which names differ so the `--op-*` aliases at the top of `operations.css` can be repointed (one block, about 15 lines). If the high-contrast switch is not `data-contrast="high"` on `<html>`, give me the attribute.
3. When `request()` rejects for a non-2xx response, set a numeric `error.status`. Without it, an HTTP failure is reported as a network failure.
4. The mount elements should not add their own `<h2>`. Each component renders its own heading ("System status", "Warnings", "Recent activity"); demo tools uses a labelled section.
5. The page `/` must still contain "Simulate alert" for `tests/test_dashboard.py::test_page_has_button_and_both_areas`. My button renders it from JS, so the static `index.html` needs that text, or Agent 4 must update that test. It also checks for "Latest warning" and "Recent events", which my UI renamed to "Warnings" and "Recent activity".

**Agent 4 (backend / integration):**
1. Add `latest_real_warning` and `latest_simulated_warning`. The UI works without them but is more robust with them.
2. Add `source` and `confidence` as separate fields on hazard entries in `events` and the warning fields. Keep `detail` for compatibility. Today the UI parses `"grok, 82%"`.
3. Add `event_log_size` (the server's `EVENT_LOG_SIZE`) to the snapshot so the "inexact while paused" detection doesn't assume 10.
4. Add `diagnostics` as in the contract. Naming should report `active` while idle, not `failed`. Optionally add `camera.stale_after_seconds`.
5. Keep `POST /api/simulate-alert` returning the full snapshot, with the simulated entry marked `simulated: true` and published on no bus. A real HazardEvent must never be produced by it.
6. Consolidate the DEVLOG entry below.

## DEVLOG entry (for Agent 4 to consolidate)

> **2026-11-14 · Agent 3 (Claude Code, Claude Opus 5.5) · design/alerts-history.** Added `dashboard/static/features/operations/` (status strip, warning panel, activity history, demo tools, pure selectors, scoped CSS) exporting `mountOperations(ctx)`. Connection is shown separately from module health, missing telemetry is shown as unknown, real warnings take priority over simulations, and announcements are deduplicated by key. History pause and clear are browser-only. Tests: repo pytest 188 passed / 1 skipped (Tiger URL unset); node unit 16/16; fixture-harness browser checks 24/24. No Python, contract, config or shared-file changes. Integration requests are in `docs/dashboard-redesign/agent-3-handoff.md`.

## Remaining limitations

- The active-warning window is the server's `hazard_active_seconds` (3 s today), measured on the server clock via `state.now`. A warning older than that shows as "Previous warning", even if the hazard is still physically there. The copy reflects this.
- With today's server, a reload while a real warning is active and a newer simulated warning exists recovers the real warning only from the event log. After 10 newer events it is gone until Agent 4's `latest_real_warning` lands.
- Grouping is presentational and limited to consecutive repeats. The 120 s window is a UI constant, not a config threshold.
- The browser checks depend on a local `playwright-core` and Chromium that are not in requirements. The pytest wrapper only runs the node unit tests.
