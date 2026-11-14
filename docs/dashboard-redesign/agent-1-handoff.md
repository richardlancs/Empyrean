# Agent 1 handoff: light design system and page foundation

**Status: READY**

| | |
|---|---|
| Branch | `design/light-foundation` |
| Worktree | `../empyrean-design-1` (no suffix needed; branch and worktree were new) |
| Base | `a5ea3afb5871ea636829e34b4a9b45e6f735a26a` (verified as `origin/main` of `richardlancs/Empyrean`) |
| Agent | Claude Code (Opus 5.5) |
| Design reference | [`design-system.md`](design-system.md) |

> **Do not merge this branch on its own.** The new `index.html` loads `/static/...`, and today's `dashboard/server.py` does not serve `/static`. Without Agent 4's static mount the page is blank. See integration request A1.

## What was built

| Recommendation | Done | Where |
|---|---|---|
| 1 Light palette, semantic states | Yes | `styles/tokens.css`: brief's tokens unchanged; teal touch, red urgent only, purple dashed simulation, amber held/degraded |
| 7 Responsive order | Yes | `styles/layout.css`. DOM order is health, warning, touch, camera, objects, find, events, demo. Wide layout puts the camera left and a 360–420px info column right. |
| 8, 17, 18 Readable type | Yes | 17px body, 13px minimum badges, sentence case. The object name (`--text-display`, about 44px) is larger than the brand (20px). |
| 11 Explain the product | Yes | Header: "Touch an object. Hear its name.", one-line explainer, Prototype chip. Footer: warnings can be missed. |
| 12, 14 Layout | Yes | 1440px max width, `clamp()` gutters, flexible tracks. Empty mounts are hidden. Spare height never lands between the touch and object list. |
| 15, 16 Consistency | Yes | `styles/components.css` `ui-` primitives: panel, button, toggle, chip, status, field, callout, list, empty, loading, feature-error, dl |
| 46, 47 Keyboard and touch | Yes | Skip link, landmarks, single `h1`, labelled mounts, a 3px focus ring (4px in high contrast), typed buttons, 44px targets |
| 48 Light / high-contrast light | Yes | Toggle in the header. Persists in `localStorage`, follows `prefers-contrast: more`, and `theme-boot.js` prevents a flash. Survives blocked storage. |
| 49 Reflow | Yes | Em breakpoints. No horizontal scroll at 360px or at 200% zoom. Long names wrap. No fixed-height text cards. |

Architecture (layering, mount contract, announcer policy) is described in `design-system.md` sections 1, 2 and 8.

## Changed files

Production:

- `dashboard/index.html`: replaced with a minimal entry document.
- `dashboard/static/app.js`: composition.
- `dashboard/static/components/app-shell.js`
- `dashboard/static/core/`:
  - transport and state: `store.js`, `normalize.js`, `socket-client.js`, `api-client.js`
  - accessibility and preferences: `announcer.js`, `preferences.js`, `theme-boot.js`
  - helpers: `clock.js`, `feature-loader.js`
- `dashboard/static/styles/`: `tokens.css`, `base.css`, `layout.css`, `components.css`

Docs: `docs/dashboard-redesign/design-system.md` and this file.

Tests and preview (`tests/ui/agent1/`, test-only):

- `test_agent1_foundation.py`: pytest. Runs the Node tests and checks the entry document, contrast, layering and the harness.
- `js/core.test.mjs`, `js/app.test.mjs`, `js/fakes.mjs`: `node --test` unit and composition tests on a fake DOM.
- `browser/foundation-check.mjs`: Playwright browser checks. Not part of pytest.
- `agent1_preview_server.py`, `agent1_fixtures.py`: fixture server for 14 scenarios.
- `stubs/features/{experience,operations}/`: **preview-only stubs** for Agents 2 and 3's modules. Never copy these into production.
- `preview/inventory.html`: visual inventory.
- `screenshots/`: 8 PNG files.

No Python under `dashboard/`, and nothing owned by another agent, was edited.

## Verification

