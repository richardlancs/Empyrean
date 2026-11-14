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
