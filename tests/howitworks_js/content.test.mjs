import test from "node:test";
import assert from "node:assert/strict";
import {
  HOTSPOTS, NODES, TOUCH_STEPS, HAZARD_STEPS, HOME_VIEW,
} from "../../howitworks/content.js";

const ids = (list) => list.map((item) => item.id);

test("ids are exactly the agreed sets", () => {
  assert.deepEqual(ids(HOTSPOTS), ["camera", "pointing", "laptop", "speaker", "hazard"]);
  assert.deepEqual(ids(NODES), ["camera", "vision", "scene", "namer", "audio", "hazard", "storage", "dashboard"]);
  assert.deepEqual(ids(TOUCH_STEPS), ["capture", "frame", "name-request", "name-result", "touch", "outputs"]);
  assert.deepEqual(ids(HAZARD_STEPS), ["hazard-frame", "hazard-event"]);
});

test("hotspots point at real steps and have complete copy and views", () => {
  const stepIds = new Set([...ids(TOUCH_STEPS), ...ids(HAZARD_STEPS)]);
  for (const spot of HOTSPOTS) {
    assert.ok(stepIds.has(spot.stepId), spot.id);
    for (const key of ["label", "does", "builtWith", "number"]) {
      assert.ok(typeof spot[key] === "string" && spot[key].trim().length > 0, `${spot.id}.${key}`);
    }
    assert.equal(spot.anchor.length, 3);
    assert.equal(spot.view.position.length, 3);
    assert.equal(spot.view.target.length, 3);
  }
  assert.equal(HOME_VIEW.position.length, 3);
  assert.equal(HOME_VIEW.target.length, 3);
});

test("steps connect real nodes and have captions", () => {
  const nodeIds = new Set(ids(NODES));
  for (const step of [...TOUCH_STEPS, ...HAZARD_STEPS]) {
    assert.ok(nodeIds.has(step.from), step.id);
    assert.ok(step.to.length > 0, step.id);
    for (const to of step.to) assert.ok(nodeIds.has(to), `${step.id} -> ${to}`);
    assert.ok(step.caption.trim().length > 0, step.id);
    assert.ok(step.message === null || /^[A-Z][A-Za-z]+$/.test(step.message), step.id);
  }
});

test("content is frozen", () => {
  assert.ok(Object.isFrozen(HOTSPOTS) && Object.isFrozen(HOTSPOTS[0]));
  assert.ok(Object.isFrozen(TOUCH_STEPS) && Object.isFrozen(TOUCH_STEPS[0]));
});
