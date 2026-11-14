// FIXTURE HARNESS for the operations feature. Every value here is artificial.
// It builds a fake ctx (subscribe / request / announce) matching the shared contract and mounts
// the real feature module against it. Open via: python3 -m http.server 8765 (from the repo root)
// then http://localhost:8765/tests/ui/agent3/harness.html

import { mountOperations } from "../../../dashboard/static/features/operations/index.js";

const now = () => Date.now() / 1000;
let nextId = 1;

function diag(overrides = {}) {
  const t = now();
  const base = {
    camera: { status: "active", detail: null, last_update_ts: t, last_frame_ts: t - 0.1, fps: 14.9, width: 640, height: 360 },
    scene: { status: "active", detail: null, last_update_ts: t },
    naming: { status: "active", detail: null, last_update_ts: t - 420 },
    storage: { status: "active", detail: null, last_update_ts: t },
    audio: { status: "active", detail: "Fixture speaker (not real audio)", last_update_ts: t },
  };
  for (const [k, v] of Object.entries(overrides)) base[k] = v === null ? undefined : { ...base[k], ...v };
  return base;
}

const hazard = (ago, type = "stairs_down", simulated = false, source = "grok", confidence = 0.82) => ({
  id: nextId++,
  ts: now() - ago,
  kind: "hazard",
  type,
  text: { stairs_down: "Stairs", drop_off: "Drop ahead", vehicle: "Vehicle", obstacle: "Obstacle" }[type],
  detail: simulated ? "" : `${source}, ${Math.round(confidence * 100)}%`,
  simulated,
});
const touch = (ago, text = "FIXTURE Heinz ketchup", detail = "") => ({
  id: nextId++, ts: now() - ago, kind: "touch", type: null, text, detail, simulated: false,
});

// Server-side fixture state (what a real /api/state would hold).
let server = null;

function snapshot(extra = {}) {
  const hz = server.events.filter((e) => e.kind === "hazard");
  return {
    now: now(),
    hazard_active_seconds: 3,
    latest_warning: hz[0] || null,
    latest_real_warning: server.legacy ? undefined : hz.find((e) => !e.simulated) || null,
    latest_simulated_warning: server.legacy ? undefined : hz.find((e) => e.simulated) || null,
    events: server.events.slice(0, 10),
    objects: [],
    diagnostics: server.legacy ? undefined : server.diagnostics(),
    ...extra,
  };
}

const SCENARIOS = {
  "Quiet, all active": () => ({ events: [touch(40), touch(95, "FIXTURE coffee mug")], diagnostics: () => diag() }),
  "Real warning active": () => ({ events: [hazard(0.5, "vehicle", false, "yolo", 0.91), touch(30)], diagnostics: () => diag() }),
  "Real + simulated together": () => ({
    events: [hazard(0.2, "stairs_down", true), hazard(1, "drop_off", false, "grok", 0.74), touch(20)],
    diagnostics: () => diag(),
  }),
  "Expired warning": () => ({ events: [touch(5), hazard(140, "obstacle", false, "grok", 0.66), hazard(400, "stairs_down", true)], diagnostics: () => diag() }),
  "Repeated warnings": () => ({
    events: [hazard(0.5), hazard(4), hazard(8), hazard(12), touch(15), touch(16), touch(200, "FIXTURE remote")],
    diagnostics: () => diag(),
  }),
  "Partial module failure": () => ({
    events: [touch(3, "FIXTURE banana", "not named yet")],
    diagnostics: () =>
      diag({
        storage: { status: "offline", detail: "FIXTURE: database host unreachable since 14:02." },
        naming: { status: "degraded", detail: "FIXTURE: 3 of the last 5 naming requests timed out; plain names used." },
        audio: { status: "unknown", detail: null, last_update_ts: null },
        camera: { last_frame_ts: now() - 9, fps: 0.4 },
      }),
  }),
  "Unknown telemetry (old server)": () => ({ legacy: true, events: [touch(10)], diagnostics: () => undefined }),
  "Overflowing history, long names": () => ({
    events: Array.from({ length: 10 }, (_, i) =>
      i % 3 === 0
        ? hazard(i * 7 + 1, ["stairs_down", "drop_off", "vehicle", "obstacle"][i % 4], i % 2 === 0)
        : touch(i * 7 + 1, `FIXTURE Extraordinarily long product name number ${i} — Organic Unsweetened Vanilla Almond Breeze Original 1.89 L`),
    ),
    diagnostics: () => diag(),
  }),
  "Empty, no data yet": () => ({ events: [], diagnostics: () => diag({ camera: { status: "starting", last_frame_ts: null, fps: null, width: null, height: null } }) }),
};

