# Empyrean dashboard design system

Owner: Agent 1 (`design/light-foundation`). Agent 4 reconciles this document with the integrated API.

The dashboard serves a helper, operator, developer or demonstrator, and may be read by a low-vision wearer. Its job is to make one interaction obvious: **touch an object, hear its name**. Everything else on the page explains or supports that.

This is a research prototype. No copy may call it a safety device, and the page never treats "no warning" as proof that the surroundings are clear.

## 1. Layers and dependency direction

```
Engine (vision, scene, namer, hazard, audio, storage)        existing Python modules
  -> dashboard bus adapter / read model (state.py ...)       Agent 4
  -> HTTP + one WebSocket (/api/*, /ws, /video)              Agent 4
  -> core/socket-client.js, core/api-client.js               transport (Agent 1)
  -> core/normalize.js -> core/store.js                      frontend state (Agent 1)
  -> features/experience, features/operations                presentation (Agents 2, 3)
```

User intent travels back the same way: a feature calls `ctx.request()`, which goes to the API client, then a validated route, then an application service, and then the existing bus or storage worker. The result arrives as new state over `/ws`.

| File | Layer | Responsibility |
|---|---|---|
| `dashboard/index.html` | entry | Document only: theme boot script, stylesheets, one module script, `<div id="app">`. No inline script or style. |
| `static/app.js` | composition | Creates store, clients, announcer, preferences and shell; loads both features; exposes `destroy()`. No feature logic. |
| `static/components/app-shell.js` | presentation | Skip link, header (purpose, Prototype label, contrast toggle), the eight mounts, footer, load-error and loading placeholders. |
| `static/core/store.js` | state | The one store: `{state, connection, receivedAt}`; coalesces updates to one notification per animation frame (250 ms fallback when the tab is hidden). |
| `static/core/normalize.js` | transport | Optional-field normalization; deep-freezes state. |
| `static/core/socket-client.js` | transport | The only `/ws` owner: parse, normalize, report bad messages, reconnect with backoff. |
| `static/core/api-client.js` | transport | The only `fetch` owner: same-origin JSON, timeouts, `ApiError`. |
| `static/core/announcer.js` | accessibility | Two live regions; keyed, deduplicated, priority-ordered announcements. |
| `static/core/preferences.js` | local view state | Theme and other per-browser display preferences; survives blocked storage. Separate from the store. |
| `static/core/theme-boot.js` | entry | Classic script in `<head>`: applies the saved theme before first paint. |
| `static/core/clock.js` | helper | Server-time estimate and age/time formatting for features. |
| `static/core/feature-loader.js` | composition | Imports and mounts one feature; failures become `FeatureError`, never uncaught. |
| `static/styles/*.css` | presentation | `tokens.css`, `base.css`, `layout.css`, `components.css`. |

Dependency rules, which are enforced by `tests/ui/agent1/test_agent1_foundation.py`:

- `core/` imports only `core/`.
- Only `socket-client.js` opens `/ws`. Only `api-client.js` calls `fetch`.
- Foundation code never uses `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `document.write`. External names are always rendered as text.
- Features may import pure helpers from `/static/core/clock.js`. Everything else reaches them through the context. Features never open sockets or call `fetch` directly.

## 2. Mount contract

`app.js` imports `/static/features/experience/index.js` (export `mountExperience`) and `/static/features/operations/index.js` (export `mountOperations`) independently and in parallel. Each export receives `ctx` and may return a cleanup function, or a promise of one.

| Key | Element id | Region name | Owner |
|---|---|---|---|
| `health` | `#health-panel` | System status | operations (Agent 3) |
| `warning` | `#warning-panel` | Warnings | operations (Agent 3) |
| `touch` | `#touch-panel` | Current touch | experience (Agent 2) |
| `camera` | `#camera-panel` | Camera view | experience (Agent 2) |
| `objects` | `#objects-panel` | Recognized objects | experience (Agent 2) |
| `find` | `#find-panel` | Find a last touch | experience (Agent 2) |
| `events` | `#events-panel` | Recent activity | operations (Agent 3) |
| `demo` | `#demo-panel` | Demo tools | operations (Agent 3) |

Each mount is a `<section aria-label="…" tabindex="-1">`. Until its feature mounts, it holds a loading placeholder and `aria-busy="true"`. After a successful mount the shell removes the placeholder and `aria-busy`, and from then on the feature owns all of the mount's contents. A mount left empty is hidden with `:empty`, so no blank boxes appear.

`ctx` (frozen):

