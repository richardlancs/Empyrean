// Composition tests: app.js + shell + store + socket + features, on a fake DOM.
import assert from "node:assert/strict";
import { test } from "node:test";

import { FEATURES, startDashboard } from "../../../../dashboard/static/app.js";
import { AREAS } from "../../../../dashboard/static/components/app-shell.js";
import { FakeDocument, FakeWebSocket, fakeFetch, fakeStorage, flushAsync } from "./fakes.mjs";

const STATE = { now: 1000, hazard_active_seconds: 5, latest_warning: null, events: [], objects: [] };

function fakeWindow({ storage = fakeStorage(), prefersMore = false } = {}) {
  const doc = new FakeDocument();
  const app = doc.createElement("div");
  app.setAttribute("id", "app");
  doc.body.append(app);
  const listeners = new Map();
  return {
    document: doc,
    location: { protocol: "http:", host: "localhost:8000" },
    localStorage: storage,
    WebSocket: FakeWebSocket,
    fetch: fakeFetch({ "GET /api/state": { json: STATE } }),
    matchMedia: (q) => ({ matches: prefersMore && q === "(prefers-contrast: more)" }),
    addEventListener: (t, l) => listeners.set(t, l),
    removeEventListener: (t) => listeners.delete(t),
    listeners,
  };
}

function recordingFeatures() {
  const calls = { experience: [], operations: [], cleanups: [] };
  const modules = {
    "/static/features/experience/index.js": {
      mountExperience(ctx) {
        calls.experience.push(ctx);
        ctx.roots.touch.append("touch content");
        ctx.subscribe((snap) => calls.experience.push(snap));
        return () => calls.cleanups.push("experience");
      },
    },
    "/static/features/operations/index.js": {
      mountOperations(ctx) {
        calls.operations.push(ctx);
        ctx.subscribe((snap) => calls.operations.push(snap));
        // returns no cleanup: the app must still release its subscription
      },
    },
  };
  return { calls, importModule: async (url) => modules[url] };
}

test("app: shell exposes all eight mounts with the contract ids, in reading order", async () => {
  FakeWebSocket.reset();
  const win = fakeWindow();
  const { calls, importModule } = recordingFeatures();
  const app = startDashboard({ win, importModule });
  await app.ready;
  const ctx = calls.experience[0];
  assert.deepEqual(Object.keys(ctx.roots), AREAS.map((a) => a.key));
  const ids = Object.values(ctx.roots).map((el) => el.id);
  assert.deepEqual(ids, [
    "health-panel", "warning-panel", "touch-panel", "camera-panel",
    "objects-panel", "find-panel", "events-panel", "demo-panel",
  ]);
  for (const key of ["subscribe", "request", "announce"]) assert.equal(typeof ctx[key], "function");
  assert.ok(Object.isFrozen(ctx) && Object.isFrozen(ctx.roots));
  // Mounted feature areas lose their loading placeholder and aria-busy.
  assert.equal(ctx.roots.touch.hasAttribute("aria-busy"), false);
  assert.equal(ctx.roots.touch.textContent, "touch content");
  app.destroy();
});

test("app: features get null state first, then normalized socket state", async () => {
  FakeWebSocket.reset();
  const win = fakeWindow();
  const { calls, importModule } = recordingFeatures();
  const app = startDashboard({ win, importModule });
  await app.ready;
  assert.equal(FakeWebSocket.instances.length, 1, "exactly one socket");
  assert.equal(FakeWebSocket.last.url, "ws://localhost:8000/ws");
  const first = calls.experience[1];
  assert.deepEqual(first, { state: null, connection: "connecting", receivedAt: null });
  FakeWebSocket.last.serverOpen();
  FakeWebSocket.last.serverSend(STATE);
  await flushAsync();
  const last = calls.operations.at(-1);
  assert.equal(last.connection, "connected");
  assert.equal(last.state.diagnostics.audio.status, "unknown");
  assert.equal(typeof last.receivedAt, "number");
  app.destroy();
});

