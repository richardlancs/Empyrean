# SPEC.md

TouchSight (working name): smart glasses that speak the name of whatever a blind or low-vision person touches, and sound an alarm when they walk toward a hazard.

Built at HackUMass XIV, 13 to 15 November 2026, by a team of four.

This file is the single source of truth for what the system does. `AGENTS.md` is the contract for how coding agents work on it. If the two disagree, stop and ask a human.

---

## 1. Goal

A wearer picks things up off a table or shelf. Each time their hand lands on an object, a speaker says exactly what it is, down to the brand ("Heinz ketchup", not "bottle"). Nothing is spoken for objects that are only in view. Touching the same object again says it again. Separately, if the wearer walks toward stairs, a drop, a vehicle or an obstacle, an alarm interrupts everything else.

### In scope

- Touch-triggered announcement of the touched object's specific name.
- Brand-level naming through Grok vision.
- Independent spoken questions about current surroundings, answered by Grok vision.
- Hazard alarm from the same camera.
- A dashboard that shows the camera feed, the objects in view, and which object is being touched.
- A touch history in Tiger Data with a "where did I last touch X" query.

### Out of scope

- Training any model. All models are pretrained.
- Navigation, route guidance, or reading long text.
- Mobile app, cloud deployment, user accounts.
- Any claim that this replaces a cane or guide dog. It is a prototype.

---

## 2. Hardware

| Item | Detail |
|---|---|
| Camera | Logitech USB webcam taped or clipped to the bridge of a pair of sunglasses, facing forward and tilted about 20 degrees down so hands and tabletop are in view |
| Computer | One laptop in a backpack, connected to the camera by USB cable. Everything runs on it |
| Speaker | JBL Go 3 paired to the laptop over Bluetooth and set as the system audio output |
| Network | Internet is needed only for Grok and Tiger Data. Use a phone hotspot if venue Wi-Fi is unreliable |

### 2.1 Stack

This is the whole stack. Do not substitute or add to it without all four people agreeing. Pin exact versions in the requirements file when each package is first installed.

| Layer | Choice | Used by |
|---|---|---|
| Language | Python 3.11 | Everything |
| Camera capture and drawing | OpenCV (`opencv-python`) | `vision/`, `dashboard/` |
| Object detection and tracking | Ultralytics YOLO, small model (`yolo11s.pt`) with COCO weights, built-in ByteTrack tracker | `vision/` |
| Hand tracking | MediaPipe Hands | `vision/` |
| Brand naming and hazard check | A Grok model that accepts images, called over the Grok API with `httpx` | `namer/`, `hazard/` |
| Database | Tiger Data (managed Postgres with time-series hypertables), `psycopg` 3 driver | `storage/` |
| Speech | `pyttsx3`, offline text to speech | `audio/` |
| Alarm sound | `pygame` mixer playing a pre-made WAV file | `audio/` |
| Web server | FastAPI on Uvicorn | `dashboard/` |
| Dashboard page | One HTML file with plain JavaScript and CSS. MJPEG for video, one WebSocket for data. No front-end framework | `dashboard/` |
| Message bus | In-process publish and subscribe, written by us in `app/`. No external broker | Everything |
| Settings and secrets | `python-dotenv` reading `.env` | Everything |
| Tests and formatting | `pytest`, `ruff` | Everything |
| Version control | Git and GitHub, one branch per person | Everything |
| Coding agents | Cursor as the main coding agent, one Grok Bot automation, Claude Code where a teammate prefers it | Everything |
| Hardware | Logitech USB webcam, one laptop, JBL Go 3 over Bluetooth | Section 2 |

---

## 3. Architecture

One Python 3.11 process on the laptop. Modules never call each other directly. They publish and subscribe to messages on an in-process bus. Section 5 defines every message.

### 3.1 Modules

