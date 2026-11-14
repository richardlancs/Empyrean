<!-- DRAFT for the team to edit. -->

# Empyrean

Camera-equipped glasses that tell you what you're touching, down to the product name when the label is readable.

Built at HackUMass XIV (13–15 November 2026) by Team Push2Prod.

> **This is a prototype, not a safety device.** It does not replace a cane or a guide dog. One webcam cannot measure distance, and hazard detection can miss things.

## Inspiration

For most of us on the team, living with a bleeding disorder means carrying a worry we can't switch off. Before we left for HackUMass, even while we were excited about the trip, we kept running through the same questions. Did we pack everything we might need? Would we still be able to take our medication on time if our flight was delayed? What would we do if one of us needed help far from home? We were excited to take part in HackUMass together, and before we even arrived, we were thinking about how we could use the weekend to make everyday life a little easier for someone else.

That experience is one of the main reasons we care about accessibility. We know how much energy it takes to plan around needs that are easy for others to overlook. We wanted to build something that could make more of the day easier for people who are blind or have low vision, starting with the objects they reach for at home, at school, or while shopping.

Think about reaching for ketchup when there are several bottles on the counter. Empyrean might recognize the object as a bottle first. If it can read enough of the label, it can tell you it's Heinz ketchup. That extra detail helps you know whether you picked up what you were looking for.

## What it does

Empyrean uses a webcam mounted on a pair of glasses to track the wearer's fingers and nearby objects. When the app detects a touch, a Bluetooth speaker says the name of the object. When the camera gets a clear view of the label and the app recognizes it, the wearer can hear the product name too.

If the system flags a potential hazard, the warning takes priority and can interrupt the current announcement. In our controlled demo, the speaker plays the warning while the dashboard shows the corresponding event. The dashboard also shows the camera feed, the objects in view, and a history of recent touches and warnings. That gives someone helping with the setup a way to see what the app picked up.

## How we built it

We angled a Logitech webcam downward from the bridge of the glasses so it could see the wearer's hands. The laptop runs three tools to turn that camera feed into a spoken response.

- YOLO finds objects in the video and tracks them as they move.
- MediaPipe finds the fingertips so the app can tell when a finger rests on an object.
- Grok Vision examines a close-up when the app needs a more specific name or can see a product label.

We connected the camera, audio, dashboard, and Tiger Data through a shared message system. When one part reports a touch or warning, the other parts can respond to that same event. The JBL can speak it, the dashboard can show it, and Tiger Data can save it for later.

### Step by step

1. A webcam on the bridge of a pair of glasses, angled down, looks at the wearer's hands and what is in front of them.
2. On the laptop, YOLO finds and tracks objects, and MediaPipe finds the fingertips.
3. When a fingertip rests on an object, the app knows what is being touched. Grok vision looks at a close-up for a more specific name when it can see the label.
4. The wearer asks out loud ("What am I touching?", "What do you see?") and the answer is spoken through a Bluetooth speaker. By default, names are spoken only in answer to a question.
5. In parallel, a hazard check watches every frame. A warning always takes priority and interrupts the current announcement.
6. Touches and hazards are logged to Tiger Data, so you can ask "where did I last touch my keys?"
7. A web dashboard on the laptop shows the camera feed with boxes, the objects in view, what was heard, and recent events.

Full behaviour, every message and every threshold: [SPEC.md](SPEC.md).

## The full story

Our challenges, what we're proud of, what we learned and what's next are on our Devpost page.
<!-- TODO: add the Devpost link here once the page is up. -->

## Hardware

| Item | Detail |
|---|---|
| Camera | Logitech USB webcam on the bridge of a pair of glasses, tilted about 20° down |
| Computer | One Windows laptop in a backpack; everything runs on it |
| Speaker | JBL Go 3 over Bluetooth, set as the system audio output |
| Network | Needed for Grok, Tiger Data and browser voice input (a phone hotspot works) |

## Setup (Windows, Python 3.11)

Tested on Windows 11 with Python 3.11.

