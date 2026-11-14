# Friendly clarity: a calmer, clearer Empyrean dashboard

Branch `design/friendly-clarity`, created from `539f0de0193876255baada563d09f06aacbd1a74`
(`design/bauhaus-polish`), the commit serving http://localhost:8002 when this work
started (process cwd `../empyrean-bauhaus`, clean tree; its full checks had passed).
The engine, backend services, contracts, shared store, WebSocket, camera stream,
audio telemetry and history queries are unchanged.

## 1. What the page answers first

At 1440 × 900, with no scrolling: **what is being touched** (name at 52 px with its
thumbnail and Touching/Holding badge), **what the audio system did** (directly
under the name), **what the camera shows** (a 740 × 415 picture beside it), and
**whether something needs attention** (one status line and one warning line
above). Before, the system status and an inactive warning took about 400 px and
the camera started below the fold (`before/before-1440x900.png` vs
`after/after-1440x900.png`).

## 2. Hierarchy changes

| Problem (before) | Change |
|---|---|
| Tall system-status block with five boxed chips | One line: connection, a dashed violet **Demo mode** tag when any module is a fake, and the summary. Every chip and detail is kept under **System details** |
| Inactive warning took a full section | One quiet line ("No recent warnings. This does not mean the path is clear."). An active real hazard still expands at once, pins to the top and hides Pip; a later simulation stays below it, smaller and dashed |
| Camera below the first screen | Touch and speech on the left (5 fr), camera on the right (7 fr); objects under touch; search and activity below |
| Heavy black borders everywhere | No page cage: transparent grid, light surfaces, 1 px warm dividers, 12 px corners. Focus rings (3 px blue, 4 px in high contrast) and selected states stay strong |
| Instructions repeated in three places | Header tagline only on wide screens; the long touch explanation moved into **How touch works**; the camera's "recorded clip" sentence folded into its title and alt text; search help shortened to one sentence |
| Secondary controls as loud as primary ones | Search is the only filled button in its area; Full screen, Pause and Clear are quiet text buttons; actual size, overlays and the legend are in **View options** |
| Tall empty search compartment, equal-height rows | Rows size to content (`align-items: start`); the search panel is 209 px |
| Ambiguous speech ring | Removed (and its Rive runtime and asset). Speech is words: **Queued, Speaking, Completed, Interrupted, Failed** for real audio; **"Demo audio — no sound."** leads for fake audio; **"No sound — the speech engine is unavailable, so phrases are only logged."** for log-only audio; **"Audio status unavailable"** without telemetry. Nothing is inferred from a touch |
| "Last speech completed" louder than "no sound played" | In demo or log-only mode the no-sound sentence leads on a pastel wash and the engine status follows in small grey text; "does not confirm it was heard" is shown only for real audio |
| Large, uninformative empty-touch art | Pointing Pip (76 px) beside "Touch an object to hear its name." |
| Camera alt text fixed | Alt text follows the state: recorded demo clip, live camera, out of date (with seconds), stream disconnected, offline, or waiting |

## 3. Two compact layouts compared (same live data, 1440 × 900)

| | A. Touch beside camera (`explorations/a-1440x900.png`) | B. Touch band, camera below (`explorations/b-1440x900.png`, `b-band.css`) |
|---|---|---|
| Touched object | immediate, top left | immediate, full width |
| Speech status | directly under the name | beside the name |
| Camera on the first screen | yes, full picture | only the top third; the band's right half is mostly empty |
| Wasted space | none visible | about 40 % of the band |

**Chosen: A.** It answers all four questions without scrolling and wastes no space.

## 4. Visual direction

Bauhaus discipline kept in alignment, type and selective asymmetry (5:7 columns,
one big name); execution softened. Tokens (`styles/tokens.css`, every pair measured):

| Token | Value | Contrast |
|---|---|---|
| page / surface | `#F8F5EF` / `#FFFFFF` | — |
| text / secondary | `#1F1F1F` / `#57524A` | 15.2:1 / 7.1:1 on page |
| control border | `#7A7367` | 4.3:1 or more |
| primary action and touch | `#1947B8` | 7.3:1; white on it 8.0:1 |
| pastel lavender / mint / peach | `#ECEAFB` / `#E4F3EA` / `#FDEBE2` | backgrounds and illustration only; secondary text on lavender 6.5:1 |
| hazard / simulation | `#B42318` / `#6D28D9` (dashed) | 6.6:1 / 6.5:1 |

High-contrast light keeps black ink, white paper, 2 px control edges and 4 px focus.

## 5. Pip assets

