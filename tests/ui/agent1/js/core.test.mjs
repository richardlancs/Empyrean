// Unit tests for dashboard/static/core. Run: node --test tests/ui/agent1/js/
import assert from "node:assert/strict";
import { test } from "node:test";

import { createAnnouncer } from "../../../../dashboard/static/core/announcer.js";
import { ApiError, createApiClient } from "../../../../dashboard/static/core/api-client.js";
import { ageSeconds, formatAge, serverNow } from "../../../../dashboard/static/core/clock.js";
import { loadFeature } from "../../../../dashboard/static/core/feature-loader.js";
import { normalizeState } from "../../../../dashboard/static/core/normalize.js";
import {
  THEME_PREFERENCE,
  createPreferences,
  resolveTheme,
} from "../../../../dashboard/static/core/preferences.js";
import { createSocketClient, dashboardSocketUrl } from "../../../../dashboard/static/core/socket-client.js";
import { createStore, immediateScheduler } from "../../../../dashboard/static/core/store.js";
import { FakeDocument, FakeWebSocket, ManualTimers, fakeFetch, fakeStorage } from "./fakes.mjs";

const BASE_STATE = { now: 1000, hazard_active_seconds: 5, latest_warning: null, events: [], objects: [] };

// ---------- normalize ----------

test("normalize: legacy state gains every optional field, with honest defaults", () => {
  const s = normalizeState(BASE_STATE);
  assert.equal(s.latest_real_warning, null);
  assert.equal(s.latest_simulated_warning, null);
  assert.equal(s.current_touch, null);
  assert.equal(s.speech, null);
  for (const key of ["camera", "scene", "naming", "storage", "audio"]) {
    assert.equal(s.diagnostics[key].status, "unknown", key);
    assert.equal(s.diagnostics[key].last_update_ts, null);
  }
  assert.equal(s.diagnostics.camera.fps, null);
  assert.deepEqual(s.capabilities, { last_seen: false, thumbnails: false, overlays: false, speech_status: false });
});

test("normalize: legacy latest_warning is split by its simulated flag", () => {
  const real = { id: 1, ts: 990, kind: "hazard", text: "Stairs", simulated: false };
  const sim = { ...real, id: 2, simulated: true };
  assert.equal(normalizeState({ ...BASE_STATE, latest_warning: real }).latest_real_warning.id, 1);
  const s = normalizeState({ ...BASE_STATE, latest_warning: sim });
  assert.equal(s.latest_real_warning, null);
  assert.equal(s.latest_simulated_warning.id, 2);
});

test("normalize: new warning fields win over latest_warning", () => {
  const real = { id: 1, ts: 990, simulated: false };
  const sim = { id: 2, ts: 995, simulated: true };
  const s = normalizeState({ ...BASE_STATE, latest_warning: sim, latest_real_warning: real, latest_simulated_warning: sim });
  assert.equal(s.latest_real_warning.id, 1);
  assert.equal(s.latest_simulated_warning.id, 2);
  assert.equal(s.latest_warning.id, 2, "latest_warning is kept for compatibility");
});

test("normalize: bad values degrade instead of breaking", () => {
  const s = normalizeState({
    ...BASE_STATE,
    events: "nope",
    objects: [null, 3, { object_id: 1 }],
    diagnostics: { camera: { status: "great", fps: "12" }, audio: { status: "active", detail: "" } },
    capabilities: { last_seen: "yes", thumbnails: true },
  });
  assert.deepEqual(s.events, []);
  assert.equal(s.objects.length, 1);
  assert.equal(s.diagnostics.camera.status, "unknown");
  assert.equal(s.diagnostics.camera.fps, null);
  assert.equal(s.diagnostics.audio.status, "active");
  assert.equal(s.diagnostics.audio.detail, null);
  assert.equal(s.capabilities.last_seen, false);
  assert.equal(s.capabilities.thumbnails, true);
});

