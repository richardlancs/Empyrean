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

- none yet

## Contract changes

Any change to `contracts/`, `config/`, `SPEC.md` or `AGENTS.md`. Needs all four to agree.

| When | What changed | Agreed by |
|---|---|---|
| 2026-11-13 21:10 | First version of all four files | pending team review |
| 2026-11-13 22:05 | Stack table added to `SPEC.md` section 2.1, `AGENTS.md` and `CLAUDE.md` | pending team review |

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
| 2 | Touch logic | |
| 3 | Grok and data | Richard Lan |
| 4 | Audio and dashboard | |

## Agent usage summary

Fill this in as you go. It becomes the SpaceXSI section of the Devpost write-up.

| Tool | What we used it for |
|---|---|
| Cursor | |
| Grok Bot | |
| Other | |