| # | Module | Folder | Owner | Subscribes to | Publishes | Built with |
|---|---|---|---|---|---|---|
| 1 | Camera capture | `vision/` | Person 1 | nothing | raw frames (internal to `vision/`) | OpenCV |
| 2 | Object tracker | `vision/` | Person 1 | raw frames | part of `FrameResult` | Ultralytics YOLO small, COCO weights, ByteTrack |
| 3 | Hand tracker | `vision/` | Person 1 | raw frames | part of `FrameResult` | MediaPipe Hands |
| 4 | Hazard detector | `hazard/` | Person 1 | `FrameResult` | `HazardEvent` | YOLO classes plus Grok vision |
| 5 | Scene database | `scene/` | Person 2 | `FrameResult`, `NameResult` | `SceneSnapshot`, `NameRequest` | In-memory state |
| 6 | Touch detector | `scene/` | Person 2 | `FrameResult` and scene state | `TouchEvent` | State machine |
| 7 | Grok namer and scene questions | `namer/` | Person 3 | `NameRequest`, `SceneQuestion`, `FrameResult` | `NameResult`, `SpeakRequest` | Grok vision API |
| 8 | Tiger Data store | `storage/` | Person 3 | `TouchEvent`, `HazardEvent`, `LastSeenQuery` | `SpeakRequest` (answers) | Tiger Data (Postgres with time-series) |
| 9 | Audio manager | `audio/` | Person 4 | `TouchEvent`, `NameResult`, `HazardEvent`, `SpeakRequest` | sound to the JBL | Offline text to speech plus a tone file |
| 10 | Dashboard | `dashboard/` | Person 4 | `FrameResult`, `SceneSnapshot`, `TouchEvent`, `HazardEvent`, `SpeakRequest` | `LastSeenQuery`, `SceneQuestion` | FastAPI, one static HTML page |

Shared folders:

| Folder | Purpose | Owner |
|---|---|---|
| `contracts/` | Message definitions from section 5 | All four. Any change needs all four people to agree |
| `config/` | Every threshold from section 9 in one place | All four, same rule |
| `app/` | Entry point that starts every module and the bus | Person 1 (integration owner) |
| `fakes/` | Fake publishers and recorded clips so each module runs alone | Whoever owns the real module also owns its fake |
| `tests/` | Smoke tests | Each person for their own modules |

### 3.2 Data flow

1. The camera gives frames. `vision/` processes 5 of them per second.
2. For each processed frame, `vision/` publishes one `FrameResult`: the image, the tracked objects, and the fingertip positions.
3. The scene database updates its list of objects. When an object is new and has been stable for 1 second, it sends a `NameRequest` with a crop of that object.
4. The Grok namer replies with a `NameResult`. The scene database stores the name on the object.
5. The touch detector compares fingertips with object boxes. On a touch it publishes a `TouchEvent`.
6. The audio manager speaks the object's name through the JBL. The Tiger Data store logs the event. The dashboard highlights the object.
7. In parallel, the hazard detector watches every `FrameResult`. On a hazard it publishes a `HazardEvent`, and the audio manager plays the alarm ahead of anything else.

---

## 4. Behaviour

### 4.1 Frames and coordinates

- Capture at 1280 x 720. Process at 640 x 360.
- All boxes and points in every message are pixels in the 640 x 360 processed frame. Origin is top-left. x grows right, y grows down.
- Boxes are `x1, y1, x2, y2` with `x1 < x2` and `y1 < y2`.
- Timestamps are seconds since the Unix epoch, UTC, as a decimal number. The field is always called `ts`.
- Target rate is 5 processed frames per second. If the laptop cannot keep up, drop frames. Never queue them.

### 4.2 Object tracking

- Use the YOLO small model (`yolo11s.pt`) with COCO weights and its built-in ByteTrack tracker so each object keeps the same `object_id` across frames. The nano model missed held objects on the real camera (a backpack at any confidence); small costs about 49 ms per frame on the laptop CPU against 24 ms.
- Drop detections with confidence below 0.3.
- Drop the `person` class. The wearer's own arm must never be an object.
- Drop boxes smaller than 0.2% of the frame area.

### 4.3 Hand tracking

- MediaPipe Hands, up to 2 hands.
- Only two landmarks matter: thumb tip (landmark 4) and index fingertip (landmark 8).
- Also report each hand's bounding box, taken from all 21 landmarks.

### 4.4 Scene database

Each object has one state:

| State | Meaning |
|---|---|
| `new` | Seen for less than 1 second. Not yet named. Not touchable |
| `idle` | Stable and in view |
| `touching` | A fingertip is on it |
| `held` | Picked up and moving with the hand |
| `lost` | Not detected right now, last seen under 2 seconds ago. Its last box is kept |

Rules:

- An object becomes `idle` after it has been detected in 5 consecutive processed frames.
- An object that is not detected becomes `lost` and keeps its last known box. After 2 seconds without detection it is removed.
- `lost` objects stay touchable. This matters because a hand covering an object usually makes the detector lose it.
- The scene database publishes a `SceneSnapshot` after every `FrameResult`.

### 4.5 Naming

