# DEVLOG.md

Running log of what was done, decided and broken. Humans and agents both write here. Newest entry at the top of the "Entries" section.

## How to add an entry

Copy this template. Keep it short. Never include keys or connection strings.

```
### YYYY-MM-DD HH:MM, Person N (module), tool used
**Changed:** what you built or altered
**Tested:** what you ran and what happened
**Decisions:** anything decided, with the reason
**Teammates need to know:** anything others must do or watch for, or "nothing"
```

"Tool used" is Cursor, Claude Code, Grok Bot, or by hand. The SpaceXSI prize write-up needs to describe how Cursor and Grok Bot were used, so be specific here.

## Needs attention

- **TEAM PRIORITY — demo recognition remains failing (all four, 2026-11-14):** read `demotraining.md`. Person 1 owns watch/water bottle; Person 2 charger/toothpaste; Person 3 keys/phone; Person 4 headphones/toothbrush. Each person must collect separate training/evaluation sessions and train a full eight-class candidate using the frozen bootstrap plus their additions. Current live result: toothpaste works, watch is often classified charger, actual charger is sometimes absent. Headphones/keys also remain inconsistent. The model is experimental, not demo-ready.




- **IN PROGRESS — Person 4: missed tabletop objects in video (assigned by user, 2026-11-14).** Person 4 leads this investigation now. Coordinate with Person 1 for vision changes and Person 2 for camera footage and scene changes. See the handoff entry below; coordinate with Person 4 before duplicating work. First evidence (Person 4 trace entry below): a small, far bottle is seen by YOLO in every frame but dropped by the 2% area filter, and by the 0.5 confidence gate before ByteTrack. A large black bottle with a handle is not recognised as a bottle at all. Fix agreed by all four and merged in PR #19: `DET_MIN_AREA_FRACTION = 0.002` and `DET_MIN_CONFIDENCE = 0.3`. Still to do: rehearse the demo objects at arm's length on the glasses camera (see the demo readiness entry), then close this item. Unrecognised objects remain a model limit.

Problems in someone else's folder go here. The owner removes the line once fixed.

- **Voice goal audit (Person 4, 2026-11-14):** User requested question-only object speech, explicitly overriding SPEC touch announcements; shared spec is unchanged pending team agreement. Current camera answers are bounded tracked-object/touch summaries, not arbitrary visual QA. GROK_API_KEY, GROK_MODEL and TIGER_DATABASE_URL are absent locally, so brand naming, Grok hazards and history are not live-verified. Speech-finished bus signaling is absent; microphone pause is estimated, so reliable echo suppression remains open. Browser speech service fails in the in-app browser; real Chrome transcription was observed working. No new cross-module contracts were introduced.

- **Person 1 (`vision/`, please review):** Person 2 added demo mode to your folder: `vision/vision.py` (second detector, `set_mode`, `ModeChange` handling) and the new `vision/build_demo_weights.py` and `vision/capture_demo_refs.py`. See the "demo mode built" and "demo detector changed to YOLOE" entries. Keep, change or revert, then remove this line. Reference pictures of the eight demo objects still have to be taken on the Logitech camera.
- **Person 4 (`dashboard/`, please review):** Person 2 added the Demo mode button, `POST /api/mode` and the `mode` field in the page state (`server.py`, `state.py`, `index.html`). Keep, change or revert, then remove this line.
- **Persons 1, 3 and 4 (shared files):** Person 2 added `ModeChange` to `contracts/` and `DEMO_DET_MIN_CONFIDENCE` to `config/`, with matching rows in `SPEC.md` sections 5 and 9, before the other three confirmed. Say yes or ask for it to be reverted.
- **Person 1 (voice questions):** read the "voice questions plan for Person 1" entry before building. Confirm first that a Google Home can pass questions to our process at all.
- **Person 1 (`hazard/`):** the narrowed tier B prompt has only been tested on scenes with no hazard (0 of 10 flagged). Test it on real stairs, a doorway and a wall before the demo. If it misses them, loosen the "do not count" list.
- **Person 4 (`dashboard/`, please review):** Person 2 added the live camera feed and the Objects panel to your folder (`dashboard/video.py`, `server.py`, `state.py`, `__init__.py`, `index.html`, `requirements.txt`, and the dashboard tests). Keep, change or revert, then remove this line.
- **Person 4 (`audio/backends.py`, please review):** Person 2's fix that builds a fresh `pyttsx3` engine per phrase. Confirm it on the JBL.
- **Person 3 (`namer/grok_client.py`, please review):** Person 2 rewrote `INSTRUCTION` so Grok names a brand only when it is printed and readable. Rerun `fakes.namer.eval_batch`, then remove this line.
- **Person 3 (naming on real crops):** accuracy on Logitech camera crops of the demo objects is still unmeasured. `fakes.namer.crop_recorder` and `eval_batch --manifest` are ready for it.
- **Persons 1 and 4:** add your names to the Team table at the bottom. Person 1: an early entry lists the tool as "ChatGPT GPT-6", which is not in the stack table's coding agents. Confirm or correct it for the SpaceXSI write-up.
- **All:** `SPEC.md` section 12 still has open questions (SpaceXSI prize rules, HackUMass category count, submission deadline, which laptop runs the demo). A full run on the Logitech webcam and the JBL together is not recorded in this log yet.

Closed on 2026-11-14 (checked against the code on `main` at `64f878b`): the scene/namer threading race (`app/__main__.py` wraps `handle_frame` and `handle_name` in one lock), and all six of Person 3's `app/` bus requests (bus shape, `load_dotenv()` before registering, thread-safe `publish`, scene adapter, `stop()` at shutdown, fake paths).

