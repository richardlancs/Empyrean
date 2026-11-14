// Preview harness: a fake ctx that feeds artificial FIXTURE snapshots to
// mountExperience. It mimics the shared contract (subscribe/request/announce)
// so the feature can be exercised before Agent 1's shell and Agent 4's API land.

import { mountExperience } from "/static/features/experience/index.js";

const now = () => Date.now() / 1000;
// Event times are anchored to when the scenario started, like real events.
let t0 = now();
const at = (ago) => t0 - ago;
const CAPS = { last_seen: true, thumbnails: true, overlays: true, speech_status: true };

function camera(age = 0.1, extra = {}) {
  return { status: "active", detail: "", last_update_ts: now(), last_frame_ts: now() - age, fps: 9.8, width: 640, height: 360, ...extra };
}
function obj(id, text, state, extra = {}) {
  return {
    object_id: id,
    text,
    class_label: extra.class_label || text,
    named: extra.named ?? true,
    state,
    last_seen_ts: now() - (state === "lost" ? 1.4 : 0),
    naming_status: extra.naming_status ?? "named",
    thumbnail_url: `/api/objects/${id}/thumbnail`,
    ...extra,
  };
}
const TABLE = () => [obj(2, "FIXTURE Cheerios cereal", "idle"), obj(5, "FIXTURE blue mug", "idle")];

function base(over = {}) {
  return {
    now: now(),
    hazard_active_seconds: 5,
    latest_warning: null,
    latest_real_warning: null,
    latest_simulated_warning: null,
    events: [],
    objects: TABLE(),
    current_touch: null,
    speech: null,
    diagnostics: { camera: camera() },
    capabilities: CAPS,
    ...over,
  };
}

const touchEvent = (text, ago) => ({ id: Math.random(), ts: at(ago), kind: "touch", type: null, text, detail: "", simulated: false });

const SCENARIOS = {
  "Empty (nothing touched yet)": () => base(),
  "Touching, named": () =>
    base({
      current_touch: { object_id: 1, text: "FIXTURE Heinz ketchup", state: "touching", ts: at(0.5) },
      objects: [obj(1, "FIXTURE Heinz ketchup", "touching"), ...TABLE()],
      speech: { text: "FIXTURE Heinz ketchup", status: "speaking", ts: at(0.3), mode: "real", object_id: 1, source: "touch" },
      events: [touchEvent("FIXTURE Heinz ketchup", 0.5)],
    }),
  "Holding": () =>
    base({
      current_touch: { object_id: 1, text: "FIXTURE Heinz ketchup", state: "held", ts: at(3) },
      objects: [obj(1, "FIXTURE Heinz ketchup", "held"), ...TABLE()],
      speech: { text: "FIXTURE Heinz ketchup", status: "completed", ts: at(2), mode: "real", object_id: 1 },
      events: [touchEvent("FIXTURE Heinz ketchup", 3)],
    }),
  "Released (last touched shown separately)": () =>
    base({
      objects: [obj(1, "FIXTURE Heinz ketchup", "idle"), ...TABLE()],
      speech: { text: "FIXTURE Heinz ketchup", status: "completed", ts: at(6), mode: "real", object_id: 1 },
      events: [touchEvent("FIXTURE Heinz ketchup", 8)],
    }),
  "Naming pending, plain label spoken": () =>
    base({
      current_touch: { object_id: 7, text: "bottle", state: "touching", ts: at(0.2) },
      objects: [obj(7, "bottle", "touching", { named: false, naming_status: "pending", thumbnail_url: null }), ...TABLE()],
      speech: { text: "bottle", status: "speaking", ts: at(0.1), mode: "real", object_id: 7 },
      events: [touchEvent("bottle", 0.2)],
    }),
  "Generic fallback and naming failure": () =>
    base({
      objects: [
        obj(8, "cup", "idle", { named: false, naming_status: "fallback" }),
        obj(9, "bottle", "idle", { named: false, naming_status: "failed", thumbnail_url: "/api/objects/404/thumbnail" }),
        obj(10, "book", "new", { named: false, naming_status: "unknown", thumbnail_url: null }),
      ],
    }),
  "Speech interrupted by a hazard": () =>
    base({
      current_touch: { object_id: 1, text: "FIXTURE Heinz ketchup", state: "touching", ts: at(1.2) },
      objects: [obj(1, "FIXTURE Heinz ketchup", "touching"), ...TABLE()],
      speech: { text: "FIXTURE Heinz ketchup", status: "interrupted", ts: at(1.1), mode: "real", object_id: 1 },
      latest_real_warning: { id: 99, ts: at(1), kind: "hazard", type: "stairs_down", text: "Stairs", detail: "grok, 80%", simulated: false },
    }),
  "Speech failed": () => base({ speech: { text: "FIXTURE mug", status: "failed", ts: at(2), mode: "real" } }),
  "Log-only (fake) audio": () =>
    base({
      current_touch: { object_id: 5, text: "FIXTURE blue mug", state: "touching", ts: at(1) },
      speech: { text: "FIXTURE blue mug", status: "completed", ts: at(0.5), mode: "fake" },
    }),
  "Lost object and long name": () =>
    base({
      objects: [
        obj(11, "FIXTURE Trader Joe's organic creamy salted peanut butter jar, large", "idle"),
        obj(12, "FIXTURE remote control", "lost"),
        ...TABLE(),
      ],
    }),
  "Stale camera (frames stopped)": () => base({ diagnostics: { camera: camera(12, { status: "degraded", fps: 0 }) } }),
  "Waiting for first frame": () => base({ objects: [], diagnostics: { camera: { status: "starting", detail: "Opening camera", last_update_ts: now(), last_frame_ts: null, fps: null, width: null, height: null } } }),
  "Old backend (no new fields)": () => ({
    now: now(),
    hazard_active_seconds: 5,
    latest_warning: null,
    events: [touchEvent("bottle", 20)],
    objects: [{ object_id: 3, text: "bottle", class_label: "bottle", named: false, state: "touching", last_seen_ts: now() }],
  }),
  "Capabilities off": () =>
    base({ capabilities: { last_seen: false, thumbnails: false, overlays: false, speech_status: false }, speech: null }),
};