test("normalize: result is deeply frozen and rejects non-objects", () => {
  const s = normalizeState({ ...BASE_STATE, objects: [{ object_id: 1, text: "Cup" }] });
  assert.ok(Object.isFrozen(s) && Object.isFrozen(s.objects) && Object.isFrozen(s.objects[0]));
  assert.throws(() => normalizeState(null), TypeError);
  assert.throws(() => normalizeState([1]), TypeError);
});

// ---------- store ----------

test("store: subscribe delivers the initial snapshot immediately", () => {
  const store = createStore({ schedule: immediateScheduler });
  const seen = [];
  store.subscribe((snap) => seen.push(snap));
  assert.deepEqual(seen, [{ state: null, connection: "connecting", receivedAt: null }]);
});

test("store: state and connection updates carry receivedAt; repeats are ignored", () => {
  let clock = 50;
  const store = createStore({ schedule: immediateScheduler, now: () => clock });
  const seen = [];
  store.subscribe((snap) => seen.push(snap));
  store.setConnection("connected");
  store.setConnection("connected");
  clock = 75;
  const state = normalizeState(BASE_STATE);
  store.receiveState(state);
  assert.equal(seen.length, 3);
  assert.equal(seen[1].connection, "connected");
  assert.equal(seen[2].state, state);
  assert.equal(seen[2].receivedAt, 75);
  assert.throws(() => store.setConnection("online"), TypeError);
});

test("store: updates inside one frame are coalesced into one notification", () => {
  const scheduled = [];
  const store = createStore({ schedule: (fn) => (scheduled.push(fn), () => {}) });
  const seen = [];
  store.subscribe((snap) => seen.push(snap));
  store.receiveState(normalizeState({ ...BASE_STATE, now: 1 }));
  store.receiveState(normalizeState({ ...BASE_STATE, now: 2 }));
  store.setConnection("connected");
  assert.equal(scheduled.length, 1);
  scheduled[0]();
  assert.equal(seen.length, 2);
  assert.equal(seen[1].state.now, 2);
  assert.equal(seen[1].connection, "connected");
});

test("store: unsubscribe is idempotent and a throwing listener does not stop others", () => {
  const errors = [];
  const store = createStore({ schedule: immediateScheduler, onListenerError: (e) => errors.push(e) });
  let calls = 0;
  const off = store.subscribe(() => {
    calls += 1;
  });
  store.subscribe((snap) => {
    if (snap.state) throw new Error("boom");
  });
  store.receiveState(normalizeState(BASE_STATE));
  assert.equal(calls, 2);
  assert.equal(errors.length, 1);
  off();
  off();
  assert.equal(store.listenerCount(), 1);
  store.destroy();
  assert.equal(store.listenerCount(), 0);
});

// ---------- socket client ----------

function socketHarness(extra = {}) {
  FakeWebSocket.reset();
  const timers = new ManualTimers();
  const states = [];
  const connections = [];
  const errors = [];
  const client = createSocketClient({
    url: "ws://test/ws",
    WebSocketImpl: FakeWebSocket,
    setTimer: timers.setTimeout,
    clearTimer: timers.clearTimeout,
    random: () => 0.5,
    onState: (s) => states.push(s),
    onConnectionChange: (c) => connections.push(c),
    onError: (e) => errors.push(e),
    ...extra,
  });
  return { client, timers, states, connections, errors };
}

test("socket: URL is same host, ws or wss by page scheme", () => {
  assert.equal(dashboardSocketUrl({ protocol: "http:", host: "localhost:8000" }), "ws://localhost:8000/ws");
  assert.equal(dashboardSocketUrl({ protocol: "https:", host: "demo.local" }), "wss://demo.local/ws");
});

test("socket: connecting -> connected, messages are normalized and delivered", () => {
  const { client, states, connections } = socketHarness();
  client.start();
  client.start(); // second start is a no-op
  assert.equal(FakeWebSocket.instances.length, 1);
  assert.deepEqual(connections, ["connecting"]);
  FakeWebSocket.last.serverOpen();
  FakeWebSocket.last.serverSend(BASE_STATE);
  assert.deepEqual(connections, ["connecting", "connected"]);
  assert.equal(states.length, 1);
  assert.equal(states[0].diagnostics.camera.status, "unknown");
});