- When an object first becomes `idle`, the scene database sends one `NameRequest` with a JPEG crop of the object, padded by 10% on each side.
- The namer asks Grok, in plain words: name the object in this image; include a brand or model only if it can actually be read printed on the object, and never guess one from shape, colour or style; if a brand is readable, reply with the brand and product type ("Diet Coke can"); otherwise reply with only the plain object name ("laptop"); at most 5 words; no sentences.
- The reply is trimmed, cut to 40 characters, and published as a `NameResult`.
- Names are cached by `object_id`. An object is named once.
- At most 2 requests in flight at a time and at most 1 new request per second. Extra requests wait, largest object first.
- A request times out after 4 seconds. On timeout or error the object keeps `name` empty and may be retried once. The scene database sends that one retry; the namer makes exactly one Grok call per request.
- If an object is touched before its name arrives, the system speaks the plain class label ("bottle"). If the name arrives within 1.5 seconds and the object is still being touched, the system then speaks the name once.

### 4.6 Touch detection

A fingertip is "on" an object when the thumb tip or index fingertip of either hand lies inside the object's box after the box has been shrunk by 10% on every side. For `lost` objects, use the last known box.

If fingertips are on more than one object, pick the object whose box centre is nearest the fingertip, measured as a fraction of that box's diagonal.

| Transition | Condition | Result |
|---|---|---|
| `idle` or `lost` to `touching` | Fingertip on the object for 2 consecutive processed frames (0.4 s) | Publish `TouchEvent` with kind `touch`. This triggers automatic object speech; independent questions also receive spoken answers |
| `touching` to `idle` | No fingertip on the object for 3 consecutive processed frames (0.6 s) | Publish `TouchEvent` with kind `release`. Not spoken |
| `touching` to `held` | The object's box centre has moved more than 15% of the frame width since the touch began, or the object has been `lost` for 1 second while a hand is still over its last box | No event |
| `held` to `idle` | No hand in view for 3 consecutive frames, or fingertips off the object for 3 consecutive frames | Publish `TouchEvent` with kind `release` |

Rules that follow from the table:

- One touch gives exactly one announcement, however long the hand stays.
- Letting go and touching again gives a new announcement. There is no cooldown on retouch.
- While an object is `held`, any new detection whose box overlaps the hand's box by an IoU of 0.3 or more is treated as the held object. It inherits the name and is not announced.
- Objects in state `new` cannot be touched.

### 4.7 Hazard detection

Two tiers run at the same time.

**Tier A, local and fast.** Uses boxes already in `FrameResult`. If an object of class `car`, `bus`, `truck`, `motorcycle` or `bicycle` covers at least 10% of the frame and its area has grown by at least 30% in the last second, publish a `HazardEvent` of type `vehicle` with source `yolo`.

**Tier B, Grok.** Every 1.5 seconds, send the current frame scaled to 512 pixels wide to Grok and ask, in plain words: this is the forward view from a camera worn at eye level by a blind pedestrian, tilted about 20 degrees down so hands and tabletop are in view; is there an immediate hazard the wearer would hit or fall from within their next two steps; count only a downward step, stair edge or drop directly ahead, an approaching vehicle, or a solid object in the walking path within about 1 metre; do not count objects on a table, objects in or near the hands, furniture or walls beside the path, or a table edge seen from above; if unsure, answer hazard false; reply with only a JSON object with fields `hazard` (true or false), `type` (one of `stairs_down`, `drop_off`, `vehicle`, `obstacle`, `none`) and `confidence` (0 to 1). If `hazard` is true and `confidence` is 0.6 or higher, publish a `HazardEvent` with source `grok`. A request times out after 3 seconds. Never have more than one tier B request in flight.

Rules:

- After any `HazardEvent`, publish no further `HazardEvent` for 3 seconds.
- Hazard detection never pauses for touch, naming, or dashboard activity.
- A false alarm is acceptable. A missed hazard is the failure to avoid, so a single positive is enough to alarm.

The tier B prompt was narrowed after the first wording raised 22 indoor alarms in about 2 minutes on tabletop scenes. The single-positive rule above still applies to whatever Grok reports.

Known limit: one webcam cannot measure distance. Tier B lags by 1 to 3 seconds and will miss some hazards. Never describe this feature as a safety device.

### 4.8 Audio

| Priority | Sound | Trigger |
|---|---|---|
| 1 (highest) | Alarm: three short 880 Hz beeps, then the spoken hazard ("Stop. Stairs.") | `HazardEvent` |
| 2 | Spoken object name | `TouchEvent` with kind `touch` |
| 3 | Spoken answer | `SpeakRequest` with priority `normal` |