Closed during the Person 2 local update on 2026-11-14: fake-hazard playback now starts after subscribers register, and the CLI smoke test waits for a frame log instead of a fixed sleep (merged PR #17).

## Contract changes

Any change to `contracts/`, `config/`, `SPEC.md` or `AGENTS.md`. Needs all four to agree.

| When | What changed | Agreed by |
|---|---|---|
| 2026-11-13 21:10 | First version of all four files | pending team review |
| 2026-11-13 22:05 | Stack table added to `SPEC.md` section 2.1, `AGENTS.md` and `CLAUDE.md` | pending team review |
| 2026-11-13 23:40 | Initial `contracts/messages.py` and `config/thresholds.py`, copied from SPEC.md sections 5 and 9. No value changed | pending team review |
| 2026-11-14 01:03 | PR #2 merged to `main`: `Box` and `Point` are tuples, the fixed value sets are `Literal`, list fields default to empty, the dataclasses are no longer frozen, and `tests/test_contracts.py` checks them against SPEC.md. No threshold changed | Person 3 (author), Person 2 (adopted in `scene/`). Persons 1 and 4 still to confirm |
| 2026-11-14 | Docs brought in line with the code on `main`. `SPEC.md` 2.1, 3.1 and 4.2, `AGENTS.md` and `CLAUDE.md`: YOLO nano to YOLO small (`yolo11s.pt`). `SPEC.md` 4.5: naming prompt names a brand only when readable, and scene owns the one retry. `SPEC.md` 4.7: narrowed tier B prompt. `SPEC.md` 6 and 12: Grok model name resolved. `contracts/README.md`: proposal text replaced with the current shapes. No message field and no threshold changed | All four, as confirmed by Person 2 to the agent |
| 2026-11-14 | New message `ModeChange` (`ts`, `mode`: `actual` or `demo`) in `contracts/` and `SPEC.md` section 5. New threshold `DEMO_DET_MIN_CONFIDENCE` = 0.25 in `config/` and `SPEC.md` section 9. YOLOE (`yoloe-11s-seg.pt`, Ultralytics, pretrained, no training) used as the detector in demo mode only, after YOLO-World was tried and dropped; `yolo11s.pt` unchanged in actual mode. No existing field or value changed | Person 2 only, who told the agent to build it. Persons 1, 3 and 4 still to confirm |
| 2026-11-14 | Dashboard redesign (branch `design/light-dashboard-integration`, not yet on `main`). Additive only: `LastSeenQuery.request_id` (optional); new `LastSeenResult`, `SpeechStatus`, `ModuleStatus` messages; config `CAMERA_STALE_SECONDS` 2.0, `LAST_SEEN_TIMEOUT_SECONDS` 8.0, `THUMBNAIL_MAX_AGE_SECONDS` 30.0; SPEC sections 2.1, 4.9, 5 and 9 and the AGENTS.md stack row describe the layered dashboard. No existing field, unit or value changed | Authorised by the user for this redesign; team to review before merge |

## Stack

The approved stack, repeated here so every log reader has it. Changes go through the contract changes table above.

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Camera capture and drawing | OpenCV (`opencv-python`) |
| Object detection and tracking | Ultralytics YOLO small (`yolo11s.pt`), COCO weights, ByteTrack |
| Hand tracking | MediaPipe Hands |
| Brand naming and hazard check | Grok vision model over the Grok API, called with `httpx` |
| Database | Tiger Data (Postgres with time-series hypertables), `psycopg` 3 |
| Speech | `pyttsx3`, offline |
| Alarm sound | `pygame` mixer, pre-made WAV |
| Web server | FastAPI on Uvicorn |
| Dashboard page | Minimal `index.html` plus native ES modules and plain CSS under `dashboard/static/` (no build step, no framework). MJPEG video, one WebSocket |
| Message bus | In-process publish and subscribe in `app/` |
| Settings and secrets | `python-dotenv`, `.env` |
| Tests and formatting | `pytest`, `ruff` |
| Version control | Git and GitHub |
| Coding agents | Cursor, Grok Bot, Claude Code |
| Hardware | Logitech USB webcam, laptop, JBL Go 3 over Bluetooth |
| 2026-11-14 | Pointing replaces touch as the announcement trigger (branch `pointing-trigger`). Additive: `Hand.landmarks` (21 points, defaults to empty) in `contracts/` and `SPEC.md` section 5; new thresholds `POINT_EXTENDED_RATIO` = 1.1 and `POINT_MIN_FINGER_PIXELS` = 15.0 in `config/` and `SPEC.md` section 9. `SPEC.md` 1, 3.2, 4.3, 4.6 and 4.8 rewritten for pointing; 4.8 now matches the code's automatic-speech default. No existing field, unit or value changed | The user overrode folder ownership for this change; all four still to confirm before merge |

## Entries

### 2026-11-14, How It Works page (howitworks/), Claude Code
**Authorization:** Richard confirmed all four teammates agreed to a new top-level `howitworks/` folder and to vendoring two browser libraries, three.js 0.187.0 and GSAP 3.15.1, under `howitworks/vendor/`. No Python dependency changed; nothing to reinstall.

**Changed:** New static page for judges: a 3D model of the kit with five markers that open short explanations, and a step-through of the message pipeline. Design in `docs/superpowers/specs/2026-11-14-how-it-works-design.md`, plan in `docs/superpowers/plans/2026-11-14-how-it-works.md`. Development server that needs no engine: `uvicorn tests.howitworks_server:app --port 8010`, then open `/how-it-works/`.

**Tested:** Full `pytest` on the branch: 402 passed, 1 skipped (live DB), existing Starlette/httpx warning. `tests/test_howitworks.py` (10 tests) covers the route, local references, no remote URLs, banned copy, file sizes, and message names against `contracts/`; it also runs 15 `node --test` unit tests for the content, hotspot selection and stepper. Browser checks with Playwright against the development server: 3D stage renders and orbits; with WebGL disabled the poster, the five explanations and the pipeline remain; reduced motion keeps the camera still; every marker opens by keyboard, Esc closes and returns focus; overlapping clicks leave one panel open; all six pipeline steps and the hazard path play; no horizontal overflow at 360 px; high-contrast theme applies; the page makes no request outside localhost.

**Dashboard edits (Person 4's folder):** Richard confirmed Person 4 agreed to three small edits. `dashboard/server.py` mounts `howitworks/` at `/how-it-works/`; the header's "How it works" pop-open in `dashboard/static/components/app-shell.js` gains a "See the full walkthrough" link (the pop-open and its three steps are unchanged); `dashboard/static/styles/base.css` opts into cross-page view transitions and names the brand so it stays in place. Tested: full `pytest` 406 passed, 1 skipped; `python -m app --fake vision` started and served `/`, `/api/state` and `/how-it-works/`; in Chromium the link opens the page, the back link returns and the dashboard panels mount again. The transition's CSS is applied on both pages; the animation itself was not visually recorded.

**Pipeline redesign and buttons (Richard's request):** The pipeline is now a graph view: modules are dots in a web that drift gently, light their neighbours on hover or focus, and spring back when dragged. A "Show as flow" button morphs the same nodes into a boxed left-to-right layout and back; the choice is remembered in the browser. Buttons on the How It Works page lose their dark outline (soft shadow instead), grow on hover and bounce back after a press, with a short vibration on phones that support it. The high-contrast theme keeps its visible control edges. Dashboard buttons in `dashboard/static/styles/` were not changed. Tested: `pytest` 406 passed, 1 skipped; in Chromium: drift, hover highlighting, click-to-jump, drag and spring back, web/flow toggle and its saved choice, button hover scale.

**Not done yet:** The 3D parts are simple stand-in shapes until generated models are added (`howitworks/assets/models/` plus `manifest.json`).

**Teammates need to know:** Nothing to reinstall. Port 8010 was in use on the build machine, so checks ran on 8765.

### 2026-11-14 20:40, Person 2 (dashboard, cross-folder authorization), Codex
**Changed:** With the user's explicit dashboard ownership override, changed the mic toggle to keep listening across questions, auto-submit final transcripts to the existing question API, and pause for pending answers and reported speaker activity. Merged current touch and question/response into one panel with a History disclosure. Removed the separate find panel, tightened the camera/activity column, simplified the header, and added a local Empyrean SVG logo. Kept the existing Grok question route and message contracts.
**Tested:** Node UI unit suite (71 passed), dashboard/UI pytest subset (76 passed), Ruff clean. Standalone dashboard preview on port 8012 rendered; DOM measurement found 16 px between camera and activity. Full pytest: 362 passed, 1 skipped, 1 detector-switch timing test failed; that test passed alone. Full suite excluding that known race: 362 passed, 1 skipped, 1 deselected.
**Decisions:** Left SPEC.md unchanged because shared-file edits require all four to agree. Its section 4.9 still describes one-utterance/manual Ask and needs a team update. The old app on port 8000 serves another checkout; this branch's preview is on 8012.
**Teammates need to know:** Pull this branch to the demo checkout and restart/refresh its app before checking the new UI. Browser speech recognition still requires a supporting browser and permission; Chrome is the reliable option observed earlier. Review the shared spec wording together.

### 2026-11-14, Person 2 (pointing review P1 fix), Codex
**Changed:** Required fingertip contact for the visible-object movement transition to held, matching the lost-object guard. A remote point can keep an object touching after camera-relative movement but cannot mark it held and transfer its name to an unrelated new detection at the hand. Updated SPEC.md section 4.6 to describe both contact requirements. Includes the P2 hand-landmarks documentation correction from `7c137a1`.
**Tested:** The new movement/name-transfer regression failed before the fix; it and the companion grasp-to-held check pass after it. Full `pytest`: 392 passed, 2 skipped. `ruff check .` and `git diff --check` passed. `python -m app --fake vision` started all modules and scene processed FrameResult 5; the dashboard port was already occupied, and Grok was disabled without credentials. Real camera and live services remain untested.
**Decisions:** User requested both fixes, a replacement PR, merge after validation, and closure of PR #31. No new imaging hardware or dependencies.
**Teammates need to know:** This replaces PR #31; the shared spec now reflects the corrected held condition and actual message layout.

### 2026-11-14 20:35, Person 2 (PR #31 message-spec correction), Codex
**Changed:** At the user's explicit request to fix review finding P2, moved `landmarks` from `FrameResult.objects` to `FrameResult.hands` in SPEC.md section 5. This corrects the documented location to match `Hand` and vision's output; it adds no field or runtime behavior.
**Tested:** `pytest -q -p no:cacheprovider`: 390 passed, 2 skipped. Checked both documented entry rows against the dataclass fields; `landmarks` appears only on hands. `git diff --check` passed.
**Decisions:** The user authorized this specific shared-file correction. P1's held-state behavior is a software issue and remains open.
**Teammates need to know:** The PR's message table now documents landmarks on hands, as implemented.

### 2026-11-14, Pointing trigger (scene, vision, contracts, config, fakes; branch `pointing-trigger`), Claude Code
**Changed:** An object's name is now spoken when the wearer points at it with one or more fingers, instead of when a fingertip lands on it. `vision/` publishes all 21 MediaPipe landmarks on the new `Hand.landmarks`. The new `scene/pointing.py` treats index, middle, ring or pinky as extended when wrist-to-tip is more than 1.1 × wrist-to-PIP, then casts a ray from the tip along knuckle→tip; the first shrunk box it hits is "pointed at". The thumb is ignored. In `scene/touch.py`, a hand with landmarks can start a touch only by pointing (a grip with curled fingers does not announce). Once touching or held, pointing or fingertip contact keeps it, so picking an object up after pointing still works. Hands without landmarks keep the old fingertip test. `TouchEvent`, `touching` and audio, storage and the dashboard are unchanged; "touch" now means "pointed at". The scripted fake hand now stands outside the bottle and points at it. Plan: `docs/superpowers/plans/2026-11-14-point-to-name.md`.
**Review fixes:** A fresh reviewer read the whole branch. Fixed four issues, each with a test that failed first. (1) Pointing at a `lost` object from a distance no longer turns it `held`; that needs a fingertip on its last box, otherwise the next object picked up could inherit its name. (2) A finger under 15 px from knuckle to tip (pointing toward the camera) casts no ray. (3) `Hand.landmarks` is no longer clamped to the frame, so a hand entering from the bottom edge keeps its true knuckle direction; `thumb_tip`, `index_tip` and `box` are still clamped. (4) Fingertips that keep a contact are matched only among objects already in contact, so an open neighbour can no longer take them and cause a repeat announcement.
**Tested:** `pytest`: 390 passed, 1 skipped (26 new tests in `tests/test_pointing.py`, `tests/test_touch.py`, `tests/test_contracts.py` and `tests/test_vision_p1.py`). `ruff check .` clean. `python -m app --fake vision namer audio storage hazard` spoke "Heinz ketchup" once per scripted cycle, right after the pointing hand appeared, with alarms still preempting. The real camera and MediaPipe pointing were not tested.
**Decisions:** Thumb excluded, because it sticks out in most poses. Ray direction is MCP→tip, which is steadier than PIP→tip. First box along the ray wins. Event and state names kept to avoid touching four modules and the database. Enter and exit timing unchanged (0.4 s and 0.6 s).
**Teammates need to know:** The user overrode folder ownership for this change, so `contracts/`, `config/`, `SPEC.md`, `vision/` and `scene/` all changed here. Please review before it merges. Pull and restart once it lands. Person 4: the dashboard still says "touching", and drawing finger rays on the video would help tune pointing. On the real camera, `POINT_EXTENDED_RATIO` may need tuning, and sweeping a finger across the table may announce more than wanted. Reaching for an object with an open hand usually points at it for over 0.4 s, so a grab often still announces; only a hand that is already gripping stays silent. Rays have no maximum length, so a relaxed open hand can announce objects across the table.

### 2026-11-14, Person 4 (audio: SIGTERM shutdown fix, dashboard FPS check), Claude Code
**Changed:** `audio/backends.py`: `PygameAlarm` sets `SDL_NO_SIGNAL_HANDLERS=1` (via `setdefault`) before importing pygame. Cause: `pygame.mixer.init()` starts SDL, which installs its own SIGTERM handler when none is set and swallows the signal. With real audio, `python -m app` ignored `kill`/SIGTERM and kept processing frames for 20+ s. Ctrl+C was never affected, because Python already owns SIGINT. Added `tests/test_audio_shutdown.py`. Removed the stale Person 4 "not built yet" line from Needs attention.

**Tested:** Reproduced on macOS with `python -m app --fake vision`: SIGTERM still running after 20 s; with `--fake vision audio` it exited in 0.02 s, which isolated the cause to the real alarm. After the fix, SIGTERM exits in 0.02 s, Ctrl+C exits cleanly in 1.0 s, and the alarm WAV still loads (0.61 s). The new test fails without the fix and passes with it. `pytest -q`: 361 passed, 5 skipped. Ruff clean. The FPS readout in `/api/state` showed a steady 5.0 fps on fake vision.

**Decisions:** Only SDL's handler is disabled. SIGTERM now has Python's default action, an immediate exit, as with fake audio. It does not run `RunningApp.stop()`. A graceful SIGTERM path would belong in `app/` (Person 1) if wanted.

**Teammates need to know:** The processed-FPS readout and the last-touched search were already built in the dashboard redesign (Richard Lan): `dashboard/services/health.py` and `LastSeenService`.

### 2026-11-14, Merge latest main (d861971, 39d9e0c) into `integration/main-voice-pip` for PR #27, Claude Code
**Changed:** Resolved the conflicts between main's independent Grok scene questions and #27's layered dashboard. The user chose: main's behaviour, #27's code. Only "Where/When did I last touch/see X?" goes to storage, as before (a correlated `LastSeenQuery`). Every other question, including "Where are my keys?" and "Find my phone", is published as `SceneQuestion`; namer answers it and speaks the answer, and `QuestionService` shows it (`answered_by: "namer"`) without speaking it again. Only one scene question is outstanding at a time, so namer's next `SpeakRequest` belongs to it; a second one meanwhile gets namer's own "Please wait…" sentence. If namer is not running, or does not answer within `LAST_SEEN_TIMEOUT_SECONDS`, the question is unavailable, and a late namer answer is not attributed to the next question. The dashboard now subscribes to `SpeakRequest`. Audio announces touches by default again (main). Kept #27's `SpeechStatus`/`ModuleStatus`/`ModeChange`/`DetectorStatus` and added main's `SceneQuestion` in `contracts/`. `SPEC.md` 4.9 now has #27's panel paragraph with a new routing table, followed by main's 4.9.1. Removed the local scene/touch phrase answers (`scene_answer`, help sentence).
**Tested:** `pytest`: 364 passed, 1 skipped. All 147 JS unit tests passed. `ruff check .` is clean. Ran `python -m app --fake vision namer storage audio`: "Where are my keys?" returned 202 `looking_up`, then `answered` by namer with the fake answer, which was spoken. "Where did I last touch the bottle?" went to history. No tracebacks.
**Decisions:** The scene-answer timeout reuses `LAST_SEEN_TIMEOUT_SECONDS` (8 s, longer than `QUESTION_TIMEOUT_SECONDS`), so no new threshold was added.
**Teammates need to know:** Edits to `SPEC.md` and `contracts/` were needed to resolve the merge; the user approved them, and all four teammates should look them over. Person 4: `dashboard/services/questions.py` and `bus_adapter.py` changed. Person 3: namer is unchanged, but the dashboard now relies on namer sending exactly one `SpeakRequest` (source `namer`) per `SceneQuestion`.

### 2026-11-14, PR #27 review fixes (branch `integration/main-voice-pip`), Claude Code
**Changed:** Fixed three things from the PR #27 review. (1) `vision/vision.py` `_apply_mode`: a cached YOLOE fallback is no longer reused once `demo-yolo11s.pt` is installed, so choosing Regular and then Demo again loads the trained checkpoint without a restart. (2) `tests/ui/agent1/test_agent1_foundation.py` passes each `*.test.mjs` file to `node --test` instead of the directory, which fails with MODULE_NOT_FOUND on Windows with Node 24. (3) `tests/test_dashboard_e2e.py`: the app fixture now stops `start()` from loading `.env`. Before this, `.env` put back the `TIGER_DATABASE_URL` and `GROK_API_KEY` the fixture had deleted, so e2e tests used the real database (`test_unavailable_history...` got `found`). That test now also listens for the spoken answer on the bus, because repeated fake hazard alarms could replace it in the dashboard's single latest-speech slot.
**Tested:** New regression test `test_a_cached_fallback_is_not_reused_once_trained_weights_are_installed` failed before the fix and passes after it. `pytest`: 360 passed, 1 skipped. `ruff check .` clean. `python -m app --fake vision` started every module and published frames with no tracebacks. Windows was not tested.
**Teammates need to know:** `vision/` belongs to Person 1. This fix was made on the integration PR at the user's request, so Person 1 should look over the `_apply_mode` change.

### 2026-11-14, Remove fake-input labels from the dashboard (branch `integration/remove-fake-labels`), Claude Code
**Changed:** At the user's request the page no longer labels fake inputs. Removed: the "Fake inputs" chip, "(fake)" after module statuses, "N running as fakes", "Live (recorded clip, not a camera)" and its alt text, "Demo audio — no sound.", the "Demo label only (fake vision)" badge, "Test clip: no detector is running" and Pip's "recorded test clip" line. Kept: the API still reports `mode: "fake"` and `fake: true`; the collapsed System details still names the real source; a fake Demo run is never called the demo-trained model (it reads "Demo object detection." / "I'm using a demo detector.").
**Tested:** `pytest` 359 passed, 1 skipped; `node --test tests/ui/` 147 passed; `ruff` clean. Five tests that required the labels now check their absence instead. On the running app with `--fake vision namer storage audio`, no visible text outside closed details mentions fake, recorded clip, test clip or no sound.
**Teammates need to know:** With fakes running, the page now looks like a real run. Open System details, or read the terminal's "(fake)" start lines, to tell them apart.

### 2026-11-14, Integration of main with the Pip/toggle dashboard (branch `integration/main-voice-pip`), Claude Code
**Changed:** The user explicitly overrode folder ownership and teammate approval for this task. Merged main `a39a8d7` into `feature/pip-companion` `fce139d`, resolving 17 conflicts without dropping either side. Contracts: one `ModeChange` (main's fields plus optional `request_id`); vision's `DetectorStatus` replaces main's `ModeChange` echo as the only switch confirmation. App: the crop recorder subscribes before any module (main's order); the lifecycle `ModuleStatus` and generic deferred fake start (branch) stay; fakes take `start=` (main's `autostart=` for the fake hazard is gone; the namer's own `autostart` is unchanged). Audio: `announce_touches` (off by default, question-only) together with `SpeechStatus`/`ModuleStatus` telemetry. Vision: the branch's lazy, validated demo loader replaces main's eager one (trained checkpoint first, eight-class check, COCO vehicles kept, YOLOE fallback); every other main line was already on the branch. Dashboard: main's question router is now `dashboard/questions.py` (wording) plus `dashboard/services/questions.py` behind `POST`/`GET /api/question`; history goes through the correlated `LastSeenService`; main's inline page, duplicate `/api/mode`, `on_mode` and `on_answer` are replaced by the layered page, `DetectorModeService` and question records. New frontend feature `dashboard/static/features/questions/` (built by a subagent in isolation, then wired into the shell here): typed question, examples, Ask, one-utterance browser speech recognition that never listens on its own and never auto-submits. SPEC 1, 3.1, 4.8, 4.9, 10, the API doc, README, CLAUDE.md and `vision/DEMO.md` now describe question-only speech and the layered dashboard.
**Tested:** `pytest` 359 passed, 1 skipped (live Tiger Data). `node --test tests/ui/` 147 passed. `ruff check .` clean. New tests cover merged contracts, `announce_touches` with telemetry and hazard priority, crop recorder start order, question routing through API/service/bus, stale scenes, storage not running, storage timeout, concurrent questions, delayed and out-of-order history results, and the microphone lifecycle (fake SpeechRecognition). Assembled check (`tests/ui/questions-integration/assembled-check.mjs`) on the real modules against `python -m app --fake vision namer storage audio [hazard]` on a spare port: 14/14 without the hazard fake (including a server restart: page reconnects and answers again), 13/13 with it. Covered: scene question, touch then "What am I touching?", history looking up then storage's answer, Regular to Demo to Regular (fake vision), simulated warning, a second page, 320 px, 200% zoom, high contrast and forced colours, and Pip beside the panel without overlap.
**Not tested (simulated only):** real camera, real microphone transcription, audible speaker, real Grok, real Tiger Data, a real trained Demo checkpoint, screen readers, Safari and Firefox.
**Decisions:** Three questions asked within a second replace each other in audio's one-item slot, and the fake vehicle hazard cuts answers off; that is SPEC 4.8, so the page says "Sent to the speaker", never "Spoken". During an urgent hazard Pip is hidden (branch design) and the sticky warning scrolls over the page; the check asserts the warning is on top.
**Teammates need to know:** Not merged to main yet; main `470b867` (Person 4's training results) is merged into this branch too. For the UI agent: the empty touch card still says "Touch an object to hear its name" (now question-only), and the Recent activity "Warning" tab wraps at 320 px.

### 2026-11-14, Pip camera companion (dashboard), Claude Code with Codex
**Changed:** Branch `feature/pip-companion` from `85e099d` (`feature/demo-model-toggle`), worktree `../empyrean-pip`. Pip now perches on the camera frame's top edge, beside the camera state, in space the row reserves (never over the picture, labels or controls). Pip is a help button ("Help with the camera.") that opens a bubble: which detector is running, from vision's confirmed status, said honestly for trained, fallback and fake ("recorded test clip, so no detector is running"); a recovery line when something is wrong; "Keep the object and your hand in view."; and a pointer to the Regular | Demo control (Pip cannot switch models). Poses follow confirmed state: reclining, attentive while touching, waiting while vision reports a switch, concerned for camera trouble or a failed switch. Hidden during an active real hazard. New `pip-companion.js`, `selectPip`, CSS, `tools/prepare_pip_poses.py`, four assets, `docs/dashboard-redesign/pip/README.md` with screenshots.
**Codex:** generated the four new poses (`codex exec` with its built-in image tool, the user's signed-in ChatGPT account, the Pip sheet as reference; no API key), recording its exact prompts, which are copied into the Pip README. Codex then reviewed the motion read-only and ranked seven changes; all were adopted, one softened (a −3° tilt kept, as the brief asks for one). Claude Code wrote all application code.
**Tested:** `pytest -q` 331 passed, 1 skipped (live Tiger Data); one earlier full run had a single failure that did not recur in three re-runs and was not identified. `ruff` clean. node 42/21/16/12/18. Live `tests/ui/toggle/pip-check.mjs` 68/68 on four servers (fake vision ok and missing checkpoint, fake hazards, the labelled camera-gap harness); `toggle-check.mjs` 30/30 on this branch.
**Decisions:** the help bubble opens in the page flow under Pip rather than floating, so it can never cover the video. Entrances play once per confirmed pose change, never on load, resize or after a hazard clears.
**Teammates need to know:** not checked with a screen reader, Firefox, Safari, the real camera, or a real hazard that clears (the fake repeats every 3 s). Generated originals are in the git-ignored `scratch/pip-art/`; their SHA-256 values are in the Pip README.

### 2026-11-14, Regular/Demo detector toggle (vision, dashboard, contracts, config), Claude Code
**Changed:** Branch `feature/demo-model-toggle` from `5a94f40` (`design/friendly-clarity`), worktree `../empyrean-toggle`. The user authorized cross-folder and shared-file changes for this task; nothing merged to `main`.
- **Reconciled from `origin/main`** (detector work only): `vision/` (trained `demo-yolo11s.pt` path with COCO vehicles and known demo classes, NMS dedupe that keeps vehicles, IDs scoped per detector and class, YOLOE fallback, DirectShow on Windows, training tools), `scripts/`, pinned `requirements*.txt`, `training_data/`, `demotraining.md`, `--record-crops`, vision and training tests. Follows Person 2's demo-training entry: prefer the trained checkpoint, keep the vehicle path, never install a two-class head, treat the release as experimental.
- **Not ported from `main`:** microphone questions (`dashboard/questions.py`, `POST /api/question`) and question-only speech. This branch still speaks on touch. Merging needs a decision on which speech behaviour wins.
- **Contracts and config (`SPEC.md` 5 and 9):** `ModeChange` gains optional `request_id`; new `DetectorStatus` (vision's confirmed state: active, switching or failed, with detector identity, checkpoint, demo kind, fake flag). New `DEMO_DET_MIN_CONFIDENCE` 0.25 (from main) and `MODE_SWITCH_TIMEOUT_SECONDS` 30.
- **Vision:** Demo is loaded and validated on a background thread while Regular keeps running; the frame loop only swaps a ready detector. Validation: file settled for 10 s and unchanged while hashed, SHA-256 and classes against `vision/models/training-status.json` (the release manifest) or `scratch/demo-training/install.json`, detection task, exactly the eight demo classes, one warm-up frame. A newer file is noticed by size and mtime the next time Demo is chosen. Failure keeps Regular and says why. Nothing is trained or downloaded.
- **Dashboard:** `DetectorModeService` (one request at a time, 409 while switching, 30 s timeout note, late answers still win), `POST`/`GET /api/mode`, `detector` in the page state, `mode_switch` capability. Page: **Regular | Demo** control under the camera heading with "General-purpose object detection." / "Custom model trained for our demo objects.", switching and failure stated in words, buttons locked (still focusable) while a request is open, **Demo-trained model** badge only for the trained checkpoint (fallback and fake vision get their own dashed labels), checkpoint status shown ("experimental; NOT demo-ready"), detector identity and checkpoint in System details. The status line's fake tag now reads **Fake inputs** instead of "Demo mode", so it cannot be confused with the Demo detector.
- **Fake vision:** simulates the switch (`FAKE_DEMO_DETECTOR=ok|missing|invalid`, `FAKE_DETECTOR_SWITCH_SECONDS`) and always reports itself as fake.
- **Docs:** `vision/DEMO.md` explains the modes, the checks, and how to install or replace a checkpoint (download, verify, copy to a temporary name, rename, wait 10 s, choose Regular then Demo).

**Tested:** `pytest -q` 330 passed, 1 skipped (live Tiger Data); `ruff check .` clean; node agent1 42, agent2 21, agent3 16, agent4 12, toggle 11. New `tests/test_demo_toggle_dashboard.py` (service, API, and the real app with fake vision for success and missing checkpoint) and `tests/test_demo_toggle_vision.py` (background load, superseded and failed loads, settling file, manifest mismatch, wrong classes, invalid and incompatible checkpoints). Live browser `tests/ui/toggle/toggle-check.mjs` 30/30 on two fake-vision servers: Regular to Demo to Regular, rapid triple click sends one request, second client sees the switch and gets 409, keyboard, refresh, missing-checkpoint failure, 360 and 768 px, high contrast, reduced motion. `python -m app --fake vision` started all seven modules.

**Not tested:** no weights on this Mac (`yolo11s.pt`, `hand_landmarker.task`, `demo-yolo11s.pt` absent), so neither real detector, the real switch latency, nor detection accuracy was run. The trained-checkpoint path is covered by unit tests with stand-in models only. No camera, speaker, Grok or Tiger Data.

**Teammates need to know:** Person 1: please review `vision/vision.py` (`load_demo_candidate`, `Vision._apply_mode`) and run the switch on the real camera with the release checkpoint. Everyone: `DetectorStatus` and `ModeChange.request_id` are shared-contract changes made under the user's authorization for this task; confirm before merging. "Demo audio — no sound." in the speech panel still means fake audio, not the Demo detector.

### 2026-11-14 17:30, Dashboard friendly clarity (design/friendly-clarity), Claude Code
**Changed:** Branch `design/friendly-clarity` from `539f0de` (`design/bauhaus-polish`, the build serving :8002). Status is one line with a Demo mode tag and a "System details" disclosure; an inactive warning is one line; touch and speech sit beside the camera so both are on the first screen; the object name leads with its thumbnail and state; speech uses plain Queued/Speaking/Completed/Interrupted/Failed and leads with "Demo audio — no sound." (or the log-only sentence) when no sound can play; camera alt text follows the real state; advanced camera controls are in "View options"; quiet secondary controls; no page-wide border cage; softened tokens with pastel accents; Pip mascot assets cut from the supplied sheet (`tools/extract_pip.py`) in four decorative placements, hidden during an active real hazard. Removed the Rive speech ring with its runtime and asset. Engine, APIs and contracts unchanged.
**Tested:** full `pytest` 288 passed, 1 skipped; `ruff` clean; node 42/21/16/12; `tests/ui/friendly/friendly-check.mjs` 48/48 on four live servers (fakes and the labelled `tests/ui/friendly/demo_harness.py`); integrated live checks normal 49/49, hazard 8/8, unavailable 4/4, disconnect 6/6. No camera, speaker, Grok or Tiger Data.
**Decisions:** layout A (touch beside camera) over B (full-width band), which left the camera mostly below the fold. Log-only audio says "No sound — the speech engine is unavailable…" rather than "Demo audio", because a real deployment can be in that state.
**Teammates need to know:** `tests/ui/friendly/demo_harness.py` is test input only; never treat its speech or camera gaps as evidence.

### 2026-11-14 16:30, Dashboard Bauhaus redesign (design/bauhaus-polish), Claude Code
**Changed:** Branch `design/bauhaus-polish` from integration commit `81bef40` (verified complete first). New Bauhaus token set (ivory, near-black, blue action, red only for hazards and errors, yellow fills with black outline, dashed violet simulation, square corners); instrument-panel composition with a full-width touch band; a Rive speech signal (`components/speech-signal.js`, recoloured MIT `progress.riv`, vendored `@rive-app/canvas@2.47.1`) that moves only for real speaking telemetry; hand-authored SVG artwork in three slots; three interactions adapted from MIT 21st.dev components in plain CSS. Engine, APIs and contracts unchanged.
**Tested:** full `pytest`, `ruff`, node tests (agent1–4 and bauhaus), the integrated live checks (normal 49/49, hazard 8/8, unavailable 4/4, disconnect 6/6) and `tests/ui/bauhaus/bauhaus-check.mjs` 25/25 (Rive behaviour and fallbacks, local-only requests, interactions, AA contrast of all visible text in both themes, frame time p95 16.7 ms). No camera, speaker, Grok or Tiger Data.
**Decisions:** direction B (instrument panel) with A's typographic touch band, chosen over A and C (`docs/dashboard-redesign/bauhaus/README.md`). The speech signal never animates for fake or log-only audio.
**Teammates need to know:** ChatGPT image generation was not available; exact prompts and slots are in the Bauhaus README. `tools/riv_recolor.py` is design tooling only.

### 2026-11-14 15:30, Dashboard redesign integration fixes (Agent 4), Claude Code
**Changed:** On `design/light-dashboard-integration`: connection changes are announced only by the shell (operations and camera duplicates removed); the operations feature now drives `roots.warning.dataset.emphasis` (`urgent`, `simulated`, none; cleared on cleanup); both feature stylesheets use the shell's token names and `data-theme="high-contrast"` (before this they silently used light fallbacks); last-touch search normalises request ids, has one overall 10 s deadline that aborts hanging requests, ignores late answers, and shows recorded neighbours; the API client's timeout now covers reading the body; storage says "Touch history is unavailable right now." on an outage ("I have not seen that." only for a real miss) and `LastSeenResult.answer` is the spoken sentence; `app/` starts fake hazard and vision publishers after every module subscribed, so the first scripted hazard reaches audio; the fake scene uses current timestamps. SPEC 4.10 and 5 updated for the spoken outage sentence.
**Tested:** full `pytest` and `ruff` (counts in `docs/dashboard-redesign/agent-4-handoff.md`); `node --test` for all four agents; live Chromium checks of the real shell and features: normal 49/49, hazard 8/8, unavailable 4/4, disconnect/reconnect 6/6. Each new regression test was also run against the old code to confirm it fails there. No camera, speaker, Grok or Tiger Data.
**Decisions:** a camera "stale" state caused by a lost dashboard connection is not announced by the camera (the shell already says it). The user's request replaced the earlier decision to keep the old spoken outage sentence.
**Teammates need to know:** `register(bus, start=False)` is now supported by `fakes/hazard` and `fakes/vision`; plain `register(bus)` still starts at once. The 50-item audit is in `docs/dashboard-redesign/verification.md` (partial: #13 and #29, fullscreen fallback).

### 2026-11-14 14:00, Dashboard light redesign (four parallel agents, consolidated by Agent 4), Claude Code
**Changed:** The single-file dashboard is now a layered application connected to the engine, on branch `design/light-dashboard-integration` (not merged to `main`). Four Claude Code (Claude Opus 5.5) agents worked in separate worktrees from `a5ea3af`; Agent 4 merged them in order and owns the Python, contract and integration changes.
- **Agent 1, `design/light-foundation` @ `399db32`:** minimal `dashboard/index.html`; `dashboard/static/app.js`, `components/app-shell.js` (eight feature mounts), `core/` (store, normalize, socket-client as the only `/ws` owner, api-client as the only `fetch` owner, keyed announcer, preferences, theme-boot, clock, feature-loader) and `styles/` (light tokens, base, layout, components). Light is the default with an optional high-contrast light mode. Docs: `docs/dashboard-redesign/design-system.md`.
- **Agent 2, `design/touch-camera` @ `fb2e1ca`:** `dashboard/static/features/experience/`: current-touch hero with real speech status, camera with honest freshness states and per-view overlay toggles, keyed object list with naming states and thumbnails, and last-touch search with race-safe polling.
- **Agent 3, `design/alerts-history` @ `a43b64d`:** `dashboard/static/features/operations/`: status strip (connection separate from module health), warning panel (real before simulated), activity history (browser-only pause and clear, grouped repeats) and demo tools.
- **Agent 4, integration:** `dashboard/api/` (routes, `/ws` hub, schemas), `dashboard/services/` (health, last-seen correlation, heartbeat), `dashboard/bus_adapter.py`, extended read model in `dashboard/state.py`, per-viewer overlays in `video.py`, bounded `thumbnails.py`, `/static` mount. Audio publishes `SpeechStatus` and `ModuleStatus`; storage publishes `LastSeenResult` for queries with a `request_id` and reports availability; `app/` publishes module lifecycle and registers the dashboard first. Cross-component fixes after merging: fake modules and the recorded clip are labelled as fakes in the status strip and camera panel.
**Tested:** full `pytest` 277 passed, 1 skipped (Tiger Data live test, no `TIGER_DATABASE_URL`); `ruff check .` clean; `node --test` agent1 42, agent2 21, agent3 16, agent4 2, all passing. `tests/test_dashboard_e2e.py` runs the real `app.start` with fake camera, namer, store, audio and hazard and checks events over the real WebSocket and a correlated last-touch search. `tests/ui/agent4/integrated-check.mjs` drove the live app in Chromium: normal (26/26), hazard (5/5), unavailable (4/4), disconnect and reconnect (3/3). Screenshots are in `docs/dashboard-redesign/screenshots/`. No physical camera, audible speaker, Grok call or Tiger Data database was used.
**Decisions:** contract changes are additive only (see the contract changes table). `current_touch` is null when nothing is in a hand; the released object is in `last_touch`. The spoken last-seen answer is unchanged, including "I have not seen that." when the database is down; the page shows `unavailable` in that case. Missing evidence is `unknown`, never healthy. The CLI test now waits for the first frame instead of sleeping 1.4 s.
**Teammates need to know:** run `python -m app --fake vision namer storage audio` for an offline demo. The API is in `docs/dashboard-redesign/api.md`; per-agent detail is in the four handoff files; the 50-item coverage is in `verification.md`. Restarting the app right after closing it no longer leaves the dashboard unserved (the port probe now ignores TIME_WAIT on macOS and Linux).


### 2026-11-14, Person 4 (candidate-v1 training and evaluation), Claude Code
**Changed:** Trained Person 4's first eight-class candidate, following `demotraining.md`, on a fresh macOS Python 3.11 `.venv` (Apple M5, MPS). Dataset `scratch/p4-dataset-v1` from `vision.extend_demo_dataset`: frozen bootstrap plus `training_data/person4/train` → 153 train images (71 + 82), and bootstrap val plus `training_data/person4/eval` → 32 val images (10 + 22). Run: `python -m vision.train_demo_detector --data scratch/p4-dataset-v1/data.yaml --weights vision/models/yolo11s.pt --project scratch/p4-runs --name candidate-v1 --epochs 45 --device mps` (script defaults otherwise: imgsz 416, batch 4, freeze 10, lr 0.001, mosaic 0.5, patience 12). All 45 epochs ran; best epoch 38. **Elapsed: 216 s wall-clock** (3 min 36 s, `/usr/bin/time`). Added `training_data/person4/results/candidate-v1.json`. Weights are not committed: `best.pt` SHA-256 `76cc6a98f28d63860855699928c1d30be7b9abe064dc8b8b98c6e0ff174863a7`, stays in `scratch/p4-runs/candidate-v1/weights/`; ask Person 4 for the file.

**Tested:** `python -m vision.evaluate_demo_detector --weights scratch/p4-runs/candidate-v1/weights/best.pt --refs training_data/person4/eval --output training_data/person4/results/candidate-v1.json --device mps` (confidence 0.25, IoU ≥ 0.5, agnostic NMS):
- **headphones 12/12.** Confidence 0.53 to 0.82, IoU ≥ 0.53. One extra box: `headphones_12.jpg` got a second, overlapping headphones box (0.31). This is the only false-positive box.
- **toothbrush 9/10.** Miss: `toothbrush_7.jpg`, the electric toothbrush held horizontally with the head pointing left, pale blue on a white table. No box at all, not a wrong class. Weakest hit: `toothbrush_2` at 0.31. `toothbrush_5` passed at IoU 0.52, on one of the eval boxes already noted as loose because it includes the hand.
- No wrong-class detections on any of the 22 eval photos.
- Median inference 6.4 ms per image on MPS, at the 416 internal size. This is model time only, not camera-loop latency.

Ultralytics validation of `best.pt` on all 32 val images: mAP50 0.885, mAP50-95 0.492. Per class (mAP50): headphones 0.859 over 14 instances, toothbrush 0.752 over 11 (recall 0.545, the weakest of my two classes), water bottle, toothpaste, phone, keys and watch 0.995 each, charger 0.495. The other six classes have only 1 or 2 bootstrap val instances each, so those figures say only that the head kept all eight classes. They are not evidence of accuracy. Charger stays weak, as in the team note.

`pytest -q` in the same venv: 207 passed, 1 skipped (existing httpx warning).

**Caveats:** Following the guide's commands, `person4/eval` is also the validation split that picked `best.pt` (epoch 38). So the 21/22 is optimistic and not a fully independent holdout. No live-app sign-off yet: the stable box, name, touch/hold/release/retouch and spoken-answer checks are still to do. Not tested on the glasses camera. MPS training printed non-deterministic-op warnings, so a rerun may differ slightly.

**Teammates need to know:** On the python.org macOS build, `scripts/setup_models.py` fails to fetch `hand_landmarker.task` with `CERTIFICATE_VERIFY_FAILED`. Rerun it once with `SSL_CERT_FILE` pointed at certifi's bundle, or run that Python's `Install Certificates.command`. No source, config, contract or dependency changes. Person 1: the toothbrush needs more horizontal, held, low-contrast views before the final merge.

### 2026-11-14, Person 4 (headphones and toothbrush captures), Claude Code
**Changed:** Captured Person 4's training and evaluation data with `vision.capture_demo_refs` on the user's own laptop webcam (index 0, 1280 x 720, Windows). `training_data/person4/train/`: 46 headphones (34 held, 12 on a table) and 36 toothbrush (24 held, 12 on a table, 6 of those standing upright). `training_data/person4/eval/`: 12 headphones and 10 toothbrush, taken at a different table and background from training. One item per photo throughout. The toothbrush is an electric toothbrush; note it if the demo uses a manual one. Three sets were rejected and moved to the git-ignored `scratch/` instead: the first training session (a second headset worn around the neck, unboxed, in all 55 photos), 7 toothbrush photos with the headphones unboxed in the background, and a first eval attempt where 10 toothbrush photos were saved under the headphones label. The remaining toothbrush training files were renumbered 1 to 36 so the capture tool cannot overwrite them; `refs.json` matches the files on disk.

**Tested:** Every box in both sessions drawn onto its photo and checked by eye. Some held toothbrush boxes are loose because they include the hand (train 3 to 6, 11, 12; eval 2, 3, 5). No training run or evaluation yet, so there are no accuracy results. Setup: fresh Python 3.11 `.venv` with `scripts/install_dependencies.py` succeeded; `pytest -q` in it: 207 passed, 1 skipped (existing httpx warning).

**Decisions:** Rejected any photo showing an unboxed demo item, following `demotraining.md`: the tool writes one box per photo and `extend_demo_dataset` rejects a second box for the same file.

**Teammates need to know:** Person 4 data is ready to extend the bootstrap with. Next for Person 4: `extend_demo_dataset`, a candidate training run, then `evaluate_demo_detector` on `training_data/person4/eval`. `capture_info.json` is rewritten each session, so the train copy records only the last of its four sessions (same camera for all).

### 2026-11-14, Person 4 (second clip: teammate's table video), Claude Code
**Changed:** Notes only. Ran the same stage-by-stage trace on the table video a teammate sent (`IMG_3646.mov`: 8.6 s, 3840 x 2160, 24 fps, sampled to 42 frames at 5 fps). The clip was not committed.

**Tested:** Same frames for the old settings (conf 0.5, area 0.02) and the new ones from PR #19 (conf 0.3, area 0.002):

| | Old settings | New settings |
|---|---|---|
| Bottle reaches `FrameResult` | 0 / 42 | 0 / 42 |
| Objects kept in total | 16 | 26 |

- **The scene:** the camera looks straight down at a table and moves fast, so many frames are blurred. On the table are a dark metal tumbler (partly lying down), a phone in a case, headphones, keys, a toothpaste tube, an electric toothbrush, a charger and a carabiner.
- **The bottle is big but not recognised.** Raw YOLO labelled the tumbler "bottle" in only 10 of 42 frames, at confidence 0.05–0.38 (median 0.14). It reached 0.3 in only 2 frames, and was never tracked. Its box was 4–18% of the frame, so the area filter was never the problem here. Unlike the laptop clip, this is a recognition limit, not a filter.
- **Most objects are outside COCO's 80 classes,** so YOLO mislabels them: toothpaste as "toothbrush", the phone as "remote" or "mouse", headphones as "mouse". Headphones, keys, toothpaste, chargers and carabiners have no COCO class.
- **False detections:** one box covering most of the frame was labelled "remote" at 0.53 and passes both settings. The new settings add true detections ("cup", "cell phone") and wrong ones ("sink", "refrigerator").

**Decisions:** PR #19 still helps small, far objects (laptop clip). It does not fix this clip, because the bottleneck is what the model recognises, plus camera angle and motion blur. No threshold change is proposed from this clip.

**Teammates need to know:**

- **Demo objects:** use COCO objects that look typical, such as a plain plastic water bottle, cup or mug, phone, banana, apple, book or scissors. Avoid metal tumblers, headphones, keys and toiletries.
- **Camera:** hold it the way the glasses will be worn, looking forward and down at the table at about arm's length rather than straight down, and keep it steady. Re-check the demo objects that way.
- **Person 3:** spoken names come from Grok's crop when naming succeeds, which can correct a wrong YOLO class. A whole-frame false box gives a useless crop.
- **All:** if the demo must handle objects outside COCO, that needs a model change, which needs the team's approval (AGENTS.md rule 7).

### 2026-11-14, Person 2 (team demo-training handoff and publication), Codex
**Changed:** User explicitly authorized fine-tuning, vision integration, then publishing current work and dependencies to main for all four people. Added `demotraining.md` with two owned items per person, the complete class map, capture/label rules, separate evaluation sessions, executable training/evaluation commands and signoff requirements. Added per-person capture selection, a frozen 71-train/10-validation-image bootstrap (82 training boxes, 13 validation objects), dataset extension with hash-leakage protection, and candidate evaluation. Added tested Python 3.11 dependency pins, a two-step installer avoiding competing OpenCV wheels, and setup-only model downloads. No secrets or weight files are committed.
**Training/results:** Three CPU runs used pretrained YOLO11s: frozen-backbone adaptation, unfrozen refinement, then additional manually labelled tabletop data. Fourteen new labelled frames came from two user-directed capture sequences; the first two tabletop snapshots stayed validation-only. Selected the third run's epoch-9 checkpoint by its fresh-table result (3/5 versus old visual prompts 0/5), rather than the aggregate-best final checkpoint (2/5 fresh). Old reference score was 5/8; all eight items are not solved. Latest user live report: toothpaste fine; watch frequently labelled charger; actual charger missed. Telemetry confirms the detector can call watch charger and Grok later correct its name; this is not purely a speech bug.
**Integration:** Demo mode prefers local `demo-yolo11s.pt`, retains COCO vehicles and known demo classes, and deduplicates overlapping object boxes without suppressing vehicles. Public IDs are scoped to detector and class to close the observed bottle-to-laptop cached-name bug. DirectShow fixes the observed Windows camera-reopen hang. Shared contracts and configured thresholds were not changed in this training session. The earlier demo-mode contract additions remain recorded with their original review status.
**Tested:** After merging incoming main (22e7996), full pytest: 207 passed, 1 skipped (live database), with the existing FastAPI/httpx deprecation warning. Ruff and diff whitespace checks passed. Both exact CLI startup checks (`python -m app --fake vision` and `python -m app --fake vision audio`) started all seven modules and delivered a scene frame; external credentials were blanked for these checks. A separate clean Windows Python 3.11 environment installed the pinned requirements and completed the documented installer; OpenCV, MediaPipe, PyTorch and Ultralytics imported, and 73 targeted tests passed. Windows Application Control blocked its freshly installed Postgres DLL, so full tests use the existing working venv; no security controls were bypassed. Live camera stayed close to 5 fps but latency sometimes exceeded 150 ms; an observed 60-frame sample had median 171.4 ms/max 277.8 ms, so latency is also not certified.
**Own-webcam capture:** The user clarified that every person must image with their own webcam. The handoff now states this explicitly; `--camera-index` overrides machine-specific settings, and each capture session records its camera index, resolution, platform and UTC time. A test covers explicit index 0 overriding a local setting of 1. Nobody needs to wait for Person 2's Logitech; final combined-model validation must still include the glasses camera.
**Teammates need to know:** Model weights are distributed separately as an explicitly failed/experimental GitHub prerelease baseline, with unchanged tensors, optimizer removed, class/status metadata and SHA-256 checksums. Pulling code alone does not install them. Do not overwrite another owner's data, train on holdouts, install a two-class head globally, or merge model files as if they were source. Preserve the microphone/audio work that reached main while this session ran; current main intentionally speaks object answers only in response to questions. Camera on Person 2's laptop remains active for testing.


### 2026-11-14, Person 2 (demo item detection investigation), Codex
**Changed:** No production code, threshold, model or runtime prompt file changed. Found localhost still in actual mode and switched the existing dashboard toggle to demo; vision logs confirm the processor switched. Confirmed all eight demo classes plus vehicles are present in the 75-prompt bank. Prepared a local YOLO-format dataset under `scratch/demo-detector-review/dataset/` from the existing 62 boxed reference photos: 54 training images and 8 validation images, one withheld per class. No training started.
**Tested:** Compared the existing visual prompt bank with plain and descriptive text prompt banks on all 62 reference photos, confidence 0.25, matching expected class with box IoU at least 0.3. Existing visual results: water bottle 8/8, toothbrush 4/6, toothpaste 7/8, charger 2/5, phone 6/9, headphones 7/10, keys 0/7, watch 5/9. Text variants did worse overall and were not installed. Results are local at `scratch/demo-detector-review/results.json`. The visual prompt bank includes these photos, so these are diagnostic reference-set results, not independent accuracy estimates. Earlier leave-one-out results remain more informative about generalization.
**Decisions:** Explained to the wearer that YOLOE is pretrained and the 62 photos are visual prompts, not weight training. Actual mode lacks five requested item classes; demo mode deliberately omits ordinary COCO classes such as laptop. No evidence supports claiming the eight items are demo-ready. Training or another model change needs explicit authorization under AGENTS.md rule 7; vision integration also needs the Person 2 cross-folder override.
**Teammates need to know:** Keys and charger remain blockers despite switching modes. If fine-tuning is approved, use held-out images and fresh live tests of every object, check false positives with non-demo objects, measure CPU latency, and preserve the separate vehicle hazard path. This laptop has no CUDA GPU. Camera remains running in demo mode for the wearer.


### 2026-11-14, Person 2 (adjacent-object naming fix in Person 3's namer), Codex
**Changed:** User explicitly approved the cross-folder change and app restart in chat. `namer/grok_client.py` now directs Grok to name the object matching the target detector label, rather than another foreground or overlapping object in the same crop. If that target is obscured, return its plain detector label. No message, model, threshold, shared file, or speech behavior changed.
**Tested:** Reproduced on saved Logitech crops: `1122-1.jpg` is labelled laptop by the detector but includes a prominent foreground bottle. Current prompt returned water bottle in 2/2 calls; candidate returned laptop in 2/2. A second laptop crop and a bottle crop were each run twice with both prompts; targeted outputs were laptop and water bottle respectively. After applying the actual code, three fresh calls returned laptop, laptop, water bottle. This is a three-image check, not a general accuracy claim. Full pytest: 188 passed, 1 skipped (live database); Ruff on the edited module clean. Comparison results are local at `scratch/adjacent-object-review/results.json`.
**Decisions:** Restarted the owned camera process to load the prompt and clear old cached names. Live MJPEG feed and advancing frames verified at localhost:8000, actual mode. Camera logs are `scratch/camera-live-20261114/naming-fix-stderr.log` and `naming-fix-stdout.log`; process ID is in `app.pid`. App remains running for the user's side-by-side retest.
**Teammates need to know:** Person 3: review the target-focused prompt. Person 1: see the new class-changing-ID item under Needs attention; the original live history proves stale names can survive a tracker class change. No vision or scene code was changed in this fix. Naming queues under heavy tracking churn also remain to investigate.


### 2026-11-14, Person 2 (first live camera result), Codex
**Changed:** No application code. Recorded the wearer-confirmed result of the actual-mode localhost rehearsal.
**Tested:** User reports object detection and audible naming succeeded. Dashboard event history contains two water-bottle touches plus laptop and cell-phone touches; audio logs confirm those five phrases were sent to speech at a logged 0 ms after each event. This verifies touch-to-speech in this run, not yet a controlled same-ID release/retouch test. Previous full suite remains 188 passed, 1 skipped; no code changed afterward.
**Decisions:** Next controlled test: hold contact for five seconds (one announcement), clear fingertips for at least one second, then retouch the same stationary object (one new announcement).
**Teammates need to know:** Naming logs also show requests waiting 20-46 seconds in the queue despite Grok calls usually completing in under a second. Tracker IDs reached 1000+ during the moving camera session. Investigate ID stability and stale naming work after the controlled stationary test; these observations alone do not prove the cause. Live frame-latency warnings included 280 ms and 332 ms. Camera and app remain running for the wearer.


### 2026-11-14, Person 2 (local main update and camera rehearsal), Codex
**Changed:** Merged `origin/main` at `2c87254` into local `p2-demo-mode` at the user's request. Resolved config/spec conflicts with the approved confidence 0.3 and minimum area 0.002 while retaining the demo threshold 0.25, YOLO small documentation, and YOLOE demo mode. Kept both branches' development entries and removed the two Needs attention items fixed by PR #17. Backup branch: `codex/p2-demo-before-main-20261114`. Nothing pushed.
**Tested:** Windows, existing Python 3.11.18 venv: full pytest 188 passed, 1 skipped (live database); Ruff on app, fake hazard, app/vision tests and config clean; staged diff whitespace check clean. Started the real app with `--record-crops`, `CAMERA_INDEX=1` from the existing environment and `YOLO_AUTOINSTALL=False` for this process. All seven modules started, MJPEG video is visible at localhost:8000, and Grok calls returned HTTP 200. One capture-to-publish warning at 159 ms, above the 150 ms target.
**Decisions:** Begin the interactive camera test in actual mode, then compare demo mode. No microphone feature or new dependency installed. Startup logs and process ID are local under `scratch/camera-live-20261114/`; naming crops for this run are under `scratch/camera_crops/session-h9_j2of2/`.
**Teammates need to know:** Live video is verified; tabletop object detection, touch/release/retouch and audible output still require the wearer to position an object and perform the test. Initial view faced the ceiling and produced no scene objects. Automated passing tests do not establish live demo accuracy.


### 2026-11-14, Person 4 (voice PR preparation), Codex
**Changed:** Committed audio behavior, dashboard voice flow and validation notes separately on `p4-output`. Merged current `origin/main` so the PR preserves the team's latest camera/detection changes; resolved the DEVLOG-only conflict by retaining main's entries and the voice notes without duplicating the earlier coordination entry. PR scope relative to main is only Person 4 runtime files, corresponding tests and DEVLOG.

**Tested:** After merging main: Python 3.11 full suite 190 passed, 1 skipped, existing FastAPI/httpx warning; repository ruff clean; diff whitespace clean. Re-ran `python -m app --fake vision`: processed frames, HTTP 200, no startup errors and clean SIGINT shutdown. Earlier live Chrome recognition and Start/Stop checks are documented above. Remaining credential/browser/echo limits are included in the PR description.

**Teammates need to know:** This PR intentionally makes object speech question-only at the user's request; it does not change shared contracts, thresholds or spec. No model/environment/secret artifacts are included. No merge to main is performed by this session.


### 2026-11-14, Person 4 (Git/instructions and final-goal audit), Codex
**Changed:** Moved the current uncommitted Person 4 work from `codex/p1-startup-crop-recording` to a new local `p4-output`, preserving existing commits and worktree changes. Remote `origin/p4-output` is an ancestor of this branch; nothing rewritten, committed, pushed or merged. Formatted the edited dashboard test. Checked scope: runtime edits are only audio/dashboard/fake audio; other changes are corresponding tests and this log. Shared contracts/config/spec and other owners' runtime files are untouched. Model assets and local Python environment are ignored by Git.

**Tested:** Python 3.11 full pytest: 190 passed, 1 skipped (live database), existing FastAPI/httpx deprecation warning. Repository-wide `ruff check .`, formatting on Person 4 paths and changed tests, and `git diff --check` passed. Bounded subprocess smoke runs of `python -m app --fake vision` and `python -m app --only dashboard --fake vision scene` reached HTTP 200, published frames/scene state, had no startup errors and shut down cleanly on SIGINT. Real app restarted. Chrome UI verified microphone off after reload, Listening after Start, and off after Stop. Left the live dashboard running and microphone off.

**Decisions:** Current user instructions take precedence over legacy touch-triggered speech requirements; record that difference without editing shared spec. No claim of complete product readiness: absent credentials, open-ended visual QA and estimated playback pause remain listed under Needs attention. Existing model code uses YOLO small, unlike the original nano spec; this audit did not change the model or its owner's code. Root dependency pinning is already listed as an owner task.

**Teammates need to know:** Current local branch is `p4-output`; changes remain uncommitted for review. Live process uses `scratch/audio311/bin/python -m app`. Browser end-to-end transcription worked earlier in Chrome; this audit additionally verified actual Start/Stop UI. Tests establish silent default touch/name handling and requested-answer/alarm behavior. Do not claim brand/history/open-ended reasoning works without completing the pending integrations and live checks.



### 2026-11-14, Person 4 (demo readiness from the trace), Claude Code
**Changed:** Notes only. What the tabletop trace below means for the demo.

**Tested:** Nothing new; this reads the existing trace.

**Decisions:**

- **The clip was for verification, not calibration.** Nothing was tuned or trained on it. It tested the suggested thresholds (area 0.002, confidence 0.3) on fixed frames, so every setting saw the same input.
- **The touch demo is mostly unaffected by the far-object problem.** A touched object is at arm's length and normally fills well over 2% of the frame, so the area filter kept it even at the old 2%. The far-object fix matters for the Objects list and things across the table. It is now live: PR #19 set confidence 0.3 and area 0.002, agreed by all four.
- **The demo risk is objects YOLO does not recognise.** The large black bottle with a handle was never labelled a bottle, even up close (raw: "suitcase", 0.07). An unrecognised object cannot be touched or named, whatever the thresholds. This is a model limit; changing models needs team approval (AGENTS.md rule 7).
- **Demo objects:** use ones the COCO model knows well and check each on the real camera, for example a plain plastic water bottle, a cup or mug, a phone, a banana or apple, a book, scissors. Avoid unusual shapes, handles, and dark or reflective bottles.

**Teammates need to know:**

- **Person 2:** before the demo, rehearse with the glasses camera at arm's length with the exact demo objects. Each one should appear in the dashboard's Objects list and be named on touch. This also settles whether the glasses-camera clip is still needed. The laptop clip already answers the threshold question; only the distance and angle differ.
- **All:** the threshold proposal was agreed and merged in PR #19. Re-check for false detections on the real camera in a busy scene.

### 2026-11-14, Person 2 (shared `config/` and `SPEC.md`, agreed by all four), Claude Code
**Changed:**
- `config/thresholds.py`: `DET_MIN_CONFIDENCE` 0.5 to 0.3 and `DET_MIN_AREA_FRACTION` 0.02 to 0.002. These are the values Person 4 proposed in the tabletop detection trace entry below.
- `SPEC.md` sections 4.2 and 9 now state the same two values. No code in `vision/`, no contracts, no model.
- `tests/test_vision_p1.py` (Person 1's test): the fake detector's "low-confidence" box was hard-coded at 0.3, which is no longer below the threshold, so the test failed. It is now 0.2. The test still checks the same thing.

**Tested:** On `main` at `d973e3a` plus this change, Windows, Python 3.11.18. Full `pytest`: 184 passed, 1 skipped (live database). `python -m app --fake vision audio` started every module and published frames. Ruff on `config/` and the edited test is clean. Not run on the real camera with the new values, and not checked against a glasses-camera clip.

**Decisions:** Person 2's human confirmed that all four teammates accepted the new defaults (AGENTS.md rules 1 and 6). The change was made before Person 4's trace was run on a glasses-camera clip; Person 2 is sending that clip to Person 4.

**Teammates need to know:**
- **All:** pull `main` after this merges. Smaller and less certain objects now reach `FrameResult`, so expect more objects in the scene and possibly false detections in busy views. Say so here if you see them.
- **Person 1:** more boxes reach ByteTrack. Latency was already over the 150 ms target on two Windows laptops (156 to 252 ms), so please measure it again.
- **Person 4:** the "IN PROGRESS" item under Needs attention is yours to remove once the glasses-camera clip confirms the fix. The large black bottle that YOLO does not recognise is not helped by this.

### 2026-11-14, Person 1 (app, fake hazard, tests), Codex
**Changed:**
- Fake hazard registration can defer playback; app starts it after all selected modules subscribe. The first vehicle event is no longer lost during startup. Direct fake users retain automatic startup by default; stopping an unstarted fake is safe.
- CLI smoke test waits for a published-frame log with a bounded 15-second timeout instead of sleeping 1.4 seconds. It runs scene plus fake vision without loading audio, and cleans up the child process and output reader.
- Added `python -m app --record-crops [DIRECTORY]`. Registers Person 3's existing background crop recorder before producers and stops it at shutdown. Each run gets a fresh `session-*` directory under `scratch/camera_crops` (or the selected directory), avoiding cross-run file collisions. The path is logged at startup.
- Regression tests cover first fake-hazard delivery to a later subscriber, crop persistence across two sessions, and recorder shutdown. No audio files, shared contracts, thresholds, model choices, or other owners' modules changed.

**Tested:**
- Non-audio suite: `python -m pytest -q --ignore=tests/test_audio.py --ignore=tests/test_audio_pyttsx3.py --ignore=tests/test_speak_test.py`: 159 passed, 1 skipped (live database), one existing FastAPI/httpx deprecation warning.
- After final cleanup, Person 1 app/hazard/vision tests: 15 passed. Ruff on app, fake hazard and app tests is clean; `git diff --check` is clean.
- Tested on macOS with Python 3.14.10 in a new local `.venv`; Python 3.11 is not installed here. No real camera, Grok call, database credentials, or audio hardware used. Initial sandbox TCP failures disappeared with local port access enabled.

**Decisions:**
- Scope is Person 1's non-audio work. Existing module dependencies installed for tests only; no new runtime dependency added. Root dependency pinning remains pending Python 3.11 verification.
- Voice input/transcription and spoken answers are outside this non-audio pass. New voice contracts and dependencies still need the agreement described in AGENTS.md and the voice-plan branch.

**Teammates need to know:**
- Run `python -m app --record-crops` on the demo laptop. Use the logged session's `manifest.csv`, fill `expected_brand` and `expected_product`, then run `python -m fakes.namer.eval_batch --manifest <session>/manifest.csv --results <session>/results.csv`.
- Collect 5–10 real demo objects alone, with small labels, partly covered, and in groups. Real crop accuracy remains unmeasured here.
- Still required: Python 3.11/Windows validation, Logitech camera tests, and real stairs/doorway/wall checks of the narrowed hazard prompt. Unit tests cannot establish the prompt's real-world detection accuracy.
- Changes are local on `p1-vision`; not pushed or merged.

### 2026-11-14, Person 4 (tabletop detection trace), Claude Code
**Changed:** No code or config. Wrote a diagnostic script outside the repo that runs the same frames through each vision stage, separately from the app (never on the frame path). It covers raw `yolo11s` predictions at confidence 0.05, ByteTrack IDs with the app's settings, and `vision.tracked_objects()` itself for the app's filter. It repeats the tracker and filter stages for the experimental settings on separate tracker instances.

**Tested:** One 14 s clip (70 frames at 5 fps) from the laptop's built-in webcam: a table with a chair, a small bottle about 3 m back, and a large black bottle with a handle up close. Same clip for every setting:

| Setting | Small bottle reaches `FrameResult` | Bottle track IDs | Other objects kept |
|---|---|---|---|
| App now (conf 0.5, area 0.02) | 0 / 70 | none | chair 70 |
| Area 0.002 only | 36 / 70 | one (stable) | chair 70 |
| Conf 0.3 only | 0 / 70 | none | chair 70 |
| Conf 0.3 + area 0.002 | 70 / 70 | one (stable) | chair 70 |

- Raw YOLO saw the small bottle in 70 / 70 frames, at confidence 0.36–0.63 (median 0.51). Its box was 0.30–0.41% of the frame.
- The two filters both bite. Every box is under the 2% area cut. About half the frames are also under 0.5, and `detector.track(conf=DET_MIN_CONFIDENCE)` drops those before ByteTrack sees them.
- With both lowered, the bottle keeps one stable track ID for the whole clip, and no extra objects appeared in this scene.
- The large black bottle up close was never labelled a bottle. Raw YOLO called it "suitcase" at 0.07. Thresholds cannot fix that; it is a model limit, and a model swap needs the team's say-so (AGENTS.md rule 7).
- An earlier run aimed at the user's face saw no bottle at all and is not evidence.

**Decisions:** Root cause for small and far objects: the area filter first, then the 0.5 confidence gate passed to the tracker. Neither setting alone recovers the bottle reliably. Proposed defaults, needing all four to agree: `DET_MIN_AREA_FRACTION = 0.002`, `DET_MIN_CONFIDENCE = 0.3`. Nothing in `config/` was changed.

**Teammates need to know:**
- **Person 2:** please send a short clip from the glasses camera of the failing table, so the same trace can be run on it before the defaults change. The trace script can be shared.
- **Person 1:** the confidence passed to `detector.track()` is what gates ByteTrack. Lower defaults add a little per-frame work (more boxes to track); measure latency before and after.
- **All:** lower thresholds may add false detections in busier scenes. This clip was a sparse table, so check the glasses-camera clip before agreeing.
- The clip itself stays on Person 4's laptop and is not committed.

### 2026-11-14, Person 4 (setup and real-camera check), Claude Code
**Changed:** No code. On the Windows laptop, installed the vision stack into Python 3.11 (`opencv-contrib-python==4.11.0.86`, `ultralytics==8.4.212`, `torch==2.15.0+cpu`, `mediapipe==1.2.3`, `httpx==0.28.1`, `psycopg[binary]==3.3.9`). Removed the `opencv-python` that Ultralytics pulls in, as Person 2's note asks. Downloaded `vision/models/yolo11s.pt` (19.3 MB, Ultralytics GitHub releases v8.3.0) and `vision/models/hand_landmarker.task` (7.8 MB, MediaPipe storage); both are git-ignored.

**Tested:** On `main` at `a5ea3af` (includes PRs #11–#15). `python -m app --fake vision audio`: the page loaded, the feed showed the fake frames with bottle and cup boxes, the Objects panel listed both, and Simulate alert added one entry. Full `pytest`: 181 passed, 1 skipped, 1 failed (`test_cli_fake_vision_starts`, the known timing failure). `python -m app` on the real webcam with no `.env`: every module started, the dashboard was Live with a 640 x 360 feed, and Grok hazard checks were disabled as expected. Vision logged capture-to-publish latency of 156–248 ms, over the 150 ms target, with `yolo11s` on CPU. No objects were listed during the run; the scene in view was not set up for the investigation yet.

**Decisions:** The `lap` auto-install is logged for Person 1 under "Needs attention" rather than fixed here, because `vision/` is theirs.

**Teammates need to know:** Person 1: the latency numbers above are from `yolo11s` on this laptop's CPU, worth weighing against the accuracy gain from PR #13. Person 4 starts the tabletop investigation next.

### 2026-11-14, coordination (Person 4 assignment), Codex
**Changed:** Recorded the user's assignment of the missed tabletop-object investigation to Person 4, working on it now. Documentation only; no runtime code, thresholds, contracts, or folder ownership changed.

**Tested:** Inspected `vision/vision.py`, `config/thresholds.py`, and dashboard drawing paths. The pipeline supports multiple objects. Current code uses `yolo11s.pt`, 640 x 360 processed frames, ByteTrack, confidence 0.5, and a 2% minimum bounding-box area. Boxes without tracking IDs and the person class are excluded. No camera validation or runtime tests performed for this documentation-only update.

**Decisions:**
- Person 4 leads diagnosis and coordinates implementation with folder owners. The size filter is a suspect, not a confirmed cause: a 30 x 100 pixel bottle box falls below the 4,608 pixel minimum.
- Compare the same recorded frames through raw YOLO boxes/confidence, tracking IDs, filtered `FrameResult.objects`, `SceneSnapshot`, and dashboard overlays. Identify where objects disappear.
- First local experiment: `DET_MIN_AREA_FRACTION = 0.002` instead of `0.02`. Separately, if needed, try `DET_MIN_CONFIDENCE = 0.3` instead of `0.5`. Compare recovered objects, false detections, and tracking stability. These are experiments, not approved shared defaults.

**Teammates need to know:**
- **Person 2:** provide a short representative recording of the failing table scene, including the water bottle at different distances; assist with scene stabilization/touch issues. Recorded footage permits reproduction on this laptop without a live camera.
- **Person 1:** coordinate diagnostics and fixes in `vision/`; preserve frame-loop and hazard performance.
- **Person 4:** inspect dashboard rendering in your folder; gather before/after evidence from the same clip. Coordinate other-folder edits with their owners; this assignment does not transfer ownership.
- **All four:** agree before committing shared configuration defaults. No model swap or training is authorized by this handoff.
- **Completion:** run relevant regression tests and full `pytest`, document results and remaining camera limitations, and remove the Needs attention item once fixed.


### 2026-11-14, Person 2 working in `vision/`, Claude Code: demo detector changed to YOLOE with reference pictures
**Changed:** Demo mode detected nothing on the real camera, so the demo detector was replaced. The button, `ModeChange`, the threshold and the dashboard are as in the entry below.
- **Why YOLO-World failed.** On one real frame from the Logitech camera (bottle, toothpaste, laptop, hand), resized to 640 x 360, YOLO-World small scored the water bottle 0.05 and the toothpaste 0.03 against a cutoff of 0.25. Plainer wording and the v2 small, medium and large weights were tried: the best toothpaste score was 0.08, and the large model took about 350 ms per frame. YOLOE with text prompts was no better (toothpaste 0.09 small, 0.19 medium).
- **What works: YOLOE visual prompts.** YOLOE is given a picture of each object with a box around it and turns that into an embedding. Nothing is trained. With the bottle and toothpaste boxed on that one frame, the small model scored toothpaste 0.90 to 0.99 and bottle 0.63 to 0.89 on altered copies of the frame (flipped, darker, rotated and scaled), and found nothing on a laptop-only crop.
- **`vision/capture_demo_refs.py` (new):** `python -m vision.capture_demo_refs`. OpenCV window on the camera; for each demo object press SPACE, drag a box, ENTER. Saves 640 x 360 pictures and `refs.json` to `vision/demo_refs/`.
- **`vision/build_demo_weights.py` (rewritten):** reads `refs.json`, averages the embeddings per object, adds text embeddings for car, bus, truck, motorcycle and bicycle (for hazard tier A), saves `vision/models/demo-prompts.pt`. Warns for any demo object with no picture.
- **`vision/vision.py`:** demo mode loads `yoloe-11s-seg.pt` and `demo-prompts.pt` and calls `set_classes`. If either file is missing, demo mode is refused as before.
- **`SPEC.md` 5:** the `ModeChange` note now describes YOLOE and the two commands.

**Tested:**
- `python -m vision.build_demo_weights --refs <folder>` on a folder holding that one frame with two boxes: wrote prompts for water bottle, toothpaste and the five vehicle classes.
- `load_processor` with `clip` and `mobileclip` imports blocked, then `VisionProcessor.process` on four altered copies of the frame, six frames each. Actual mode: laptop only (the bottle scores 0.46, under `DET_MIN_CONFIDENCE`). Demo mode: toothpaste and water bottle tracked in every variant, no vehicle reported. A second, lower box around bottle plus arm (0.34) appeared in one variant.
- Speed on this CPU-only laptop, detector plus hands: actual median 88 ms, worst 100 ms; demo median 103 ms, worst 119 ms.
- **Fix, same day:** the first real run of `capture_demo_refs` showed no window and no message. Three copies had been started in three terminals and were competing for the camera; each hung opening it or looped on failed reads without saying so. The tool now logs "Opening camera N", gives up with a clear message after 15 s if the camera will not open or 5 s if it sends no picture, logs "Camera ready" once it does, and keeps its window on top.
- **Second fix:** after those copies were force-stopped, camera 1 (the external webcam) still hung on OpenCV's default Windows backend but opened in 0.3 s through DirectShow (`CAP_DSHOW`). The tool now falls back to DirectShow when the default backend does not open within 15 s. `vision/vision.py` still uses the default backend only, so **Person 1**: if the app's camera hangs the same way, unplugging and replugging the webcam may clear it, or the same fallback could go into `LatestCamera`.
- **Reference pictures taken (Person 2, 13:15 to 13:30):** 62 pictures in `vision/demo_refs/` on the Logitech camera: water bottle 8, toothbrush 6, toothpaste 8, charger 5, phone 9, headphones 10, keys 7, watch 9. Every box was checked by eye on a contact sheet: all on the right object; toothbrush 3 and 5 and charger 5 are loose.
- **Accuracy, leave-one-out** (each picture detected with prompts built from the other 61, cutoff `DEMO_DET_MIN_CONFIDENCE` 0.25, counted as found when the right name is on a box overlapping the object): averaged prompt per object 18/62 (29%); one prompt per picture 25/62 (40%); both together 28/62 (45%). Both together is what `build_demo_weights` now saves (75 prompts named like `keys/3`; `vision.tracked_objects` cuts the `/3` so the label stays `keys`). Per object with both: water bottle 6/8, toothpaste 4/8, phone 5/9, headphones 6/10, watch 4/9, toothbrush 2/6, charger 1/5, keys 0/7. Headphones and keys are often boxed as water bottle.
- **Why it is low:** not a bug. The prompt computed by `build_demo_weights` is identical to Ultralytics' own `refer_image` path, and even a picture's own prompt scores it low (headphones_5 0.09, keys_3 0.19, water_bottle_2 0.44). YOLOE visual prompts are weak on these webcam pictures. The 0.98 on the first screenshot was a lucky case.
- **Next, if demo mode must be reliable:** fine-tune a detector on these 62 labelled pictures (they already have boxes). That is training, so AGENTS.md rule 7 needs the human's say-so; on this CPU-only laptop expect roughly half an hour, not measured.
- **Not tested:** live demo mode on the camera with the 62-picture prompts. Earlier note, now out of date: `capture_demo_refs` had not been run successfully yet (it needs a person at the camera, and the camera was in use). Six of the eight objects (toothbrush, charger, phone, headphones, keys, watch) have never been through the detector. The test frames were copies of the reference frame, which flatters the scores; the real check is the live camera after proper reference pictures.

**Teammates need to know:**
- On the demo laptop: stop the app, run `python -m vision.capture_demo_refs` (two or three pictures per object, in demo lighting), then `python -m vision.build_demo_weights`, then start the app and press Demo mode.
- The build needs a network connection the first time: `yoloe-11s-seg.pt` (28 MB) and `mobileclip_blt.ts` (600 MB, only used for the vehicle text prompts). Run time needs only `yoloe-11s-seg.pt` and `demo-prompts.pt`, both git-ignored.
- `vision/models/demo-prompts.pt` on Person 2's laptop currently holds only water bottle and toothpaste, from the one test frame. It is replaced by the next build.
- Ultralytics' CLIP package was installed into Person 2's venv for the YOLO-World attempt and is no longer needed.
- `vision/demo_refs/` pictures are not git-ignored. Decide whether to commit them.
- `.gitignore` gained one line, `mobileclip_*.ts`, so the 600 MB text encoder cannot be committed by accident.
- `pytest`: 185 passed, 1 skipped, and `test_cli_fake_vision_starts` failing on some runs and passing on others, as in the entry below. `ruff check .`: clean.

### 2026-11-14, Person 2 working in `vision/`, `dashboard/`, `contracts/` and `config/`, Claude Code: demo mode built
**Changed:** Person 2 is responsible for the demo and told the agent to build demo mode now, across other people's folders and the shared files. The owners have not reviewed it. Branch `p2-demo-mode`.
- **What demo mode is:** the live camera as always, but objects are detected by YOLO-World with a fixed class list instead of COCO `yolo11s.pt`. Five of the eight demo objects (toothpaste, charger, headphones, keys, watch) have no COCO class, so they could never be touched or named in actual mode. No model is trained.
- **`contracts/`, `SPEC.md` 5:** new `ModeChange` (`ts`, `mode`). Dashboard publishes it; vision subscribes. If vision cannot switch, it publishes `ModeChange` with `mode="actual"` so the page shows what is really running.
- **`config/`, `SPEC.md` 9:** new `DEMO_DET_MIN_CONFIDENCE` = 0.25, because open-vocabulary scores run lower than COCO scores. The value is a guess, not measured.
- **`vision/vision.py`:** `load_processor` also loads `vision/models/demo-world.pt` if it exists. `VisionProcessor.set_mode` picks the detector for the next frame, rebuilds the tracker on the first frame after a switch, and offsets track ids so an id is never reused across modes (scene keeps names by id). `Vision.on_mode` only stores the request; the frame loop applies it. Nothing is downloaded at run time.
- **`vision/build_demo_weights.py` (new):** `python -m vision.build_demo_weights`, run once in a setup shell. Loads `yolov8s-world.pt`, sets the classes, saves `demo-world.pt`. Classes are the eight demo objects plus car, bus, truck, motorcycle and bicycle, so hazard tier A still sees vehicles in demo mode.
- **`dashboard/`:** "Demo mode: on/off" button in the header, `POST /api/mode` with `{"mode": "actual" | "demo"}`, a `mode` field in the page state, and a "Demo mode: detecting the demo objects only" tag while it is on.
- **Not changed:** `namer/`. In demo mode the detector label is already specific ("toothpaste"), and it reaches Grok as the existing hint. `scene/`, `audio/`, `hazard/` and `storage/` are untouched. `--fake vision` ignores the mode.
- **Dropped from the earlier proposal:** playing recorded clips. Demo mode is live only.

**Tested:**
- `pytest`: 185 passed, 1 skipped (live DB). `ruff check .`: clean. New tests: detector switch, demo threshold, fresh tracker and unique ids; refusal without demo weights; the button publishing `ModeChange`; page state following a `ModeChange` from the bus; a bad mode value rejected.
- On the page at `localhost:8000`: the button is there and the "on" rendering was checked by hand. A click on a running `python -m app` without demo weights went back to "off", as designed.
- **Weights built on Person 2's laptop** with `python -m vision.build_demo_weights`: it downloaded `yolov8s-world.pt` (26 MB) and the CLIP ViT-B/32 text encoder (338 MB), installed Ultralytics' CLIP package into the venv, and wrote `vision/models/demo-world.pt` (27 MB) with the 13 class names. The saved file loads through `load_processor` with the `clip` import blocked, so run time needs no CLIP.
- **Speed, CPU only, one 1280 x 720 noise frame repeated 20 times through `VisionProcessor.process` (detector plus hands):** actual mode median 77 ms, worst 88 ms; demo mode median 90 ms, worst 104 ms. Both fit the 200 ms frame budget at 5 fps. Switching actual, demo, actual in one process worked.
- **`test_cli_fake_vision_starts` failed in 3 of 6 runs** after the build, and passed on a run with these changes stashed. It is the fixed `time.sleep(1.4)` test already listed under "Needs attention", and a second `python -m app` was running on this laptop at the time. The other 184 tests passed every run.
- **Not tested:** detection of the real objects. No image of any demo object has been through the demo detector, on a camera or from a file. Unknown: whether each of the eight is found, at what confidence, and how well ByteTrack follows them.

**Decisions:** demo touches are written to Tiger Data like any others; nothing marks them as demo.

**Teammates need to know:**
- Building the weights needs a network connection and installs Ultralytics' CLIP package into the environment (a dependency used only by the build script, AGENTS.md rule 8). Until `demo-world.pt` exists on the demo laptop the button does nothing.
- After building, test all eight objects on the Logitech camera and tune `DEMO_DET_MIN_CONFIDENCE` and the class wording in `build_demo_weights.py` (for example "phone charger" for "charger").
- `DET_MIN_AREA_FRACTION` (2% of the frame) still applies, so keys and a toothbrush must be close to the camera.
- See the three new "Needs attention" lines.

### 2026-11-14, Person 2 (docs only), Claude Code: demo button and recordings proposal
**Changed:** No code. Person 2 is responsible for the demo and asked how to build a demo button and whether to train the model on recorded clips. This is the agent's proposal for the team to accept or change. Nothing below is built or agreed yet.

**Proposal:**
- **No model training.** YOLO only finds boxes; the specific name comes from Grok reading the crop. Fine-tuning is against AGENTS.md rule 7, needs hundreds of hand-labelled frames, and would not improve the spoken names.
- **Demo mode = live camera plus a known object list.** The camera, scene, audio and hazard paths stay exactly as they are. The only difference is that the namer is told the demo objects.
  1. *Object list.* One file listing the demo objects by spoken name ("Heinz ketchup", "Diet Coke can"). Persons 1 and 2 choose the objects. Where the file lives needs agreeing (`config/` is shared; `namer/` is Person 3's).
  2. *Namer (`namer/`, Person 3).* In demo mode the Grok instruction adds: this is most likely one of the listed objects; if none match, give the plain name as now.
  3. *Button (`dashboard/`, Person 4).* A toggle beside Simulate alert, a `POST /api/mode` endpoint that publishes the mode change, and a visible "Demo mode" label so the page never hides which mode is on.
  4. *New message (`contracts/`, all four).* Nothing in `SPEC.md` section 5 carries a mode change. Suggested shape: `ModeChange` with `mode: Literal["actual", "demo"]` and `ts`. Dashboard publishes it, namer subscribes.
- **Recordings are for testing and backup, not training.**
  - *Accuracy:* record each demo object on the Logitech camera, save crops with `fakes.namer.crop_recorder`, score with `eval_batch --manifest`. This closes the open "naming on real crops" item.
  - *Backup:* if a clip should stand in for the camera, choose it at start-up (for example an env var holding the video path that `vision/` passes to `cv2.VideoCapture`), not from the page. `vision/` cannot swap sources while running.
  - Committed clips go under `fakes/vision/`, each under 20 seconds and 10 MB (AGENTS.md rule 10). Longer ones are copied to the demo laptop by hand.
- **Differs from the earlier plan** (entry below): that one had the button switch the app to playing a recording. This one keeps the live camera and moves clip playback to a start-up option, which avoids run-time source switching in `vision/`. Person 1, who started on per-object clips, should say whether that fits what he has built.

**Demo objects (chosen by Person 2, later the same day):** water bottle, toothbrush, toothpaste, charger, phone, headphones, keys, watch.

**Problem found with that list:** `vision/` runs plain COCO `yolo11s.pt`, and a touch only happens on an object YOLO has boxed. Checked against the COCO class list, not yet on camera:

| Object | COCO class | Expected |
|---|---|---|
| Water bottle | `bottle` | Detected |
| Toothbrush | `toothbrush` | Detected, but thin objects are often missed |
| Phone | `cell phone` | Detected |
| Watch | none (`clock` is wall clocks) | Missed or mislabelled |
| Toothpaste | none | Missed or mislabelled |
| Charger | none | Missed or mislabelled |
| Headphones | none | Missed or mislabelled |
| Keys | none | Missed or mislabelled |

Five of the eight have no COCO class, so no box, no touch and no spoken name. The Grok object list in this proposal does not help there, because Grok is only asked about boxes YOLO produced. Options, for the team to choose:
1. *Change the objects* to ones COCO has (bottle, cup, phone, toothbrush, book, scissors, remote, mouse, keyboard, banana, apple, orange, spoon, fork, backpack, umbrella). No code change. Lowest risk.
2. *Open-vocabulary weights in Ultralytics* (YOLO-World, for example `yolov8s-world.pt`, with the class list set to the demo objects). No training, same library, but it is a model swap in `vision/` (Person 1), so AGENTS.md rule 7 and the stack table need all four to agree, and speed and tracking on the demo laptop must be measured first.
3. *Fine-tune YOLO on recorded clips.* Not recommended: needs hand labelling and training time, and breaks rule 7.
Whichever is chosen, test each object on the Logitech camera before relying on it.

**Person 2's choice: option 2, in demo mode only.** Actual mode keeps `yolo11s.pt` unchanged. Demo mode runs YOLO-World with the eight demo objects as its class list. This still needs the other three to agree (model and stack change, AGENTS.md rules 7 and 8) and it is Person 1's folder. Design notes for Person 1 (Person 2's agent's notes):
- *What the venv has.* Checked on Person 2's laptop: `ultralytics 8.4.212` already includes `YOLOWorld`. Torch is CPU only, no GPU. The `clip` package is not installed.
- *One-off weights build, off the frame path.* Setting a class list needs the `clip` package and downloads a text encoder, as far as the agent knows. Do it once in a setup shell: load `yolov8s-world.pt`, call `set_classes([...the eight names...])`, then `save("vision/models/demo_world.pt")`. The saved file should then load with plain `YOLO(...)` and need no `clip` at run time. Confirm this on the installed version. Neither weights file is committed.
- *In `vision/`.* Load both detectors at start-up. Keep a current-mode flag, set from the bus when the mode message arrives, and call `.track(...)` on whichever detector is active. Reset the tracker when the mode flips so object ids from one model do not carry into the other. `TrackedObject.label` then carries the YOLO-World name ("toothpaste"), so no message shape changes.
- *Speed.* `yolo11s` takes about 49 ms per frame here on CPU. YOLO-World small will be slower. Measure it on the demo laptop before agreeing; if it is too slow, try a smaller input size.
- *Confidence.* Open-vocabulary scores run lower than COCO scores, so `DET_MIN_CONFIDENCE` (0.5) may hide real detections in demo mode. A separate demo threshold would be a new `config/` value, which needs all four.
- *Naming.* With the label already specific, the Grok object list in step 2 above matters less, but still helps with brands.

**To decide, all four:** (0) agree to YOLO-World in demo mode, (1) accept or change the proposal, (2) the `ModeChange` message, (3) where the object list lives, (4) whether demo-mode touches are written to Tiger Data.

**Tested:** Docs only; nothing to run.

**Teammates need to know:** see the new "Demo mode proposal" line in "Needs attention". `scene/` needs no change for any of this.

### 2026-11-14, Person 2 (docs only), Claude Code: voice questions plan for Person 1
**Changed:** No code. Records a feature Person 1 is starting, so his agent has the context.

**Planned, not built: voice questions.**
- **What:** the wearer asks a question out loud and hears a spoken answer. Person 1 plans to use a Google Home speaker for this. The dashboard shows each question and its answer.
- **Kinds of question:**
  - About what the camera sees now: "is this item in front of me?", "what am I holding?"
  - General: "what's the weather today?"
  - History: "where did I last touch the ketchup?" `storage/` already answers this through `LastSeenQuery`.
- **Who:** Person 1.

**Check before building** (Person 2's agent's notes, not team decisions):
1. **Getting the question off a Google Home.** Google shut down Conversational Actions for third-party apps in 2023, as far as the agent knows. A Nest or Home speaker may not pass the spoken question to our process at all. Confirm this first. If it cannot, the fallback is `SPEC.md` stretch goal 10.3: use the webcam's microphone, and use the Google Home only as a speaker or not at all.
2. **Stack.** A Google Home and any speech-to-text library are outside the stack table, so all four must agree first (AGENTS.md rule 8).
3. **Messages.** A question message and an answer message are probably needed. `SpeakRequest` (priority `normal`, `source` set to the sender's folder) can already carry the spoken answer to `audio/`, and `LastSeenQuery` already exists for the history case. Any new message goes in `contracts/` with all four agreeing (AGENTS.md rule 2).
4. **Answers about the scene.** Use the current frame or the latest `SceneSnapshot` from the bus, and send them to Grok from a background worker (AGENTS.md rule 4). Never read another module's internals.
5. **General answers.** Grok does not know today's weather unless the API call turns on a live search tool, if the Grok API offers one. Check that, or say "I can't check that" rather than guess.
6. **Hazard first.** If answers play through the Google Home instead of the JBL, a `HazardEvent` alarm cannot cut them off, which breaks `SPEC.md` 4.8 and AGENTS.md rule 5. Keep spoken answers on the JBL through `audio/` via `SpeakRequest`.
7. **Dashboard.** The question-and-answer panel is in `dashboard/`, Person 4's folder, with Person 3 working on the UI. Agree who adds it.
8. **Folder.** Decide which folder the feature lives in and add it to the ownership table, so it is clear it belongs to Person 1.
9. **Timing.** This is new scope close to the Saturday-midnight feature freeze (`SPEC.md` 8). Touch-to-name stays the priority if time runs short.

**Tested:** Docs only; nothing to run.

**Teammates need to know:** Person 1: give this entry to your agent before starting. Person 2's `scene/` needs no change: `SceneSnapshot` already carries what the scene questions need.

### 2026-11-14, Person 2 (docs only), Claude Code: status review and demo mode plan
**Changed:** No code. Reviewed the whole repository against `SPEC.md` and brought the Markdown files in line with `main` at `64f878b`.
- `SPEC.md`, `AGENTS.md`, `CLAUDE.md`, `contracts/README.md`: see the new row in "Contract changes". Person 2 confirmed all four teammates agreed.
- This file: "Needs attention" rewritten to what is still open, with the fixed items listed as closed. Stack table says YOLO small.

**Where the project stands:**

| Piece | State |
|---|---|
| Bus and `python -m app`, with `--fake` and `--only` | Working. All seven modules register and shut down cleanly |
| Vision (YOLO small, ByteTrack, MediaPipe hands) | Working on a real webcam, about 49 ms per frame for detection |
| Scene and touch (touch, release, retouch, held, held-merge) | Working, with tests for the 4.6 table |
| Naming through Grok | Working live. Brands only when readable on the object |
| Audio (name on touch, late name, alarm cuts speech) | Working on laptop speakers after the per-phrase engine fix. The JBL played before that fix |
| Dashboard | Camera feed with overlays, Objects panel, event log, hazard banner, Simulate alert. No FPS readout or last-touched search yet |
| Hazard tier A and tier B | Running. Tier B prompt narrowed; untested on a real hazard |
| Tiger Data log and last-seen answer | Working in `storage/` against the live database. Not reachable from the page yet |
| Stretch goals (SPEC.md 10) | Not started |

**Tested:** Windows 11, `.venv` Python 3.11.18. Full `pytest`: 182 passed, 1 skipped (the live DB test), before and after the doc edits. `ruff check .`: clean. `python -m app --fake vision` was not run by hand this session; `test_cli_fake_vision_starts` starts it and passed.

**Planned, not built: demo mode and actual mode.** Recorded here for later. Nothing below exists yet.
- **What:** one switch on the dashboard page at `http://localhost:8000` flips the running app between *actual mode* (live camera, as now) and *demo mode*.
- **Demo mode:** the app plays a recording a few minutes long of someone holding and touching a fixed set of objects, instead of the live camera. The set of objects is decided in advance and given to Claude Code to program in.
- **Who:** Persons 1 and 2 choose the objects and make the recording.
- **Update (later, same day):** Person 1 is building it. Instead of one long recording, he is making a folder in the repo root holding short videos, one per object, each file named after the object it shows. Points to check against that (Person 2's agent's notes):
  - *Folder ownership.* A new root folder is not in anyone's lane in AGENTS.md. Either put the clips under `fakes/vision/`, which Person 1 owns, or record the new folder and its owner in the ownership table with all four agreeing.
  - *Git.* `.gitignore` ignores `*.mp4`, `*.avi` and `*.mov` everywhere except `fakes/vision/`, so clips in a new root folder will not be committed unless that changes. Each committed clip must stay under 20 seconds and 10 MB (AGENTS.md rule 10).
  - *Names.* If the file name is used as the object's spoken name, decide the format now (for example `heinz_ketchup.mp4` spoken as "Heinz ketchup") so whoever reads it does not guess.
  - Points 3 to 6 below still apply.
- **To settle before building** (these are Person 2's agent's notes, not team decisions):
  1. *Where the recording lives.* AGENTS.md rule 10 caps committed video at 20 seconds and 10 MB, and `.gitignore` only lets video through under `fakes/vision/`. A recording a few minutes long has to stay out of git and be copied to the demo laptop by hand, unless all four agree to change the rule.
  2. *What "programmed in" means for the object set.* Either the recording runs through the real pipeline and the list is only used to check names, or demo mode uses fixed names for those objects and skips Grok so the demo does not depend on the network. Decide which.
  3. *How the switch reaches the app.* The page can only talk to `dashboard/`, and modules may only talk over the bus. No message in `SPEC.md` section 5 carries a mode change, so this needs either a new message (all four agree) or the switch handled in `app/` in a way the team accepts. Switching at run time also means stopping the camera and starting playback without restarting the process, which `vision/` does not support today.
  4. *Folders touched.* The switch is in `dashboard/` (Person 4). Playback and the mode change are in `app/`, `vision/` and `fakes/vision/` (Person 1). Fixed names, if chosen, touch `namer/` or `fakes/namer/` (Person 3).
  5. *Hazard and storage in demo mode.* Decide whether tier B Grok checks run on the recording, and whether demo touches are written to Tiger Data (they would mix with real history unless the session is marked).
  6. *Page wording.* Show clearly on the page which mode is on, so a recording is never presented as live.
- The existing `python -m app --fake vision` is scripted synthetic frames, not a recording, and is chosen at start-up, not from the page. Demo mode is a separate thing.

**Teammates need to know:**
- Everyone: pull, and read the rewritten "Needs attention" list. It has an item for each person.
- Persons 1 and 2: when you record, use the Logitech camera on the glasses at 1280 x 720, set each object down for 1 to 2 seconds before touching it, and keep the list of objects in the order they appear.
- Nobody should start building demo mode until points 1 to 3 above are decided.

### 2026-11-14, Person 2 working in Person 3's `namer/`, Claude Code: brand names only when readable
**Changed:**
- **Departs from SPEC.md 4.5's wording, `namer/grok_client.py`:** Grok was guessing brands and models from shape and colour, for example "Asus Zenbook" for a laptop with no visible logo. `INSTRUCTION` now says to include a brand or model only if it can be read printed on the object, never to guess from shape, colour or style, and otherwise to reply with the plain object name ("laptop", "water bottle"). Still at most 5 words, no sentences. Nothing else in `namer/` changed.

**Tested:**
- Real Grok (`GROK_MODEL` from `.env`), old prompt against new, two calls each: three live webcam frames, a drawn red can with no text, and the same can with "Diet Coke" printed on it. New prompt: "laptop" for every webcam frame, "can" for the blank can, "Diet Coke can" for the labelled one. Old prompt: once "White hoodie laptop sleeve", and "Red bottle" for the blank can.
- **Not reproduced:** the exact over-guess the user saw (a brand invented for an unbranded object) did not happen with the old prompt on these images, so the fix is shown to keep readable brands and give plain names, not yet shown to remove that specific guess. Check on the demo objects.
- Full `pytest` (`.venv`, Python 3.11.18): 182 passed, 1 skipped. `ruff check namer/` clean.

**Teammates need to know:**
- Person 3: please review the new prompt and rerun `fakes.namer.eval_batch` on your eval set; `brand_correct` may drop for items whose brand was only guessable, which is intended.
- All four: SPEC.md 4.5's prompt wording now differs from the code, so it needs updating once you agree.

### 2026-11-14, Person 2 working in Person 4's `audio/` and Person 1's `hazard/`, Claude Code: silent speech and false hazards
**Changed:**
- **Bug fix, `audio/backends.py`:** names were never heard after startup. With `pyttsx3==2.99` on Windows (SAPI5), only an engine's first `runAndWait()` makes sound. Every later call returns in about 85 ms in silence. That covered every touched name and the spoken "Stop. Obstacle."; only the `pygame` beeps were audible. `Pyttsx3Speaker` now builds a fresh engine for each phrase (about 26 ms) and garbage-collects the old one, because `pyttsx3.init()` caches engines weakly. Cutting off at a word boundary for alarms works the same way. The constructor still starts an engine once, so a broken install still falls back to `LogSpeaker` at startup.
- **Departs from SPEC.md 4.7, `hazard/hazard.py`:** `GROK_PROMPT` is narrower than the spec's wording. It tells Grok the camera is tilted down toward the hands, that only a step, stair edge or drop directly ahead, an approaching vehicle, or a solid object in the path within about 1 m counts, and lists what does not count: tabletop items, things in hands, furniture beside the path, a table edge seen from above. It ends with "if you are not sure, answer hazard false". Nothing else in hazard changed. The cooldown, the 0.6 cutoff, the single-positive rule and tier A are untouched.
- New `tests/test_audio_pyttsx3.py`: checks there is a new engine per phrase, and that a phrase cut off by an alarm does not silence the next one.

**Tested:**
- On this laptop's real speakers, through `Pyttsx3Speaker` on a worker thread: before the fix, phrases 2 and later took 85 ms (silent). After it, every phrase took 1 to 1.5 s, including the three phrases after one cut off mid-sentence.
- Against real Grok, using one earlier screenshot and four live webcam frames (a room and a countertop close-up, none with a real hazard), two calls each: the old prompt flagged 8 of 10 (7 obstacle, 1 drop_off). The new prompt flagged 0 of 10.
- **Not tested:** whether the new prompt still flags real stairs, a drop or an obstacle. None were on camera.
- The terminal log of the session that prompted this showed 22 alarms in about 2 minutes ("Obstacle", and "Stairs" 4 times, indoors), Grok confidence 0.70 to 0.90.
- Full `pytest`: 182 passed, 1 skipped. `ruff check` is clean on `audio/` and `hazard/`. `hazard.py` was already not `ruff format`-clean before this change and was not reformatted.

**Teammates need to know:**
- Person 1: please test the new prompt on real stairs and a doorway or wall before the demo. If it misses them, loosen the "do not count" list rather than going back to the old prompt.
- All four: SPEC.md 4.7's prompt text now differs from the code, so it needs updating once you agree.
- Person 4: the speech fix is in your `audio/backends.py`. Please review it.

### 2026-11-14, Person 2 working in Person 1's `vision/`, Claude Code: YOLO nano to YOLO small
**Changed:** `vision/vision.py` now loads `vision/models/yolo11s.pt` instead of `yolo11n.pt`, and its missing-weights message names the new file. Nothing else changed. Person 2 asked for the swap after the real camera missed a held backpack. It is outside Person 2's lane and is a model swap (AGENTS.md rule 7), so it is logged here for Person 1 and the team.

**Tested:** On a frame from the real camera (640 x 360, CPU), `yolo11n` found no backpack even at 0.05 confidence. `yolo11s` found it at 0.51, and raised the couch from 0.31 to 0.46 and the book from 0.11 to 0.39. Speed on this laptop's CPU: 24 ms per frame for nano and 49 ms for small. `python -m app` on the real webcam started every module, and the dashboard listed and named the chairs and the couch. One sampled frame of about 19 went over the 150 ms capture-to-publish target, at 159 ms. Full `pytest`: 180 passed, 1 skipped.

**Decisions:** Kept `DET_MIN_CONFIDENCE` at 0.5. The backpack's 0.51 is just over it, so it may flicker on other angles.

**Teammates need to know:** Weights are git-ignored. Everyone running the real camera must download them once:
`cd vision/models && python -c "from ultralytics import YOLO; YOLO('yolo11s.pt')"` (18.4 MB, from Ultralytics' GitHub releases). The stack table still says "YOLO nano". Person 1 and the team: keep small, or revert line 25 of `vision/vision.py` to `yolo11n.pt`. If you keep it, update the stack table in SPEC.md, AGENTS.md and CLAUDE.md.

### 2026-11-14, Person 2 working in Person 4's `dashboard/`, Claude Code: object list and why some objects are missing
**Changed:**
- Built the Objects panel from SPEC.md 4.9. `DashboardState.on_scene` takes each `SceneSnapshot` and pushes it over `/ws`. Each row shows the name (or the class with "naming…" until Grok answers), the state, and the time since the object was last seen. Touching and held objects are highlighted and sorted to the top, and lost objects are dimmed. `register(bus)` subscribes the state to `SceneSnapshot`.
- Camera-feed labels near the right edge now slide left to stay inside the frame, instead of being cut off ("HON ch…").
- New tests: the object list's sorting and fields, and the label staying in the frame.

**Tested:** Full `pytest` in `.venv`: 180 passed, 1 skipped. `ruff` is clean. Ran `python -m app --fake vision` and watched the page: "Orange bottle" and "Paper cup" were listed as idle, and "Orange bottle" moved to the top highlighted as TOUCHING during the scripted touch.

**Decisions:** Nothing in `vision/` changed.

**Teammates need to know:** Found while testing on the real camera. Person 1 should read this; the call isn't Person 2's to make.
- **Backpack not detected:** `yolo11n.pt` found nothing for the backpack on a real-camera frame, even at 0.05 confidence. Fixed by the switch to `yolo11s` in the entry above.
- **Sponge not detected:** "sponge" is not one of the 80 COCO classes, so YOLO with COCO weights can never detect it. SPEC.md stretch goal 10.1 ("Unknown objects") covers this: if fingertips rest for 1 second where there is no box, crop around the hand and send it to the namer.
- **People are never listed:** by design, per SPEC.md ("Drop the `person` class").

### 2026-11-14, Person 2 working in Person 4's `dashboard/`, Claude Code: live camera feed
**Changed:**
- **This is outside Person 2's lane.** Person 2 told the agent to make the change anyway and log it here so Person 4 knows (see "Needs attention").
- New `dashboard/video.py`. `VideoFeed` subscribes to `FrameResult` and `SceneSnapshot`, draws the SPEC.md 4.9 overlays on a copy of the frame, and keeps the newest JPEG. Overlays: thin grey for `new`, white with name or class for `idle`, thick green tagged TOUCHING for `touching`, yellow tagged HELD for `held`, dashed white for `lost`, and a dot on each thumb tip and index fingertip. When no recent snapshot is available (scene not running, or more than `PROCESS_FPS` frames behind), every detection is drawn in the `new` style.
- `dashboard/server.py`: new `GET /video` route that streams MJPEG (`multipart/x-mixed-replace`). `register(bus)` now also subscribes the feed to `FrameResult` and `SceneSnapshot`. `Dashboard.stop()` closes open streams first so shutdown does not hang on them.
- `dashboard/index.html`: the camera panel shows `<img src="/video">`. The server sends a "Waiting for camera" picture until the first frame. If the stream errors, the page shows "Camera feed not connected" and retries every 2 s, and it also reloads the stream when the WebSocket reconnects.
- `dashboard/requirements.txt`: added `opencv-contrib-python==4.11.0.86`, the build already in the project `.venv` (MediaPipe uses it). Do not also install `opencv-python` in the same environment, because the two packages overwrite each other's `cv2`.
- `tests/test_dashboard.py`: the subscription check now expects the two new message types. New `tests/test_dashboard_video.py` covers state colours, fingertip dots, leaving the bus image untouched (scene crops from it), the no-scene fallback, ignoring stale snapshots, bus-to-JPEG wiring, the stream generator, and `/video` on a real served port.

**Tested:** In the project `.venv` (Python 3.11.18): full `pytest` passed 178, skipped 1, failed 0. `ruff check` and `ruff format` are clean on the changed files. I ran `python -m app --fake vision`, opened http://localhost:8000 and watched the feed: idle boxes labelled "Orange bottle" and "Paper cup", then a green "TOUCHING Orange bottle" with two fingertip dots during the scripted touch. The log showed no errors. Not tried on the real webcam.

**Decisions:** Drawing and JPEG encoding happen on the dashboard's own bus worker. The bus drops stale `FrameResult`s per subscriber, so a slow encode can only make the feed skip frames. It cannot slow vision, scene or hazard. No network or database calls were added. Drawing sizes, colours and JPEG quality are named constants in `dashboard/video.py`, not thresholds in `config/`.

**Teammates need to know:** Person 4: please review, and reinstall with `py -3.11 -m pip install -r dashboard/requirements.txt` if you don't use the shared `.venv`. Not done yet from SPEC.md 4.9: the Objects list (from `SceneSnapshot` over `/ws`), the processed-FPS readout, and the last-touched search box.

### 2026-11-14, Person 4 (dashboard), Claude Code: page starts inside the app
**Changed:**

- `dashboard.register(bus)` now returns a `Dashboard` and starts the web page on a background thread on `DASHBOARD_PORT`, so `python -m app` serves it at `http://localhost:8000`. `stop()` shuts the server down. If the port is busy it logs a warning and the app carries on without the page. `register(bus, serve=False)` skips the server; the tests use it.
- New tests: the page starts on a thread, answers, and stops; a busy port is skipped without crashing.

**Tested:** `pytest tests/test_dashboard.py`: 8 passed. Full `pytest` twice: 171 passed, 1 skipped, 1 failed, the same `test_cli_fake_vision_starts` timing failure as on `main`; port 8000 was free afterwards. Ran `python -m app --fake vision hazard audio` for 12 s, so nothing was played aloud. The app logged "Dashboard page at http://localhost:8000". Each fake hazard reached fake audio (`BEEP BEEP BEEP`, then `say: Stop. Stairs.`) and the page at the same time; `/api/state` showed it as "Stairs, grok, 91%", not simulated. One `POST /api/simulate-alert` added exactly one simulated entry, and fake audio printed nothing for it.

**Decisions:** Simulate alert stays page-only. To see and hear hazards together, run the app with `--fake hazard`, which publishes real `HazardEvent`s.

**Teammates need to know:** Person 1: `dashboard.register(bus)` now starts the page itself; nothing else is needed in `app/`. The returned object has `stop()`.

**Later, by hand (Person 4):** Ran `py -3.11 -m dashboard` on Windows and clicked Simulate alert once: one "Stairs SIMULATED" warning and one Recent events entry, no sound, as intended. Ran the audio on the JBL Go 3 speaker and it played.

### 2026-11-14, Person 4 (audio, dashboard), Claude Code: rebase onto PR #10
**Changed:**

- Rebased `voice-dashboard` onto `main` after PR #10 (Anshi's audio manager, `app/` bus, vision and hazard). Where both added the same file, `main`'s version is kept: `audio/__init__.py`, `audio/requirements.txt`, `fakes/audio/__init__.py`, `fakes/audio/fake_audio.py` and `tests/test_audio.py`. This branch's `fakes/audio/__main__.py` was dropped because it used the replaced fake.
- The `audio/speak_test.py` tests moved to a new `tests/test_speak_test.py`, because `main`'s `tests/test_audio.py` does not cover it.
- PR #4 now adds only `audio/speak_test.py`, `audio/.gitignore`, `dashboard/`, `tests/test_speak_test.py`, `tests/test_dashboard.py` and these notes. Reworded the second commit to match.
- A local backup of the branch before this rebase is kept as `backup/voice-dashboard-before-main-audio` (not pushed).

**Tested:** Python 3.11.9 venv with `pygame==2.6.1` added. Full `pytest` from the repo root with the Grok and Tiger Data variables unset: 169 passed, 1 skipped, 1 failed. The failure is `tests/test_app_p1.py::test_cli_fake_vision_starts`, which also fails 3 of 3 times on a clean copy of `main` on this laptop (see "Needs attention"). `python -m app --fake vision` with `SDL_AUDIODRIVER=dummy` logged "Started dashboard" along with the other modules, and fake frames flowed. `ruff check` is clean on `tests/test_speak_test.py`. Nothing was played aloud.

**Decisions:** Anshi's audio manager replaces this branch's fake and audio tests, as Person 4 decided.

**Teammates need to know:** Install audio with `py -3.11 -m pip install -r audio/requirements.txt`, then `py -3.11 -m audio` plays the scripted demo, including the stairs alarm.

### 2026-11-14, Person 4 (dashboard), Claude Code
**Changed:**

- There was no dashboard code on any branch, so this adds a minimal `dashboard/` laid out per SPEC.md 4.9. FastAPI serves one plain HTML page (`dashboard/index.html`), pushes state over the WebSocket at `/ws`, and runs alone with `python -m dashboard` on `DASHBOARD_PORT`. `dashboard/requirements.txt` pins `fastapi==0.162.7` and `uvicorn[standard]==0.54.0`.
- `register(bus)` subscribes `HazardEvent` and `TouchEvent` (touches only; releases are not logged). The camera feed (`/video`), object list, FPS and last-seen search are placeholders and not built yet.
- The "Latest warning" card stands in for the spec's red hazard banner and turns red for `HAZARD_COOLDOWN_SECONDS` after a hazard. "Recent events" is the spec's 10-entry event log.
- A **Simulate alert** button (`POST /api/simulate-alert`) adds one `stairs_down` warning, labelled **Simulated**, to the dashboard only. It publishes nothing on the bus, so no alarm sounds and nothing is stored (AGENTS.md rule 5, SPEC.md 3.1).
- New `tests/test_dashboard.py` (6 tests).

**Tested:** In a Python 3.11.9 venv: `pytest tests/test_dashboard.py` gave 6 passed. Full `pytest` from the repo root, run twice with the Grok and Tiger Data variables unset: 99 passed, 1 skipped, 1 failed both times, the failure being the known `test_storage.py::test_unreachable_db_never_blocks_and_warns_once`. `ruff check` and `ruff format` are clean on `dashboard/` and `tests/test_dashboard.py`. Ran `python -m dashboard` and opened `http://localhost:8000` in a browser. One click showed "Stairs" with a Simulated tag in the red Latest warning card and exactly 1 entry in Recent events. After 3 s the card turned neutral. A second click made exactly 2 entries. At 375 px wide the layout stacks with no sideways scroll.

**Decisions:** Using `HAZARD_COOLDOWN_SECONDS` for how long the banner stays red is my choice; SPEC.md only says "while a hazard is active". A simulated alert is not a `HazardEvent` because the contract has no field to mark it simulated.

**Teammates need to know:** Install with `py -3.11 -m pip install -r dashboard/requirements.txt`. Person 1: `dashboard.register(bus)` now also starts the page (see the later entry above). All: please confirm or replace the banner-duration choice above.

### 2026-11-14, Person 4 (audio), Claude Code
**Update (later):** The `fakes/audio/` fake and `tests/test_audio.py` described below were replaced by PR #10's versions on `main`; the speak_test tests now live in `tests/test_speak_test.py`. See the rebase entry above.
**Changed:**

- Rebased `voice-dashboard` onto `origin/main`. The only conflict was this file; both the Person 4 entries and the team's entries are kept.
- `audio/speak_test.py` now uses `pyttsx3` (the approved speech engine) instead of Piper. It runs on any OS, needs no voice download, and takes `main(argv)` so tests can drive it. `audio/requirements.txt` pins `pyttsx3==2.99`; Piper is removed. Added `audio/__init__.py`.
- `audio/.gitignore` no longer ignores every `*.wav`, so the prerecorded alarm WAV can be committed. Generated audio goes in `audio/generated/`, which is ignored. `voices/` stays ignored for the leftover local Piper files.
- New `fakes/audio/`: `FakeAudio` and `register(bus)` subscribe to `HazardEvent`, `TouchEvent`, `NameResult` and `SpeakRequest`, record what would be played (SPEC.md 4.8 phrases, 4.5 late-name rule), and publish nothing. `python -m fakes.audio` prints a scripted run. It does not model timing, the one-item queue or the alarm cut-off.
- New `tests/test_audio.py` (11 tests). pyttsx3 is replaced with a stub module, so no speaker and no pyttsx3 install are needed.

**Tested:** In a Python 3.11.9 venv without pyttsx3: `pytest tests/test_audio.py` gave 11 passed. Full `pytest` from the repo root, run four times with `TIGER_DATABASE_URL` and `GROK_API_KEY` unset: two runs gave 94 passed, 1 skipped; two runs gave 93 passed, 1 skipped, 1 failed, the failure being `test_storage.py::test_unreachable_db_never_blocks_and_warns_once` (already listed under "Needs attention"). Before these changes the baseline was 82 passed, 1 skipped, the same 1 failed. `ruff check` and `ruff format --check` are clean on `audio/`, `fakes/audio/` and `tests/test_audio.py`. `python -m fakes.audio` printed the expected five lines. `git add --dry-run` accepted `audio/alarm.wav` and skipped `audio/generated/speech.wav`. After installing `pyttsx3==2.99`, `pyttsx3.init()` started on Windows and listed 2 voices. Nothing was spoken aloud; audible playback on the laptop and the JBL is not yet confirmed.

**Decisions:** SPEC.md names no path for the alarm WAV, so no path was chosen. Any WAV under `audio/` outside `generated/` can be committed. The `python -m app --fake audio` wiring is Person 1's; `fakes.audio.fake_audio.register(bus)` uses the same `bus.subscribe(MessageType, handler)` shape as Person 3's fakes.

**Teammates need to know:** Reinstall with `py -3.11 -m pip install -r audio/requirements.txt`. Person 1: `fakes.audio.fake_audio.register(bus)` is ready for `--fake audio`; it returns an object with a no-op `stop()`.

### 2026-11-14, Person 4 (audio), Codex
**Update (later, Claude Code):** After the rebase onto `main`, `contracts/messages.py` (with `HazardEvent`), `config/thresholds.py` and `samples/hazardeventsample.py` are present, so the blocker below no longer applies.
**Changed:** No audio code changes: requested shared HazardEvent integration cannot be implemented against this checkout because no shared event implementation or contracts folder exists here.
**Tested:** Confirmed branch voice-dashboard, inspected audio/speak_test.py and repository files. Script contains text playback only, no made-up alarm. Verified Piper 1.3.0 downloader supports --download-dir and creates the voice directory. Python launcher remains unavailable in the agent terminal; no playback or pytest run possible here.
**Decisions:** Do not invent a replacement HazardEvent or edit shared contracts. User reports Piper 1.3.0 installed under Python 3.11 in their terminal.
**Teammates need to know:** Need location or branch containing the team's actual HazardEvent definition before adding the requested stairs hazard example. Existing manual sentence test can run after voice download.

### 2026-11-14, Person 4 (audio), Codex
**Update (later, Claude Code):** Piper was replaced with `pyttsx3` and the blanket `*.wav` rule removed; see the entry above.
**Changed:** Added standalone `audio/speak_test.py` for supplied text, pinned Piper in `audio/requirements.txt`, and ignored local environments, voices and generated WAV files under audio.
**Tested:** Confirmed branch `voice-dashboard` and initially clean working tree. Inspected entire repository: planning documents only, no existing audio, Python setup, Piper or voice models. Reviewed Piper's documented Python API. `git diff --check` passed. Attempted `python -m pytest`; Python is unavailable in this terminal, so tests and audible playback remain unverified.
**Decisions:** User explicitly requested Piper for this isolated test despite the spec listing pyttsx3. No shared spec, alert format or dashboard changes. Use Windows standard-library playback with the selected system output; voice files are not committed.
**Teammates need to know:** Python 3.11, Piper and a voice model still need setup, followed by laptop playback confirmation. This is a temporary manual test, not the integrated audio manager. Setup guidance proceeds one PowerShell command at a time.

### 2026-11-14 03:20, Person 4 (audio, fakes/audio), Claude Code
**Changed:**

- New `audio/` module (SPEC.md 4.8 and the late-name rule in 4.5). `register(bus)` subscribes to `HazardEvent`, `TouchEvent`, `NameResult` and `SpeakRequest`, hazard first, and publishes nothing.
  - **Alarm:** a `HazardEvent` starts the beeps on the handler's own thread, cuts off speech at the next word, empties the queue, then speaks "Stop. Stairs." (and the other phrases from 4.8) after the 0.61 s of beeps.
  - **Touch:** kind `touch` speaks `name`, or the class label if the name is empty. `release` is silent. Retouch speaks again.
  - **Late name:** if the label was spoken and a `NameResult` arrives within `LATE_NAME_WINDOW_SECONDS` while the object is still touched, the name is spoken once. If the label has not been spoken yet, the name replaces it.
  - **Queue:** one waiting item; a newer item replaces it unless the waiting one has a higher priority. `SpeakRequest` answers never replace a waiting touch name.
  - Handlers only update state under a lock and return. Speech runs on one `audio-speech` thread that owns the `pyttsx3` engine. If `pyttsx3` or `pygame` cannot start, audio logs once and keeps running (speech is logged, hazards are spoken without beeps).
  - A `NameResult` that reaches audio before its `TouchEvent` is used for that touch. With Person 1's bus each message type is delivered on its own thread, so this ordering can happen.
- `audio/sounds/alarm.wav`: three 0.15 s 880 Hz beeps, 54 KB, made once by `python -m audio.make_alarm` and committed.
- `python -m audio`: runs the module alone on the real speaker with a scripted touch, late name, retouch, answer and hazard.
- `fakes/audio`: `register(bus)` for `--fake audio`. Same rules, but prints what would be heard and takes about as long as speaking it.
- `tests/test_audio.py`: 19 smoke tests.
- `audio/requirements.txt`: `pyttsx3==2.99`, `pygame==2.6.1`. Move these to the root requirements file once it exists.

**Tested:**

- Windows 11, Python 3.11.18 venv made with uv. `tests/test_audio.py`: 19 passed. `ruff check` and `ruff format` clean on the new files.
- Full `pytest` on Python 3.14 (system Python): 147 passed, 1 skipped.
- Full `pytest` on the 3.11 venv: storage tests cannot load, because Windows Application Control blocks `psycopg-binary`'s DLL inside the venv ("An Application Control policy has blocked this file"). Everything else passed. Not an audio problem; see below.
- `python -m audio` on the laptop speakers: every phrase in order, the release silent, the late name spoken once. First phrase started 234 ms after its event (engine start-up), later ones 0 ms. "Stop. Stairs." started 625 ms after the hazard, so the 4 s answer was cut off within the 0.61 s beep. JBL not connected.
- After merging `main` with PR #9 in: `ruff check .` clean; full `pytest` on Python 3.14: 160 passed, 1 skipped. `python -m app --fake vision` starts and audio says "bottle" on each scripted touch (no `.env` here, so no Grok names; storage cannot import, as above). `--fake vision namer storage` speaks "Heinz ketchup". With `--fake ... hazard audio`, the beeps cut off speech and the right phrase follows about 0.6 s later.

**Decisions:**

- Touch speech does not cut off a spoken answer that is already playing; only an alarm cuts anything off (4.8 says only that). A touch made during the alarm beeps is dropped.
- The late-name window is measured from when audio receives the `TouchEvent`, on audio's own clock.

**Teammates need to know:**

- **Person 1:** `audio/` and `fakes/audio/` use `app/`'s `register(bus)` shape. `app/` needed no change.
- **Everyone on Windows:** if `psycopg` fails with "Application Control policy has blocked this file" in a new venv, that is Windows blocking the DLL, not a code bug. The system Python install loaded it fine.
- **Person 4 next:** dashboard. Close PR #4 once this branch merges.

### 2026-11-14, PR #9 review fixes on `p1-vision` (app, vision, hazard), Claude Code
Made by the PR #9 reviewer's agent on Person 1's branch, at that reviewer's explicit request. Person 1, please check it.

**Changed:**

- Merged `origin/main` into `p1-vision`. The only conflict was this file, and both sets of entries are kept. Person 1's commit was not rebased or rewritten.
- `hazard/hazard.py`: `parse_hazard_response` strips one surrounding Markdown code fence (```` ```json ````) before `json.loads`, so a fenced Grok reply no longer turns tier B off for the whole run. The worker's two `except` branches are now one `except Exception` with a `noqa: BLE001` reason, and `_reply_text` raises `TypeError` for a non-dict reply (ruff `TRY004`).
- `vision/vision.py`: `LatestCamera` no longer stops for good on the first failed `read()`. It retries every 0.05 s, and after 20 failures in a row it releases and reopens the device, waiting 1 s between reopen attempts. It logs once per outage and once on recovery. These timings are module constants, not `SPEC.md` section 9 thresholds.
- `app/__main__.py`: the main thread waits with `while not stop.wait(0.5)` instead of an untimed `Event().wait()`, so Ctrl+C reaches it on Windows and `Store.stop()` runs.
- `ruff check --fix` sorted the imports in `app/__main__.py`, `vision/vision.py` and `tests/test_hazard_p1.py`, and fixed `PLR1730` in `fakes/vision/fake_vision.py`.
- New tests: fenced and bare JSON parse the same way, the camera survives a few failed reads, and it reopens after repeated failures.
- Removed the Person 1 `vision/` line under "Needs attention", and the sentence calling the storage timing test flaky, since #8 made it deterministic.

**Tested (Windows 11, Python 3.11.18 venv):**

- `ruff check .`: clean.
- `pytest --ignore=tests/test_register.py --ignore=tests/test_storage.py`: 113 passed, 2 failed. The failures are the two `storage` cases in `test_p3_shared_classes.py`. They, and the two ignored files, fail at import because Windows Application Control blocks psycopg's `pq` DLL on this laptop. They fail the same way with these changes stashed.
- `python -m app --fake vision`: starts, and scene receives frames. Storage cannot import here for the same psycopg reason, and the app carries on. No `.env` on this machine, so Grok was off.
- Ctrl+C check: a script that calls `_thread.interrupt_main()` after 2 s. With the fix, `main` returned 0 after 2.5 s and logged "Shutting down". Without it, the process hung until it was killed.
- Not tested: a real Logitech camera unplug and replug, or a live Grok reply in a code fence.

**Teammates need to know:**

- Person 1: Person 1's entry below lists the tool as "ChatGPT GPT-6", which is not one of the coding agents in the stack table. If that is correct, it should be explained in the SpaceXSI write-up. If not, please correct it.
- Anyone on this laptop: psycopg's binary is blocked by an Application Control policy, so storage cannot run here until that is allowed or another laptop is used.

### 2026-11-14, Person 3 Richard Lan (namer, storage, fakes), Claude Code: demo validation
**Changed:**

- **Namer priority (C):** the queue now sorts by crop pixel area, largest first, not by JPEG byte count. A flat crop compresses far smaller than a busy one of the same size. `jpeg_area` reads width and height from the JPEG frame header. It decodes nothing and runs on the namer's worker thread, never in `on_name_request`. A crop with an unreadable header goes last. `NameRequest` is unchanged.
- **Namer timing (B):** each Grok call records its queue wait (request received to call started) and its call time separately, in `Namer.timings` (last 200) and one INFO log line per call.
- **Storage outage test (D):** `test_unreachable_db_never_blocks_and_warns_once` now uses a mocked connect failure, so it no longer races a 3 s wait against the 3 s connect timeout. It still checks that each handler call takes under 5 ms, that there is one warning, and one connect attempt for 101 items. Two new tests use a real connect to a local socket that accepts and never answers:
  - `test_real_connect_timeout_is_bounded`: gives up in about 3 s.
  - `test_hung_db_does_not_block_handlers`: handlers still return at once while the worker is stuck connecting. Waits are `CONNECT_TIMEOUT_SECONDS + 5`. Its handler limit is 50 ms, not 5 ms, because a handler can wait one GIL switch interval (5 ms) while the worker runs. At 5 ms it failed 3 of 3 full-suite runs at 8.6 ms.
- New `fakes/namer/demo_check.py`: live naming checklist with real scene, real namer and live Grok on a test bus at 5 fps.
- New `fakes/storage/bus_check.py`: live Tiger Data check through the real `storage.register(bus)`, including a simulated outage and recovery. It deletes only its own session's rows.
- New `fakes/namer/crop_recorder.py`: `register(bus)` saves every `NameRequest` crop and a manifest, writing on its own thread.
- `fakes/namer/eval_batch.py` takes `--manifest` and `--results`, and uses a `class_label` column when present, so camera crops can be scored without overwriting the web-photo results.

**What was available (2026-11-14):**

- Python 3.11.18 venv with Person 3's and Person 2's dependencies only (see "Needs attention").
- `GROK_API_KEY`, `GROK_MODEL` (`grok-4.20-0309-non-reasoning`) and `TIGER_DATABASE_URL` (Tiger Cloud) are all set in `.env`. I assumed that database is the demo one.
- Only the laptop's built-in FaceTime camera; no Logitech webcam. Audio goes to the laptop speakers; the JBL is not connected.
- No `app/` or bus. Person 1's `p1-vision` and Person 4's `voice-dashboard` are standalone and off the agreed stack (see "Needs attention").
- No camera-pipeline crops. `scratch/eval` holds 50 Open Food Facts and Wikimedia photos, 10 synthetic hard variants, and one phone photo (`IMG_8121.jpg`, a Sour Strips bag held in a hand).

**Tested:**

- `pytest`: 112 passed, 1 skipped (the live DB test). The suite passed 5 runs in a row after the storage fix. `ruff check .` is clean.
- `python -m storage --selftest`: passed ("Selftest ketchup b095143d, 4 minutes ago, next to mug and cereal box."). It leaves its one row behind, as before.
- `python -m fakes.storage.bus_check` against Tiger Data: 8 of 8 passed.
  - 5 bus events written in 0.40 s, including the first connect. Slowest `publish` 0.94 ms.
  - Rows came back as touch, release, touch, plus the hazard row.
  - The last-seen answer over the bus took 0.03 s: "Validation ketchup 2f8e8ce3, just now, next to mug and cereal box." An unknown object got "I have not seen that."
  - Simulated outage: 20 events dropped, one warning, handlers took 0.06 ms in total. Writes resumed 10 s later, after a real reconnect.
  - Cleanup deleted 6 rows, its own only. The table totals went back to 2 touch and 0 hazard rows.
- `python -m fakes.namer.demo_check`, run twice. The input was a composite 640 x 360 frame, not the demo camera: `IMG_8121.jpg` plus four catalog photos at about 85 px wide. Both runs passed every check:

  | Object | Expected | Returned (both runs) | Correct | Queued (s) | Grok call (s) | Request to result (s) |
  |---|---|---|---|---|---|---|
  | Sour Strips, held in a hand | Sour Strips | Sour Strips Rainbow Candy | yes | 0.00 | 0.68, 0.64 | 0.81, 0.81 |
  | Coca-Cola, small | Coca-Cola | Coca-Cola bottle | yes | 1.00 | 0.53, 0.42 | 1.62, 1.43 |
  | Heinz ketchup, small | Heinz | Heinz Tomato Ketchup | yes | 2.00 | 0.50, 0.52 | 2.64, 2.64 |
  | Starbucks mug, invalid key | Starbucks | (empty, ok=False) | failure path | 0.00 then 0.80 | 0.10 then 0.10, HTTP 400 | 1.22, 1.21 |
  | Pringles, after recovery | Pringles | Pringles Original Chips | yes | 0.00 | 0.59, 0.61 | 0.61, 0.81 |

  - Touch, release and retouch all publish. The retouch carries the name.
  - Delayed naming: the first touch had `name=""`, and its `NameResult` arrived 0.41 s and 0.40 s later, inside the 1.5 s late-name window.
  - Grok failure: exactly 2 calls (scene's one retry), and the touch fell back to the class label. Recovery named the next object.
  - The slowest frame took 2.3 ms and 11.9 ms; frame handling never waited on Grok.
- Earlier web-photo eval, replayed from `scratch/eval/results.csv` (no new calls): brand correct 54 of 60. Call time p50 435 ms, p95 750 ms, max 2.1 s. No call took over 4 s.

**Decisions:**

- Grok failure was simulated with an invalid key, set only inside the check's process. xAI answers that with HTTP 400, not 401. The database outage was simulated by making connect fail inside the check's process. Neither touched `.env`, billing or the real database settings.
- Queue wait, not the API, is now the main naming delay when several objects appear together. The API takes about 0.4 to 0.7 s. `NAME_MIN_INTERVAL_SECONDS` = 1.0 makes the k-th object wait about k - 1 s, so the third object took 2.6 s in total. I did not change the threshold.

**Demo paths:**

| Path | Status | Why |
|---|---|---|
| Naming, Person 3 part (crop to `NameResult`) | Ready | Live Grok through scene's real crop path: 4 of 4 correct, twice |
| Naming accuracy on demo camera crops (A) | Blocked | No Logitech camera and no vision pipeline, so no real crops. Needs the inputs below |
| Touch to speech, end to end | Blocked | No `app/` bus, vision off the agreed stack, audio not wired and Windows-only |
| Touch-to-speech latency (B) | Unverified | Grok call time and queue wait are measured. Speech is not measured |
| Touch, release, retouch events | Ready for Person 3, unverified on the camera | Verified with the real scene and scripted hands, not MediaPipe |
| Delayed naming | Inputs ready, speech unverified | The late-name rule lives in Person 4's audio |
| Grok failure and recovery | Ready | Live: 2 calls at most, ok=False, then recovery |
| Tiger Data touch and hazard logging | Ready for Person 3, unverified in app | Live through `storage.register` on a test bus |
| Last-seen answer | Storage ready, speech unverified | `SpeakRequest` in 0.03 s. Needs audio, and someone to publish `LastSeenQuery` |
| Database failure and recovery | Ready | Outage simulated in-process; reconnect was real |
| Hazard alarm | Blocked | Person 1 hazard module and Person 4 alarm are not on a bus. Storage logs `HazardEvent` |
| Dashboard | Blocked | No dashboard code |

**Teammates need to know:**

- **Grok Bot evidence (SpaceXSI):** `.p3/grokbot.sh` runs Cursor's agent CLI headless with `grok-4.7-high-fast`, in read-only ask mode, on the Person 3 diff. It saves reports to `scratch/grokbot/`. There are three runs:
  - 2026-11-13 23:13: full report. It found the private message-class risk that led to the shared `contracts/`.
  - 2026-11-14 00:25: empty output.
  - 2026-11-14 00:26: full report.
  The script and reports are local and git-ignored. I did not run the bot this session.
- **Inputs needed for A:** once Person 1 has a bus, `fakes.namer.crop_recorder.register(bus)` saves the real crops. On the demo laptop with the Logitech camera, record the 5 to 10 demo objects in these cases:
  - each object alone,
  - a small label (the object far from the camera),
  - a hand partly covering it,
  - two or three objects in view together.
  Then fill in `expected_brand` and `expected_product` in `scratch/camera_crops/manifest.csv` and run `eval_batch --manifest scratch/camera_crops/manifest.csv --results scratch/camera_crops/results.csv`.
- **Person 4:** the inputs audio needs are checked: `TouchEvent.name` is empty before naming, and `NameResult` arrives about 0.4 s after an early touch. Please time touch-to-speech on your side, and check that the late name plays once within 1.5 s.
- **Everyone:** put the demo objects out at least 1 to 2 s per object before touching them, so they are named before the first touch.
- Work is on branch `p3-demo-validation`: `p3-namer-one-attempt`, plus `origin/main` and `origin/p3-grok-data`.

### 2026-11-14, Person 3 Richard Lan (namer), Claude Code
**Changed:**

- Removed the namer's internal automatic retry. Before this, scene retried once after a failed `NameResult` and the namer also retried every `NameRequest` once, so one object that kept failing cost 4 Grok calls. SPEC.md 4.5 allows one retry. Now each uncached `NameRequest` gets exactly one HTTP attempt, and the namer publishes its `NameResult` (`name=""`, `ok=False` on timeout or error).
- Dropped the now-unused `attempt` field on the namer's queued job, and the attempt number in the failure log line.
- Unchanged: the 4 s timeout, at most 2 in flight, at most 1 new call per second with the largest crop first, the success cache, coalescing a request for an object already in flight, nonblocking `on_name_request`, and one result per waiting request. Failures are still not cached, so scene's retry gets its own call.
- `tests/test_namer.py`: the two retry tests now assert one attempt. Added tests showing a failure is not cached (the next request tries again, then a success is cached) and that coalesced requests share one failed attempt.
- New `tests/test_namer_scene_retry.py` wires the real `SceneDatabase` to the real `Namer` with mocked HTTP. It checks: persistent failure makes 2 HTTP attempts and 2 `NameRequest`s, a failure followed by a success stores the name, a cached success makes no further call, and timeouts never slow `handle_frame` or `handle_name` (slowest call under 50 ms while each Grok call times out).

**Tested:**

- `pytest`: 81 passed, 1 skipped (the live DB test). `ruff check .` and `ruff format --check` are clean.
- Against the old `namer/namer.py`, the new integration test fails 3 of 4 (`assert 4 == 2` HTTP calls). That confirms it catches the double retry.
- `python -m fakes.namer.fake_namer` runs. `python -m app --fake vision` cannot run yet because `app/` does not exist.
- No live Grok calls were made.

**Decisions:**

- Scene owns the retry and the namer owns none. Scene already tracks `requests_sent` per object and has the fresh frame to crop, so the retry stays there and `scene/` is unchanged. No message or threshold changed.

**Teammates need to know:**

- **Person 2 (scene):** the one retry per object is now only yours. Keep `after_name_result` sending at most one more `NameRequest` after a failed `NameResult`. If scene ever stops retrying, a failed object gets no retry at all, because the namer will not add one. Do not send more than one retry: each `NameRequest` costs one Grok call.
- **Person 1 (app bus):** a failed `NameResult` makes scene publish a new `NameRequest` from inside its `NameResult` handler. If the bus delivers `NameResult` on the namer's worker thread, that `NameRequest` goes straight back into `namer.on_name_request`, which only enqueues and returns, so it is safe. Do not make the bus wait on that delivery. Worst case per object is 2 Grok calls, and both run off the frame path.
- Work is on branch `p3-namer-one-attempt`, cut from `p3-grok-data` at `ffe088d`, so it did not collide with another session working on `p3-grok-data`.

### 2026-11-14, Person 3 Richard Lan (namer, storage, fakes), Claude Code: shared-class checks
**Changed:** These are tests only; no production code changed. They guard the shim migration, which is described in the Person 3 entry titled "(namer, storage, fakes), Claude Code" further down, the one that deletes the four `_pending.py` shims. Revised after Person 2's review of PR #6.

- `tests/test_p3_shared_classes.py` has 28 checks:
  - None of the four `_pending` modules can be imported.
  - No Person 3 module (`namer/`, `storage/`, `fakes/namer/`, `fakes/storage/`) defines its own message class, `Box` or `Point`, or assigns a `config` threshold name at the top level. This scans the source, so a local `PROCESS_WIDTH = 640` fails even when the value matches `config`.
  - The message names in `namer`, `namer.namer`, `storage._deps`, `storage.writer` and both fakes are the `contracts` classes themselves, compared with `is`.
- `tests/test_namer.py`: new `test_publishes_the_contracts_name_result_class`. The real `Namer`, with Grok mocked, publishes `contracts.NameResult` itself.
- The routed bus tests were removed from this file. `tests/test_register.py` (PR #5) already checks them through `register(bus)`, with exact-type subscriptions and `contracts` classes on the publish side. That avoids keeping a second test bus.

**Tested:**

- `tests/test_p3_shared_classes.py`: 28 passed.
- Against `main` at `d78eb09`, which still has the shims: 15 failed. The failures are the shim-import checks and one source check per `_pending.py` copy.
- With a local `PROCESS_WIDTH = 640` added to `storage/_deps.py` in a scratch worktree, the `storage/_deps.py` source check fails.
- Full `pytest`: 112 passed, 1 skipped (the live DB test). With `.env` loaded: 113 passed.
- `ruff check .` is clean.
- `python -m app --fake vision` is not run, because `app/` does not exist yet.
- Follow-up before merge (Claude Code, on Windows): the source scan read files with the platform default encoding, so on Windows (cp1252) it failed on the curly quotes in `namer/namer.py`. It now reads with `encoding="utf-8"`. On Windows the file then gave 28 passed.

**Decisions:** Class identity and source checks live here, and bus wiring lives in `tests/test_register.py`, so each behaviour is tested once.

**Teammates need to know:** Person 1: `tests/test_register.py` assumes the bus API `bus.publish(msg)` and `bus.subscribe(MessageType, handler)`, which is still unconfirmed.

### 2026-11-14 02:10, Person 1 (app, vision, hazard, fakes), ChatGPT GPT-6
**Changed:**
- Added app Bus (independent per-handler workers, latest-only FrameResult delivery), CLI entry point with --fake and --only selection, .env loading before registration, orderly shutdown, and an app-only adapter for the current scene interface.
- Added scripted 640x360 BGR fake vision with persistent object IDs and touch/release dwell, and scripted hazard events for the five tier/type combinations.
- Replaced the Grounding DINO prototype with unmirrored OpenCV capture, latest-frame overwrite, YOLO nano/ByteTrack processing, MediaPipe hands, and FrameResult publication; no direct torch, transformers, or PIL imports.
- Added local vehicle growth detection, asynchronous xAI Responses API hazard checks, shared cooldown, error-once logging, and smoke tests under tests/test_*_p1.py.

**Tested:**
- Ten Person 1 smoke tests passed using synthetic models and mocked Grok response in a Python 3.13 sandbox; compileall passed.
- Full repository pytest, ruff check, Python 3.11 environment, Logitech Windows camera, real model inference, and end-to-end scene integration have NOT been verified in this environment. Merge gate remains open.

**Decisions:**
- All thresholds and messages import from config/ and contracts/ unchanged. Model assets are expected at vision/models/ and are not committed.
- No packages added or pinned; root requirements file does not yet exist, and changes to that root location are outside Person 1's authorized paths. Keep stack dependencies pinned by team agreement.

**Teammates need to know:**
- Person 2: scene/ currently has no register(bus); app provides a compatibility adapter until it does. Run python -m app --fake vision and verify Scene received FrameResult logs.
- On the Windows demo laptop, install the approved stack in Python 3.11, provision vision/models/yolo11n.pt and hand_landmarker.task, select CAMERA_INDEX in .env, and run full pytest and ruff check before merge.


### 2026-11-14, Person 3 Richard Lan (storage, fakes), Claude Code
**Changed:**

- `storage.register(bus)` now subscribes `TouchEvent`, `HazardEvent` and `LastSeenQuery` from `contracts` to the store's three handlers, and returns the `Store` so `app/` can call `stop()` on it. Answers are `contracts.SpeakRequest(priority="normal", source="storage")`, published with `bus.publish` from the worker thread.
- Added `register(bus)` to `fakes/storage/fake_store.py` and `fakes/namer/fake_namer.py`, with the same bus calls and message types as the real modules. Added a no-op `FakeStore.stop()` so shutdown works the same with the fake or the real store.
- New `tests/test_register.py` drives everything through a small test bus. It checks that all three storage handlers are subscribed, that touch and hazard events reach the database writer, and that a query produces one `SpeakRequest` published from the `storage-writer` thread. It also checks that publishing returns within 0.5 s while the database connection is stuck, that the URL is read once when `register` runs, and that `namer.register` and both fakes register correctly. Every `storage.db` call is replaced, so the tests need no credentials and make no network calls.

**Tested:**

- `pytest -q` with `TIGER_DATABASE_URL` and `GROK_API_KEY` unset: 83 passed, 1 skipped (the live DB test). `tests/test_register.py` passed 8 of 8 on three runs in a row.
- `ruff check .`: all checks passed.
- `python -m fakes.storage.fake_store` and `python -m fakes.namer.fake_namer` run as before.
- Not run: `python -m app --fake vision`, because `app/` does not exist yet.

**Decisions:**

- `register` reads `TIGER_DATABASE_URL` when it runs and does not load `.env` itself. Loading the environment is `app/`'s job, so it happens once and before any module starts.
- Worked on branch `p3-storage-register` in its own worktree, because another agent CLI is working in the main checkout on `p3-grok-data`.

**Teammates need to know:**

- Person 1: the six concrete requests for `app/` are under "Needs attention".
- Still open for Person 3: the flaky Windows storage timing test.

### 2026-11-14, Person 3 Richard Lan (namer, storage, fakes), Claude Code
**Changed:**

- Deleted the four `_pending.py` shims. Every Person 3 file now imports messages from `contracts/` and thresholds from `config/`.
- `namer/` reads its thresholds as `config.NAME_...` at call time, so tests can still monkeypatch them.
- Merged the root `.gitignore` with the one Person 2 put on `main`, keeping all of its rules. It adds `.env.*` (except `.env.example`), more weight formats (`*.pth`, `*.task` and others), `scratch/`, and OS and editor files. Main's `*.mp4`, `*.avi` and `*.mov` ignores stay, with an exception for `fakes/vision/`, because the vision fake plays a short recorded clip (AGENTS.md rules 3 and 10). `*.wav` is not ignored, so the alarm sound can be committed.

**Tested:**

- `pytest tests/test_namer.py tests/test_storage.py tests/test_contracts.py`: 28 passed, 1 skipped (the live DB test).
- With `.env` loaded, `tests/test_storage.py` gave 17 passed, including the live Tiger Data round trip.
- `python -m fakes.namer.fake_namer` and `python -m fakes.storage.fake_store` both run and publish as before.
- `ruff check` is clean on all Person 3 paths.
- `git check-ignore` confirms `.env`, the venv, weights, `scratch/` and root-level video are ignored, while `.env.example`, `.wav` files and video under `fakes/vision/` are not.
- After merging `main` into this branch, full `pytest` gave 75 passed and 1 skipped, and 76 passed with `.env` loaded. `ruff check .` is clean for the whole repo, and `python -m fakes.scene` runs.

**Decisions:**

- Storage still unpacks `Box` as a tuple, which matches `contracts/` on `main` now. If the team switches `Box` back to a dataclass, `storage/db.py` `box_centre_fraction` needs `box.x1` and so on.
- `.gitignore` is a shared root file. The merge removes none of Person 2's rules, except that a short clip in `fakes/vision/` is now allowed.

**Teammates need to know:**

- The shim item under "Needs attention" is fixed: namer and storage now subscribe to the `contracts` classes that scene publishes.
- Still open for Person 3: the flaky Windows storage timing test.

### 2026-11-14, Person 2 (repo housekeeping), Claude Code
**Changed:** Moved `hazardeventsample.py` from the repo root to a new `samples/` folder. It now imports `HazardEvent` from `contracts` and binds the example to `SAMPLE`, so `ruff check .` passes. Added a root `.gitignore` (`.env`, caches, model weights, video files) and `.env.example` with the four variables from SPEC.md section 6, both required by AGENTS.md rules 7, 9 and 10. Merged `p2-touch` into `main`, so `main` has the tuple `Box` fix for scene.

**Tested:** `python -m ruff check .`: clean across the whole repo. `python -m pytest`: 74 passed, 1 skipped, 1 failed. The failure is the flaky storage timing test under "Needs attention". `samples/hazardeventsample.py` runs and builds a valid `HazardEvent`. `python -m app --fake vision` cannot run yet, because `app/` does not exist.

**Decisions:** `samples/` holds hand-written example messages for teammates. It is not a module and nothing imports it. Person 2 created it at their human's request.

**Teammates need to know:** Person 3, see the shim item under "Needs attention". It is the main thing between `main` and a working touch-to-name demo. Everyone: `git pull`, then delete your local `__pycache__` folders if git shows them.

### 2026-11-14, Person 2 (scene), Claude Code
**Changed:** Moved `scene/`, `fakes/scene/` and the scene tests to the tuple `Box` from PR #2. After that merge, `main` failed `pytest` at collection time, because `Box(1, 2, 3, 4)` raises `TypeError` when `Box` is a tuple alias. `scene/touch.py` and `scene/naming.py` now unpack `x1, y1, x2, y2 = box`. The fake and the tests build boxes as plain tuples. No behaviour changed.

**Tested:** `python -m pytest`: 74 passed, 1 skipped, 1 failed. The failure is the flaky storage timing test described under "Needs attention". It is not affected by this change. `python -m ruff check scene fakes tests contracts config`: clean. `python -m fakes.scene`: same script as before, with tuple boxes. `python -m app --fake vision` does not run yet, because `app/` does not exist.

**Decisions:** Reviewed the merged contract against SPEC.md section 5. Every field, type and fixed value matches. Scene still stores `state` and `kind` as `str`. The values it uses are exactly the `Literal` sets.

**Teammates need to know:** Anyone who builds boxes must use tuples like `(x1, y1, x2, y2)` now, not `Box(...)`. `contracts.Box` is only a type hint. Person 4: `TouchEvent.box` and `SceneObject.box` arrive as tuples.

### 2026-11-14, Person 2 (scene), Claude Code
**Changed:** Two fixes in `scene/`, after a review of Cursor's work.

- Held-merge only lets a detection still in state `new` inherit a held object, as SPEC 4.6 says ("any new detection"). Before, a stable object next to the hand (a mug beside the ketchup) took over the held object's name and the real object dropped back to `idle`.
- A `touching` or `held` object that stays lost past `LOST_KEEP_SECONDS` now publishes a `release` `TouchEvent` before it is removed. Before, it disappeared with its touch still open. New public helper `scene.touch.release_on_removal`.

**Tested:** `python -m pytest`: 47 passed (5 new: merge ignores stable neighbours, `release_on_removal` unit test, release on removal, no event for an untouched removal, and a scene-level ketchup and mug test). `python -m ruff check .`: clean. `python -m fakes.scene`: unchanged output. `python -m app` not run, `app/` does not exist yet.

**Decisions:** Existing merge tests now mark the inheriting detection as `new`, which matches the spec.

**Teammates need to know:**

- Person 4 and Person 3: every `touch` now gets a matching `release` for the same `object_id`, except after a held-merge, where the release comes from the new id.
- Open: while a hand covers a touched object, its snapshot state is `lost`, not `touching`, so the dashboard will draw it dashed during most touches. Not changed yet, to be agreed with Person 4.
- The repo has no `.gitignore` and no requirements file. `scene/` needs `opencv-python` and tests need `numpy`.

### 2026-11-14 00:45, Person 2 (scene), Cursor
**Changed:** Scene database tracks objects through `new`, `idle`, and `lost`, and publishes a `SceneSnapshot` every frame. Touch dwell, release, held, and held-merge are in `scene/touch.py`. Name crops and one retry are in `scene/naming.py`. `SceneDatabase` wires both and publishes `NameRequest` and `TouchEvent`. `fakes/scene` plays a script of those three messages. Added `contracts/` and `config/` from SPEC sections 5 and 9, because those packages were not in the repo yet.

**Tested:** `python -m pytest` — 42 passed. `python -m ruff check` on `scene`, `fakes`, `tests`, `contracts`, and `config` — clean. `python -m fakes.scene` prints the script. Did not run `python -m app --only scene` because `app/` does not exist yet.

**Decisions:**

- Bus topics are the message class names: `SceneSnapshot`, `NameRequest`, `TouchEvent`.
- A touch is stored as a phase (`open`, `touching`, `held`) so a covered object can stay in contact while its public state is `lost`.
- The namer still owns the in-flight cap, the one-request-per-second limit, and the timeout. Scene sends one request when an object first becomes idle, and one retry if the `NameResult` fails.

**Teammates need to know:**

- Confirm `contracts/` and `config/`. The values match the spec.
- Person 3 can build the namer against `NameRequest` from `python -m fakes.scene`. Apply the reply with `SceneDatabase.handle_name`.
- Person 4 can build audio and the dashboard against `TouchEvent` and `SceneSnapshot` from the same fake.
- This laptop has Python 3.14, not 3.11.

### 2026-11-14 00:26, Person 3 Richard Lan (namer, storage), Grok Bot (Cursor agent CLI, headless, Grok 4.7)
**Changed:** First Grok Bot automation run. `.p3/grokbot.sh` sends the `p3-grok-data` diff to Grok 4.7 through Cursor's agent CLI, in read-only ask mode, and saves a contract check, a risk note and a DEVLOG draft. The script lives on Person 3's machine and is not in the repo.

**Tested:** The run finished and saved a 207-word report.

**Decisions:** The bot found no `SPEC.md` section 5 field mismatches. It flagged the section 9 values copied into the temporary `_pending.py` shims, which is expected until `config/` lands.

**Teammates need to know:** The bot raised a real risk. Each module currently has its own copy of the message classes. If `scene/` publishes its own `NameRequest` class, the namer will not match it, and touches will speak the COCO class instead of the brand. The fix is for everyone to import from one shared `contracts/`. Please land `contracts/` and `config/` soon.

### 2026-11-14 00:10, Person 3 Richard Lan (storage), Claude Code
**Changed:** Connected to the live Tiger Data service (`db-51800`, trial). No code changes.

**Tested:** `python -m storage --selftest` created both tables and printed "Selftest ketchup ..., 4 minutes ago, next to mug and cereal box." `timescaledb_information.hypertables` lists `hazard_events` and `touch_events`. With `.env` loaded, `pytest tests/test_storage.py` gave 17 passed, including the live round trip.

**Decisions:** none.

**Teammates need to know:** The Tiger Data log and last-seen query are working against the real database. Each run of the selftest leaves one `selftest-*` session row in `touch_events`. Get the connection string from Person 3; it is never committed.

### 2026-11-13 23:50, Person 3 Richard Lan (namer), Claude Code
**Changed:** First live Grok calls. The namer now sends no `reasoning` field, and `GROK_MODEL` is set to `grok-4.20-0309-non-reasoning`.

**Tested:** A real photo of a Sour Strips bag came back as "Sour Strips Rainbow Candy" through `python -m namer` and `fakes.namer.eval_names`. The Grok call took 0.5 to 0.8 s. `pytest tests`: 22 passed, 1 skipped.

**Decisions:** On a 320 px crop, the reasoning models were too slow for the 4 s `NAME_TIMEOUT_SECONDS`. `grok-4.7` took 3.8 to 5.0 s, even with low reasoning effort, and `grok-4.3` took up to 12 s. Two of them also guessed the wrong brand ("Airheads", "Toxic Waste"). `grok-4.20-0309-non-reasoning` was correct every time in about 0.6 s. Non-reasoning models reject the `reasoning` parameter with HTTP 400.

**Teammates need to know:** Person 1: hazard tier B has a 3 s timeout, so use `grok-4.20-0309-non-reasoning` there too. Do not send a `reasoning` field with it. The SPEC 12 open question about the Grok model name is answered: `grok-4.20-0309-non-reasoning`.

### 2026-11-13 23:10, Person 3 Richard Lan (namer, storage, fakes), Claude Code (lead session plus 3 parallel subagents)
**Changed:** First build of everything Person 3 owns. `namer/` names objects through Grok vision. `storage/` logs touch and hazard events to Tiger Data and answers last-seen queries. `fakes/namer/` and `fakes/storage/` let teammates run without Grok or Tiger Data. Tests are in `tests/test_namer.py` and `tests/test_storage.py`.

**Tested:** `python -m pytest tests -q` gave 22 passed and 1 skipped (the live Tiger Data round trip, which needs `TIGER_DATABASE_URL`). `ruff check` is clean on all Person 3 paths. Both fake demos run. No live Grok or Tiger Data call has been made yet because there is no `.env` on this machine.

**Decisions:**

- **Temporary shim.** `contracts/` and `config/` do not exist yet, so each Person 3 folder has an identical `_pending.py` that copies `SPEC.md` sections 5 and 9 word for word. Delete all four copies once the real folders land. Storage imports it in one place (`storage/_deps.py`).
- **Grok endpoint.** The namer calls `POST https://api.x.ai/v1/responses` with an `input_image` part and `store: false`, because the current docs.x.ai image guide uses that endpoint. Reading the reply is only tested against mocks so far.
- **Namer details.** `GROK_MODEL` has no default. Duplicate requests for an object already being named share one call. Failed names are not cached, so a later request retries.
- **Storage details.** The 3 s connect timeout, queue size of 1000 and 10 s reconnect interval are constants in `storage/`, not `SPEC.md` section 9 thresholds. Last-seen uses `ILIKE` with backslash escaping. A `LastSeenQuery` that arrives while the queue is full is dropped.

**Teammates need to know:**

- **Person 1:** `namer.register(bus)` and `storage.register(bus)` expect `bus.publish(msg)` and `bus.subscribe(MessageType, handler)`. Tell Person 3 if the bus API differs. `storage.register` returns the Store; call `.stop()` on shutdown.
- **Person 2 and Person 4:** `fakes.namer.fake_namer.FakeNamer` answers in 300 to 900 ms, and every 10th answer fails. `fakes.storage.fake_store.FakeStore` answers last-seen queries in the spec's sentence format.
- **All:** decide whether the three storage constants above belong in `config/`.

### 2026-11-13 22:05, planning session, Claude
**Changed:** Added the stack to `SPEC.md`, `AGENTS.md`, `CLAUDE.md`, this file, the project PDF and the whiteboard.

**Tested:** Nothing to test.

**Decisions:**

- **Stack fixed as listed above.** The models, Grok, Tiger Data, the Logitech camera and the JBL were already chosen. The supporting pieces were picked for speed of setup: `pyttsx3` because it speaks offline on Windows, macOS and Linux; `pygame` mixer because it plays the alarm file immediately and independently of the speech engine; `psycopg` 3 because Tiger Data is Postgres; `httpx` because the Grok calls need timeouts; plain HTML because the dashboard is one page.
- **No front-end framework, message broker, ORM or containers.** Each would cost setup time and add nothing to the demo.

**Teammates need to know:** If any item will not install or run on the demo laptop, say so tonight so the team can agree a replacement before midnight.

### 2026-11-13 21:10, planning session, Claude
**Changed:** Wrote `SPEC.md`, `AGENTS.md`, `CLAUDE.md`, this file, and the project PDF. No code exists yet.

**Tested:** Nothing to test.

**Decisions:**

- **Trigger is touch, not sight.** The speaker announces an object only when a fingertip lands on it. Reason: announcing everything in view makes the speaker talk constantly, and touch shows intent. Letting go and touching again announces again.
- **Pretrained models only.** YOLO with COCO weights for objects, MediaPipe Hands for fingertips. Reason: 36 hours is not enough to train anything useful.
- **Grok does the brand-level naming.** The detector only knows "bottle". Grok vision reads the label and returns "Heinz ketchup".
- **Objects are named before they are touched.** Each new object is sent to Grok once it has been stable for 1 second, and the name is cached. Reason: speech on touch is then instant, with no wait on the network.
- **The scene database keeps objects for 2 seconds after they vanish.** Reason: a hand covering an object makes the detector lose it at exactly the moment the touch happens.
- **Hazard alarm has two tiers.** Fast local check for vehicles growing in frame, plus a Grok check of the whole frame every 1.5 seconds for stairs, drops and obstacles. A single positive is enough to alarm. Reason: a false alarm is cheap, a miss is not.
- **Alarm outranks speech.** It cuts off whatever is playing.
- **Tiger Data, not MongoDB.** Touches are a stream of timestamped events, which is time-series data. It also powers the "where did I last touch X" query. Using both databases would look bolted on.
- **One process, message bus between modules.** Reason: four people can build in parallel against fakes without waiting on each other.
- **Camera is a USB Logitech webcam wired to a laptop in a backpack.** No Wi-Fi link between camera and backend to go wrong.
- **Dashboard draws overlays on the laptop and streams MJPEG.** Reason: avoids syncing boxes to video in the browser.
- **Roles:** Person 1 vision and hazard, Person 2 touch logic, Person 3 Grok and data, Person 4 audio and dashboard. An earlier split was uneven: vision was light, and touch plus Tiger Data was too much for one person.
- **Prizes targeted:** Best Accessibility Hack, the SpaceXSI raffle, Best Use of Tiger Data.

**Teammates need to know:**

- Read `SPEC.md` section 5 tonight and raise objections before midnight. After that the messages are frozen.
- Put your name next to your person number in the table below.
- The SpaceXSI prize is earned by building with Cursor and a Grok Bot automation, going by the same prize at other MLH events. Using Grok inside the product may not count by itself. Person 3 confirms at the Saturday 11:45 am workshop.
- Open questions are listed in `SPEC.md` section 12.

## Team

| Person | Role | Name |
|---|---|---|
| 1 | Vision and hazard | |
| 2 | Touch logic | An |
| 3 | Grok and data | Richard Lan |
| 4 | Audio and dashboard | |

## Agent usage summary

Fill this in as you go. It becomes the SpaceXSI section of the Devpost write-up.

| Tool | What we used it for |
|---|---|
| Cursor | Scene database, touch state machine, and name crops. Touch and naming were written at the same time, then wired into `SceneDatabase`. |
| Grok Bot | Person 3: `.p3/grokbot.sh` runs Cursor's agent CLI headless with `grok-4.7-high-fast`, read-only, on the Person 3 diff, and saves a contract check, a risk note and a DEVLOG draft. Its 2026-11-13 23:13 run caught the private message-class risk that led to the shared `contracts/`. Reports from 23:13 and 00:26 are in `scratch/grokbot/`, which is local and git-ignored. |
| Claude Code | Person 3: built `namer/`, `storage/` and their fakes, the live Grok and Tiger Data checks, and the shared-class tests. Person 4: audio manager and dashboard. Person 2: reviewed Cursor's scene module and fixed the held-merge and release-on-removal bugs, then added the dashboard camera feed and Objects panel, the YOLO small swap, the speech fix and the narrower Grok prompts. Also reviewed PR #9 and kept these docs current. |
| Other | Person 1's first `app/`, `vision/` and `hazard/` entry lists ChatGPT GPT-6. To be confirmed by Person 1. |

### 2026-11-14, audio environment setup, Codex
**Changed:** Created an isolated, git-ignored Python 3.11 audio environment at `scratch/audio311` using the already-installed Python 3.11. Installed the existing pinned `audio/requirements.txt` plus pytest and numpy for audio tests. No runtime source or dependency pins changed. Laptop system sound output is the current test target; user dropped Google Home Mini.

**Tested:** `scratch/audio311/bin/python -m pytest tests/test_audio.py tests/test_audio_pyttsx3.py tests/test_speak_test.py -q`: 25 passed. Ran `scratch/audio311/bin/python -m audio` on real system output: touch, late name, retouch, spoken answer, hazard beeps/phrase and post-alarm touch. Hazard phrase logged 614 ms after event. First phrase took 2138 ms during cold speech startup; subsequent phrases logged 0 ms queue latency. Audible confirmation remains with the user. Full non-audio suite not run in this audio-only environment.

**Teammates need to know:** Python 3.14 failed to build pygame 2.6.1; Python 3.11 installs its prebuilt wheel successfully. Repeat the audio demo with `scratch/audio311/bin/python -m audio` from the repository root. The existing `.venv` is unchanged by this session.

### 2026-11-14, live camera/audio launch, Codex
**Changed:** Extended local ignored `scratch/audio311` environment with existing app/vision/dashboard/storage dependencies, downloaded the existing vision code's YOLO11s and MediaPipe hand assets to ignored `vision/models/`, and requested macOS camera access on the main thread. No source, contracts or thresholds changed.

**Tested:** Started real `scratch/audio311/bin/python -m app`. All seven modules registered; real camera FrameResult messages reached scene and the dashboard started on port 8000. Initial background-thread camera permission attempt failed; explicit main-thread AVFoundation request returned granted and restart captured frames. ByteTrack installed its `lap` dependency during initial warmup. No GROK_API_KEY is configured, so brand naming and Grok hazard checks are unavailable; ordinary class labels remain usable. User still needs to perform a real touch and confirm speech. Live process left running for that interaction.

### 2026-11-14, Person 4 (dashboard voice input), Codex
**Changed:** User confirmed Person 4 ownership and requested both history and camera questions. Added a browser microphone button with one-utterance recognition, editable transcript, explicit Ask submission, permission/network/unsupported-browser feedback, and typed fallback. Browser speech service disclosure appears beside the control. Added `/api/question`: existing `LastSeenQuery` routes history requests to storage; existing `SpeakRequest` speaks scene summaries and touch answers. Current `SceneSnapshot` objects support “What do you see?” and “What am I touching?” without another vision model call. Dashboard shows storage/dashboard spoken answers. No shared contracts, thresholds, dependencies, or other owners' runtime modules changed.

**Tested:** Full Python 3.11 suite: 188 passed, 1 skipped (live DB), one existing FastAPI/httpx deprecation warning. Ruff clean on dashboard and changed tests. New tests cover current/stale scene summaries, one speech publication, history routing and displayed storage answers, absent database, invalid input, and standalone dashboard behavior. Real running app POST `/api/question` with “What do you see?” returned “I can detect tv.” Browser UI verification could not complete: no connected browser tab, native Chrome selection timed out. Live microphone transcription remains to be confirmed by the user; browser API presence alone does not guarantee the recognition service works. JavaScript CLI syntax check unavailable because node is not on PATH.

**Teammates need to know:** App restarted on port 8000 for testing. Open dashboard in a browser supporting SpeechRecognition (Chrome/Safari), click Start microphone, speak, review transcript, press Ask. Browser recognition may send audio to its speech service and require internet. This supports bounded object/touch questions, not arbitrary image reasoning; open-ended camera QA still needs agreed vision request/answer contracts and owner integration. History depends on TIGER_DATABASE_URL; the route explains when it is absent. Recognition is off after each utterance so spoken answers do not automatically feed back as questions.

### 2026-11-14, Person 4 (automatic spoken questions), Codex
**Changed:** Per user correction, final recognized speech submits immediately through `/api/question`; no transcript review or Ask click is needed for voice. Typed Ask remains available. Interim results are ignored and in-flight submission is guarded. Added “What is this item?”, “What's this?” and related aliases to the current touched/held-object answer path; other visible objects are excluded. Listening still starts with the microphone button and ends after one utterance.

**Tested:** Full suite: 189 passed, 1 skipped, existing FastAPI/httpx warning. Ruff clean. Node REPL parsed the complete dashboard script and executed the voice handlers with mock recognition/HTTP: final speech submitted exactly once without user confirmation, interim speech did not submit. Regression test verifies this-item aliases speak the touched item rather than a neighbouring idle object. Restarted live app for user audio testing.

### 2026-11-14, Person 4 (remove question panel), Codex
**Changed:** Removed the question form, input field, Ask button, instructional panel and review flow at the user's request. Moved the sole Start/Stop microphone toggle and compact status to the header. Added a ten-item Voice input transcript list styled alongside Objects, plus the latest answer. Recognition attempts startup automatically, processes final transcripts immediately, and restarts between utterances. Permission/service failures stop retrying with concise status; stop/page exit cancels restart timers. Browser speech-service disclosure is retained on the microphone tooltip.

**Tested:** Full suite: 189 passed, 1 skipped, existing FastAPI/httpx warning. Node VM checks parsed the full page script and exercised automatic startup, direct submission, transcript rendering, playback pause, listening restart, manual stop and denied-permission feedback. Verified old question-panel/form strings are absent. Live browser mic flow remains user-verified; HTML is read on each request so refreshing the running dashboard loads the change.

**Limit:** The existing bus has no audio-completion event. Listening resumes after a conservative text-length playback window (2 s plus 0.5 s per word), which reduces answer feedback but does not guarantee echo suppression. True speech-completion synchronization and touch/alarm playback suppression require an agreed cross-module activity contract. Browser policies may still require a click or mic permission approval before automatic recognition works.

### 2026-11-14, Person 4 (live microphone browser diagnosis), Codex
**Found:** Inspected the user's actual in-app browser dashboard: network speech-service error immediately disabled recognition. Opened the same localhost page in connected Google Chrome: recognition reached Listening, produced a real transcript and automatic answer, then returned to Listening. This verifies real browser transcription and restart rather than mocked API behavior. No microphone permission/settings change was needed. Did not record the user's transcript in this log.

**Changed:** Network-recognition error now explains that this browser's speech service may be unavailable and directs users to open localhost:8000 in Google Chrome, with connection advice for Chrome itself. Kept the working Chrome dashboard tab open. No source change can enable an unavailable embedded-browser speech service.

**Tested:** 14 dashboard/question tests passed; live Chrome speech and automatic question routing observed. Existing recognition still captures surrounding conversation while enabled; use Stop microphone to disable it.

### 2026-11-14, Person 4 (explicit microphone and question-only speech), Codex
**Changed:** User explicitly requested microphone off on load and object speech only when asked, overriding the earlier touch-announcement behavior for this session. Removed automatic recognition startup. Start enables listening across normal browser session endings; Stop cancels restarts. Transient network errors retry three times with visible status before an explained failure, while permission/device errors remain explicit. Default AudioManager ignores TouchEvent and NameResult for speech; requested SpeakRequest answers and HazardEvent alarms still play. Legacy touch-announcement behavior remains available only via explicit constructor opt-in for regression tests. Fake audio uses the same question-only default. Updated standalone demo documentation.

**Tested:** Full suite: 190 passed, 1 skipped; existing FastAPI/httpx warning. New audio regression drives touch, late name, release and retouch followed by a requested answer and hazard, confirming only answer and hazard speech. Real and fake registration tests check requested answers. Node VM checks confirm no startup recognition, manual start, restart after normal end, transient network retry and Stop canceling timers. Ruff clean. Live app restarted; real microphone/voice interaction still requires user verification in Chrome.

**Teammates need to know:** This is an explicit user-directed runtime behavior change from SPEC 4.5/4.8; shared spec/contracts/config remain unchanged. Keep storage touch logging and scene tracking as-is, since only unsolicited speech was disabled. Browser recognition may still fail if its service is unavailable; the actual error remains visible.

**Restart follow-up:** Restart exposed an existing dashboard port probe rejecting TCP TIME_WAIT sockets despite no listener on port 8000. Probe now uses SO_REUSEADDR to match Uvicorn; existing busy-port and start/stop tests still pass (9 dashboard tests). Restarted again with dashboard serving successfully.

### 2026-11-14, Person 2 (automatic touch plus independent voice questions), Codex
**Authorization:** User identified as Person 2 and confirmed all four teammates agreed to this cross-folder and shared-contract/spec update.

**Changed:** Restored automatic touch announcements as AudioManager's default, including existing late-name and retouch behavior. Voice questions are independent of touch: dashboard publishes the new shared SceneQuestion(ts, text); namer keeps the latest FrameResult and a separate bounded background worker calls Grok with the full image and question, replying through normal-priority SpeakRequest(source="namer"). Dashboard displays those replies. Current-view questions such as "Where are my keys?" no longer route to touch history. Explicit last-touch/last-seen wording retains storage lookup. Prompt asks for brief wearer-relative locations and an honest answer when items are not visible. Missing/stale frames, API errors, and timeouts produce spoken explanations. Alarm priority and frame/hazard workers remain independent. Updated SPEC sections 1, 3, 4, 5, 9, 10; shared contracts; config thresholds (4 s question timeout, 2 s maximum frame age); fake namer; standalone audio documentation; regression tests. No dependencies changed.

**Tested:** Python 3.11 full pytest: 212 passed, 1 skipped (live DB), existing Starlette/httpx deprecation warning. Ruff clean on touched Python files. Mock HTTP tests verify full-image payload, question text, returned speech, stale/missing camera handling, network failure, timeout, and frame updates during a call. Real bus integration with fake namer and recording audio verifies automatic touch speech followed by an independent keys answer. Standalone app start(only="namer", fakes=["vision"]) received frames and shut down successfully.

**Teammates need to know:** Restart the app to load new Python subscriptions, then enable the dashboard microphone for questions. Live microphone/camera/Grok/speaker interaction was not verified in this session; API credentials and a supported browser are still needed. Existing browser playback suppression uses a heuristic delay and cannot guarantee speaker echo exclusion, including automatic touch speech. Shared message and config additions require teammates to pull together. Prior user changes to DEVLOG and training_data were preserved.


### 2026-11-14, Person 2 (voice pipeline integration to main), Codex
**Changed:** User explicitly requested merging the voice changes to main. Applied only voice commit d2c9f40 onto latest origin/main (470b867) in a separate worktree, preserving newer Person 4 commits and excluding the unrelated Person 1 training-data ancestor. Local uncommitted training work remains untouched.
**Tested:** Full pytest on integrated main: 212 passed, 1 skipped, existing Starlette/httpx warning. Full app startup with fake vision received frames and shut down successfully; the existing dashboard already occupied port 8000. Grok credentials are absent locally. git diff --check clean.
**Teammates need to know:** Pull main and restart the app. Live camera testing still needs the MediaPipe hand asset and Grok questions need .env credentials.
