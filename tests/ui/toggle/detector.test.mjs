// Regular | Demo view model. Run: node --test tests/ui/toggle/
// All data here is artificial fixture data.

import assert from "node:assert/strict";
import { test } from "node:test";

import { checkpointStatus, selectDetector } from "../../../dashboard/static/features/experience/selectors.js";
import { selectDetectorDetails } from "../../../dashboard/static/features/operations/selectors.js";

const CKPT = "demo-yolo11s.pt, 19.2 MB, SHA-256 c1e2dd03c6a1, installed 2026-11-14 10:00, status: experimental; NOT demo-ready";
const detector = (over = {}) => ({
  state: "active", active_mode: "actual", switching_to: null, detector: "General-purpose COCO detector (yolo11s.pt)",
  checkpoint: "", demo_kind: "none", demo_available: true, message: "", failed_mode: null, fake: false,
  request_id: null, updated_ts: 100, can_switch: true, ...over,
});
const snap = (d, connection = "connected", caps = { mode_switch: true }) => ({ connection, state: { capabilities: caps, detector: d } });
const idle = { sending: null, error: null, requestId: null, at: null };

test("regular active: Regular pressed, plain support text, no badge", () => {
  const vm = selectDetector(snap(detector()), idle);
  assert.equal(vm.pressed, "actual");
  assert.equal(vm.locked, false);
  assert.equal(vm.support, "General-purpose object detection.");
  assert.equal(vm.badge, null);
});

test("switching keeps the old mode pressed and locks both choices", () => {
  const vm = selectDetector(snap(detector({ state: "switching", switching_to: "demo" })), idle);
  assert.equal(vm.pressed, "actual");
  assert.equal(vm.busy, "demo");
  assert.equal(vm.locked, true);
  assert.match(vm.status, /Switching to Demo… Regular stays on until Demo is ready\./);
});

test("a request in flight locks the control before the engine answers", () => {
  const vm = selectDetector(snap(detector()), { ...idle, sending: "demo" });
  assert.equal(vm.locked, true);
  assert.equal(vm.pressed, "actual");
  assert.match(vm.status, /Asking to switch to Demo/);
});

test("trained demo shows the badge and the checkpoint's recorded status", () => {
  const vm = selectDetector(snap(detector({ active_mode: "demo", demo_kind: "trained", checkpoint: CKPT })), idle);
  assert.equal(vm.pressed, "demo");
  assert.deepEqual(vm.badge, { kind: "trained", text: "Demo-trained model" });
  assert.equal(vm.support, "Custom model trained for our demo objects.");
  assert.equal(vm.note, "Checkpoint status: experimental; NOT demo-ready.");
});

test("a fallback or fake demo is never called the trained model", () => {
  const fallback = selectDetector(snap(detector({ active_mode: "demo", demo_kind: "prompt-fallback" })), idle);
  assert.notEqual(fallback.badge.text, "Demo-trained model");
  assert.match(fallback.support, /not the demo-trained model/);
  const fake = selectDetector(snap(detector({ active_mode: "demo", demo_kind: "fake", fake: true })), idle);
  assert.match(fake.badge.text, /fake vision/);
  assert.doesNotMatch(fake.support, /trained/);
});

test("failure keeps Regular and says why", () => {
  const vm = selectDetector(snap(detector({ state: "failed", failed_mode: "demo", message: "No demo-trained checkpoint is installed." })), idle);
  assert.equal(vm.pressed, "actual");
  assert.equal(vm.tone, "error");
  assert.equal(vm.locked, false);
  assert.match(vm.status, /Could not switch to Demo\. Still using Regular\. No demo-trained checkpoint/);
});

test("disconnected: last known mode, locked, said in words", () => {
  const vm = selectDetector(snap(detector({ active_mode: "demo", demo_kind: "trained" }), "reconnecting"), idle);
  assert.equal(vm.locked, true);
  assert.equal(vm.pressed, "demo");
  assert.match(vm.status, /Disconnected\. Demo was active/);
});

test("unknown, unsupported and missing state never show an active mode", () => {
  assert.equal(selectDetector(snap(detector({ state: "unknown", active_mode: null })), idle).pressed, null);
  assert.equal(selectDetector(snap(detector(), "connected", { mode_switch: false }), idle).pressed, null);
  assert.equal(selectDetector({ connection: "connecting", state: null }, idle).locked, true);
});

test("a page's own refusal shows until the engine reports something newer", () => {
  const local = { ...idle, error: "Another switch is already in progress.", at: 100 };
  assert.match(selectDetector(snap(detector()), local).status, /Another switch/);
  assert.doesNotMatch(selectDetector(snap(detector({ updated_ts: 101 })), local).status, /Another switch/);
});

test("checkpointStatus reads the recorded status only", () => {
  assert.equal(checkpointStatus(CKPT), "experimental; NOT demo-ready");
  assert.equal(checkpointStatus("demo-yolo11s.pt"), "");
  assert.equal(checkpointStatus(null), "");
});

test("System details row names the detector and its checkpoint", () => {
  const row = selectDetectorDetails({ detector: detector({ active_mode: "demo", demo_kind: "trained", checkpoint: CKPT, detector: "Demo-trained detector (demo-yolo11s.pt), with COCO for vehicles" }) }, true);
  assert.equal(row.statusLabel, "Demo: active");
  assert.match(row.detail, /demo-yolo11s\.pt/);
  assert.equal(row.facts[0].value, CKPT);
  assert.equal(selectDetectorDetails({}, true).statusLabel, "Not reported");
  assert.match(selectDetectorDetails({ detector: detector() }, false).statusLabel, /last known/);
});