- `roots` holds all eight elements, keyed as above. A feature writes only into its own four.
- `subscribe(callback)` calls the callback immediately with `{state, connection, receivedAt}`, then once per coalesced update, and returns an idempotent unsubscribe. `state` is `null` until the first message. `connection` is `connecting` (before the first open), `connected`, or `reconnecting` (after any loss, or a failed first attempt). `receivedAt` is browser milliseconds. The app also releases every subscription a feature made when it unmounts, even ones its cleanup forgot.
- `request(path, {method = "GET", body})` sends a same-origin JSON request. `body` is a plain object. It resolves with the parsed body (`null` for an empty response). It rejects with `ApiError {kind: "network" | "timeout" | "http" | "parse", status, message}`, where `message` comes from FastAPI's `detail` when present and otherwise is plain wording. Paths must start with `/`. HTTP 202 counts as success. The default timeout is 10 s.
- `announce(text, {priority = "polite", key})` queues a screen-reader announcement and returns `true` if it will be spoken. See section 8.

Load failures: if a module fails to import, lacks its export, or throws while mounting, the error is logged with `console.error` and each of that feature's mounts shows "Could not show …" with an explanation and a "Technical details" disclosure. The other feature and the shell keep working.

Rules for features:

- Build the DOM once and update text and attributes in place on each snapshot. Do not rebuild forms or focused controls. Snapshots arrive many times a second.
- Use `textContent` for names, answers and details.
- Treat every additive field as optional. Normalization guarantees the following:
  - `events` and `objects` are arrays.
  - `latest_real_warning`, `latest_simulated_warning`, `current_touch` and `speech` are an object or `null`. When only `latest_warning` is sent, it is split by its `simulated` flag.
  - `diagnostics` always has `camera`, `scene`, `naming`, `storage` and `audio`. Each has a valid `status` (`unknown` when not reported) plus `detail` and `last_update_ts`, which may be `null`. `camera` also has `last_frame_ts`, `fps`, `width` and `height`, which may be `null`.
  - `capabilities` has `last_seen`, `thumbnails`, `overlays` and `speech_status`. Each is `true` only when the server sent `true`.
  - Fields inside objects and events, such as `naming_status` and `thumbnail_url`, are passed through untouched and may be missing.
- Use `clock.js` for ages: `ageSeconds(ts, snapshot)` and `formatAge(seconds)`. They use `state.now` to correct for the difference between the laptop and browser clocks.
- When the connection changes from `reconnecting` to `connected`, the camera feature should reload `/video`, because the old MJPEG stream died with the server.

Warning emphasis hook: while a **real** warning is active, the operations feature sets `roots.warning.dataset.emphasis = "urgent"`. The shell then pins the warning slot to the top of the viewport (`position: sticky`) with a raised edge. While only a simulation is active, it sets `"simulated"`, which is never pinned. When nothing is active, it removes the attribute. A real active warning takes priority even if a simulation happened later. The pin takes no space when inactive, so the warning never permanently dominates the page.

## 3. Tokens

All colours, spacing, type, radii and motion values are custom properties in `styles/tokens.css`. Feature styles use them and define no palette of their own.

### Colour (light / high contrast)

| Token | Light | High contrast | Use |
|---|---|---|---|
| `--color-page` | `#F5F7FA` | `#FFFFFF` | Page background |
| `--color-surface` | `#FFFFFF` | `#FFFFFF` | Panels, inputs |
| `--color-surface-sunken` | `#EEF2F6` | `#F1F4F8` | Hover fill, disabled fill, loading bars, neutral callout |
| `--color-text` | `#172B4D` | `#0B1A33` | Primary text |
| `--color-text-secondary` | `#526176` | `#2E3B50` | Metadata, hints |
| `--color-border` | `#D8E1EB` | `#68788D` | Decorative edges and dividers |
| `--color-border-control` | `#68788D` | `#172B4D` | Inputs, outlined buttons (meaningful boundaries) |
| `--color-accent` | `#0F766E` | `#0B5D56` | Touch emphasis, primary action |
| `--color-accent-hover` | `#0B5F58` | `#084A44` | Primary hover |
| `--color-on-accent` | `#FFFFFF` | `#FFFFFF` | Text on accent |
| `--color-accent-soft` | `#E6F4F1` | `#EEF8F6` | Touch backgrounds |
| `--color-accent-text` | `#0F766E` | `#0B5D56` | Accent used as text or link |
| `--color-caution` / `-soft` | `#92400E` / `#FFF4D6` | `#7A3306` / `#FFF4D6` | Held, waiting, degraded |
| `--color-danger` / `-soft` | `#B42318` / `#FEF3F2` | `#9A1B12` / `#FEF3F2` | Urgent hazards and errors only |
| `--color-danger-hover`, `--color-on-danger` | `#912018`, `#FFFFFF` | `#7A140D`, `#FFFFFF` | Danger button |
| `--color-sim` / `-soft` | `#6D28D9` / `#F3EEFF` | `#5B21B6` / `#F3EEFF` | Simulation and demo only |
| `--color-neutral` / `-soft` | `#526176` / `#EEF2F6` | `#2E3B50` / `#F1F4F8` | Neutral chips |
| `--color-focus` | `#1D4ED8` | `#1D4ED8` | Keyboard focus ring |