test("socket: malformed messages are reported and dropped, not rendered", () => {
  const { client, states, errors } = socketHarness();
  client.start();
  FakeWebSocket.last.serverOpen();
  FakeWebSocket.last.serverSend("{not json");
  FakeWebSocket.last.serverSend("[1,2]");
  assert.equal(states.length, 0);
  assert.equal(errors.length, 2);
  assert.match(errors[0].message, /not valid state JSON/);
});

test("socket: reconnects with capped exponential backoff and resets after success", () => {
  const { client, timers, connections } = socketHarness({ minDelayMs: 500, maxDelayMs: 4000 });
  client.start();
  FakeWebSocket.last.serverOpen();
  const delays = [];
  for (let i = 0; i < 5; i += 1) {
    FakeWebSocket.last.serverClose();
    delays.push(timers.delays()[0]);
    timers.advance(delays.at(-1));
  }
  assert.deepEqual(delays, [500, 1000, 2000, 4000, 4000]);
  assert.equal(connections.at(-1), "reconnecting");
  FakeWebSocket.last.serverOpen();
  assert.equal(connections.at(-1), "connected");
  FakeWebSocket.last.serverClose();
  assert.equal(timers.delays()[0], 500, "backoff resets after a successful open");
});

test("socket: first failure before any open reports reconnecting, not connecting", () => {
  const { client, timers, connections } = socketHarness();
  client.start();
  FakeWebSocket.last.serverClose();
  timers.advance(10_000);
  assert.deepEqual(connections, ["connecting", "reconnecting"]);
});

test("socket: stop closes the socket and prevents any further reconnect", () => {
  const { client, timers } = socketHarness();
  client.start();
  FakeWebSocket.last.serverOpen();
  const ws = FakeWebSocket.last;
  client.stop();
  assert.ok(ws.closed);
  assert.equal(ws.onclose, null, "handlers detached");
  timers.advance(60_000);
  assert.equal(FakeWebSocket.instances.length, 1);
});

test("socket: reconnectNow skips the wait while disconnected", () => {
  const { client, timers } = socketHarness();
  client.start();
  FakeWebSocket.last.serverOpen();
  FakeWebSocket.last.serverClose();
  assert.equal(timers.pending, 1);
  client.reconnectNow();
  assert.equal(FakeWebSocket.instances.length, 2);
  assert.equal(timers.pending, 0);
});

// ---------- api client ----------

test("api: GET and POST JSON, 202 counts as success", async () => {
  const fetchImpl = fakeFetch({
    "GET /api/state": { json: BASE_STATE },
    "POST /api/last-seen": (path, init) => ({ status: 202, json: { request_id: "r1", echo: JSON.parse(init.body) } }),
  });
  const api = createApiClient({ fetchImpl });
  assert.equal((await api.request("/api/state")).now, 1000);
  const answer = await api.request("/api/last-seen", { method: "post", body: { query: "ketchup" } });
  assert.deepEqual(answer, { request_id: "r1", echo: { query: "ketchup" } });
  const sent = fetchImpl.calls[1].init;
  assert.equal(sent.method, "POST");
  assert.equal(sent.headers["Content-Type"], "application/json");
  assert.equal(sent.credentials, "same-origin");
});

test("api: non-2xx rejects with the server's message", async () => {
  const api = createApiClient({
    fetchImpl: fakeFetch({
      "POST /api/last-seen": { status: 422, json: { detail: [{ msg: "query must not be empty" }] } },
      "GET /api/broken": { status: 500, text: "" },
    }),
  });
  await assert.rejects(api.request("/api/last-seen", { method: "POST", body: { query: "" } }), (e) => {
    assert.ok(e instanceof ApiError);
    assert.equal(e.kind, "http");
    assert.equal(e.status, 422);
    assert.equal(e.message, "query must not be empty");
    return true;
  });
  await assert.rejects(api.request("/api/broken"), /HTTP 500/);
});