Run on macOS with Python 3.11.18 (shared `.venv`, with `fastapi==0.162.7` from `dashboard/requirements.txt` present), Node 26.13 and Playwright 1.64.1 Chromium.

| Check | Result |
|---|---|
| `node --test tests/ui/agent1/js/` | 42 passed. Store, normalize, socket client (backoff, bad messages, stop), API client (202, errors, timeout, same-origin), announcer (keys, dedupe, priority ordering), preferences (blocked storage), clock, feature loader, app composition (mount ids, failure isolation, cleanup, theme, connection announcements) |
| `pytest tests/ui/agent1` | 30 passed, including WCAG contrast for every token pair in both themes |
| `node tests/ui/agent1/browser/foundation-check.mjs` | 69 of 69 passed, on two consecutive runs. Covers widths 360/768/1440 and 640 CSS px (1280px at 200% zoom); long names; skip link and focus ring; 44px targets; landmarks; theme persistence, no flash, blocked storage and `prefers-contrast`; reduced motion; warning pinning (real, simulated, real-after-simulation, expired); announcements (none on steady snapshots, touch once, warning first); reconnect; cleanup; feature-load failure; no console errors |
| Full `pytest` on the branch | 211 passed, 1 skipped, **1 failed**: `tests/test_dashboard.py::test_page_has_button_and_both_areas`, which is expected and listed as A2. On the untouched base it was 181 passed, 1 skipped, 1 failed (`test_cli_fake_vision_starts`, the known timing flake in DEVLOG "Needs attention", which passed on the later run). |
| `ruff check` / `ruff format --check` on `tests/ui/agent1` | Clean |

Screenshots are in `tests/ui/agent1/screenshots/`:

- `touch-360.png`, `touch-768.png`, `touch-1440.png`, `touch-zoom200-1280.png`
- `touch-1440-high-contrast.png`
- `hazard-active-1440.png`
- `features-missing-768.png`
- `inventory-1440.png`

### Foundation verification and integrated verification

What was verified is the **foundation**: shell, layout, tokens, store, transport, announcer, theme, error handling and cleanup. It ran against fixture data and the **stub** feature modules. No real feature module from Agent 2 or 3 existed on this base.

The following has **not** been verified. Agent 4 should cover it after integration:

- Agents 2 and 3's real components inside this shell, including their feature CSS against these tokens.
- The real `/ws` payload and Agent 4's new fields.
- `/video` MJPEG in the real `<img>`.
- The real last-seen and thumbnail routes.
- Any hardware, camera, speaker, Grok or Tiger Data behaviour. Screenshots and fixtures prove none of it.

Not tested at all:

- A real screen reader. The live-region DOM behaviour was checked, but not VoiceOver or NVDA output.
- Firefox and Safari. Only Chromium was tested.
- Real browser zoom. A 640px CSS viewport was used as its equivalent.

## API assumptions

- `/ws` sends the whole state as JSON text after every change, including the existing `now` field, which is used for clock correction. Additive fields follow the shared contract. Missing ones are normalized as described in `design-system.md` section 2.
- `/api/state`, `POST /api/simulate-alert`, `/video`, `/api/last-seen` (202 plus `request_id`) and `GET /api/last-seen/{id}` are used as the brief specifies. The foundation itself calls none of them; features do, through `ctx.request`.
- FastAPI error bodies (`{"detail": "..."}` or a validation list) become `ApiError.message`.

## Integration requests

**A1, Agent 4, required.** Serve `dashboard/static` at `/static` in `dashboard/server.py` `create_app()`, and keep `/` serving `index.html`. For example:

```python
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

Starlette serves `.js` as `text/javascript`, which module scripts need; this was verified in the preview server. Consider `Cache-Control: no-store` on `/` during the hackathon so a reload always picks up new modules.

**A2, Agent 4, required.** Update `tests/test_dashboard.py::test_page_has_button_and_both_areas`. It looks for "Simulate alert", "Latest warning", "Recent events" and "Simulated" in the HTML of `/`. Those labels are now rendered by Agent 3's operations feature in JavaScript, so the entry document cannot contain them without embedding feature content. Suggested replacement:

- `/` returns 200 with `<div id="app">` and `/static/app.js`.
- `/static/app.js` and both feature entry modules return 200.
- `operations/index.js` contains "Simulate alert".
- Keep the "safety" assertion.

**A3, Agent 4.** Consolidate the DEVLOG entry below.

**A4, Agent 2 (experience).**

- Mount into `touch`, `camera`, `objects` and `find` only.
- Use `--text-display` for the touched name, and `ui-panel--accent` and `ui-chip--touch` for touch emphasis.
- Reload `/video` when the connection goes from `reconnecting` to `connected`.
- Announce a touch with a key from the touch event, for example `touch:${event id}` or `touch:${object_id}:${ts}`. Never key on anything derived from `now`, and never announce ages.
- Hidden headings are fine, but every mount needs a heading.
- The stub in `tests/ui/agent1/stubs/` shows contract usage only. Its markup is not a design to copy.

**A5, Agent 3 (operations).**

- Set and clear `roots.warning.dataset.emphasis` as described in `design-system.md` section 2:
  - `"urgent"` for an active **real** warning, which takes priority over a later simulation
  - `"simulated"` for a simulation
  - remove the attribute when nothing is active
- Do not announce connection changes; `app.js` already does.
- Show `ctx` connection state in health honestly: an open socket proves only the page connection.
- Use `ui-button--sim` and `ui-panel--sim` for demo tools and simulated warnings.
- The health strip can use `.ui-status[data-status]` directly; it accepts the diagnostics statuses.

**A6, everyone.** `ctx.subscribe` is called once per animation frame at most, so features should update DOM in place rather than rebuilding it. `globalThis.empyreanDashboard` exposes `{store, socket, ready, destroy}` as a debugging and test handle; production code should not depend on it.

## Remaining limitations

- This branch on its own does not serve the new assets (see A1), and one existing test fails until A2 is done.
- The Node unit tests run inside pytest only when `node` is on `PATH`; otherwise that test is skipped. The browser check needs Playwright, either local or global, and `PYTHON` pointing at a venv with FastAPI. It defaults to `../Empyrean/.venv/bin/python`, which is specific to this machine.
- Wide-layout whitespace still appears where one column is naturally longer than the other, for example a long activity list beside a short search panel. These gaps are page background, not empty panels.
- High contrast deliberately changes the brief's hues (darker teal, red, purple and amber) to reach 7:1. Light mode uses the brief's values exactly.

## DEVLOG entry for Agent 4 to consolidate

```
### 2026-11-14, Agent 1 (dashboard redesign: light foundation), Claude Code
**Changed:** New layered dashboard front end on branch design/light-foundation from a5ea3af: minimal dashboard/index.html; dashboard/static/app.js (composition); components/app-shell.js (header, skip link, the eight feature mounts, load-error and loading states); core/ store, normalize, socket-client (only /ws owner, backoff reconnect), api-client (only fetch owner), announcer (keyed, deduplicated, warning-first live regions), preferences and theme-boot (light and high-contrast light, persisted, no flash), clock, feature-loader; styles/ tokens, base, layout, components. Docs in docs/dashboard-redesign/design-system.md and agent-1-handoff.md.
**Tested:** node --test (42 passed), pytest tests/ui/agent1 (30 passed, WCAG contrast in both themes), Playwright browser check against a fixture preview server with stub features (69/69 passed, 360/768/1440 px and 200% zoom). Full pytest: 211 passed, 1 skipped, 1 failed (test_dashboard page-text test, needs updating; see handoff A2). No hardware, audio, Grok or database verification.
**Decisions:** Brief's light tokens kept unchanged (all pairs at least 4.5:1). Camera not sticky (sticky grid items overlapped the activity panel). Warnings always announced before polite messages; polite messages are delayed, not dropped.
**Teammates need to know:** Agent 4 must serve /static (handoff A1) and update test_page_has_button_and_both_areas (A2). Agents 2 and 3: contract details and the warning emphasis hook are in design-system.md section 2.
```