All light values from the brief are used unchanged. The test suite measured every pair, and none needed adjusting. The colours added beyond the brief are hover shades, sunken surface, neutral, and all of high contrast. Each was chosen to pass the same checks.

### Measured contrast

The light theme needs at least 4.5:1 for text. High contrast needs at least 7:1. Boundaries and focus need at least 3:1. These are checked in CI-style tests (`test_token_contrast_meets_wcag`).

| Pair | Light | High contrast |
|---|---|---|
| text on page | 13.14 | 17.36 |
| text-secondary on surface / page | 6.31 / 5.88 | 11.30 / 11.30 |
| text-secondary on accent-soft | 5.58 | 10.44 |
| on-accent on accent | 5.47 | 7.74 |
| accent-text on accent-soft (lowest text pair) | 4.84 | 7.14 |
| caution on caution-soft | 6.47 | 8.32 |
| danger on danger-soft | 6.05 | 7.61 |
| on-danger on danger | 6.57 | 8.27 |
| sim on sim-soft | 6.25 | 7.91 |
| border-control on surface / page | 4.51 / 4.20 | 14.10 / 14.10 |
| focus on surface / page | 6.70 / 6.24 | 6.70 / 6.70 |

`--color-border` (`#D8E1EB`, about 1.3:1) is decorative only. Never use it as the only boundary of a control. Use `--color-border-control` for that.

### Semantic colour rules

- **Teal** marks the core touch experience: the current touch, the "touching" state and the primary action.
- **Red** is reserved for urgent real hazards and failures. It is not used for "offline but harmless" decoration.
- **Purple with dashed borders** marks simulation and demo-only content, so it is never mistaken for a real warning.
- **Amber** marks held, waiting and degraded states.
- Colour is never the only signal. Chips carry text and an optional `data-icon` glyph. `.ui-status` uses a different shape per status: ● active, ◔ starting, ▲ degraded, ■ offline, ? unknown. Simulation uses dashed borders. The danger panel uses a thicker border and a tinted fill.

### Spacing, radius, sizing

- **Spacing:** the scale is 8px-based: `--space-half` 4px, then `--space-1` 8, `--space-2` 16, `--space-3` 24, `--space-4` 32, `--space-5` 40, `--space-6` 48 and `--space-8` 64. Panels use 16px padding on mobile and 24px from 45em up. Grid gaps are 16 to 24px.
- **Radius:** `--radius` (12px) for panels, `--radius-sm` (8px) for controls, `--radius-pill` for chips.
- **Sizing:** `--target-min` is 44px and applies to every control. The content width is capped at `--content-max` (1440px). `--gutter` is `clamp(16px, 3vw, 32px)`. `--info-column` is `clamp(360px, 30vw, 420px)`.

### Type

- **Font:** the system UI stack (`--font-sans`). Sizes are in rem, so the browser's text-size setting and zoom both apply.
- **Scale:**
  - `--text-badge`: 13px. The smallest text anywhere.
  - `--text-small`: 15px. Metadata and hints.
  - `--text-body`: 17px.
  - `--text-large`: 20px. Section titles and the brand.
  - `--text-xl`: 24px. Warning text.
  - `--text-display`: `clamp(2rem, 1.5rem + 2vw, 2.75rem)`, about 32–44px. **Reserved for the touched object's name**, which is always the largest text on the page.
- **Hierarchy:** the brand ("Empyrean", 20px) is deliberately smaller than the object name (44px at 1440px wide).
- **Casing:** labels use sentence case. No tiny all-caps labels anywhere.

## 4. Primitives (`components.css`, prefix `ui-`)

| Class | Purpose |
|---|---|
| `.ui-panel` (+ `--accent`, `--caution`, `--danger`, `--sim`, `--flush`), `__header`, `__title`, `__subtitle` | Surfaces and section headings. |
| `.ui-stack` (`--tight`), `.ui-row` | Vertical and wrapping horizontal rhythm. |
| `.ui-button` (+ `--secondary`, `--quiet`, `--sim`, `--danger`), `[aria-busy=true]`, `:disabled` | Buttons, at least 44×44px. Busy shows a spinner. |
| `.ui-toggle[aria-pressed]` | Two-state button. A box glyph shows the state, and `aria-pressed` announces it. |
| `.ui-chip` (+ `--touch`, `--caution`, `--danger`, `--sim`, `--outline`), `[data-icon]` | Badges at 13px or larger. |
| `.ui-status[data-status]` | Status with a shape-coded glyph. |
| `.ui-field`, `.ui-label`, `.ui-hint`, `.ui-input[aria-invalid]`, `.ui-field-error`, `.ui-inline-form` | Form fields. |
| `.ui-callout` (+ variants), `__title` | Inline results and messages. |
| `.ui-list` | Unstyled list with dividers. |
| `.ui-empty`, `__title` | Empty state: what is missing and what will appear. |
| `.ui-loading`, `__bar`, `.ui-spinner` | Loading. The shimmer stops under reduced motion. |
| `.ui-feature-error` | A feature that failed to start. |
| `.ui-dl` | Key/value pairs. Collapses to one column below 22.5em. |
| `.ui-visually-hidden`, `.ui-numeric` | Screen-reader-only text and tabular numbers. |