**1. Install the packages and model files.** In PowerShell, from the repo folder, in a fresh virtual environment:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe scripts/install_dependencies.py
.venv/Scripts/python.exe scripts/setup_models.py
```

The installer uses the pinned versions in `requirements.txt` and `requirements-vision.txt`, and keeps the two OpenCV packages from clashing. The model script puts `yolo11s.pt` and `hand_landmarker.task` in `vision/models/`. Model files are never committed. Optional demo-detector weights are described in [demotraining.md](demotraining.md).

**2. Activate the environment** each time you open PowerShell, so `python` means this venv:

```powershell
.venv\Scripts\Activate.ps1
```

**3. Create a `.env` file.** Copy `.env.example` to `.env` and fill in the values. Never commit `.env`.

| Variable | Meaning |
|---|---|
| `GROK_API_KEY` | Key for the Grok API |
| `GROK_MODEL` | A Grok model that accepts images |
| `TIGER_DATABASE_URL` | Connection string for the Tiger Data service |
| `CAMERA_INDEX` | Which camera to open (default `0`) |

Without a `.env` the app still runs. Objects show as "naming…" and nothing is saved.

## Run it

| Command | What it does |
|---|---|
| `python -m app` | Everything, on the real webcam |
| `python -m app --fake vision` | Everything, with a scripted fake camera (no webcam needed) |
| `python -m app --fake vision hazard` | Fake camera plus scripted hazards, to see and hear the alarm |
| `python -m audio` | Audio demo only: a spoken answer, interrupted by a stairs alarm |
| `python -m dashboard` | Dashboard page only, with no other modules |
| `python -m pytest` | All tests |

Then open **http://localhost:8000** in Chrome. Press **Ctrl+C** in PowerShell to stop.

On the dashboard:

- **Microphone** starts and stops listening. Ask "What am I touching?" or "What do you see?" and the answer is spoken. Voice input uses the browser's speech recognition, which may send audio to the browser's speech service and needs internet.
- **Demo mode** switches the camera to the fixed set of demo objects; off returns to the standard detector.
- The **Latest warning** card turns red for a few seconds after a hazard.
- **Objects** lists what the camera sees; the touched object is highlighted.
- **Voice input** shows what was heard and the latest answer.
- **Recent events** shows the last 10 touches and hazards.
- **Simulate alert** adds a test warning, marked *Simulated*, to the page only. It makes no sound and is not saved.

## Demo tips

- With Demo mode off, use everyday objects the standard detector knows well: a plain plastic water bottle, a cup or mug, a phone, a banana or apple, a book, scissors. Unusual items (metal tumblers, headphones, keys, toiletries) are often missed or mislabelled.
- Demo mode targets the team's eight demo objects. It is still being trained; see [demotraining.md](demotraining.md) for its current status.
- Wear or hold the camera as it will be used: steady, looking forward and down at arm's length, in good light.

## How the code is organised

One Python 3.11 process. Modules never call each other; they publish and subscribe to messages on an in-process bus ([SPEC.md](SPEC.md) section 5).

| Folder | What it does | Owner |
|---|---|---|
| `vision/` | Camera, YOLO object tracking, MediaPipe hands | Person 1 |
| `hazard/` | Hazard detection (YOLO vehicles plus Grok) | Person 1 |
| `app/` | Starts every module and the message bus | Person 1 |
| `scene/` | Object states and touch detection | Person 2 |
| `namer/` | Brand-level names from Grok vision | Person 3 |
| `storage/` | Tiger Data history and "last seen" answers | Person 3 |
| `audio/` | Speech and the hazard alarm | Person 4 |
| `dashboard/` | The web dashboard | Person 4 |
| `fakes/` | Stand-ins so each module runs alone | Each module's owner |
| `contracts/`, `config/` | Shared message shapes and thresholds | All four |

<!-- TODO: replace Person 1-4 with names or GitHub handles if the team wants them public. -->

## Built with

Python 3.11 · OpenCV · Ultralytics YOLO11 (COCO) with ByteTrack · MediaPipe Hands · Grok vision API (`httpx`) · Tiger Data (Postgres, `psycopg` 3) · `pyttsx3` · `pygame` · FastAPI and Uvicorn · `pytest` and `ruff`.

AI coding agents used: Cursor, Grok Bot and Claude Code. See [DEVLOG.md](DEVLOG.md) for how.

## More

- [SPEC.md](SPEC.md): what the system does, every message and threshold
- [AGENTS.md](AGENTS.md): rules for the coding agents and folder ownership
- [DEVLOG.md](DEVLOG.md): what was built, tested and decided, session by session
