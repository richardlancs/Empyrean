import test from "node:test";
import assert from "node:assert/strict";
import { createSelection } from "../../howitworks/stage/selection.js";

function setup() {
  const calls = [];
  const selection = createSelection({ ids: ["a", "b"], onChange: (now, before) => calls.push([now, before]) });
  return { selection, calls };
}

test("opening one then another reports each change once", () => {
  const { selection, calls } = setup();
  selection.open("a");
  selection.open("b");
  assert.deepEqual(calls, [["a", null], ["b", "a"]]);
  assert.equal(selection.current, "b");
});

test("re-opening the current id and closing nothing are silent", () => {
  const { selection, calls } = setup();
  selection.close();
  selection.open("a");
  selection.open("a");
  assert.deepEqual(calls, [["a", null]]);
});

test("unknown ids throw and change nothing", () => {
  const { selection, calls } = setup();
  assert.throws(() => selection.open("nope"), RangeError);
  assert.equal(selection.current, null);
  assert.equal(calls.length, 0);
});

test("toggle opens then closes", () => {
  const { selection, calls } = setup();
  selection.toggle("a");
  selection.toggle("a");
  assert.equal(selection.current, null);
  assert.deepEqual(calls, [["a", null], [null, "a"]]);
});