test("app: a failed feature shows a visible error in its own mounts only", async () => {
  FakeWebSocket.reset();
  const win = fakeWindow();
  const errors = [];
  const original = console.error;
  console.error = (e) => errors.push(e);
  try {
    const app = startDashboard({
      win,
      importModule: async (url) => {
        if (url.includes("operations")) throw new TypeError("Failed to fetch dynamically imported module");
        return { mountExperience: (ctx) => void ctx.roots.touch.append("ok") };
      },
    });
    const results = await app.ready;
    assert.deepEqual(results.map((r) => r.status), ["mounted", "failed"]);
    const doc = win.document;
    for (const id of ["health-panel", "warning-panel", "events-panel", "demo-panel"]) {
      const slot = doc.getElementById(id);
      assert.match(slot.textContent, /Could not show/, id);
      assert.match(slot.textContent, /Failed to fetch dynamically imported module/, id);
    }
    assert.equal(doc.getElementById("touch-panel").textContent, "ok");
    assert.equal(errors.length, 1, "failure is logged, not swallowed");
    app.destroy();
  } finally {
    console.error = original;
  }
});

test("app: destroy runs cleanups, releases every subscription and closes the socket", async () => {
  FakeWebSocket.reset();
  const win = fakeWindow();
  const { calls, importModule } = recordingFeatures();
  const app = startDashboard({ win, importModule });
  await app.ready;
  assert.equal(app.store.listenerCount(), 2);
  app.destroy();
  assert.deepEqual(calls.cleanups, ["experience"]);
  assert.equal(app.store.listenerCount(), 0);
  assert.ok(FakeWebSocket.last.closed);
  assert.equal(win.listeners.has("online"), false);
  assert.equal(win.document.getElementById("app").children.length, 0);
});

test("app: contrast toggle applies and saves the theme; saved theme wins at start", async () => {
  FakeWebSocket.reset();
  const storage = fakeStorage();
  const win = fakeWindow({ storage });
  const app = startDashboard({ win, importModule: async () => ({}) });
  await app.ready;
  const html = win.document.documentElement;
  assert.equal(html.getAttribute("data-theme"), "light");
  const toggle = win.document.body.find((el) => el.getAttribute("data-shell-control") === "contrast");
  assert.equal(toggle.getAttribute("type"), "button");
  assert.equal(toggle.getAttribute("aria-pressed"), "false");
  toggle.dispatch("click");
  assert.equal(html.getAttribute("data-theme"), "high-contrast");
  assert.equal(toggle.getAttribute("aria-pressed"), "true");
  assert.equal(storage.data.get("empyrean.theme"), '"high-contrast"');
  app.destroy();

  const again = startDashboard({ win: fakeWindow({ storage }), importModule: async () => ({}) });
  assert.equal(again.store.getSnapshot().connection, "connecting");
  again.destroy();
});

test("app: works when storage throws (private mode)", async () => {
  FakeWebSocket.reset();
  const win = fakeWindow({ storage: fakeStorage({ throwing: true }), prefersMore: true });
  const warn = console.warn;
  console.warn = () => {};
  try {
    const app = startDashboard({ win, importModule: async () => ({}) });
    await app.ready;
    assert.equal(win.document.documentElement.getAttribute("data-theme"), "high-contrast");
    app.destroy();
  } finally {
    console.warn = warn;
  }
});

test("app: connection loss and restore are each announced once", async () => {
  FakeWebSocket.reset();
  const win = fakeWindow();
  const app = startDashboard({ win, importModule: async () => ({}) });
  await app.ready;
  const polite = () => win.document.body.find((el) => el.getAttribute("data-announcer") === "polite");
  FakeWebSocket.last.serverOpen();
  FakeWebSocket.last.serverClose();
  await new Promise((r) => setTimeout(r, 150));
  assert.equal(polite().textContent, "Dashboard connection lost. Reconnecting.");
  app.socket.reconnectNow();
  FakeWebSocket.last.serverOpen();
  await new Promise((r) => setTimeout(r, 150));
  assert.equal(polite().textContent, "Dashboard connection restored.");
  app.destroy();
});

test("app: FEATURES matches the shared contract", () => {
  assert.deepEqual(
    FEATURES.map((f) => [f.url, f.exportName, [...f.areas]]),
    [
      ["/static/features/experience/index.js", "mountExperience", ["touch", "camera", "objects", "find"]],
      ["/static/features/operations/index.js", "mountOperations", ["health", "warning", "events", "demo"]],
    ],
  );
});
