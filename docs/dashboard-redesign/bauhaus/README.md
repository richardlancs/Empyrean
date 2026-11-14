# Empyrean Bauhaus redesign

Branch `design/bauhaus-polish`, created from the completed integration commit
`81bef40cf3289a00cbdd4a4ca6fedf3ebda9aa41` on `design/light-dashboard-integration`
(verified first: clean tree, 281 passed / 1 skipped, ruff clean, node 42/21/16/12,
and the six cleanup fixes present). The layered application, the engine wiring
and every API are unchanged; this branch changes presentation, adds one Rive
component, artwork and three adapted interactions.

## 1. Design rationale

Empyrean is a working accessibility instrument, so the Bauhaus language is used
for function: a disciplined grid, strong rules instead of floating cards, one
typographic headline (the touched object), and colour that always means
something.

| Colour | Use | Never |
|---|---|---|
| Ivory `#F4F0E7` / `#FFFCF5` | paper and panels | — |
| Near-black `#171717` | text, rules, the identity rail | — |
| Blue `#1947B8` | action, touch, selection, focus | decoration |
| Red `#B42318` | hazards and errors only | camera "opening" or "stale" (moved to yellow in pass 2) |
| Yellow `#F2C94C` | held state, caution fills, always with near-black text and outline | text, or a fill without an outline (1.4:1 on ivory) |
| Violet `#6D28D9` + dashed line | simulation only, always labelled "Simulated" | real warnings |

Square corners everywhere; circles only where they mean something (status dots,
the fingertip, the speech signal). No shadows, gradients, glass, or floating
decoration. Measured contrast: every text pair ≥ 6.1:1 in light and ≥ 7.8:1 in
high contrast (`tokens.css` comments, `test_token_contrast_meets_wcag`, and the
live audit of every visible text element in `tests/ui/bauhaus/bauhaus-check.mjs`).

## 2. Three compositions explored (same live state, an object being touched)

Each was a stylesheet injected only into the screenshot browser over the same
live app (`tests/ui/bauhaus/shoot.mjs --css`); the stylesheets and captures are
in `explorations/`.

| | A. Asymmetric typographic | B. Instrument panel | C. Geometric hand–object–sound |
|---|---|---|---|
| Files | `a-typographic.css/.png` | `b-instrument.css/.png` | `c-geometric.css/.png` |
| Touched object found | fastest (poster headline) | good, but wrapped in a 400 px column | slowed by shapes above the name |
| Speech status and hazards | speech clear; warnings fell below the camera and fold | warnings and status at the top | shapes compete with status |
| Camera usefulness | squeezed into a narrow column | large, framed instrument | large |
| Readability, keyboard | good | good, ruled modules keep reading order obvious | decorative shapes add noise |
| Distinctive without distraction | distinctive | distinctive and calm | floating yellow circle is pure decoration |
| Working accessibility dashboard | weak on hazards and camera | strongest | weakest |

**Chosen: B's rails and ruled modules, with A's typographic weight given to a
full-width touch band above the camera.** C's geometry survives only where it
carries meaning: the Rive speech signal (circles and arcs = sound) and the
idle-state illustration.

## 3. Revision passes

| Pass | Screenshot | Changes |
|---|---|---|
| 0 | `screenshots/pass0-1440.png` | first implementation of the chosen direction |
| 1 (remove generic patterns and competing focal points) | `pass1-1440.png`, `pass1-360.png`, `pass1-hc-1440.png` | black bands at the page edges removed (the grid carried the container padding); the footer strip shrunk from a second headline to a 300 px secondary figure |
| 2 (alignment, typography, consistency, motion, responsiveness) | `pass2-1440.png`, `pass2-360.png` | red removed from non-error camera states (opening and stale now use the yellow caution fill); status cells on an aligned grid at every width; speech column narrowed signal (56 px) on phones; status symbol kept on the same line as its words; the still image redrawn to match the Rive file's first frame so loading the animation causes no visual jump |

Before and after: `screenshots/before/*` (integration branch) and
`screenshots/after-*` (this branch).

## 4. Rive

