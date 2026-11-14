// Integration fixes Agent 4 made in the merged feature code (node --test).
import test from "node:test";
import assert from "node:assert/strict";
import { selectHealth } from "../../../dashboard/static/features/operations/selectors.js";

test("fake modules are labelled fake in the status strip and summary", () => {
  const entry = (mode) => ({ status: "active", detail: "x", last_update_ts: 100, mode });
  const state = {
    now: 100,
    diagnostics: {
      camera: { ...entry("fake"), last_frame_ts: 100, fps: 5, width: 640, height: 360 },
      scene: entry("real"),
      naming: entry("fake"),
      storage: entry("fake"),
      audio: entry("unknown"),
    },
  };
  const model = selectHealth({ state, connection: "connected", nowSeconds: 100 });
  const byId = Object.fromEntries(model.modules.map((m) => [m.id, m]));
  assert.equal(byId.camera.statusLabel, "Active (fake)");
  assert.equal(byId.storage.statusLabel, "Active (fake)");
  assert.equal(byId.scene.statusLabel, "Active");
  assert.equal(byId.audio.statusLabel, "Active");
  assert.match(model.summary, /3 running as fakes/);
});

import { selectCamera } from "../../../dashboard/static/features/experience/selectors.js";

test("a fake camera clip is never titled plain Live", () => {
  const camera = (mode) => ({
    status: "active", detail: "", last_update_ts: 100, mode,
    last_frame_ts: 100, fps: 5, width: 640, height: 360,
  });
  const view = (mode) =>
    selectCamera(
      { state: { now: 100, diagnostics: { camera: camera(mode) } }, connection: "connected", receivedAt: 1000 },
      "loaded",
      1000,
    );
  assert.equal(view("real").title, "Live");
  assert.equal(view("fake").title, "Live (recorded clip, not a camera)");
  assert.equal(view("fake").kind, "live");
});

import { selectWarnings, warningEmphasis } from "../../../dashboard/static/features/operations/selectors.js";

test("warning emphasis: urgent for an active real warning, simulated only alone, none otherwise", () => {
  const real = { id: 1, ts: 100, kind: "hazard", type: "vehicle", text: "Vehicle", simulated: false };
  const sim = { id: 2, ts: 101, kind: "hazard", type: "stairs_down", text: "Stairs", simulated: true };
  const pick = (state, now) => warningEmphasis(selectWarnings({ state, nowSeconds: now }));
  const base = { now: 101, hazard_active_seconds: 3 };
  assert.equal(pick({ ...base, latest_real_warning: real, latest_simulated_warning: sim }, 101), "urgent");
  assert.equal(pick({ ...base, latest_real_warning: null, latest_simulated_warning: sim }, 101), "simulated");
  assert.equal(pick({ ...base, latest_real_warning: real, latest_simulated_warning: null }, 110), null);
  assert.equal(pick({ ...base, latest_real_warning: null, latest_simulated_warning: null }, 101), null);
  assert.equal(warningEmphasis(null), null);
});
