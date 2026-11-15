# How It Works Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `/how-it-works` page in the dashboard app: an orbitable 3D model of the rig with five hotspots that fly the camera in and open a panel, a step-through of the pipeline, and an animated transition from the dashboard.

**Architecture:** A self-contained static page in a new top-level `howitworks/` folder, served by the existing FastAPI app through one `StaticFiles` mount. All copy lives in one data module; the stepper and hotspot selection are pure state modules tested with `node --test`; three.js and the SVG are thin views over them. No live data, no engine changes.

**Tech Stack:** Plain HTML, native ES modules, plain CSS. three.js and GSAP vendored as ES modules under `howitworks/vendor/` (import map, no CDN, no build step). `pytest` and `node --test` for tests, Playwright for browser checks.

**Spec:** `docs/superpowers/specs/2026-11-14-how-it-works-design.md`. Read it first; this plan does not repeat its page description or copy table.

## Global Constraints

- **Gate 1:** no task starts until Richard confirms all four teammates agreed to the `howitworks/` folder and to vendoring three.js and GSAP. Record it in `DEVLOG.md` in Task 1.
- **Gate 2:** Task 6 (the only task touching `dashboard/`) starts only after Richard confirms Person 4 agreed. Until then nothing under `dashboard/` is edited.
- Work on a new branch `how-it-works` cut from `origin/main`. Commit only inside `howitworks/`, `tests/`, `DEVLOG.md` and (Task 6) the three named `dashboard/` files.
- No `contracts/`, `config/`, `SPEC.md`, `AGENTS.md`, `CLAUDE.md` or `requirements*.txt` changes. No Python dependency added.
- No CDN URLs anywhere. Every `src`, `href` and `import` resolves to a local file.
- No `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `document.write`. Text is set with `textContent`.
- Colours, spacing, radius, fonts and durations come from `/static/styles/tokens.css` (linked, not copied). No new colour literals except inside three.js materials, which read the token values from `getComputedStyle` at start.
- Copy never contains "safety device" or "cane". The Prototype chip is always visible.
- No file in `howitworks/` over 10 MB; each `.glb` under 3 MB; folder under 8 MB.
- All figures and message names come from `SPEC.md` sections 2, 3, 5, 7 as they read on `main` at build time. Where the design doc's table disagrees with the spec, the spec wins.
- `prefers-reduced-motion: reduce` means: no idle drift, camera cuts instead of easing, pipeline tokens do not travel.
- Page URL is `/how-it-works/`; all asset URLs inside the page are relative.
- Python: type hints and a one-line docstring on every function. JS: one short comment per exported function.
- Before reporting any task done: run `pytest` and report the real result.

## Review Focus

1. **A model file is missing or corrupt** (the normal state until Task 5): the page must show the stand-in for that object, with no console error beyond one warning, and every hotspot still works. Pinned in Task 2.
2. **WebGL is unavailable or the 3D import fails:** the poster stays, the five panels appear as a plain list, the pipeline still works. Pinned in Task 2 (browser check) and Task 1 (list exists in the HTML before any script runs).
3. **Rapid or overlapping hotspot clicks** (click B while flying to A; Esc mid-flight): the last action wins, exactly one panel is open, focus ends on the right hotspot. Pinned in Task 3.
4. **Stepper driven past its ends or while playing** (Next on the last step, Back on the first, node click during Play, Play at the end): index stays in range, Play at the end restarts from step 0, a manual action pauses Play. Pinned in Task 4.
5. **High-contrast theme and narrow width (360 px):** text stays readable, hotspots stay visible against the scene, nothing overflows horizontally. Pinned in Task 7.

---

## File map

```
howitworks/
  index.html          document: theme boot, token CSS, import map, static fallback markup
  how.css             page layout and components, tokens only
  main.js             composition: reads prefs, mounts pipeline, then stage; owns fallback switch
  content.js          all copy and data (HOTSPOTS, NODES, TOUCH_STEPS, HAZARD_STEPS)
  stage/selection.js  pure: which hotspot is open
  stage/standins.js   simple-shape stand-in for each object
  stage/models.js     load each GLB, fall back to its stand-in
  stage/scene.js      renderer, camera, controls, lights, idle drift, flyTo
  stage/hotspots.js   hotspot buttons (CSS2DRenderer) and the detail panel
  pipeline/stepper.js pure: step index, play/pause
  pipeline/diagram.js SVG nodes/edges, token animation, caption, controls
  vendor/three/       three.module.js (+ three.core.js if the pinned build has it), addons/
  vendor/gsap/        GSAP ES module files
  vendor/LICENSES.md
  assets/models/      glasses.glb backpack.glb speaker.glb (Task 5)
  assets/poster.webp  (placeholder in Task 1, real in Task 5)