test("api: network failure and timeout become ApiError kinds", async () => {
  const down = createApiClient({
    fetchImpl: async () => {
      throw new TypeError("Failed to fetch");
    },
  });
  await assert.rejects(down.request("/api/state"), (e) => e.kind === "network");

  const slow = createApiClient({
    timeoutMs: 10,
    fetchImpl: (path, init) =>
      new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(new Error("aborted")))),
  });
  await assert.rejects(slow.request("/api/state"), (e) => e.kind === "timeout");
});

test("api: rejects cross-origin paths and GET bodies before sending", async () => {
  const fetchImpl = fakeFetch({});
  const api = createApiClient({ fetchImpl });
  await assert.rejects(api.request("https://evil.example/api"), TypeError);
  await assert.rejects(api.request("//evil.example/api"), TypeError);
  await assert.rejects(api.request("/api/state", { body: { a: 1 } }), TypeError);
  assert.equal(fetchImpl.calls.length, 0);
});

// ---------- announcer ----------

function announcerHarness() {
  const doc = new FakeDocument();
  const timers = new ManualTimers();
  const announcer = createAnnouncer({
    container: doc.body,
    now: () => timers.now,
    setTimer: timers.setTimeout,
    clearTimer: timers.clearTimeout,
  });
  const region = (p) => doc.body.find((el) => el.getAttribute("data-announcer") === p);
  return { doc, timers, announcer, region };
}

test("announcer: creates polite and assertive live regions", () => {
  const { region } = announcerHarness();
  assert.equal(region("polite").getAttribute("aria-live"), "polite");
  assert.equal(region("polite").getAttribute("role"), "status");
  assert.equal(region("assertive").getAttribute("aria-live"), "assertive");
  assert.equal(region("assertive").getAttribute("aria-atomic"), "true");
});

test("announcer: a key is announced once; snapshots repeating the same event stay silent", () => {
  const { announcer, timers, region } = announcerHarness();
  assert.equal(announcer.announce("Touching Heinz ketchup", { key: "touch:7" }), true);
  timers.advance(200);
  assert.equal(region("polite").textContent, "Touching Heinz ketchup");
  for (let i = 0; i < 20; i += 1) assert.equal(announcer.announce("Touching Heinz ketchup", { key: "touch:7" }), false);
  // Release then retouch is a new event with a new key, so it is announced again.
  assert.equal(announcer.announce("Touching Heinz ketchup", { key: "touch:9" }), true);
});

test("announcer: unkeyed repeats are suppressed within the window, allowed after it", () => {
  const { announcer, timers } = announcerHarness();
  assert.equal(announcer.announce("Lookup failed"), true);
  timers.advance(1000);
  assert.equal(announcer.announce("Lookup failed"), false);
  timers.advance(5000);
  assert.equal(announcer.announce("Lookup failed"), true);
});

test("announcer: messages in quick succession are combined, not lost", () => {
  const { announcer, timers, region } = announcerHarness();
  announcer.announce("Touching mug", { key: "a" });
  announcer.announce("Released mug", { key: "b" });
  timers.advance(200);
  assert.equal(region("polite").textContent, "Touching mug Released mug");
});

for (const order of ["polite first", "assertive first"]) {
  test(`announcer: a warning is read first and polite text waits for it (${order})`, () => {
    const { announcer, timers, region } = announcerHarness();
    const polite = () => announcer.announce("Touching mug", { key: "a" });
    const warn = () => announcer.announce("Warning: stairs ahead", { priority: "assertive", key: "hazard:1" });
    if (order === "polite first") {
      polite();
      warn();
    } else {
      warn();
      polite();
    }
    timers.advance(200);
    assert.equal(region("assertive").textContent, "Warning: stairs ahead");
    assert.equal(region("polite").textContent, "", "polite waits while the warning is read");
    timers.advance(1500);
    assert.equal(region("polite").textContent, "Touching mug", "polite text is delayed, not dropped");
  });
}

test("announcer: empty text and bad priority are rejected", () => {
  const { announcer } = announcerHarness();
  assert.equal(announcer.announce("   "), false);
  assert.throws(() => announcer.announce("x", { priority: "urgent" }), TypeError);
});

