# Agent 2 handoff: touch-to-speech, camera, objects, last-touch search

**Status: READY**

| | |
|---|---|
| Base commit | `a5ea3afb5871ea636829e34b4a9b45e6f735a26a` (verified as `origin/main`, remote `richardlancs/Empyrean`) |
| Branch | `design/touch-camera` |
| Worktree | `../empyrean-design-2` |
| Agent | Claude Code (Claude Opus 5.5) |
| Date | 2026-11-14 |

## What this branch adds

`mountExperience(ctx)` in `dashboard/static/features/experience/index.js` mounts four panels into `ctx.roots.touch`, `ctx.roots.camera`, `ctx.roots.objects` and `ctx.roots.find`, and returns a cleanup function. It renders nothing outside those four roots, opens no sockets, and makes network calls only through `ctx.request` (last-seen search). The camera `<img>` loads `/video` directly; that is the MJPEG stream, not an API call.

### Files (all new; nothing existing was edited)

| File | Layer | Role |
|---|---|---|
| `dashboard/static/features/experience/index.js` | Feature controller | Subscribes via `ctx.subscribe`, keeps local view prefs, stream reopen/backoff, 1 s age ticker, announcements, cleanup |
| `dashboard/static/features/experience/selectors.js` | Selectors/presenters | Pure functions: snapshot → view models. No DOM, timers or network |
| `dashboard/static/features/experience/last-seen.js` | Feature controller | Async search state machine (POST → poll), generation-guarded, timeout, dispose |
| `dashboard/static/features/experience/touch-card.js` | Leaf view | Current-touch hero, last touched, speech activity |
| `dashboard/static/features/experience/camera-panel.js` | Leaf view | Image, state line, fit/fullscreen, overlay toggles, legend, measurement footer |
| `dashboard/static/features/experience/object-list.js` | Leaf view | Keyed rows (focus-stable), selection, full-name toggle, thumbnails |
| `dashboard/static/features/experience/find-panel.js` | Leaf view | Search form and result states |
| `dashboard/static/features/experience/dom.js` | Leaf helper | `el()`/`setText()`; all text via `textContent` |
| `dashboard/static/features/experience/experience.css` | Styles | All selectors prefixed `experience-` |
| `tests/ui/agent2/selectors.test.mjs`, `last-seen.test.mjs` | Tests | `node --test` unit tests (21 cases) |
| `tests/ui/agent2/test_agent2_ui.py` | Tests | Runs the Node tests under `pytest` (skips if Node is missing) |
| `tests/ui/agent2/harness/` | Preview only | Fixture server + fake `ctx`, clearly labelled FIXTURE. Never imported by the app |
| `tests/ui/agent2/screenshots/` | Evidence | 1440 px touching state; 360 px long-name/lost/stale-search state |

## Recommendations completed

| # | Item | How |
|---|---|---|
| 3 | Current-touch hero | Largest text is the touched name; Touching/Holding badge (text + colour + top stripe); "Touch an object to hear its name" when none; previous touch shown only as "Last touched"; one-line explanation of touch-to-speech |
| 28 | Speech activity | Only from `state.speech`. Queued/speaking/completed/interrupted/failed with phrase and time. "Last speech completed … does not confirm it was heard". Fake mode → "Log-only audio: no sound is played". No telemetry → "Audio status unavailable". Never derived from TouchEvent. No browser TTS |
| 6, 33 | Camera states | Starting, waiting for first frame, opening video, live, stale (`last_frame_ts` older than 2 s), stream error, dashboard connection lost, frame timing unavailable. A loaded `<img>` or open socket alone never shows "Live". Stale image greyed with a dashed "out of date" label. Touch and object panels show a notice when frames stop or the connection drops |
| 13, 29 | Presentation | 16:9 frame, `object-fit: contain` (no stretching); "Show actual size" toggle; fullscreen with `webkit` fallback and an "Open video in a new tab" link where fullscreen is unsupported. All keyboard operable |
| 27, 30, 31 | Overlays | Selecting an object sets `selected_id`; boxes/hand markers/labels toggles. Stream reopens only when the URL options change (verified: src stable across snapshots). Toggles disabled with an explanation when `capabilities.overlays` is not true, and plain `/video` is used. Legend in a `<details>` |
| 32 | Camera detail | Footer: frame rate, frame age, frame size; "Unknown" when null |
| 19, 20 | Object readability | Two-line clamp, "Show full name"/"Show less" (`aria-expanded`), full name in `title`. States: New, In view, Touching, Holding, Temporarily lost; raw state kept in `data-state` |
| 21, 22, 23 | Object context | "N in view, M temporarily lost (hidden from the camera for a moment)". "Last seen just now / less than a minute ago / N minutes ago", exact time in tooltip. No decimals |
| 24, 25 | Lost and unnamed | Lost rows dashed but full-contrast. `naming_status`: pending → "Naming in progress", fallback → "General name", failed → "Naming failed, showing general name". Empty name without status → "No specific name" / "Not named yet", never "naming…" |
| 26 | Thumbnails | `thumbnail_url` set once per row (no per-frame reload); error → "No image"; initial letter when unsupported; `src` cleared on row removal and unmount |
| 50 | Last-touch search | "Find a previously touched item" with explanation that it searches touch history and may be spoken. States: loading, found (answer + "Recorded at … · N minutes ago" + "not a guarantee it is still there"), not found, unavailable, timeout (10 s), error, retry. Generation guard + `request_id` match; polling stops on newer search, answer, timeout and unmount. Disabled with a reason when `capabilities.last_seen === false` |

## Tests run