| | |
|---|---|
| Discovered through | https://github.com/rive-app/awesome-rive (runtime list → the MIT runtime repos) |
| Candidates inspected | `rive-wasm` examples (`message_icon`, `rating_animation`, `look`, `switch_event_example`: saturated pink gradients or figurative avatars, rejected) and `rive-android` test assets (`artboard_animations`, `basketball`, `button`, `circle_move`, `loopy`, `progress`, `blend_state`) |
| Chosen asset | `progress.riv` from https://github.com/rive-app/rive-android, path `app/src/main/res/raw/progress.riv`, branch `master` at `a637c284e421a16b03b0c0e62e3e0ffe26cc1668`, sha256 `5e11544033eccde437d658e240eb84b03032f3380ed020947012d5c5262c6b96` |
| Licence | MIT, Copyright (c) 2020-2024 Rive (`dashboard/static/assets/rive/LICENSE-rive-android`) |
| Modification | colours only, 42 values: background `#313131` → transparent; white → `#171717`; Google blue `#4285F4` and greens → `#1947B8`; reds `#DB4437`/`#EA4335` → `#171717` (red stays reserved for hazards); yellows → `#F2C94C`; alpha kept. Geometry and timing untouched. Tool: `tools/riv_recolor.py` (parses the whole file and refuses to write unless it ends exactly at the end of the file; field types from rive-runtime `core_registry.hpp`, MIT, commit `364421d0`, stored in `tools/riv_field_types.json`) |
| Shipped file | `dashboard/static/assets/rive/speech_signal.riv`, sha256 `ffa1ee4b5abddc52e0f975551edcd4d954af2d8fbc589f126bef87171b709865` |
| Runtime | `@rive-app/canvas@2.47.1` (MIT, released 2026-10-24), from npm tarball sha256 `92f1ed8e536971fa2fb3ce94c763caea539b7e8687f6c0fa65352bfdc68d4e5a`; vendored `vendor/rive/rive.js` sha256 `51502697bcadb2a284bb482a09dac4a7ed7b88dd75ee5c7ad05d12b78447151a` and `rive.wasm` sha256 `4166e1b487c7c9c3d2652240dc4a048b63c9fc4bdbac4296943b56e4173fe94f` (2.8 MB together), licence `vendor/rive/LICENSE` |
| Component | `dashboard/static/components/speech-signal.js` |

Behaviour: the still image (`speech-signal-still.svg`) renders at once; the
runtime loads only when the browser is idle; WASM comes from `/static/vendor/rive/`
and the runtime's CDN fallback is disabled. The animation plays **only while
the speech telemetry says `status: "speaking"` with `mode: "real"`** and the
dashboard is connected, so printed (fake) or log-only speech never animates it.
It pauses offscreen and when the page is hidden, is never loaded under reduced
motion, falls back to the still on any runtime or file error, and is disposed on
unmount. It is `aria-hidden`; the speech status text beside it is always
present and is updated in the same render, never after an animation.

## 5. Generated images: unresolved dependency

**No ChatGPT/OpenAI image-generation access was available in this session**: no
image tool, no `OPENAI_API_KEY` in the environment or `.env`, and no ChatGPT or
OpenAI CLI. No image was generated and none is claimed. Instead the three slots
ship with **hand-authored SVGs** (marked "Hand-authored (not generated)" in each
file) in the same vocabulary, so the page is complete and a generated image can
replace a file without code changes.

Shared style line for every prompt: *Original Bauhaus-inspired flat geometric
illustration for an accessibility prototype. Palette only: warm ivory #F4F0E7
background (or transparent), near-black #171717, deep blue #1947B8, yellow
#F2C94C. Circles, squares, straight lines, one restrained diagonal. Flat colour,
no gradients, no shadows, no texture, no text, no letters, no numbers, no logos,
no people's faces, no photographic elements. Strong asymmetric composition on a
grid, generous empty space.*

| Slot (file to replace) | Placement and alt | Size, format | Prompt (after the style line) |
|---|---|---|---|
| `assets/illustrations/touch-idle.svg` → `touch-idle.png` | touch band when nothing is touched; decorative (`alt=""`), the sentence "Touch an object to hear its name" carries the meaning | 960 × 400, PNG with transparent background | *A blue circle (a fingertip) touching the corner of a solid near-black square (an object); three concentric arcs to the right, alternating yellow and black, suggesting sound; a thin black baseline; one small outlined triangle.* |
| `assets/illustrations/history-empty.svg` → `history-empty.png` | empty Recent activity; decorative, the empty-state sentence carries the meaning | 640 × 320, PNG transparent | *An empty record card: a black outlined rectangle containing three short dashed grey lines, a small yellow circle with a black outline overlapping its top-right corner, a thin black baseline. Quiet and sparse.* |
| `assets/illustrations/how-it-works.svg` → `how-it-works.png` | footer strip above three HTML steps ("The camera sees…", "A fingertip lands…", "The speaker says…"); decorative | 1200 × 240, PNG transparent | *Three geometric glyphs in a row joined by black lines on a baseline: a black outlined square with a blue circle inside (a camera), a black square with a blue circle at its lower corner (a touch), three concentric yellow and black arcs (sound).* |

Rules for any future generated image: keep it out of the camera feed, object
thumbnails and history; never let it resemble a detected object or a real
observation; no embedded text (labels stay HTML); optimise (≤ 120 KB) and record
the prompt, date and tool here.

## 6. 21st.dev interactions (adapted to native CSS, no framework added)

