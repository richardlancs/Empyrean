import test from "node:test";
import assert from "node:assert/strict";
import { createStepper } from "../../howitworks/pipeline/stepper.js";

const STEPS = [
  { id: "s0", from: "a", to: ["b"] },
  { id: "s1", from: "b", to: ["c"] },
  { id: "s2", from: "c", to: ["d", "e"] },
];

/** A stepper with hand-cranked timers. */
function setup() {
  const pending = new Map();
  let nextId = 1;
  const changes = [];
  const stepper = createStepper({
    steps: STEPS,
    onChange: (index, step) => changes.push([index, step.id]),
    intervalMs: 10,
    setTimer: (fn) => { const id = nextId++; pending.set(id, fn); return id; },
    clearTimer: (id) => pending.delete(id),
  });
  const tick = () => {
    const [id, fn] = [...pending.entries()][0] ?? [];
    if (!fn) return false;
    pending.delete(id);
    fn();
    return true;
  };
  return { stepper, changes, tick, pending };
}

test("stays inside its range", () => {
  const { stepper } = setup();
  stepper.back();
  assert.equal(stepper.index, 0);
  stepper.goTo(2);
  stepper.next();
  assert.equal(stepper.index, 2);
  assert.throws(() => stepper.goTo(99), RangeError);
  assert.throws(() => stepper.goTo(-1), RangeError);
  assert.equal(stepper.index, 2);
});

test("play advances one step per interval and stops at the end", () => {
  const { stepper, tick, pending } = setup();
  stepper.play();
  assert.equal(stepper.playing, true);
  tick();
  assert.equal(stepper.index, 1);
  tick();
  assert.equal(stepper.index, 2);
  assert.equal(stepper.playing, false);
  assert.equal(pending.size, 0);
});

test("play on the last step restarts from the first", () => {
  const { stepper } = setup();
  stepper.goTo(2);
  stepper.play();
  assert.equal(stepper.index, 0);
  assert.equal(stepper.playing, true);
});

test("any manual move pauses play", () => {
  for (const move of [(s) => s.next(), (s) => s.back(), (s) => s.goTo(1), (s) => s.jumpToNode("c")]) {
    const { stepper, pending } = setup();
    stepper.play();
    move(stepper);
    assert.equal(stepper.playing, false);
    assert.equal(pending.size, 0);
  }
});

test("jumpToNode goes to the first step that involves the node", () => {
  const { stepper } = setup();
  stepper.jumpToNode("c");
  assert.equal(stepper.index, 1);
  stepper.jumpToNode("e");
  assert.equal(stepper.index, 2);
  stepper.jumpToNode("nowhere");
  assert.equal(stepper.index, 2);
});

test("onChange fires only on a real change, and pause is idempotent", () => {
  const { stepper, changes } = setup();
  stepper.goTo(0);
  stepper.pause();
  stepper.next();
  assert.deepEqual(changes, [[1, "s1"]]);
});

test("destroy cancels a pending tick", () => {
  const { stepper, pending } = setup();
  stepper.play();
  stepper.destroy();
  assert.equal(pending.size, 0);
});
