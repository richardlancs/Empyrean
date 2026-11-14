# AGENTS.md

Contract for every coding agent working in this repository (Cursor, Claude Code, Grok Bot, or any other). Four people are building this in parallel during a 36-hour hackathon, each with their own agent. These rules exist so four agents do not break each other's work.

Read this file fully before changing anything. Then read `SPEC.md`.

## The project in five lines

- Smart glasses for blind and low-vision people: a webcam on sunglasses, a laptop in a backpack, a JBL Go 3 speaker.
- When the wearer touches an object, the speaker says its specific name ("Heinz ketchup").
- When the wearer walks toward a hazard, an alarm interrupts everything.
- A dashboard shows the feed, the objects, and what is being touched.
- One Python 3.11 process. Modules talk only through the messages in `SPEC.md` section 5.

## Stack

Use exactly this. The full table with the folder each item belongs to is in `SPEC.md` section 2.1.

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

Do not swap any item for an alternative (a different detector, database, web framework, speech engine, or a front-end framework) and do not add a message broker, an ORM, or a container setup. If something in the stack cannot do the job, stop and tell your human.

## Who owns what

Ask your human which person they are before you start. Then work only in that person's folders.

| Person | Role | Folders they own |
|---|---|---|
| 1 | Vision and hazard | `vision/`, `hazard/`, `app/`, `fakes/vision/`, `fakes/hazard/` |
| 2 | Touch logic | `scene/`, `fakes/scene/` |
| 3 | Grok and data | `namer/`, `storage/`, `fakes/namer/`, `fakes/storage/` |
| 4 | Audio and dashboard | `audio/`, `dashboard/`, `fakes/audio/` |
| All four together | Shared | `contracts/`, `config/`, `SPEC.md`, `AGENTS.md`, `CLAUDE.md` |

## Rules

### 1. Stay in your lane

- Create and edit files only in your human's folders.
- Never edit another person's folder, even to fix an obvious bug. Write the problem in `DEVLOG.md` under "Needs attention" and tell your human.
- Never edit `contracts/`, `config/`, `SPEC.md`, `AGENTS.md` or `CLAUDE.md` unless your human says all four teammates have agreed to the change. Then record the change in `DEVLOG.md`.

### 2. The messages are law

- `SPEC.md` section 5 defines every message. Do not rename a field, change a type, change a unit, or add a required field.
- Coordinates are always pixels in the 640 x 360 processed frame, origin top-left. Boxes are always `x1, y1, x2, y2`.
- Timestamps are always seconds since the Unix epoch, UTC, in a field called `ts`.
- Modules communicate only by publishing and subscribing on the bus. Never import from another module's folder. Importing from `contracts/` and `config/` is fine.
- If the spec seems wrong or incomplete, stop and ask your human. Do not guess, and do not work around it.

### 3. Every module runs alone

- Each module must start and do something useful with fakes standing in for the modules it depends on. See `SPEC.md` section 6 for the commands.
- If you own a module, you also own its fake: something that publishes realistic messages of the types your module publishes, from a recorded clip or a script.
- Keep the fake up to date whenever the real module's output changes.

### 4. Never block the frame loop

- No network call, database write, model download, or sleep may run on the path that handles `FrameResult`.
- Grok calls happen only in `namer/` and `hazard/`, on background workers, with the timeouts in `SPEC.md` section 9.
- Tiger Data calls happen only in `storage/`, on a background worker.
- If a network service is down, the app keeps running. Log it once, not on every frame.

### 5. Hazard comes first

- Nothing may delay, pause, queue behind, or disable the hazard path.
- The alarm always outranks speech. Do not add any way to produce an alarm other than a `HazardEvent`.
- Never write copy, comments or UI text that calls this a safety device or a replacement for a cane. It is a prototype.

### 6. No magic numbers

- Every threshold is in `config/` under the name given in `SPEC.md` section 9. Read it from there.
- To try a different value, change it locally and tell your human. A new default needs all four to agree.

### 7. No model training

- All models are pretrained. Do not fine-tune, train, or swap a model without your human's say-so.
- Model weight files are never committed.

### 8. Dependencies

- The stack table above is the approved list. Anything outside it needs all four teammates to agree first.
- Before adding a small helper package, check whether one already in the requirements file does the job.
- If you add one, pin its version in the requirements file and note it in `DEVLOG.md` so teammates reinstall.

### 9. Secrets

- Keys and connection strings live in `.env`, which is git-ignored. Read them from the environment.
- Never print, log, commit, or paste a key or connection string, including in `DEVLOG.md`.
- Keep `.env.example` listing the variable names with empty values.

### 10. Git

- One branch per person, named `p1-vision`, `p2-touch`, `p3-grok-data`, `p4-output`.
- Small commits with a message that says what changed and why.
- Merge to `main` only when `python -m app --fake vision` still starts and `pytest` passes.
- Never force-push `main`. Never rewrite another person's commits.
- Do not commit recorded video longer than 20 seconds or larger than 10 MB.

### 11. Code style

- Python 3.11 with type hints on every function.
- One short docstring per public function saying what it does.
- Prefer plain functions and small classes. No frameworks beyond those named in `SPEC.md`.
- Log with the standard logging module, using the module folder name as the logger name. No bare print calls outside `fakes/` and tests.

### 12. Tests

- Each module has at least one smoke test in `tests/` that feeds it recorded or scripted messages and checks what it publishes.
- `scene/` must have tests for each row of the touch table in `SPEC.md` section 4.6, including retouch.
- Run `pytest` before telling your human a task is done.

### 13. Keep the log

After every working session, add an entry to `DEVLOG.md` in the format that file describes. Include:

- What changed.
- What was tested and how.
- Anything a teammate needs to know or do.
- Which agent did the work. The SpaceXSI prize asks the team to describe how Cursor and Grok Bot were used, so this record feeds the submission.

### 14. Done means

A task is done when all of these are true:

1. It behaves as `SPEC.md` describes.
2. It runs alone against fakes.
3. Its smoke test passes.
4. It publishes and consumes only the messages in `SPEC.md` section 5.
5. `DEVLOG.md` has an entry for it.

### 15. When unsure

Ask your human. A two-minute question costs less than another person's agent building against a wrong assumption.

## Priorities when time is short

1. Touch an object, hear its name. This is the demo and is never cut.
2. Dashboard showing the feed and the touched object.
3. Hazard alarm.
4. Tiger Data log.
5. Last-seen query.
6. Stretch goals in `SPEC.md` section 10.
