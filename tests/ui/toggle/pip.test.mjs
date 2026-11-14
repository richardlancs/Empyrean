// Pip's pose and help text from confirmed state. Run: node --test tests/ui/toggle/
// All data here is artificial fixture data.

import assert from "node:assert/strict";
import { test } from "node:test";

import { PIP_TIP, selectDetector, selectPip } from "../../../dashboard/static/features/experience/selectors.js";

const detector = (over = {}) => ({
  state: "active", active_mode: "actual", switching_to: null, detector: "x", checkpoint: "", demo_kind: "none",
  demo_available: true, message: "", failed_mode: null, fake: false, request_id: null, updated_ts: 1, can_switch: true, ...over,
});
const snap = (d, connection = "connected") => ({ connection, state: { capabilities: { mode_switch: true }, detector: d } });
const live = { kind: "live" };
const idle = { sending: null, error: null, requestId: null, at: null };
const pip = (d, { cam = live, touch = null, connection = "connected", local = idle } = {}) => {
  const s = snap(d, connection);
  return selectPip(s, cam, selectDetector(s, local), touch);
};

test("reclines with the Regular sentence and the tip when all is well", () => {
  const vm = pip(detector());
  assert.equal(vm.pose, "recline");
  assert.equal(vm.mode, "I’m using the general-purpose detector.");
  assert.equal(vm.tip, PIP_TIP);
  assert.equal(vm.recovery, "");
});

test("Demo sentence only for the trained checkpoint; fallback and fake are said plainly", () => {
  assert.equal(pip(detector({ active_mode: "demo", demo_kind: "trained" })).mode, "I’m using the model trained for our demo objects.");
  assert.match(pip(detector({ active_mode: "demo", demo_kind: "prompt-fallback" })).mode, /not the model trained/);
  assert.match(pip(detector({ active_mode: "demo", demo_kind: "fake", fake: true })).mode, /recorded test clip, so no detector is running\. The control is set to Demo/);
});

test("attentive while something is touched", () => {
  assert.equal(pip(detector(), { touch: { objectId: 1, text: "mug" } }).pose, "attentive");
});

test("waits only when vision confirms a switch, not for this page's unsent click", () => {
  const confirmed = pip(detector({ state: "switching", switching_to: "demo" }));
  assert.equal(confirmed.pose, "wait");
  assert.match(confirmed.recovery, /Waiting for Demo to load\. The current detector keeps running/);
  assert.equal(pip(detector(), { local: { ...idle, sending: "demo" } }).pose, "recline");
});

test("concerned with a specific recovery for camera trouble and a failed switch", () => {
  assert.match(pip(detector(), { cam: { kind: "offline" } }).recovery, /camera is offline/);
  assert.match(pip(detector(), { cam: { kind: "disconnected" } }).recovery, /video stream dropped/);
  assert.match(pip(detector(), { cam: { kind: "stale" } }).recovery, /stopped updating/);
  assert.match(pip(detector(), { cam: { kind: "stale" }, connection: "reconnecting" }).recovery, /lost its connection/);
  const failed = pip(detector({ state: "failed", failed_mode: "demo", message: "No demo-trained checkpoint is installed." }));
  assert.equal(failed.pose, "concerned");
  assert.match(failed.recovery, /did not finish\. No demo-trained checkpoint/);
});

test("camera trouble outranks a touch; unknown detector is never described as running", () => {
  assert.equal(pip(detector(), { cam: { kind: "offline" }, touch: { objectId: 1 } }).pose, "concerned");
  assert.match(pip(detector({ state: "unknown", active_mode: null })).mode, /has not said/);
});

test("Pip never claims listening, recognition or sound", () => {
  const all = [
    pip(detector()), pip(detector({ active_mode: "demo", demo_kind: "trained" })),
    pip(detector({ state: "switching", switching_to: "demo" })), pip(detector(), { cam: { kind: "offline" } }),
  ];
  for (const vm of all) {
    const text = `${vm.mode} ${vm.recovery} ${vm.tip}`;
    assert.doesNotMatch(text, /listen|hear|heard|microphone|recogni[sz]ed|spoke|played|sound/i, text);
  }
});
