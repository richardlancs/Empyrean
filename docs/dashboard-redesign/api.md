# Dashboard API and engine integration (Agent 4)

This is the implemented contract on `design/light-dashboard-integration`. Where it
differs from the brief it says so. Everything here is backed by tests in
`tests/test_dashboard_*.py`.

## 1. Layers and the event flow

```
engine modules (vision, scene, namer, hazard, audio, storage)
   │  contracts/ messages on app/bus.py (one worker thread per subscription)
   ▼
dashboard/bus_adapter.py ── the only place the dashboard subscribes
   │
   ├─ dashboard/state.py            read model: objects, touch, speech, naming, warnings, events
   │     └─ services/health.py      measured diagnostics (frames, scene, naming, module status)
   ├─ dashboard/video.py            MJPEG pictures, per-viewer overlays
   ├─ dashboard/thumbnails.py       bounded recent object crops
   └─ services/last_seen.py         correlated last-touch searches
   │
dashboard/api/  routes.py (HTTP), realtime.py (/ws hub), schemas.py
   │
dashboard/static/ core/socket-client.js → core/store.js → features/* → components
```

Reverse path (user intent):

```
find panel → ctx.request → POST /api/last-seen → LastSeenService.submit
  → bus.publish(LastSeenQuery(request_id)) → storage worker (Tiger Data or fake)
  → bus: SpeakRequest (spoken answer, unchanged) + LastSeenResult(request_id)
  → LastSeenService.on_result → GET /api/last-seen/{id} (and a /ws push)
```

| Layer | Inputs | Outputs | Failure states |
|---|---|---|---|
| `bus_adapter.connect` | the bus | subscriptions only | none; a failing handler is logged by the bus and the others continue |
| `DashboardState` (read model) | HazardEvent, TouchEvent, SceneSnapshot, FrameResult, NameRequest, NameResult, SpeechStatus, ModuleStatus | `snapshot()` dict | missing evidence is `null` or `"unknown"`, never assumed healthy |
| `HealthMonitor` | frames, snapshots, naming lifecycle, ModuleStatus | `diagnostics` | stale camera → `degraded` then `offline`; quiet scene with no frames → `unknown`, not failed |
| `LastSeenService` | `submit(text)`, LastSeenResult | request records | 422 bad text, 429 too many pending, 503 no bus; timeout → `unavailable` |
| `ThumbnailCache` | FrameResult (reference only), SceneSnapshot | JPEG bytes per object | no frame for the snapshot → no crop; expired → 404 |
| `VideoFeed` | FrameResult, SceneSnapshot | `(sequence, jpeg)` per option set | encoding error logged once; viewers keep the previous picture |
| `Heartbeat` | 1 s timer | expiry + one `/ws` push | exceptions logged once |
| `api/routes.py` | HTTP | JSON, MJPEG, JPEG | validation errors → 422 `{detail, errors}` |
| `api/realtime.py` | `/ws` | page state JSON | one-slot queue per page: slow pages skip stale states |

Route handlers never touch the database, a model, or the speaker. The camera
publishing path is untouched: drawing, thumbnails and health each run on their
own bus worker, and the bus keeps only the newest FrameResult per subscriber.

## 2. New and changed bus messages (contracts/, SPEC.md section 5)

All additive. Old constructor calls still work.

| Message | From → to | Notes |
|---|---|---|
| `LastSeenQuery.request_id: str \| None = None` | dashboard → storage | optional |
| `LastSeenResult(ts, request_id, status, answer, matched_at=None, label="", neighbours=[])` | storage → dashboard | only for queries with a `request_id`; `status` is `found`, `not_found`, `unavailable`. A DB outage, error or missing `TIGER_DATABASE_URL` is `unavailable`, never `not_found` |
| `SpeechStatus(ts, speech_id, text, status, mode, kind, object_id=None, source="", detail="")` | audio → dashboard | `status`: queued, speaking, completed, interrupted, failed. `mode`: real (pyttsx3), fake (`--fake audio` prints), unavailable (TTS could not start; logged only — such phrases end as `failed`, never `completed`). `kind`: touch, answer, hazard |
| `ModuleStatus(ts, module, status, mode="unknown", detail="")` | any → dashboard | app/ sends `starting`/`offline` per module at startup with mode real/fake; audio and storage send their own availability changes |

Spoken behaviour is unchanged: the last-seen `SpeakRequest` still says
"I have not seen that." when the database is down (existing behaviour kept on
purpose; the page shows the truthful `unavailable`).

## 3. HTTP endpoints