| Interaction | Reference (inspected) | Licence | Adaptation | Where |
|---|---|---|---|---|
| Circle grows to fill on hover/focus | https://21st.dev/@dillionverma/components/interactive-hover-button (Magic UI; source `magicuidesign/magicui` `apps/www/registry/magicui/interactive-hover-button.tsx`) | MIT (21st.dev listing and GitHub repo) | A small blue circle at the start of secondary buttons scales to fill with the light blue tint. The original swaps the label for a white one mid-transition; here the text never changes colour, so every frame keeps ≥ 15:1 contrast. Disabled buttons do not react | camera controls, Pause / Clear / Show cleared activity |
| Label nudge with arrow, then a loading state | https://21st.dev/@cnippet-dev/components/cnippet-button/sliding (bundle `cdn.21st.dev/larsen66/cnippet-button/sliding/bundle.1783605523635.html`) | MIT (21st.dev listing) | On hover/focus the "Search" label moves 4 px left and an arrow slides in; while a search runs (`data-loading`) a still square replaces the arrow. Arrow space is reserved, so no layout shift; no continuous motion; the accessible name stays "Search" | last-touch search button |
| Segmented control | https://21st.dev/@alexisroe/components/segmented | MIT (21st.dev listing) | Equal square segments in one ruled rail with the selected one filled (as in the original). Added: a black bar under the rail slides to the selected segment. Fill and label change at once so no text is ever half-covered; only the bar moves. Pure CSS with `:has()` | All / Touch / Warning filters |

Rejected: `@clevision/components/buttons/button-loading` (no licence stated);
`@anubra266` segment and tab components (no licence stated); Adobe
`css-segmentedcontrol` (Apache-2.0, fine, but the MIT one fitted better).
All motion is 120–180 ms, transform/opacity only, and switched off under reduced
motion by `base.css`.

## 7. Asset, source and licence inventory

| Item | Path | Source | Licence | Notes |
|---|---|---|---|---|
| Rive runtime | `dashboard/static/vendor/rive/rive.js`, `rive.wasm` | npm `@rive-app/canvas@2.47.1` | MIT | hashes in section 4 |
| Speech signal | `dashboard/static/assets/rive/speech_signal.riv` | rive-android `progress.riv` | MIT | recoloured |
| Speech signal still | `assets/illustrations/speech-signal-still.svg` | hand-authored for Empyrean | project | matches frame 0 |
| Touch idle | `assets/illustrations/touch-idle.svg` | hand-authored (not generated) | project | slot for a generated PNG |
| Empty history | `assets/illustrations/history-empty.svg` | hand-authored (not generated) | project | slot for a generated PNG |
| How it works | `assets/illustrations/how-it-works.svg` | hand-authored (not generated) | project | slot for a generated PNG |
| Field-type table | `tools/riv_field_types.json` | generated from rive-runtime `core_registry.hpp` @ `364421d0` | MIT | design tooling only |
| Interaction ideas | CSS in `experience.css`, `operations.css` | 21st.dev components in section 6 | MIT | re-implemented, no code copied |

## 8. Verification

| Check | Result |
|---|---|
| `pytest -q` (repo root) | see handoff for the final count (all pass except the live Tiger Data skip) |
| `ruff check .` | clean |
| `node --test` agent1 / agent2 / agent3 / agent4 / bauhaus | 42 / 21 / 16 / 12 / 8 |
| `tests/ui/agent4/integrated-check.mjs` on this build: normal / hazard / unavailable / disconnect | 49/49, 8/8, 4/4, 6/6 (three checks now read the shell's tokens instead of the old palette literals) |
| `tests/ui/bauhaus/bauhaus-check.mjs` | 25/25: Rive loads after content, plays only for real speaking, stops on completion, pauses offscreen and when hidden, local-only requests, disposed on destroy; fake speech never animates; reduced motion never loads it; a failed runtime keeps the still; the three interactions behave; every visible text element meets AA in both themes |
| Rive performance with the MJPEG stream and `/ws` updates running | frame time p95 16.7 ms over 3 s, 0 long tasks |

States exercised live: touching, holding (scene fake), released and retouch
(clip cycle); speech queued, speaking, completed and interrupted (fake audio and
the scripted hazard) and unavailable (`--only dashboard`); "failed" only in the
existing unit tests. Active real warning followed by a simulation; camera
opening, live, offline, disconnect and recovery (stale frames only in unit
tests). Search found, not found, timeout with hanging POST and GET, unavailable
storage (pytest e2e) and overlapping searches (unit and pytest). Activity
populated and cleared-empty. Light and high contrast; keyboard and focus;
reduced motion; 360, 768, 1440 px and 720 CSS px at 2× (real browser zoom not
used).

**Not verified:** physical camera, audible speech or alarm, Grok, Tiger Data,
the Rive animation driven by a real speech engine (its motion was exercised
with `tests/ui/bauhaus/launch_with_speech.py`, a test harness that replays
`mode: "real"` telemetry without speaking), screen readers, Firefox and Safari.