// --- fake shared context ---------------------------------------------------
const listeners = new Set();
let current = { state: null, connection: "connecting", receivedAt: null };
let scenarioName = Object.keys(SCENARIOS)[0];
let freezeAt = null; // stale-camera scenario: stop sending updates

function publish(patch) {
  current = { ...current, ...patch };
  for (const fn of listeners) fn(current);
}
function pushScenario() {
  if (arguments[0] === "reset") t0 = now();
  publish({ state: SCENARIOS[scenarioName](), receivedAt: Date.now() });
}

const ctx = {
  roots: {
    touch: document.getElementById("touch-panel"),
    camera: document.getElementById("camera-panel"),
    objects: document.getElementById("objects-panel"),
    find: document.getElementById("find-panel"),
  },
  subscribe(fn) {
    listeners.add(fn);
    fn(current);
    return () => listeners.delete(fn);
  },
  async request(path, { method = "GET", body } = {}) {
    const res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const err = new Error(`HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  },
  announce(text, { priority = "polite", key } = {}) {
    const li = document.createElement("li");
    li.textContent = `[${priority}] ${text} (key ${key})`;
    document.getElementById("announcements").prepend(li);
  },
};

mountExperience(ctx);

// Simulated "engine" ticking at about 5 snapshots a second, like the backend.
setTimeout(() => {
  publish({ connection: "connected" });
  pushScenario();
}, 600);
setInterval(() => {
  if (current.connection !== "connected") return;
  if (scenarioName.startsWith("Stale")) {
    // Snapshots keep arriving, but last_frame_ts stays frozen.
    freezeAt ??= current.state?.diagnostics?.camera?.last_frame_ts;
    const state = SCENARIOS[scenarioName]();
    state.diagnostics.camera.last_frame_ts = freezeAt;
    publish({ state, receivedAt: Date.now() });
    return;
  }
  freezeAt = null;
  pushScenario();
}, 200);

const select = document.getElementById("scenario");
for (const name of Object.keys(SCENARIOS)) select.append(new Option(name, name));
select.addEventListener("change", () => {
  scenarioName = select.value;
  freezeAt = null;
  pushScenario("reset");
});
document.getElementById("drop").addEventListener("click", () => {
  publish({ connection: current.connection === "connected" ? "reconnecting" : "connected" });
});
document.getElementById("play").addEventListener("click", () => {
  const steps = ["Touching, named", "Holding", "Released (last touched shown separately)", "Touching, named"];
  steps.forEach((name, i) =>
    setTimeout(() => {
      scenarioName = name;
      select.value = name;
      pushScenario("reset");
    }, i * 2000),
  );
});

// Expose for automated checks.
window.__harness = { setScenario(name) { scenarioName = name; select.value = name; freezeAt = null; pushScenario("reset"); }, ctx, scenarios: Object.keys(SCENARIOS) };
