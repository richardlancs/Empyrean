// Unit tests for dashboard/static/features/operations/selectors.js. Run: node --test tests/ui/agent3/
// All data here is artificial fixture data.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  HistoryModel,
  emptyHistoryText,
  eventKey,
  formatRelative,
  groupEntries,
  pendingText,
  selectHealth,
  selectWarnings,
  warningDetails,
  warningKey,
} from "../../../dashboard/static/features/operations/selectors.js";

const NOW = 1_800_000_000;
const hazard = (ts, type = "stairs_down", simulated = false, extra = {}) => ({
  id: ts, ts, kind: "hazard", type, text: "Stairs", detail: simulated ? "" : "grok, 82%", simulated, ...extra,
});
const touch = (ts, text = "FIXTURE ketchup") => ({ id: ts, ts, kind: "touch", type: null, text, detail: "", simulated: false });

test("warning identity ignores server id but separates real from simulated", () => {
  assert.equal(warningKey({ ...hazard(NOW), id: 1 }), warningKey({ ...hazard(NOW), id: 99 }));
  assert.notEqual(warningKey(hazard(NOW)), warningKey(hazard(NOW, "stairs_down", true)));
  assert.equal(eventKey(hazard(NOW)), warningKey(hazard(NOW)));
});

test("an active real warning is kept when a simulation is newer (old server, single latest_warning)", () => {
  const real = hazard(NOW - 1);
  const sim = hazard(NOW, "stairs_down", true);
  const state = { now: NOW, hazard_active_seconds: 3, latest_warning: sim, events: [sim, real] };
  const w = selectWarnings({ state, nowSeconds: NOW });
  assert.equal(w.real.warning, real);
  assert.ok(w.real.active);
  assert.equal(w.sim.warning, sim);
});

test("remembered real warning survives once the server log no longer holds it", () => {
  const real = hazard(NOW - 1);
  const sim = hazard(NOW, "stairs_down", true);
  const state = { now: NOW, latest_warning: sim, events: [sim] };
  const w = selectWarnings({ state, remembered: { real }, nowSeconds: NOW });
  assert.equal(w.real.warning, real);
});

test("new fields latest_real_warning / latest_simulated_warning are preferred", () => {
  const real = hazard(NOW - 2, "vehicle");
  const state = { now: NOW, latest_real_warning: real, latest_simulated_warning: null, latest_warning: null, events: [] };
  const w = selectWarnings({ state, nowSeconds: NOW });
  assert.equal(w.real.warning.type, "vehicle");
  assert.equal(w.sim, null);
});

test("expiry is based on hazard_active_seconds", () => {
  const state = { now: NOW, hazard_active_seconds: 3, latest_warning: hazard(NOW - 10), events: [] };
  const w = selectWarnings({ state, nowSeconds: NOW });
  assert.equal(w.real.active, false);
});

test("warning details explain confidence without calling it a safety probability", () => {
  const rows = warningDetails(hazard(NOW));
  const conf = rows.find((r) => r.label === "Model confidence");
  assert.equal(conf.value, "82%");
  assert.match(conf.note, /not the chance/);
  assert.equal(rows.find((r) => r.label === "Source").value, "Grok vision check");
  const simRows = warningDetails(hazard(NOW, "stairs_down", true));
  assert.match(simRows[0].value, /simulated/);
});

test("missing diagnostics are unknown, never active", () => {
  const h = selectHealth({ state: { now: NOW }, connection: "connected", nowSeconds: NOW });
  assert.ok(h.modules.every((m) => m.status === "unknown" && m.tone === "unknown"));
  assert.match(h.summary, /0 of 5 modules active/);
  assert.match(h.summary, /5 not reported/);
});

test("connected socket does not make modules healthy, and disconnection marks values as last known", () => {
  const state = {
    now: NOW,
    diagnostics: {
      camera: { status: "active", detail: null, last_update_ts: NOW, last_frame_ts: NOW - 0.2, fps: 14.8, width: 640, height: 360 },
      scene: { status: "active", detail: null, last_update_ts: NOW },
      naming: { status: "active", detail: null, last_update_ts: NOW - 600 },
      storage: { status: "offline", detail: "Database unreachable", last_update_ts: NOW },
      audio: { status: "unknown", detail: null, last_update_ts: null },
    },
  };
  const h = selectHealth({ state, connection: "connected", nowSeconds: NOW });
  assert.equal(h.connection.label, "Dashboard connected");
  assert.equal(h.modules.find((m) => m.id === "storage").tone, "error");
  // Naming idle for 10 minutes is still active, not failed.
  assert.equal(h.modules.find((m) => m.id === "naming").statusLabel, "Active");
  assert.ok(h.attention);
  const lost = selectHealth({ state, connection: "reconnecting", nowSeconds: NOW });
  assert.match(lost.modules[0].statusLabel, /last known/);
  assert.notEqual(lost.modules[0].tone, "ok");
});