tests/howitworks_server.py   dev/test FastAPI app
tests/test_howitworks.py
tests/howitworks_js/*.test.mjs
```

---

### Task 1: Scaffold, content, static fallback page

**Files:**
- Create: `howitworks/index.html`, `howitworks/how.css`, `howitworks/main.js`, `howitworks/content.js`, `howitworks/vendor/**`, `howitworks/vendor/LICENSES.md`, `howitworks/assets/poster.webp` (flat placeholder)
- Create: `tests/howitworks_server.py`, `tests/test_howitworks.py`, `tests/howitworks_js/content.test.mjs`
- Modify: `DEVLOG.md` (team agreement, pinned library versions)

**Interfaces:**
- Produces, `content.js` (all frozen):
  - `HOTSPOTS: Array<{id, label, does, builtWith, number, stepId, anchor: [x,y,z], view: {position: [x,y,z], target: [x,y,z]}}>` with ids exactly `camera, pointing, laptop, speaker, hazard`.
  - `NODES: Array<{id, label}>` with ids exactly `camera, vision, scene, namer, audio, hazard, storage, dashboard`.
  - `TOUCH_STEPS: Array<{id, from, to: string[], message: string|null, caption}>`, six entries, ids `capture, frame, name-request, name-result, touch, outputs`, following design doc 5.3.
  - `HAZARD_STEPS`: same shape, ids `hazard-frame, hazard-event`.
  - `HOME_VIEW: {position, target}`.
- Produces, `tests/howitworks_server.py`: `build_dev_app() -> FastAPI` and module-level `app`; mounts `howitworks/` at `/how-it-works` with `StaticFiles(html=True)` and `dashboard/static/` at `/static`. Run with `uvicorn tests.howitworks_server:app --port 8010`.
- Produces, `index.html` element ids: `#stage` (contains `#stage-poster`, `#stage-canvas-host`), `#hotspot-panel`, `#hotspot-list` (the plain list of all five panels), `#pipeline`, `#pipeline-caption`.

- [ ] **Step 1: Write the failing tests.** `tests/test_howitworks.py` using `TestClient(build_dev_app())`:

```python
def test_page_is_served(): # GET /how-it-works/ -> 200, "How it works" and "Prototype" in body
def test_every_local_reference_exists(): # every src/href/import-map target in index.html -> 200
def test_no_remote_urls(): # no "http://" or "https://" in any howitworks/*.html|js|css outside vendor/, except the "http://www.w3.org/" XML namespaces
def test_no_banned_copy(): # "safety device", "cane" absent (case-insensitive) from index.html and content.js
def test_no_unsafe_dom_writes(): # innerHTML|outerHTML|insertAdjacentHTML|document.write absent outside vendor/
def test_file_sizes(): # each file <= 10 MB, each .glb <= 3 MB, folder <= 8 MB
def test_message_names_exist_in_contracts(): # every non-null `message` in content.js is a class in contracts.messages
def test_fallback_list_is_in_html(): # #hotspot-list has 5 <li>, present with no JS
def test_js_unit_tests(): # skipif no node; `node --test tests/howitworks_js/` exits 0
```

`content.test.mjs`: ids match the lists above exactly; every `HOTSPOTS[i].stepId` is a `TOUCH_STEPS` or `HAZARD_STEPS` id; every step's `from`/`to` are `NODES` ids; no empty strings.

- [ ] **Step 2:** Run `pytest tests/test_howitworks.py -v`. Expected: all fail (module not found).
- [ ] **Step 3: Vendor the libraries.** Use Context7 to confirm the current stable three.js and GSAP versions and their ES-module file layout. Fetch with `npm pack three@<ver>` and `npm pack gsap@<ver>` in the scratchpad, then copy only: three's module build file(s) and `examples/jsm/{loaders/GLTFLoader.js, libs/meshopt_decoder.module.js, renderers/CSS2DRenderer.js, controls/OrbitControls.js}` plus whatever those import (keep relative paths intact under `vendor/three/addons/`); GSAP's ES module `index.js` and the files it imports. Write `LICENSES.md` with both licences and exact versions.
- [ ] **Step 4: Write `content.js`** from design doc 5.2 and 5.3, checked against `SPEC.md` on `main`. `anchor`/`view` values are first guesses; Task 3 tunes them.
- [ ] **Step 5: Write `index.html`, `how.css`, `main.js`.** Head mirrors `dashboard/index.html`: `/static/core/theme-boot.js`, the four `/static/styles/*.css`, then `how.css`, then an import map `{ "three": "./vendor/three/three.module.js", "three/addons/": "./vendor/three/addons/", "gsap": "./vendor/gsap/index.js" }`, then `<script type="module" src="./main.js">`. Body: skip link; header with `← Dashboard` link to `/`, brand, `How it works`, Prototype chip (reuse `app-header`, `app-brand`, `ui-chip` classes); `#stage` with the poster `<img>`; `#hotspot-list` written out statically in HTML from the same copy (visible by default); `#pipeline` with the six steps as a static `<ol>`; closing line about how it was built. `main.js` for now only marks `document.documentElement.dataset.js = "ready"`.
- [ ] **Step 6:** Run `pytest tests/test_howitworks.py -v`. Expected: all pass.
- [ ] **Step 7:** Add the `DEVLOG.md` entry (agreement, versions, what was tested). Commit: `howitworks: scaffold page, content and vendored libraries`.

### Task 2: 3D stage on stand-ins

**Files:**
- Create: `howitworks/stage/standins.js`, `howitworks/stage/models.js`, `howitworks/stage/scene.js`
- Modify: `howitworks/main.js`, `howitworks/how.css`

**Interfaces:**
- Consumes: `HOME_VIEW` from `content.js`; `#stage-canvas-host`, `#stage-poster`, `#hotspot-list`.
- Produces:
  - `buildStandIn(THREE, name: "glasses"|"backpack"|"speaker") -> THREE.Group`
  - `loadRig(THREE, {baseUrl, onFallback(name)}) -> Promise<THREE.Group>`; never rejects. Children are named `glasses`, `backpack`, `speaker`, plus the cable line, Bluetooth arc, fingertip marker, ray and bottle from design doc 5.1.
  - `createStage(host: Element, {reducedMotion: boolean}) -> Promise<Stage>`; rejects if WebGL context creation fails. `Stage = { scene, camera, labelRoot: Element, flyTo(view, {instant?: boolean}) -> Promise<void>, setIdle(on: boolean), onFrame(fn), destroy() }`. A new `flyTo` cancels the one in flight.
  - `main.js`: on `createStage` success, add class `has-stage` to `#stage` (CSS then hides the poster) and set `hidden` on `#hotspot-list`, since the hotspot buttons and panel now carry the same content; on failure, leave the static page as is and `console.warn` once.

- [ ] **Step 1:** Implement `standins.js`: each object from boxes, cylinders and tori only, materials coloured from the page tokens, sized so the rig fits a unit of about 2 across.
- [ ] **Step 2:** Implement `models.js`: for each name try `GLTFLoader` (with `MeshoptDecoder`) on `${baseUrl}${name}.glb`; on any error call `onFallback(name)` and use the stand-in. Normalise each loaded model to its stand-in's bounding box so positions hold when real models arrive.
- [ ] **Step 3:** Implement `scene.js`: renderer with transparent background over the page colour, soft key and fill light, ground shadow, `OrbitControls` (no pan, zoom clamped, damping), idle drift of a few degrees that stops on first pointer/keyboard interaction, pauses on `visibilitychange` and via `IntersectionObserver`, and never starts under reduced motion. `flyTo` tweens camera position and controls target with GSAP over 0.9 s; `instant` or reduced motion sets them directly. Dynamic `import()` three and GSAP inside `createStage` so the pipeline never waits on them.
- [ ] **Step 4:** Wire `main.js` as described under Produces.
- [ ] **Step 5: Browser check (Playwright)** against `uvicorn tests.howitworks_server:app --port 8010`:
  - Page shows the stand-in rig; drag orbits; console has exactly three fallback warnings (no GLBs yet) and no errors. *(Review Focus 1)*
  - Reload with WebGL disabled (override `HTMLCanvasElement.prototype.getContext` to return `null` via an init script): poster and the five-item list are visible, pipeline section present, no uncaught error. *(Review Focus 2)*
  - With `reducedMotion: "reduce"` emulated: camera position is identical across two frames 500 ms apart.
- [ ] **Step 6:** `pytest`. Commit: `howitworks: 3D stage with stand-in rig and fallbacks`.

### Task 3: Hotspots, fly-in, panel

**Files:**
- Create: `howitworks/stage/selection.js`, `howitworks/stage/hotspots.js`, `tests/howitworks_js/selection.test.mjs`
- Modify: `howitworks/main.js`, `howitworks/how.css`, `howitworks/content.js` (tuned `anchor`/`view`)

**Interfaces:**
- Consumes: `Stage`, `HOTSPOTS`, `HOME_VIEW`.
- Produces:
  - `createSelection({ids: string[], onChange(current: string|null, previous: string|null)}) -> {current: string|null, open(id), close(), toggle(id)}`. `open` of an unknown id throws; `open` of the current id is a no-op; `onChange` fires only on real change.
  - `mountHotspots({stage, hotspots, selection, panel: Element, onSeeStep(stepId)}) -> {destroy()}`.

- [ ] **Step 1: Failing test** `selection.test.mjs`: open A then B gives `onChange` calls `(A,null)`, `(B,A)` and `current === B`; `close()` when nothing is open does not call `onChange`; `open("nope")` throws; `toggle(A)` twice ends `null`. *(Review Focus 3, state half)*
- [ ] **Step 2:** `node --test tests/howitworks_js/` fails. Implement `selection.js`. Passes.
- [ ] **Step 3:** Implement `hotspots.js`. Each hotspot is a `<button class="hotspot">` with `aria-label` "`<label>`: show details", attached with a `CSS2DObject` at `anchor`. Each frame, a hotspot whose anchor faces away from the camera (dot product of camera direction and anchor-from-centre) gets `hidden` and `tabindex="-1"`. On selection change: `stage.flyTo(view)` or `stage.flyTo(HOME_VIEW)`, set `aria-expanded`, dim the others, fill the panel (heading, `does`, `builtWith`, `number`, a "See it in the pipeline" button calling `onSeeStep`, a Close button) using `textContent`, move focus into the panel on open and back to the hotspot on close. Esc and a click on empty canvas call `selection.close()`.
- [ ] **Step 4:** Style the marker per design doc 5.2: a ring in `--color-accent` at reduced opacity, filled with its label shown on `:hover` and `:focus-visible`; minimum hit area 44 px.
- [ ] **Step 5: Tune** `anchor` and `view` for all five in the browser until each fly-in frames its part.
- [ ] **Step 6: Browser check:** Tab reaches each visible hotspot; Enter opens, Esc closes and focus returns; clicking hotspot B during the fly to A ends with only B's panel open and the camera at B's view; Esc mid-flight ends at home with no panel. *(Review Focus 3)*
- [ ] **Step 7:** `pytest`. Commit: `howitworks: hotspots with camera fly-in and detail panel`.

### Task 4: Pipeline stepper

**Files:**
- Create: `howitworks/pipeline/stepper.js`, `howitworks/pipeline/diagram.js`, `tests/howitworks_js/stepper.test.mjs`
- Modify: `howitworks/main.js`, `howitworks/how.css`

**Interfaces:**
- Consumes: `NODES`, `TOUCH_STEPS`, `HAZARD_STEPS`; `#pipeline`, `#pipeline-caption`.
- Produces:
  - `createStepper({steps, onChange(index, step), intervalMs = 2500, setTimer = setTimeout, clearTimer = clearTimeout}) -> {index, playing, next(), back(), goTo(i), jumpToNode(nodeId), play(), pause(), destroy()}`.
  - `mountPipeline(root: Element, {reducedMotion}) -> {selectStep(stepId: string), destroy()}`; `selectStep` switches to the hazard sequence when given a hazard step id, and scrolls `root` into view.
  - `main.js` passes `pipeline.selectStep` as `onSeeStep` to `mountHotspots`.

- [ ] **Step 1: Failing test** `stepper.test.mjs` with injected timers: `next()` on the last step stays on the last; `back()` on step 0 stays on 0; `play()` advances one step per interval and stops (`playing === false`) after the last; `play()` when already on the last step restarts from 0; `next()`, `back()`, `goTo()` and `jumpToNode()` during play set `playing` false; `jumpToNode("namer")` goes to the first step whose `from` or `to` includes it; `jumpToNode` of a node in no step leaves the index unchanged; `goTo(99)` throws `RangeError`. *(Review Focus 4)*
- [ ] **Step 2:** Fails, implement `stepper.js`, passes.
- [ ] **Step 3:** Implement `diagram.js`: build the SVG with `createElementNS` in the layout of design doc 5 (main line of five, three branches); each node is a focusable `<g role="button" tabindex="0">` with a `<title>`. On change: mark active node(s) and edge(s), set the caption text (`aria-live="polite"`), and move a token `<g>` (rounded rect plus the message name in `--font-mono`) along the active edge with GSAP over 0.8 s; when `message` is `null` no token shows; under reduced motion the token is placed at the edge end with no tween. Controls are real `<button>`s: Play/Pause (label and `aria-pressed` follow state), Back, Next, and "What about hazards?" which swaps to `HAZARD_STEPS` and shows the alarm edge drawn in front of the speech edge in `--color-danger`. Replace the static `<ol>` from Task 1 only after the SVG is mounted. GSAP is imported dynamically; if that import fails, steps still change without tweening.
- [ ] **Step 4: Browser check:** Play runs all six steps and stops; each message name appears; node click jumps; a hotspot's "See it in the pipeline" scrolls down and selects the matching step; hazard sequence plays; with WebGL disabled the stepper still works.
- [ ] **Step 5:** `pytest`. Commit: `howitworks: pipeline step-through`.

### Task 5: Real models and poster

**Files:**
- Create: `howitworks/assets/models/{glasses,backpack,speaker}.glb`, replace `howitworks/assets/poster.webp`

This task waits on Richard for inputs. Tasks 1 to 4 do not wait on it.

- [ ] **Step 1: Give Richard these ChatGPT image prompts** (one image each, square, 1024 or larger):
  - *Glasses:* "Product render of a pair of black wayfarer sunglasses with a small black USB webcam clipped to the centre of the bridge, lens facing forward and tilted slightly down, a thin black cable leaving the camera along the right arm. Single object, three-quarter front view from slightly above, arms open, whole object in frame with margin, plain light grey background, soft even studio lighting, no shadows on the background, no text, no logos, no people."
  - *Backpack:* "Product render of a plain charcoal fabric backpack standing upright, main zip open at the top with the edge of a closed silver laptop visible inside. Single object, three-quarter front view from slightly above, whole object in frame with margin, plain light grey background, soft even studio lighting, no text, no logos, no people."
  - *Speaker:* "Product render of a small rounded-rectangle portable Bluetooth speaker in dark blue woven fabric with a short fabric loop on one side. Single object, three-quarter front view, whole object in frame with margin, plain light grey background, soft even studio lighting, no text, no logos, no brand marks."
  - *Poster:* "Clean product illustration of a wearable kit laid out as worn with no person: black sunglasses with a small webcam on the bridge at the top, a charcoal backpack behind and below, a small dark blue speaker clipped to the strap, a thin cable from glasses to backpack. Warm off-white background (#F8F5EF), soft shadow, three-quarter view, generous margin, no text, no logos." Landscape 16:9.
- [ ] **Step 2:** Richard runs the three object images through Tripo or Meshy, exports GLB, and saves them into the scratchpad or `howitworks/assets/models/raw/` (git-ignored locally; never committed).
- [ ] **Step 3:** For each: `npx @gltf-transform/cli optimize raw/<name>.glb <name>.glb --compress meshopt --texture-compress webp --texture-size 1024`. Confirm the exact flags with `npx @gltf-transform/cli optimize --help` first.
- [ ] **Step 4:** Load the page and screenshot. A model that is visibly broken (missing arms, melted geometry) after one regeneration is dropped; delete its `.glb` so the stand-in is used.
- [ ] **Step 5:** Convert the poster to WebP at 1600 px wide, under 300 KB (`npx sharp-cli` or macOS `sips` plus `cwebp` if present; otherwise keep PNG and update the `<img>`).
- [ ] **Step 6:** Re-tune any hotspot `anchor` that no longer sits on its part. `pytest` (size test now covers real files). Commit: `howitworks: generated models and poster`.

### Task 6: Dashboard link, mount and transition

**Gate 2 applies.** Record Person 4's agreement in `DEVLOG.md` first.

**Files:**
- Modify: `dashboard/server.py` (in `_build_app`, next to the `/static` mount), `dashboard/static/components/app-shell.js` (the `welcome` block and header), `dashboard/static/styles/base.css` (append), `howitworks/how.css`, `tests/test_howitworks.py`

- [ ] **Step 1: Failing tests** added to `tests/test_howitworks.py`, built the way the existing dashboard tests build the real app (read `tests/` for the fixture in use):

```python
def test_real_dashboard_serves_page(): # GET /how-it-works/ -> 200
def test_dashboard_still_serves_index_and_static(): # GET / -> 200, GET /static/app.js -> 200
def test_dashboard_header_links_to_page(): # app-shell.js contains href "/how-it-works/"
def test_both_pages_opt_into_view_transitions(): # "@view-transition" in base.css and how.css
```

- [ ] **Step 2:** `dashboard/server.py`: add `HOW_DIR = Path(__file__).resolve().parents[1] / "howitworks"` and, guarded by `HOW_DIR.is_dir()`, `app.mount("/how-it-works", StaticFiles(directory=HOW_DIR, html=True), name="how-it-works")`.
- [ ] **Step 3:** `app-shell.js`: inside the existing `app-welcome__panel`, after the `<ol>`, add `<a class="ui-button ui-button--secondary" href="/how-it-works/">See the full walkthrough</a>`. The pop-open and its three steps stay. (Smallest change to Person 4's file; replacing the pop-open is their call.)
- [ ] **Step 4:** Append to `dashboard/static/styles/base.css` and add to `how.css`:

```css
@view-transition { navigation: auto; }
.app-brand { view-transition-name: empyrean-brand; }
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*), ::view-transition-old(*), ::view-transition-new(*) { animation: none; }
}
```

In `how.css` only: give `#stage` `view-transition-name: how-stage` and a `::view-transition-new(how-stage)` rise-and-fade of 24 px over 320 ms using `--easing`.
- [ ] **Step 5:** `pytest` (whole suite; the existing dashboard and agent1 foundation tests must still pass) and `python -m app --fake vision` starts.
- [ ] **Step 6: Browser check in Chrome** on the real app: the header link navigates with the brand held in place and the stage rising in; `← Dashboard` plays the reverse; the dashboard's socket reconnects and the camera panel resumes.
- [ ] **Step 7:** Commit: `dashboard: link and serve the How It Works page (agreed with Person 4)`.

### Task 7: Final verification and log

- [ ] **Step 1: Browser pass** at 1440 px and 360 px, in light and high-contrast themes (set `localStorage["empyrean.theme"] = "high-contrast"`): no horizontal scroll, hotspots visible against the scene, panel and captions readable. Fix what fails. *(Review Focus 5)*
- [ ] **Step 2:** Keyboard-only run through every hotspot and every stepper control.
- [ ] **Step 3:** With the network offline (Playwright `context.setOffline(true)` after the server is up on localhost), reload: the page is complete.
- [ ] **Step 4:** `pytest`, `ruff check tests/howitworks_server.py tests/test_howitworks.py dashboard/server.py`, `python -m app --fake vision`. Report actual output.
- [ ] **Step 5:** `DEVLOG.md` entry: what changed, what was tested and how, what teammates need to do (pull, no reinstall needed), that Claude Code did the work, and anything not verified. Commit.