Rules:

- An alarm cuts off whatever is playing and empties the queue.
- The speech queue holds one item. A newer item replaces a waiting older one. Stale speech is worse than no speech.
- Spoken hazard phrases: `stairs_down` is "Stop. Stairs.", `drop_off` is "Stop. Drop ahead.", `vehicle` is "Stop. Vehicle.", `obstacle` is "Stop. Obstacle."
- Text to speech runs offline on the laptop so speech never waits on the network.
- The alarm beeps are a pre-made sound file, not generated at run time.

### 4.9 Dashboard

One web page served from the laptop on port 8000.

| Area | Content |
|---|---|
| Left, large | Live camera feed with overlays, streamed as MJPEG at `/video` |
| Right, top | Object list: name (or class label until named), state, seconds since last seen. Touched objects are highlighted and sorted to the top |
| Right, bottom | Event log: last 10 touch and hazard events with times |
| Top bar | Processed frames per second, a red banner while a hazard is active, and a "last touched" search box |

Overlays, drawn on the laptop before streaming:

| Object state | Box |
|---|---|
| `new` | Thin grey, no label |
| `idle` | White, labelled with name or class |
| `touching` | Thick green, tagged TOUCHING |
| `held` | Yellow, tagged HELD |
| `lost` | Dashed white |

Hands are drawn as dots at the thumb tip and index fingertip.

Object list and events reach the page over one WebSocket at `/ws`, sent after every `SceneSnapshot`.

The search box publishes a `LastSeenQuery`. The answer is shown on the page and spoken through the JBL.

### 4.9.1 Independent voice questions

Touch announcements remain automatic and never require microphone input or a question.
The dashboard microphone transcribes a question and publishes `SceneQuestion`.
The namer retains the latest `FrameResult` and uses a separate background worker to
send the full current image and question to Grok. Answers are short and spoken via
`SpeakRequest` with source `namer`, and shown on the dashboard. "Where are my keys?"
asks about the current view; Grok describes left/right/ahead only when supported by
that image, and says when the item is not visible. Explicit "Where did I last touch X?"
questions still use `LastSeenQuery` and storage. No route guidance is provided.

The worker runs at most one question call with one waiting question; excess requests
receive a busy answer. Frames older than `QUESTION_MAX_FRAME_AGE_SECONDS` are rejected.
`QUESTION_TIMEOUT_SECONDS` bounds each call. Errors produce an unavailable answer and
are logged once until recovery. Questions never gate touch naming or hazard processing.
Audio priorities remain alarm, automatic touch, then requested answers. Browser speech
recognition may need microphone permission and a supported browser; it starts only when
the microphone button is enabled. Its playback pause is heuristic and cannot guarantee
that speaker output will not be transcribed.

### 4.10 Tiger Data

Two time-series tables.

`touch_events`

| Column | Type | Meaning |
|---|---|---|
| `ts` | timestamp with time zone | When it happened. Time column of the hypertable |
| `session_id` | text | One value per run of the app |
| `object_id` | integer | Tracker ID |
| `class_label` | text | COCO class |
| `name` | text, may be empty | Grok name |
| `kind` | text | `touch` or `release` |
| `cx`, `cy` | real | Box centre as a fraction of frame width and height, 0 to 1 |
| `neighbours` | array of text | Names of up to 3 nearest other objects at that moment |

`hazard_events`

| Column | Type | Meaning |
|---|---|---|
| `ts` | timestamp with time zone | When it happened |
| `session_id` | text | One value per run |
| `type` | text | `stairs_down`, `drop_off`, `vehicle`, `obstacle` |
| `source` | text | `yolo` or `grok` |
| `confidence` | real | 0 to 1 |

Last-seen query: given some text, find the most recent `touch_events` row whose `name` or `class_label` contains it, ignoring case. The answer is one sentence, for example "Heinz ketchup, 4 minutes ago, next to mug and cereal box." If nothing matches: "I have not seen that."

Writes to Tiger Data must never block the frame loop. If the database is unreachable, keep running and drop the writes.

---

## 5. Messages

These are the contract between modules. Field names, types and units are fixed.