// ---------- fake ctx

const listeners = new Set();
let store = { state: null, connection: "connecting", receivedAt: null };
function emit(patch) {
  store = { ...store, ...patch };
  for (const l of listeners) l(store);
}
function pushState() {
  emit({ state: snapshot(), receivedAt: Date.now() });
}

const logEl = document.getElementById("fixture-announcements");
const announcedKeys = new Set();
function announce(text, { priority = "polite", key } = {}) {
  const dedupeKey = key || text;
  if (announcedKeys.has(dedupeKey)) return;
  announcedKeys.add(dedupeKey);
  const li = document.createElement("li");
  li.textContent = `[${priority}] ${text}  (key: ${dedupeKey})`;
  logEl.prepend(li);
}

class HttpError extends Error {
  constructor(status) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

async function request(path, { method = "GET" } = {}) {
  const mode = document.getElementById("fixture-request").value;
  if (path !== "/api/simulate-alert" || method !== "POST") throw new HttpError(404);
  await new Promise((r) => setTimeout(r, mode === "slow" ? 2000 : 250));
  if (mode === "http") throw new HttpError(500);
  if (mode === "network") throw new TypeError("Failed to fetch");
  server.events.unshift(hazard(0, "stairs_down", true));
  const result = snapshot();
  setTimeout(pushState, 400); // the socket delivers the same state again: must not duplicate
  return result;
}

const ctx = {
  roots: {
    health: document.getElementById("health-panel"),
    warning: document.getElementById("warning-panel"),
    events: document.getElementById("events-panel"),
    demo: document.getElementById("demo-panel"),
  },
  subscribe(cb) {
    listeners.add(cb);
    cb(store);
    return () => listeners.delete(cb);
  },
  request,
  announce,
};

// ---------- controls

function load(name) {
  server = SCENARIOS[name]();
  if (store.connection === "connecting") emit({ connection: "connected" });
  pushState();
}

const scenarios = document.getElementById("fixture-scenarios");
for (const name of Object.keys(SCENARIOS)) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = name;
  b.addEventListener("click", () => load(name));
  scenarios.append(b);
}

const ACTIONS = {
  "Push real warning": () => { server.events.unshift(hazard(0, "obstacle", false, "grok", 0.7)); pushState(); },
  "Push simulated via socket": () => { server.events.unshift(hazard(0, "drop_off", true)); pushState(); },
  "Push touch": () => { server.events.unshift(touch(0, `FIXTURE touch ${nextId}`)); pushState(); },
  "Burst 15 touches (one update)": () => {
    for (let i = 0; i < 15; i += 1) server.events.unshift(touch(0, `FIXTURE burst ${nextId}`));
    pushState();
  },
  "Replay same snapshot": () => emit({ state: { ...store.state }, receivedAt: Date.now() }),
  "Reconnect cycle": () => {
    emit({ connection: "reconnecting" });
    setTimeout(() => { emit({ connection: "connected" }); pushState(); }, 1500);
  },
};
const actions = document.getElementById("fixture-actions");
for (const [name, fn] of Object.entries(ACTIONS)) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = name;
  b.addEventListener("click", fn);
  actions.append(b);
}

document.getElementById("fixture-connection").addEventListener("change", (e) => emit({ connection: e.target.value }));
document.getElementById("fixture-contrast").addEventListener("change", (e) => {
  document.documentElement.dataset.theme = e.target.checked ? "high-contrast" : "light";
});

window.__fixture = { load, ACTIONS, emit, get store() { return store; }, get server() { return server; } };
window.__cleanup = mountOperations(ctx);
const initial = new URLSearchParams(location.search).get("scenario");
load(initial && SCENARIOS[initial] ? initial : "Quiet, all active");

// Mirror the shell's theme-boot: prefers-contrast: more starts in high contrast.
if (window.matchMedia && window.matchMedia("(prefers-contrast: more)").matches) {
  document.documentElement.dataset.theme = "high-contrast";
  document.getElementById("fixture-contrast").checked = true;
} else {
  document.documentElement.dataset.theme = "light";
}
