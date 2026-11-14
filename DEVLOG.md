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

Problems in someone else's folder go here. The owner removes the line once fixed.

- **Repo root:** there is no requirements file yet (AGENTS.md rule 8). Whoever builds `app/` should add one with the stack pinned, tested on Python 3.11. Versions installed and tested for Person 3's and Person 2's code (Python 3.11.18, uv venv, macOS arm64, 2026-11-14): `opencv-python==5.0.0.93`, `numpy==2.4.6`, `httpx==0.28.1`, `psycopg==3.3.9`, `psycopg-binary==3.3.9`, `python-dotenv==1.2.4`, `pytest==9.2.0`, `ruff==0.17.5`. That venv does not have `ultralytics`, `mediapipe`, `pyttsx3`, `pygame`, `fastapi` or `uvicorn`, so their versions must come from whoever installs them.
- **Persons 1 and 2 (delivering `NameResult` to scene):** `SceneDatabase.handle_name` and `handle_frame` change the same track state without a lock. `NameResult` is published on the namer's worker thread. If the bus calls `handle_name` inline on that thread, it can run while the frame thread is inside `handle_frame`. Example: `_publish_name_requests` sets `requests_sent = 1` just after a failure set it to 2, which allows a third Grok call. Either queue `NameResult` and hand it to scene on the frame thread (`fakes/namer/demo_check.py` does this), or Person 2 adds a lock in scene.
- **Person 1 (`app/` bus):** Person 3's modules are ready to be registered. Requests for `app/`:
  1. **Bus shape.** `namer.register(bus)`, `storage.register(bus)`, `fakes.namer.fake_namer.register(bus)` and `fakes.storage.fake_store.register(bus)` call only `bus.publish(msg)` and `bus.subscribe(MessageType, handler)`, keyed on the `contracts` class. If the bus uses a different shape, tell Person 3 before building against it.
  2. **Load `.env` before registering.** Call `load_dotenv()` at the top of `app/` before any `register(bus)`. `storage.register` reads `TIGER_DATABASE_URL` once, when the `Store` is created. If it is not set at that moment, storage drops every write for the whole run, even if `.env` is loaded later. Do not rely on the Grok client loading `.env` the first time it calls Grok, because that happens after storage has already read the variable.
  3. **Publishing from worker threads.** `namer` publishes `NameResult` from its own worker thread, and `storage` publishes `SpeakRequest` from its `storage-writer` thread. The fakes do the same, except the fake store, which answers on the delivering thread. `bus.publish` must be safe to call from any thread: guard the subscriber list with a lock or copy it before delivering. Subscribers that run on the frame thread, such as scene, must not be called with the bus lock held. Person 3's handlers only enqueue and return, so delivering to them inline is safe.
  4. **Scene adapter.** `SceneDatabase` calls `publish(topic_name, msg)`, where the topic is the class name. Until Person 2 changes that, wire it with `SceneDatabase(lambda _topic, msg: bus.publish(msg))`, or with `fakes.scene` for `--fake scene`.
  5. **Shutdown.** Keep what each `register` returns and call `stop()` on it at shutdown: `Namer.stop(timeout=...)`, `Store.stop()`, `FakeNamer.stop(timeout=...)`, and `FakeStore.stop()`, which does nothing. `Store.stop()` waits up to 5 s for its worker to finish and close the database connection.
  6. **`--fake namer storage`.** Use the `register` functions in `fakes/namer/fake_namer.py` and `fakes/storage/fake_store.py`. They subscribe to the same message types as the real modules, so the rest of `app/` does not change.

- **Person 4 (`dashboard/`, please review):** Person 2 added the live camera feed to your folder at their own request, outside the ownership rule. New `dashboard/video.py`, plus edits to `dashboard/server.py`, `dashboard/__init__.py`, `dashboard/index.html`, `dashboard/requirements.txt` and `tests/test_dashboard.py`, and a new `tests/test_dashboard_video.py`. Details are in the 2026-11-14 Person 2 entry below. Keep it, change it or revert it as you see fit, then remove this line. Nothing in `vision/` or `app/` changed, so Person 1 has nothing to do.
- **Person 3 (`namer/grok_client.py`, please review):** Person 2 rewrote `INSTRUCTION` at their own request, outside the ownership rule, so Grok names a brand only when it is printed and readable. Details are in the 2026-11-14 Person 2 naming entry below. Keep, change or revert it, then remove this line.

## Contract changes

Any change to `contracts/`, `config/`, `SPEC.md` or `AGENTS.md`. Needs all four to agree.

| When | What changed | Agreed by |
|---|---|---|
| 2026-11-13 21:10 | First version of all four files | pending team review |
| 2026-11-13 22:05 | Stack table added to `SPEC.md` section 2.1, `AGENTS.md` and `CLAUDE.md` | pending team review |
| 2026-11-13 23:40 | Initial `contracts/messages.py` and `config/thresholds.py`, copied from SPEC.md sections 5 and 9. No value changed | pending team review |
| 2026-11-14 01:03 | PR #2 merged to `main`: `Box` and `Point` are tuples, the fixed value sets are `Literal`, list fields default to empty, the dataclasses are no longer frozen, and `tests/test_contracts.py` checks them against SPEC.md. No threshold changed | Person 3 (author), Person 2 (adopted in `scene/`). Persons 1 and 4 still to confirm |

## Stack

The approved stack, repeated here so every log reader has it. Changes go through the contract changes table above.

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Camera capture and drawing | OpenCV (`opencv-python`) |
| Object detection and tracking | Ultralytics YOLO nano, COCO weights, ByteTrack |
| Hand tracking | MediaPipe Hands |
| Brand naming and hazard check | Grok vision model over the Grok API, called with `httpx` |
| Database | Tiger Data (Postgres with time-series hypertables), `psycopg` 3 |
| Speech | `pyttsx3`, offline |
| Alarm sound | `pygame` mixer, pre-made WAV |
| Web server | FastAPI on Uvicorn |
| Dashboard page | One HTML file, plain JavaScript and CSS, MJPEG video, one WebSocket |
| Message bus | In-process publish and subscribe in `app/` |
| Settings and secrets | `python-dotenv`, `.env` |
| Tests and formatting | `pytest`, `ruff` |
| Version control | Git and GitHub |
| Coding agents | Cursor, Grok Bot, Claude Code |
| Hardware | Logitech USB webcam, laptop, JBL Go 3 over Bluetooth |

## Entries

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
| Other | Claude Code reviewed Cursor's scene module and fixed the held-merge and release-on-removal bugs. |