Feature CSS is scoped with `experience-` and `operations-` prefixes. It composes these primitives and does not restyle them globally. The full set is rendered in both themes at `/preview/inventory` in the Agent 1 preview harness. The screenshot is `tests/ui/agent1/screenshots/inventory-1440.png`.

## 5. Responsive order

DOM order, which is also the reading and tab order and the mobile order, is:

1. Purpose and header
2. Health
3. Warning
4. Touch
5. Camera
6. Recognized objects
7. Last-touch search
8. Activity
9. Demo tools

Wider layouts only rearrange columns and never use CSS `order`. Breakpoints are in em, so 200% zoom falls back to the narrower layout.

| Width | Layout |
|---|---|
| < 45em (720px) | One column in DOM order. |
| 45em–64em | Health, warning, touch and camera are full width, then objects and find side by side, then events and demo full width. |
| ≥ 64em (1024px) | Camera on the left, with an information column of `clamp(360px, 30vw, 420px)` holding touch then objects. Below that: activity on the left, with find and demo on the right. Health and warning run full width above. When the camera is taller than touch plus objects, the spare height goes below the object list, never between touch and list. |

The camera is **not** sticky. Sticky grid items are bounded by the whole grid rather than their own area, so a sticky camera slid over the activity panel. The browser check found this, and the behaviour was dropped.

## 6. Keyboard, focus, targets

- The first Tab reaches a visible "Skip to dashboard" link. Activating it focuses `<main>`.
- The page has these landmarks: `header`, `main`, `footer`, and one `h1`. The eight mounts are labelled `section` regions.
- Every element shares one focus ring: a 3px solid `--color-focus` outline with a 2px offset, 4px in high contrast. The forced-colours mode uses `Highlight`.
- Every button declares `type`. Controls are at least 44×44px, and the browser check enforces this.

## 7. Themes and motion

- **Light** is the default. **High contrast** is a stronger light theme, not a dark mode: darker text, accent and status hues, visible borders, 2px control borders, a 4px focus ring and no shadows.
- The header's "High contrast" toggle saves the choice in `localStorage` (`empyrean.theme`). Without a saved choice, the OS setting `prefers-contrast: more` selects high contrast.
- `theme-boot.js` applies the theme in `<head>` before the stylesheets render, so there is no flash. If storage is blocked, the page uses light, the toggle still works for that visit, and one console warning explains that preferences cannot be saved.
- `prefers-reduced-motion: reduce` effectively turns off transitions and animations (0.01ms) and stops the loading shimmer. Content never depends on motion.

## 8. Screen-reader announcement policy

The announcer owns two visually hidden live regions: `role=status` / `aria-live=polite` and `role=alert` / `aria-live=assertive`.

- **Announce events, not state.** Announce the following:
  - a new touch, keyed by its touch event, so a release followed by a retouch counts as a new event
  - a newly active **real** warning, which is assertive
  - a finished lookup
  - a failed user action
  - dashboard connection lost or restored, which `app.js` announces once per transition. Features must not repeat it.
- **Never announce** snapshots, ages ("4 s ago"), FPS, timer ticks, list re-sorts, or simulations as if they were real.
- **Keys:** pass a key that identifies the event (`touch:<event id>`, `hazard:<id>`, `last-seen:<request_id>`). Each key is spoken once (the last 500 are remembered). Without a key, identical text is not repeated within 5 s.
- **Priority:** a warning is always read first. Polite messages queued in the same moment wait about 1.5 s after it. They are delayed, not dropped, regardless of which feature announced first. Messages arriving within 100 ms are combined into one utterance.
- The dashboard never uses browser text-to-speech. The speaker on the glasses is the voice.

## 9. Honest status

- An open socket proves only that this page can reach the dashboard server.
- A touch event or speak request does not prove audio played.
- Engine completion does not prove the wearer heard anything.
- Missing instrumentation is shown as unknown or unavailable, never as active or successful.
- "No active warning" is always worded so that it does not imply the way is clear.