test("camera freshness: old last_frame_ts shows no recent frames", () => {
  const state = { now: NOW, diagnostics: { camera: { status: "active", last_frame_ts: NOW - 30, last_update_ts: NOW } } };
  const cam = selectHealth({ state, connection: "connected", nowSeconds: NOW }).modules[0];
  assert.equal(cam.statusLabel, "No recent frames");
  assert.equal(cam.tone, "caution");
});

test("history dedupes replays and keeps a bounded memory", () => {
  const h = new HistoryModel({ limit: 5 });
  const events = [touch(NOW - 1), hazard(NOW - 2)];
  assert.equal(h.ingest(events).length, 2);
  assert.equal(h.ingest(events).length, 0); // reconnect replay
  for (let i = 0; i < 10; i += 1) h.ingest([touch(NOW + i)]);
  assert.equal(h.entries.length, 5);
  assert.equal(h.keys.size, 5);
});

test("pause freezes the view and counts new events exactly", () => {
  const h = new HistoryModel();
  h.ingest([touch(NOW)]);
  h.pause();
  h.ingest([touch(NOW + 1), touch(NOW)]);
  h.ingest([touch(NOW + 2), touch(NOW + 1), touch(NOW)]);
  assert.equal(h.visible().length, 1);
  assert.equal(h.pendingCount, 2);
  assert.equal(h.pendingInexact, false);
  assert.equal(pendingText(h.pendingCount, h.pendingInexact), "2 new events since pausing.");
  h.resume();
  assert.equal(h.visible().length, 3);
});

test("pause reports an inexact count when the server log rolled past what we knew", () => {
  const h = new HistoryModel();
  h.ingest([touch(NOW)]);
  h.pause();
  const burst = Array.from({ length: 10 }, (_, i) => touch(NOW + 100 - i));
  h.ingest(burst, { retention: 10 });
  assert.equal(h.pendingInexact, true);
  assert.match(pendingText(h.pendingCount, true), /At least 10/);
});

test("clear hides only what is known now; new events still appear; restore brings them back", () => {
  const h = new HistoryModel();
  h.ingest([touch(NOW), touch(NOW - 1)]);
  h.clear(NOW);
  assert.equal(h.visible().length, 0);
  assert.equal(h.entries.length, 2); // nothing deleted
  h.ingest([touch(NOW + 1), touch(NOW)]);
  assert.equal(h.visible().length, 1);
  h.restore();
  assert.equal(h.visible().length, 3);
  assert.match(emptyHistoryText("all", { cleared: true, totalKnown: 3 }), /cleared/);
});

test("repeats group with a count, keep every occurrence, and keep a stable key", () => {
  const h = new HistoryModel();
  h.ingest([hazard(NOW - 20), hazard(NOW - 40), touch(NOW - 50)]);
  const first = groupEntries(h.visible());
  assert.equal(first.length, 2);
  assert.equal(first[0].items.length, 2);
  h.ingest([hazard(NOW)]);
  const second = groupEntries(h.visible());
  assert.equal(second[0].items.length, 3);
  assert.equal(second[0].key, first[0].key);
  // Real and simulated never merge.
  h.ingest([hazard(NOW + 1, "stairs_down", true)]);
  assert.equal(groupEntries(h.visible())[0].items[0].event.simulated, true);
  assert.equal(groupEntries(h.visible())[0].items.length, 1);
});

test("filters", () => {
  const h = new HistoryModel();
  h.ingest([touch(NOW), hazard(NOW - 1)]);
  assert.equal(groupEntries(h.visible(), "touch").length, 1);
  assert.equal(groupEntries(h.visible(), "hazard")[0].items[0].event.kind, "hazard");
  assert.equal(emptyHistoryText("touch", {}), "No touches yet.");
});

test("relative time", () => {
  assert.equal(formatRelative(1), "just now");
  assert.equal(formatRelative(12.7), "12 s ago");
  assert.equal(formatRelative(185), "3 min ago");
  assert.equal(formatRelative(NaN), "time unknown");
});