### `FrameResult` (vision to everyone, once per processed frame)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | Capture time |
| `frame_id` | integer | Counts up from 0 |
| `image` | 640 x 360 BGR image | The processed frame |
| `objects` | list | One entry per tracked object: `object_id` (integer), `class_label` (text), `confidence` (0 to 1), `box` (`x1, y1, x2, y2`) |
| `hands` | list | One entry per hand: `side` (`left`, `right` or `unknown`), `thumb_tip` (`x, y`), `index_tip` (`x, y`), `box` (`x1, y1, x2, y2`) |

### `SceneSnapshot` (scene to dashboard, once per processed frame)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | Time of the frame it describes |
| `frame_id` | integer | Matches the `FrameResult` |
| `objects` | list | One entry per object: `object_id`, `class_label`, `name` (text or empty), `state` (`new`, `idle`, `touching`, `held`, `lost`), `box`, `last_seen_ts` |

### `NameRequest` (scene to namer)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | When requested |
| `object_id` | integer | Object to name |
| `class_label` | text | COCO class, as a hint |
| `crop_jpeg` | bytes | JPEG of the object, padded 10% |

### `NameResult` (namer to scene and audio)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | When answered |
| `object_id` | integer | Object named |
| `name` | text | At most 40 characters. Empty if naming failed |
| `ok` | true or false | False on timeout or error |

### `TouchEvent` (scene to audio, storage, dashboard)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | When the transition happened |
| `object_id` | integer | Object touched |
| `class_label` | text | COCO class |
| `name` | text or empty | Grok name if known |
| `kind` | text | `touch` or `release` |
| `box` | `x1, y1, x2, y2` | Object box at that moment |
| `neighbours` | list of text | Names or class labels of up to 3 nearest other objects |

### `HazardEvent` (hazard to audio, storage, dashboard)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | When detected |
| `type` | text | `stairs_down`, `drop_off`, `vehicle`, `obstacle` |
| `source` | text | `yolo` or `grok` |
| `confidence` | number | 0 to 1 |

### `LastSeenQuery` (dashboard to storage)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | When asked |
| `text` | text | What to search for |

### `ModeChange` (dashboard to vision, and vision back to dashboard)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | When the mode was set |
| `mode` | text | One of `actual`, `demo` |

The dashboard publishes this when the Demo mode button is pressed. In `demo`, vision detects with pretrained YOLOE (`yoloe-11s-seg.pt`) instead of `yolo11s.pt`. YOLOE is prompted with reference pictures of the demo objects, taken with `python -m vision.capture_demo_refs` and turned into prompts once by `python -m vision.build_demo_weights`. Nothing is trained. The camera, hands, scene, naming, audio and hazard paths are unchanged. If vision cannot switch (the demo prompts are not built), it publishes `ModeChange` with `mode` set to `actual`, so the page shows the mode that is really running.

### `SceneQuestion` (dashboard to namer)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | When asked, Unix epoch seconds UTC |
| `text` | text | The wearer's question about the current surroundings |

Answers use `SpeakRequest` with source `namer`. The namer subscribes to `FrameResult`
for current image context; no other module calls the namer directly.

### `SpeakRequest` (anyone to audio)

| Field | Type | Meaning |
|---|---|---|
| `ts` | number | When requested |
| `text` | text | What to say |
| `priority` | text | `normal` only. Alarms come from `HazardEvent`, never from here |
| `source` | text | Folder name of the sender |

---

## 6. Running it

These are the commands the finished project must support. Whoever builds `app/` makes them work.

| Command | What it does |
|---|---|
| `python -m app` | Runs everything against the real camera |
| `python -m app --fake vision` | Replaces `vision/` with a recorded clip from `fakes/`. Any module folder name can follow `--fake`, and several can be listed |
| `python -m app --only dashboard --fake vision scene` | Runs one module with fakes for the rest |
| `pytest` | Runs every smoke test |

Settings come from a `.env` file that is never committed:

| Variable | Meaning |
|---|---|
| `GROK_API_KEY` | Key for the Grok API |
| `GROK_MODEL` | Name of a Grok model that accepts images. Use `grok-4.20-0309-non-reasoning`; the reasoning models were too slow for the 3 s and 4 s timeouts |
| `TIGER_DATABASE_URL` | Connection string for the Tiger Data service |
| `CAMERA_INDEX` | Which camera OpenCV opens. Default 0 |

---

## 7. Latency targets

| Path | Target |
|---|---|
| Frame captured to `FrameResult` published | 150 ms or less |
| Fingertip lands to speech starts | 1 second or less, of which 0.4 s is the required dwell |
| Object stable to name stored | 2 seconds or less |
| Vehicle grows in frame to alarm (tier A) | 0.5 seconds or less |
| Hazard enters view to alarm (tier B) | 3 seconds or less |