test("announcer: destroy removes regions and cancels pending writes", () => {
  const { doc, announcer, timers } = announcerHarness();
  announcer.announce("Touching mug", { key: "a" });
  announcer.destroy();
  timers.advance(500);
  assert.equal(doc.body.children.length, 0);
});

// ---------- preferences ----------

test("preferences: theme round-trips through storage", () => {
  const storage = fakeStorage();
  const prefs = createPreferences({ storage });
  prefs.set(THEME_PREFERENCE, "high-contrast");
  assert.equal(storage.data.get("empyrean.theme"), '"high-contrast"');
  assert.equal(resolveTheme(createPreferences({ storage }), () => ({ matches: false })), "high-contrast");
});

test("preferences: OS prefers-contrast is the default only when nothing is saved", () => {
  const more = (q) => ({ matches: q === "(prefers-contrast: more)" });
  assert.equal(resolveTheme(createPreferences({ storage: fakeStorage() }), more), "high-contrast");
  const storage = fakeStorage();
  createPreferences({ storage }).set(THEME_PREFERENCE, "light");
  assert.equal(resolveTheme(createPreferences({ storage }), more), "light");
  assert.equal(resolveTheme(createPreferences({ storage: fakeStorage() }), undefined), "light");
});

test("preferences: throwing storage falls back to memory and warns once", () => {
  const warnings = [];
  const prefs = createPreferences({ storage: fakeStorage({ throwing: true }), onWarning: (m) => warnings.push(m) });
  assert.equal(prefs.get(THEME_PREFERENCE, "light"), "light");
  prefs.set(THEME_PREFERENCE, "high-contrast");
  prefs.set(THEME_PREFERENCE, "high-contrast");
  assert.equal(prefs.get(THEME_PREFERENCE), "high-contrast");
  assert.equal(warnings.length, 1);
  const none = [];
  createPreferences({ storage: null, onWarning: (m) => none.push(m) });
  assert.equal(none.length, 1);
});

// ---------- clock ----------

test("clock: server time follows state.now plus browser time since arrival", () => {
  const snap = { state: { now: 1000 }, receivedAt: 5_000 };
  assert.equal(serverNow(snap, 7_500), 1002.5);
  assert.equal(ageSeconds(990, snap, 5_000), 10);
  assert.equal(ageSeconds(1010, snap, 5_000), 0, "future timestamps clamp to 0");
  assert.equal(ageSeconds(null, snap), null);
  assert.equal(formatAge(0.4), "just now");
  assert.equal(formatAge(12.9), "12 s ago");
  assert.equal(formatAge(185), "3 min ago");
  assert.equal(formatAge(7300), "2 h ago");
  assert.equal(formatAge(null), "");
});

// ---------- feature loader ----------

const SPEC = { name: "experience", url: "/static/features/experience/index.js", exportName: "mountExperience", areas: ["touch"] };

test("feature loader: mounts and returns the cleanup", async () => {
  let got = null;
  const cleanup = () => {};
  const result = await loadFeature(SPEC, {
    context: { roots: {} },
    importModule: async () => ({ mountExperience: (ctx) => ((got = ctx), cleanup) }),
  });
  assert.equal(result.status, "mounted");
  assert.equal(result.cleanup, cleanup);
  assert.deepEqual(got, { roots: {} });
});

test("feature loader: load failure, missing export and mount error are reported, never thrown", async () => {
  const reported = [];
  const onError = (e) => reported.push(e);
  const a = await loadFeature(SPEC, {
    context: {},
    onError,
    importModule: async () => {
      throw new TypeError("Failed to fetch dynamically imported module");
    },
  });
  const b = await loadFeature(SPEC, { context: {}, onError, importModule: async () => ({}) });
  const c = await loadFeature(SPEC, {
    context: {},
    onError,
    importModule: async () => ({
      mountExperience: () => {
        throw new Error("render bug");
      },
    }),
  });
  assert.deepEqual([a.status, b.status, c.status], ["failed", "failed", "failed"]);
  assert.deepEqual(reported.map((e) => e.phase), ["load", "load", "mount"]);
  assert.match(reported[1].cause.message, /does not export mountExperience/);
  assert.equal(reported[2].cause.message, "render bug");
});
