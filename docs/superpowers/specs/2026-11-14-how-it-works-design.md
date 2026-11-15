# How It Works page: design

Date: 2026-11-14. Status: awaiting approval. Nothing is built.

## 1. Intent

Hackathon judges should understand Empyrean in about a minute without anyone
narrating: what the wearer carries, what each part does, and how one touch
travels through the software to become a spoken name. The page is reached
from the dashboard and feels like part of it.

Decided by Richard: lives inside the dashboard app; built in a new folder
because team sign-off is not yet given; the 3D model comes from ChatGPT
renders run through an image-to-3D service; audience is judges; build
approach is three.js (approach A below).

## 2. Goals, non-goals, anti-goals

Goals

- A 3D model of the rig (sunglasses with webcam, backpack with laptop, JBL
  speaker) the visitor can orbit, with five quiet hotspots.
- Clicking a hotspot flies the camera to that part and opens a short panel.
- Below it, a step-through of the pipeline that follows one touch from
  camera to speaker, naming the message passed at each step.
- An animated transition from the dashboard into the page and back.
- Works with no internet: every library and asset is served locally.
- Usable by keyboard and screen reader, and with reduced motion.

Non-goals

- No live data. The page does not open the WebSocket or the video stream.
- No public hosting, no landing page, no mobile-first layout (it must not
  break at 360 px, but the demo is a laptop screen).
- No change to any engine module, message, threshold or Python dependency.

Anti-goals

- Copy that calls this a safety device or a cane replacement. It is a
  prototype, and the Prototype chip stays visible.
- A page that is blank or broken when WebGL is unavailable or a model file
  is missing.
- Anything that slows the dashboard or the frame loop. The page loads its
  3D code only on its own route.

## 3. Constraints

- Stack rule: plain HTML, native ES modules, plain CSS, no build step, no
  framework. three.js and GSAP are additions outside the approved stack and
  **need all four teammates to agree before building**. They are browser
  files only; `requirements.txt` does not change.
- Ownership: the page lives in a new top-level folder `howitworks/`, which
  no one owns yet (needs team agreement). Three edits fall in Person 4's
  `dashboard/` and must be made by Person 4 or with their agreement:
  1. `dashboard/server.py`: mount `howitworks/` and serve its `index.html`
     at `/how-it-works`.
  2. `dashboard/static/components/app-shell.js`: the header's "How it
     works" control becomes (or gains) a link to `/how-it-works`.
  3. One CSS rule opting the dashboard into the cross-page transition, and
     a transition name on the header brand.
- Venue Wi-Fi is unreliable, so no CDN. Libraries are vendored at pinned
  versions under `howitworks/vendor/` with their licence files.
- Repo rule: no committed file over 10 MB. Target under 3 MB per model
  after compression, under 8 MB for the whole folder.
- Dashboard foundation rules are followed here too: no `innerHTML`, text
  rendered as text, colours and spacing from `dashboard/static/styles/tokens.css`
  (linked, not copied).

## 4. Approaches considered

- **A. three.js, chosen.** Each object is its own model file, positioned in
  code. Hotspots are real HTML buttons placed over the canvas. GSAP drives
  camera moves and the pipeline animation. Picked because image-to-3D gives
  the best result one object at a time, so no scene has to be composed in
  Blender, and the camera moves can be shaped freely. Cost: the most code.
- **B. Google model-viewer.** A web component with hotspots and camera
  moves built in. Far less code, but it wants one combined model file and
  the camera motion is plainer.
- **C. Pre-rendered turntable images.** Not real 3D. Kept only as the idea
  behind the no-WebGL fallback.

## 5. The page

```
┌────────────────────────────────────────────────┐
│ ← Dashboard   Empyrean  How it works [Prototype]│
│                                                │
│   3D rig, slow idle drift, drag to orbit       │
│   ◦ Camera   ◦ Pointing   ◦ Laptop             │
│   ◦ Speaker  ◦ Hazard watch                    │
│   click ◦ → fly in, panel slides in at right   │
├────────────────────────────────────────────────┤
│ Follow one touch   [▶ Play]  [‹ Back] [Next ›] │
│ Camera → Vision → Scene → Grok namer → Audio   │
│           ↘ Hazard ───────────────↗ (alarm)    │
│           ↘ Tiger Data    ↘ Dashboard          │
│ Caption for the current step                   │
└────────────────────────────────────────────────┘
```

