// Unit tests for components/speech-signal.js with a fake DOM and a fake Rive runtime.
import test from "node:test";
import assert from "node:assert/strict";
import { createSpeechSignal, signalShouldMove, SIGNAL_ANIMATION } from "../../../dashboard/static/components/speech-signal.js";

class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.hidden = false;
    this.parent = null;
  }
  append(...nodes) {
    for (const n of nodes) {
      n.parent = this;
      this.children.push(n);
    }
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
    this.parent = null;
  }
  setAttribute(k, v) {
    this.attributes[k] = v;
  }
}

function fakeEnv({ hidden = false } = {}) {
  const listeners = {};
  const doc = {
    hidden,
    head: new FakeNode("head"),
    createElement: (tag) => new FakeNode(tag),
    addEventListener: (type, fn) => {
      listeners[type] = fn;
    },
    removeEventListener: (type) => {
      delete listeners[type];
    },
  };
  let observerCallback = null;
  const win = {
    IntersectionObserver: class {
      constructor(cb) {
        observerCallback = cb;
      }
      observe() {}
      disconnect() {
        observerCallback = null;
      }
    },
  };
  return {
    doc,
    win,
    listeners,
    setVisible: (v) => observerCallback?.([{ isIntersecting: v }]),
    observerActive: () => observerCallback !== null,
  };
}

function fakeRuntime({ failLoad = false } = {}) {
  const instances = [];
  class Rive {
    constructor(opts) {
      this.opts = opts;
      this.calls = [];
      instances.push(this);
      queueMicrotask(() => (failLoad ? opts.onLoadError?.() : opts.onLoad?.()));
    }
    play(name) {
      this.calls.push(["play", name]);
    }
    pause(name) {
      this.calls.push(["pause", name]);
    }
    cleanup() {
      this.calls.push(["cleanup"]);
    }
    resizeDrawingSurfaceToCanvas() {}
  }
  return { runtime: { Rive }, instances };
}

const flush = () => new Promise((r) => setImmediate(r));

function mount({ reduced = false, failLoad = false, rejectRuntime = false, hidden = false } = {}) {
  const env = fakeEnv({ hidden });
  const { runtime, instances } = fakeRuntime({ failLoad });
  let loads = 0;
  let idle = null;
  const root = new FakeNode("div");
  const signal = createSpeechSignal(root, {
    doc: env.doc,
    win: env.win,
    reducedMotion: () => reduced,
    loadRuntime: () => {
      loads += 1;
      return rejectRuntime ? Promise.reject(new Error("no runtime")) : Promise.resolve(runtime);
    },
    scheduleIdle: (fn) => {
      idle = fn;
      return 1;
    },
    cancelIdle: () => {
      idle = null;
    },
  });
  return {
    env,
    root,
    signal,
    instances,
    loads: () => loads,
    runIdle: async () => {
      idle?.();
      await flush();
      await flush();
    },
  };
}

test("only real speaking telemetry justifies motion", () => {
  assert.equal(signalShouldMove({ status: "speaking", mode: "real" }), true);
  assert.equal(signalShouldMove({ status: "speaking", mode: "fake" }), false);
  assert.equal(signalShouldMove({ status: "speaking", mode: "unavailable" }), false);
  assert.equal(signalShouldMove({ status: "queued", mode: "real" }), false);
  assert.equal(signalShouldMove({ status: "completed", mode: "real" }), false);
  assert.equal(signalShouldMove(null), false);
});

test("the still is shown at once and the runtime loads only when idle", async () => {
  const m = mount();
  assert.equal(m.root.dataset.signal, "still");
  assert.equal(m.loads(), 0, "nothing loads before the browser is idle");
  const [still, canvas] = m.root.children;
  assert.equal(still.tagName, "img");
  assert.equal(still.alt, "");
  assert.equal(canvas.hidden, true);
  await m.runIdle();
  assert.equal(m.loads(), 1);
  assert.equal(m.root.dataset.signal, "ready");
  assert.equal(canvas.hidden, false);
  assert.equal(still.hidden, true);
  assert.equal(m.instances[0].opts.autoplay, false);
});

test("it plays only while active, visible and the page is shown", async () => {
  const m = mount();
  await m.runIdle();
  const rive = m.instances[0];
  m.signal.update({ active: true });
  assert.deepEqual(rive.calls.at(-1), ["play", SIGNAL_ANIMATION]);
  assert.equal(m.root.dataset.signal, "playing");
  m.env.setVisible(false);
  assert.deepEqual(rive.calls.at(-1), ["pause", SIGNAL_ANIMATION]);
  m.env.setVisible(true);
  assert.equal(m.root.dataset.signal, "playing");
  m.env.doc.hidden = true;
  m.env.listeners.visibilitychange();
  assert.equal(m.root.dataset.signal, "ready");
  m.env.doc.hidden = false;
  m.env.listeners.visibilitychange();
  m.signal.update({ active: false });
  assert.deepEqual(rive.calls.at(-1), ["pause", SIGNAL_ANIMATION]);
  assert.equal(m.root.dataset.signal, "ready");
});

test("the one-shot animation repeats only while still justified", async () => {
  const m = mount();
  await m.runIdle();
  const rive = m.instances[0];
  m.signal.update({ active: true });
  const before = rive.calls.length;
  rive.opts.onStop();
  assert.deepEqual(rive.calls.at(-1), ["play", SIGNAL_ANIMATION]);
  m.signal.update({ active: false });
  const paused = rive.calls.length;
  rive.opts.onStop();
  assert.equal(rive.calls.length, paused, "no replay after speech stopped");
  assert.ok(before > 0);
});

test("reduced motion never loads the runtime", async () => {
  const m = mount({ reduced: true });
  await m.runIdle();
  m.signal.update({ active: true });
  assert.equal(m.loads(), 0);
  assert.equal(m.root.dataset.signal, "still");
});

test("a runtime or file failure keeps the still image", async () => {
  for (const failure of [{ rejectRuntime: true }, { failLoad: true }]) {
    const m = mount(failure);
    await m.runIdle();
    m.signal.update({ active: true });
    const [still, canvas] = m.root.children;
    assert.equal(m.root.dataset.signal, "fallback", JSON.stringify(failure));
    assert.equal(still.hidden, false);
    assert.equal(canvas.hidden, true);
  }
});

test("destroy disposes of the instance, listeners, observer and nodes", async () => {
  const m = mount();
  await m.runIdle();
  m.signal.destroy();
  assert.deepEqual(m.instances[0].calls.at(-1), ["cleanup"]);
  assert.equal(m.root.children.length, 0);
  assert.equal(m.env.listeners.visibilitychange, undefined);
  assert.equal(m.env.observerActive(), false);
  assert.equal(m.root.dataset.signal, undefined);
});

test("destroy before the idle callback means nothing ever loads", async () => {
  const m = mount();
  m.signal.destroy();
  await m.runIdle();
  assert.equal(m.loads(), 0);
});