- `node --test tests/ui/agent2/`: 21 passed (touch → hold → release → retouch, old-backend fallback, speech never inferred, speech interrupted by hazard, fake audio, camera live/stale/unknown/waiting/disconnected, stopped frames flag touch and object data, overlay URL, naming states, counts, find availability, search found/not-found/unavailable/timeout/retry, newer search wins over a slow older one, mismatched `request_id` ignored, dispose stops polling).
- `pytest` (whole repo, in this worktree, Python 3.11.18): **183 passed, 1 skipped**.
- `ruff check` and `ruff format --check` on `tests/ui/agent2`: clean.
- Browser checks in the fixture harness (Playwright, Chromium): every harness scenario; search found, not found, unavailable, HTTP 500, timeout, and slow-then-fast race; stream failure → "Video stream disconnected" → backoff reconnect → Live; socket drop → connection-lost notices; focus kept on an object row across 7+ snapshots; selection and toggles change `/video` params; no horizontal overflow at 360, 768 and 1440 px and at 200 % zoom; all controls ≥ 44 px (checkboxes are 22 px inside 44 px labels).
- Contrast (WCAG): text 14.1, muted on white 6.3, muted on touching/held rows 5.6/5.8, white on primary 5.5, primary on soft 4.8, caution 6.5, hazard 6.1, demo 6.3, control border 4.5, focus ring 6.7. No token changes were needed. Stale lists are marked with a dashed outline rather than fading, to keep contrast.
- Reduced motion: the feature has no animations or transitions; a `prefers-reduced-motion` guard is included anyway.

**Not verified:** anything against the real engine, camera, speaker or database. All browser checks used FIXTURE data. Safari/Firefox not tried. No screen reader was used; announcements were checked through the harness log only.

Run the harness: `python tests/ui/agent2/harness/serve.py` then open http://localhost:8765/. Query words: `slow`, `never` (timeout), `down` (unavailable), `zebra` (not found), `broken` (HTTP 500).

## API assumptions (Agent 4)

All from the shared contract; listed so mismatches are easy to spot.

- Snapshot `now` (server Unix seconds) is present. It is used with `receivedAt` to age timestamps without trusting the browser clock.
- `current_touch.state` is `"touching"` or `"held"`. If the field is absent (old backend), the first object with state touching/held is used instead.
- `speech.ts` is when that status began. `interrupted` is matched to `latest_real_warning.ts >= speech.ts - 0.5` only to add the sentence "A warning was raised at about this time".
- `diagnostics.camera.last_frame_ts` is the **capture time of the newest frame the dashboard received** (not the time of the last WebSocket push).
- `capabilities.overlays === true` means `/video` honours `boxes`, `hands`, `labels` (each `0`/`1`) and `selected_id`. The UI always sends all three flags when supported, plus `r=<n>` as a cache-buster on deliberate reopen. Please ignore unknown params.
- `thumbnail_url` is same-origin and stable per object until the crop changes. A 404 is shown as "No image".
- `POST /api/last-seen` → 202 `{request_id}` (string or number). `GET /api/last-seen/{id}` returns the same `request_id`. Unknown/expired id may 404; the UI reports that as an error with retry.
- `ctx.request` rejects with an `Error` carrying a numeric `status` for non-2xx responses. Messages for 404/405 ("not offered yet") and 503 ("unavailable") use it. Without `status` a generic message is shown.

## Integration requests

**Agent 1 (shell):**
1. Link `/static/features/experience/experience.css` and call `mountExperience(ctx)` with the four roots.
2. The CSS reads these tokens, with the agreed hex values as fallbacks: `--color-text`, `--color-text-secondary`, `--color-surface`, `--color-bg`, `--color-border`, `--color-border-strong`, `--color-primary`, `--color-primary-soft`, `--color-caution`, `--color-caution-soft`, `--color-danger`, `--color-danger-soft`, `--color-demo`, `--color-demo-soft`, `--color-focus`, `--space-1..3`, `--radius`, `--font-size-body`. If your names differ, tell the integrator; the mapping is one block at the top of `experience.css`.
3. Suggested layout: touch panel full width at the top; camera beside objects on wide screens; find under the camera or objects. Panels are min-width 0 and fluid.
4. The `ctx.request` error should carry `.status` (see above).

**Agent 4 (backend):** implement the fields and endpoints above. In particular, `diagnostics.camera.last_frame_ts`, `fps`, `width` and `height` come from `FrameResult` in the dashboard's `VideoFeed.on_frame`. Width and height can be the processed frame's 640 × 360. Without them the camera can only say "Frame timing unavailable", by design.

## DEVLOG entry (for Agent 4 to consolidate)

> **2026-11-14, Agent 2 (Claude Code), `design/touch-camera`.** Added the experience feature (`dashboard/static/features/experience/`): current touch with real speech status, camera with honest freshness states, overlay/fit/fullscreen controls, keyed object list with naming states and thumbnails, and last-touch search with race-safe polling. Tested with `node --test` (21), full `pytest` (183 passed, 1 skipped), ruff, and a fixture browser harness at 360/768/1440 px and 200 % zoom. Not yet run against the real engine; needs Agent 4's telemetry fields and endpoints, and Agent 1's shell.

## Remaining limitations

- Depends on Agent 4's new fields. Against today's backend it degrades honestly: touch falls back to object states, speech shows "Audio status unavailable", the camera shows "Frame timing unavailable", overlays and thumbnails are off, and search reports that it is not offered.
- Fullscreen fallback is a link to the raw `/video` stream, which has no stale-state labelling.
- Touch announcements fire on a new touch (not on hold). If Agent 3's warning panel also announces, the shell's dedupe keys keep them separate (`touch:…`, `find:…`, `camera:…`, `speech:…`).