### 5.1 The 3D rig

- Three models: glasses with camera, backpack (laptop visible in the open
  top), speaker. Arranged as worn, with no human figure: glasses at head
  height, backpack behind and below, speaker clipped to the strap. A thin
  line suggests the USB cable; a dotted arc suggests Bluetooth.
- A hand is not modelled. The Pointing hotspot sits in front of the camera
  with a drawn ray from a small fingertip marker to a simple bottle shape.
- Lighting and background match the dashboard: warm off-white page, soft
  shadow, no dark "tech" scene.
- Idle: a slow drift of a few degrees. It stops on first interaction, when
  the tab is hidden, when the canvas is off screen, and entirely under
  reduced motion.

### 5.2 Hotspots

Small ring markers in the accent blue, low contrast with the scene until
hovered or focused, when the ring fills and a one-word label appears. Each
is a `<button>` positioned by three.js's CSS2DRenderer, in tab order, with
an accessible name. Hotspots behind the model fade out and leave tab order.

Click or Enter: the camera eases to a saved viewpoint for that part
(about 0.9 s), other hotspots dim, and a panel opens. Esc, the panel's
close button, or clicking empty space returns the camera and restores
focus to the hotspot. Under reduced motion the camera cuts instead of
easing.

Each panel has the same four parts: a plain sentence of what it does, what
it is built with, one number, and a "See it in the pipeline" link that
scrolls to and selects the matching step below.

| Hotspot | What it does | Built with | Number |
|---|---|---|---|
| Camera | Sees objects and hands in front of the wearer | Logitech webcam, OpenCV, YOLO11s with ByteTrack, MediaPipe Hands | 5 frames a second at 640 x 360 |
| Pointing | Works out which object the finger selects | Ray from the extended finger, a small state machine in `scene/` | Speech starts within 1 s |
| Laptop | Runs everything as one Python process; names objects and keeps history | In-process message bus, Grok vision, Tiger Data | Name stored within 2 s of an object settling |
| Speaker | Says the name; the alarm interrupts everything | pyttsx3 offline speech, pygame alarm, JBL Go 3 | Alarm always outranks speech |
| Hazard watch | Watches every frame for things to warn about | YOLO classes plus a Grok check, on its own path | Alarm within 0.5 s (fast tier) or 3 s |

All figures are from `SPEC.md` sections 2, 3 and 7. The builder re-reads
those sections and `main` at build time and uses what they say then; where
this table and the spec disagree, the spec wins.

### 5.3 The pipeline

A hand-drawn inline SVG with eight nodes: Camera, Vision, Scene, Grok
namer, Audio on the main line; Hazard, Tiger Data and Dashboard as
branches. Each node is a button.

"Follow one touch" has six steps, matching `SPEC.md` section 3.2. On each
step the active node and edge light up, a small labelled token (the
message name in monospace) travels along the edge, and the caption
changes:

1. Camera to Vision: a frame is captured; 5 a second are processed.
2. Vision publishes `FrameResult`: image, tracked objects, fingertips.
3. Scene sends `NameRequest` with a crop once an object is stable for 1 s.
4. Grok namer replies `NameResult`; the name is stored on the object.
5. The finger's ray lands; Scene publishes `TouchEvent`.
6. Audio speaks the name; Tiger Data logs it; the Dashboard highlights it.

A seventh, separate control, "What about hazards?", plays the parallel
path: `FrameResult` to Hazard to `HazardEvent` to Audio, with the alarm
visibly cutting in front of speech.

Play runs the steps about 2.5 s apart and can be paused. Back and Next
step manually; clicking a node jumps to the first step that involves it.
The caption is an `aria-live="polite"` region. Under reduced motion,
tokens do not travel; the step simply changes.

A closing line names how the project was built (four people, each with a
coding agent, modules meeting only through messages), since the prize
asks for it.

### 5.4 The transition

Cross-document View Transitions: both pages declare
`@view-transition { navigation: auto }`. The header brand and Prototype
chip carry a shared transition name so they stay put while the page body
cross-fades and the 3D stage rises in. Chrome and Safari animate; Firefox
and anything older navigate instantly, which is acceptable. The reverse
plays on "← Dashboard". The dashboard reconnects its socket on return as
it already does on any load.