---

## 8. Checkpoints

Times assume hacking ends Sunday morning. Shift them if the deadline differs.

| When | What must work |
|---|---|
| Fri midnight | Section 5 agreed by all four. Each module runs alone against fakes |
| Sat noon | Touch an object and hear its name, end to end, on the real camera |
| Sat 8 pm | Hazard alarm, Tiger Data log and dashboard all live |
| Sat midnight | Feature freeze. Only tuning, the write-up and rehearsal after this |

Cut order if behind: last-seen query first, then tier B hazard, then the held state. Touch to speech is never cut.

---

## 9. Thresholds

All of these live in `config/`. Nothing below is hard-coded anywhere else.

| Name | Value | Used by |
|---|---|---|
| `PROCESS_FPS` | 5 | vision |
| `PROCESS_WIDTH`, `PROCESS_HEIGHT` | 640, 360 | vision |
| `DET_MIN_CONFIDENCE` | 0.3 | vision |
| `DET_MIN_AREA_FRACTION` | 0.002 | vision |
| `DEMO_DET_MIN_CONFIDENCE` | 0.25 | vision |
| `STABLE_FRAMES` | 5 | scene |
| `LOST_KEEP_SECONDS` | 2.0 | scene |
| `BOX_SHRINK_FRACTION` | 0.10 | scene |
| `TOUCH_ENTER_FRAMES` | 2 | scene |
| `TOUCH_EXIT_FRAMES` | 3 | scene |
| `HELD_MOVE_FRACTION` | 0.15 | scene |
| `HELD_LOST_SECONDS` | 1.0 | scene |
| `HELD_MERGE_IOU` | 0.3 | scene |
| `NAME_CROP_PADDING` | 0.10 | scene |
| `NAME_MAX_IN_FLIGHT` | 2 | namer |
| `NAME_MIN_INTERVAL_SECONDS` | 1.0 | namer |
| `NAME_TIMEOUT_SECONDS` | 4.0 | namer |
| `NAME_MAX_CHARS` | 40 | namer |
| `LATE_NAME_WINDOW_SECONDS` | 1.5 | audio |
| `HAZARD_VEHICLE_MIN_AREA_FRACTION` | 0.10 | hazard |
| `HAZARD_VEHICLE_GROWTH` | 0.30 | hazard |
| `HAZARD_GROK_INTERVAL_SECONDS` | 1.5 | hazard |
| `HAZARD_GROK_WIDTH` | 512 | hazard |
| `HAZARD_GROK_MIN_CONFIDENCE` | 0.6 | hazard |
| `HAZARD_GROK_TIMEOUT_SECONDS` | 3.0 | hazard |
| `HAZARD_COOLDOWN_SECONDS` | 3.0 | hazard |
| `QUESTION_TIMEOUT_SECONDS` | 4.0 | namer |
| `QUESTION_MAX_FRAME_AGE_SECONDS` | 2.0 | namer |
| `DASHBOARD_PORT` | 8000 | dashboard |

---

## 10. Stretch goals

Only after the Sat 8 pm checkpoint is met.

1. **Unknown objects.** If fingertips rest for 1 second where no object box exists, crop the area around the hand and send it to the namer. COCO has only 80 classes, so many groceries are never detected.
2. **Teach mode.** The wearer names a personal item ("my allergy meds"). Store an embedding in Tiger Data and match later touches by vector similarity.
3. **Voice query.** Implemented as current-view questions and explicit history queries (section 4.9.1).

---

## 11. Prize targets

| Prize | How this project qualifies |
|---|---|
| Best Accessibility Hack (HackUMass) | The whole project |
| Build Your Hackathon A-Team with SpaceXSI (MLH) | Built with Cursor and a Grok Bot automation. Record how in `DEVLOG.md` |
| Best Use of Tiger Data (MLH) | Time-series touch history and the last-seen query |

---

## 12. Open questions

| Question | Who resolves it | By when |
|---|---|---|
| Exact rules of the SpaceXSI prize | Person 3, at the Saturday 11:45 am workshop | Sat noon |
| Current name of a Grok model that accepts images | Resolved: `grok-4.20-0309-non-reasoning` (Person 3, 2026-11-13) | Done |
| How many HackUMass categories one project may enter | Person 4, from the Devpost page | Sat noon |
| Exact submission deadline | Person 4 | Fri midnight |
| Which laptop runs the demo, and its operating system | All | Fri midnight |