Source: the supplied sheet
`/Users/richardlan/Documents/Codex/2026-11-14/referenced-chatgpt-conversation-this-is-an/outputs/empyrean-pip-mascot-poses.png`
(1536 × 1024 RGBA, sha256 `0cc443881b720634ea4177c4efa5651029f869b17731a99ff71174c9b8898405`).
Prepared by `tools/extract_pip.py` (re-runnable):

- Each pose is the one connected shape in the sheet's alpha channel. Everything
  else is dropped: 3,929 other fragments, 3,891 of them under 50 pixels, all
  near-transparent (the stray coloured dots visible on the sheet).
- Body alpha in the sheet tops out at 254; pixels at 200 or above are made fully
  opaque so Pip is not faintly see-through; the anti-aliased outline keeps its
  partial alpha.
- Cropped with 4 % padding, resized on premultiplied colour (no dark halo), and
  checked on the page colour, white and a dark checkerboard: one shape each,
  fully transparent edges, no specks (`test_friendly.py`).

| File | Pose | Size | Placement (alt="", words beside it carry the meaning) |
|---|---|---|---|
| `assets/pip/pip-wave.png` | waving, eyes open | 201 × 192 (shown 84 × 80) | **How it works** welcome panel in the header, closed by default |
| `assets/pip/pip-point.png` | pointing | 211 × 192 (shown 84 wide) | beside "Touch an object to hear its name." when nothing is touched |
| `assets/pip/pip-sit.png` | seated | 203 × 192 (shown 68 × 64) | empty Recent activity |
| `assets/pip/pip-peek.png` | sign-holding, cropped above the sign | 445 × 189 (shown 216 wide) | **How touch works**: Pip peeks over an HTML sign whose text is real and grows with it |

Not shipped: the closed-eyes "happy" pose (so no pose reads as reassurance) and
the narrow sign pose. Rules enforced: Pip is decorative everywhere, 64–96 px in
panels, at most one prominent Pip at a time, hidden during an active real
hazard (`layout.css`), never in the camera feed, thumbnails or history. No Pip
pose is tied to speech, so nothing suggests listening or microphone input.

## 6. Earlier resources

- **Rive** (`awesome-rive`): the speech ring was removed because it was ambiguous;
  with it went `@rive-app/canvas`, the WASM, the recoloured asset, the recolouring
  tool and their tests (2.8 MB less to load). No new Rive asset was added: no
  candidate in the MIT runtime repos explained touch-to-speech better than words.
- **21st.dev**: kept where it helps. The Search arrow nudge and loading square
  (cnippet "sliding", MIT) and the sliding filter bar (alexisroe "segmented",
  MIT). The circle fill (Magic UI, MIT) remains only on the few outlined
  secondary buttons; quiet buttons have no motion. Everything is off under
  reduced motion.

## 7. Verification

Commands and results on the final commit (see the handoff line in `DEVLOG.md`):

| Check | Result |
|---|---|
| `pytest -q` | 288 passed, 1 skipped (live Tiger Data test; no database URL) |
| `ruff check .` | clean |
| `node --test` agent1 / agent2 / agent3 / agent4 | 42 / 21 / 16 / 12 |
| `tests/ui/friendly/friendly-check.mjs` (four live servers) | 48 / 48 |
| `tests/ui/agent4/integrated-check.mjs` normal / hazard / unavailable / disconnect | 49/49, 8/8, 4/4, 6/6 |

Demo inputs used where hardware or services are absent, all labelled:
`python -m app --fake vision namer storage audio` (recorded clip, fake namer,
in-memory store, printed speech), `--fake … hazard` (scripted hazards),
`--only dashboard --fake scene` (camera offline, nothing running), and
`tests/ui/friendly/demo_harness.py`, which replays real-mode speech statuses
(queued, speaking, completed, failed) and log-only audio without speaking, stops
and restarts the recorded clip (stale, offline, recovery), or runs the real
storage module with no database (search unavailable). One display-only input:
a long name pushed into the browser store to check wrapping.

Covered live: active touch and no touch; real, fake, log-only, failed and
unavailable audio; active real hazard then a simulation; camera live, stale,
offline and recovery; empty (cleared) and populated history with grouped
repeats; search found, not found, unavailable, and timed out with hanging POST
and GET; long names; both light themes; keyboard (skip link, focus ring on every
control reached); reduced motion; 360, 768, 1440 px and 720 CSS px at 2×;
contrast of every visible text element in both themes.

**Not verified:** the physical camera, audible speech or alarm, Grok, Tiger Data,
screen readers, Firefox, Safari and real browser zoom. Fake-backed checks do not
establish any of them.