| Method and path | Reply |
|---|---|
| `GET /` | `dashboard/index.html` (no-store) |
| `GET /static/...` | files under `dashboard/static/`; `.js` is `text/javascript`, `.css` is `text/css` |
| `GET /video` | MJPEG, original overlays (unchanged) |
| `GET /video?boxes=0\|1&hands=0\|1&labels=0\|1&selected_id=<int>` | MJPEG with this viewer's overlays. Omitted = original. Unknown params (for example `r=` cache busters) are ignored. Bad values → 422 |
| `GET /api/state` | page state (section 4) |
| `POST /api/simulate-alert` | page state after adding one simulated warning. Publishes nothing on the bus: no HazardEvent, no alarm, no storage row |
| `POST /api/last-seen` `{"query": "keys"}` | **202** `{"request_id": "<32 hex>", "status": "pending"}`. 422 empty/too long (> 60 chars after trimming)/extra fields, 429 more than 8 searches pending, 503 no engine attached (`python -m dashboard` alone) |
| `GET /api/last-seen/{request_id}` | `{request_id, status, answer, matched_at, query, label, neighbours, detail, submitted_at}`; `status` pending, found, not_found, unavailable. 404 unknown or expired id |
| `GET /api/objects/{object_id}/thumbnail` | `image/jpeg` crop (longest edge ≤ 160 px) or 404 `{detail}` |
| `WS /ws` | page state on connect and after each change, at most 10 per second, plus a 1 s heartbeat |

Every error body is `{"detail": "<one plain sentence>"}` (422 adds `errors`).

Last-seen timing: storage answers on its worker; a pending search becomes
`unavailable` with detail "History storage did not answer in time" after
`LAST_SEEN_TIMEOUT_SECONDS` (8 s). Finished searches can be read for 120 s;
at most 64 are kept. Poll every 500 ms; a `/ws` push also follows each answer.
`matched_at` is the Unix time of the matching recorded touch. The search looks
at recorded touches only (name or class label contains the text); there is no
location data, so never show a room or position. `neighbours` are the objects
recorded next to it at that moment.

## 4. Page state (`/api/state` and `/ws`)

Existing fields are unchanged: `now`, `hazard_active_seconds`, `latest_warning`,
`events`, `objects`. Additions:

```jsonc
{
  "latest_real_warning": null | {id, ts, kind:"hazard", type, text, detail, simulated:false, source:"yolo"|"grok", active},
  "latest_simulated_warning": null | {... simulated:true, source:"simulation", active},
  // latest_warning stays "whichever came last" for compatibility (no "active" key).
  // A simulation never changes latest_real_warning, so a still-active real warning keeps priority.

  "current_touch": null | {
    "object_id": 3, "text": "Heinz ketchup", "state": "touching" | "held", "ts": 1763000001.6,
    "class_label": "bottle", "name": "Heinz ketchup", "named": true,
    "naming_status": "named", "released_ts": null,
    "speech": null | <speech entry for this object, from this touch>
  },
  // null when nothing is in a hand. A release clears it (another object still held takes over).
  "last_touch": null | <same shape; state may be "released" with released_ts>,

  "speech": null | {speech_id, text, status, ts, mode, kind, object_id, source, detail},
  // null until audio reports anything. ts is when this status began.

  "diagnostics": {
    "camera":  {status, detail, last_update_ts, mode, last_frame_ts, fps, width, height},
    "scene":   {status, detail, last_update_ts, mode},
    "naming":  {...}, "storage": {...}, "audio": {...},
    "hazard":  {...}   // always "unknown" unless not started: hazard checks report no health
  },
  "capabilities": {
    "last_seen": true,      // an engine bus is attached
    "thumbnails": true,     // frames are arriving to crop from
    "overlays": true,       // /video honours the overlay parameters
    "speech_status": true   // audio has reported speech or its status
  }
}
```

Each object also has `name`, `box` (`[x1, y1, x2, y2]` in 640×360 pixels),
`naming_status` (`pending` request outstanding, `named`, `fallback` the namer
answered without a specific name, `failed` timeout or error, `unknown` no
request seen) and `thumbnail_url` (`null`, or a same-origin URL whose `v=`
changes at most every 5 s).

Diagnostics rules:

- `status` is starting, active, degraded, offline or unknown; `mode` is real,
  fake or unknown (from app/ startup), so fakes are never presented as real.
- Camera: `active` while a frame arrived within `CAMERA_STALE_SECONDS` (2 s),
  `degraded` up to 10 s, then `offline`. `fps` is measured from capture
  timestamps and frame ids over about 3 s; `last_frame_ts` is the capture time
  of the newest frame received. Nulls when nothing has arrived.
- Scene: judged against the camera. No frames → `unknown` ("Idle"), not failed.
- Naming: from NameRequest/NameResult. No requests yet keeps the lifecycle
  status; a failed last answer is `degraded`; no answer for 8 s is `degraded`.
- Storage and audio: only what they report. Nothing reported → `unknown`.
- A connected `/ws` proves only the page connection. Speech `completed` means the
  engine returned; it does not prove anyone heard it.

## 5. Running it

| Command | What the page shows |
|---|---|
| `python -m app --fake vision` | recorded clip (camera mode fake), real scene, namer, storage, audio |
| `python -m app --fake vision namer storage audio` | everything offline-safe: fake namer, in-memory store, printed speech (all labelled fake) |
| `python -m app --only dashboard --fake vision scene` | the SPEC example; namer/storage/audio show "Not started in this run" |
| `python -m dashboard` | page only, no engine: last-touch search answers 503, diagnostics unknown |
