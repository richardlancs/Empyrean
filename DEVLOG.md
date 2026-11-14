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

- **Person 3 (`tests/test_storage.py`):** `test_unreachable_db_never_blocks_and_warns_once` is flaky on Windows. It failed 2 of 3 runs on Person 2's laptop. `_wait_for` gives up after 3 s, and `CONNECT_TIMEOUT_SECONDS` is also 3 s. On Windows, a refused connection to `127.0.0.1:1` can take about that long, so `dropped` reaches 100 just after the wait ends. Give the wait a longer timeout than the connect timeout. Found by Person 2, 2026-11-14.
- **Repo root:** there is no requirements file yet (AGENTS.md rule 8). Whoever builds `app/` should add one with the stack pinned, tested on Python 3.11.
- **Person 1 (`app/` bus):** Person 3's `register(bus)` expects `bus.publish(msg)` and `bus.subscribe(MessageType, handler)`. `SceneDatabase` takes `publish(topic_name, msg)`, where the topic is the class name. Wire scene with `SceneDatabase(lambda _topic, msg: bus.publish(msg))`, or tell Person 2 which shape the bus uses.

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
| Grok Bot | |
| Other | Claude Code reviewed Cursor's scene module and fixed the held-merge and release-on-removal bugs. |