### 5.5 Loading and fallback

- First paint is the header, a poster image of the rig, and the full
  pipeline section. The 3D code and models load after, and the poster
  cross-fades to the live canvas when ready.
- If WebGL is unavailable or a model fails to load, the poster stays and
  the five hotspot panels are shown beneath it as a plain list. The
  pipeline section never depends on WebGL.
- All explanation text is in the DOM, not drawn in the canvas.
- High-contrast theme from the dashboard is honoured via `theme-boot.js`.

## 6. Files

```
howitworks/
  index.html
  how.css
  main.js            composition only
  content.js         all copy: hotspots, steps, captions (one place to edit)
  stage/             scene, model loading, hotspots, camera moves
  pipeline/          SVG diagram and stepper
  vendor/            three (module build + GLTFLoader, MeshoptDecoder,
                     CSS2DRenderer, OrbitControls), gsap; pinned, licences
  assets/models/     glasses.glb, backpack.glb, speaker.glb
  assets/poster.webp
tests/test_howitworks.py
```

Exact three.js and GSAP versions are confirmed against their docs when
vendoring and recorded in `DEVLOG.md`.

## 7. Getting the models

1. Claude writes three ChatGPT image prompts: one object each, three-quarter
   view, plain light background, even lighting, no text or logos.
2. Richard generates them, runs each through an image-to-3D service (Tripo
   or Meshy free tier), and saves the GLB files into
   `howitworks/assets/models/`.
3. Claude compresses them with `gltf-transform` (run through `npx`; a
   developer tool only, nothing is added to the repo's dependencies) and
   checks size and appearance.
4. Known risk: thin parts such as glasses arms often come out badly. If a
   model is unusable after one retry, that object is built from simple
   shapes in code instead, in the same style, so the page never waits on
   an asset. Until real models arrive, the page runs on these simple
   stand-ins.
5. The poster is one more ChatGPT render of the whole rig.

Helpful tools, none required: Playwright and Context7 (already connected)
for checking the page and library docs; Blender MCP for mesh clean-up;
Meshy's MCP to automate step 2 if Richard has an API key.

## 8. Testing

- `tests/test_howitworks.py`: the route returns the page; every file the
  page references exists; no file in `howitworks/` exceeds 10 MB; page
  copy does not contain "safety device" or "cane"; every message name in
  `content.js` exists in `contracts/`.
- Existing `pytest` suite and `python -m app --fake vision` still pass.
- In a browser (Playwright): each hotspot opens and closes by mouse and
  keyboard; the stepper runs all steps; reduced motion and forced WebGL
  failure both give a usable page; the transition plays in Chrome.

## 9. Left to the builder

Exact camera viewpoints and easing; hotspot marker styling within the
tokens; SVG layout; wording polish within the content above; whether
Person 4's link replaces or sits inside the existing pop-open.

## 10. Build order and what gets cut

Decided by Richard: the 3D rig is the part that must survive.

1. 3D rig with hotspots and panels, on simple stand-in shapes.
2. Pipeline stepper.
3. Real generated models and the poster.
4. The three `dashboard/` edits and the page transition.

If time runs out, cut from the bottom. Without step 4 the page still
exists but has no link or animation from the dashboard.

## 11. Gates

- **Nothing is built until all four teammates agree** to the `howitworks/`
  folder and to vendoring three.js and GSAP. `AGENTS.md` rule 8 requires
  this first; it is Richard's to obtain. (Claude's call: no library-free
  head start either, because the folder itself needs agreement.)
- If the libraries are refused, stop and return to this design rather
  than improvising; approach C is the likely replacement.
- The three `dashboard/` edits are made by Claude as the last build step,
  **only after Richard confirms Person 4 has agreed** (decided by Richard).
  The agreement is recorded in `DEVLOG.md`.
- Until those edits land, the page is served for development and tests by
  a small FastAPI app created inside `tests/test_howitworks.py` that mounts
  `howitworks/` and `dashboard/static/` at the same URLs the real server
  will use (Claude's call). Assets are served under `/how-it-works/`.
