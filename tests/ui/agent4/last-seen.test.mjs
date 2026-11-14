// Integration regressions for last-touch search: id normalisation, an overall
// deadline that fires while requests hang, and late results being ignored.
import test from "node:test";
import assert from "node:assert/strict";
import {
  createLastSeenController,
  normalizeRequestId,
  POLL_INTERVAL_MS,
  SEARCH_TIMEOUT_MS,
} from "../../../dashboard/static/features/experience/last-seen.js";
import { createApiClient, ApiError } from "../../../dashboard/static/core/api-client.js";

/** Timers the test advances by hand. */
function manualTimers() {
  let now = 0;
  let seq = 0;
  const pending = new Map();
  return {
    setTimer(fn, ms) {
      const id = ++seq;
      pending.set(id, { at: now + ms, fn });
      return id;
    },
    clearTimer(id) {
      pending.delete(id);
    },
    async advance(ms) {
      const until = now + ms;
      for (;;) {
        const due = [...pending.entries()].filter(([, t]) => t.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        pending.delete(due[0]);
        now = due[1].at;
        due[1].fn();
        await flush();
      }
      now = until;
    },
  };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

/** A request() whose calls are recorded and resolved or left hanging by the test. */
function controllableRequest() {
  const calls = [];
  const request = (path, options = {}) =>
    new Promise((resolve, reject) => {
      const call = { path, options, resolve, reject, aborted: false };
      options.signal?.addEventListener("abort", () => {
        call.aborted = true;
      });
      calls.push(call);
    });
  return { request, calls };
}

function harness() {
  const timers = manualTimers();
  const { request, calls } = controllableRequest();
  const views = [];
  const controller = createLastSeenController({
    request,
    onChange: (v) => views.push(v),
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  return { timers, calls, views, controller, last: () => views[views.length - 1] };
}

test("request ids are normalised from numbers and strings", () => {
  assert.equal(normalizeRequestId(42), "42");
  assert.equal(normalizeRequestId(" abc "), "abc");
  assert.equal(normalizeRequestId(""), null);
  assert.equal(normalizeRequestId(null), null);
  assert.equal(normalizeRequestId(Number.NaN), null);
});

test("a numeric request_id is matched against the poll reply", async () => {
  const h = harness();
  h.controller.search("keys");
  h.calls[0].resolve({ request_id: 42, status: "pending" });
  await flush();
  await h.timers.advance(POLL_INTERVAL_MS);
  assert.equal(h.calls[1].path, "/api/last-seen/42");
  h.calls[1].resolve({ request_id: 42, status: "found", answer: "Keys, just now.", matched_at: 100 });
  await flush();
  assert.equal(h.last().status, "found");
  assert.equal(h.last().matchedAt, 100);
});

test("a POST that never answers times out at the overall deadline and is aborted", async () => {
  const h = harness();
  h.controller.search("keys");
  assert.equal(h.last().status, "loading");
  await h.timers.advance(SEARCH_TIMEOUT_MS);
  assert.equal(h.last().status, "timeout");
  assert.equal(h.calls[0].aborted, true);
  h.calls[0].resolve({ request_id: "late" }); // arrives after the deadline
  await flush();
  await h.timers.advance(POLL_INTERVAL_MS * 4);
  assert.equal(h.calls.length, 1, "no polling after a timed-out POST");
  assert.equal(h.last().status, "timeout");
});

test("a GET that never answers times out and a late answer is ignored", async () => {
  const h = harness();
  h.controller.search("keys");
  h.calls[0].resolve({ request_id: "r1", status: "pending" });
  await flush();
  await h.timers.advance(POLL_INTERVAL_MS); // first GET starts and hangs
  assert.equal(h.calls.length, 2);
  await h.timers.advance(SEARCH_TIMEOUT_MS);
  assert.equal(h.last().status, "timeout");
  assert.equal(h.calls[1].aborted, true);
  h.calls[1].resolve({ request_id: "r1", status: "found", answer: "Keys.", matched_at: 1 });
  await flush();
  assert.equal(h.last().status, "timeout");
});

test("a replaced search cannot change the view, even when it answers later", async () => {
  const h = harness();
  h.controller.search("keys");
  h.controller.search("phone");
  assert.equal(h.calls[0].aborted, true);
  h.calls[1].resolve({ request_id: "b" });
  await flush();
  h.calls[0].resolve({ request_id: "a" }); // the old POST answers late
  await flush();
  await h.timers.advance(POLL_INTERVAL_MS);
  assert.deepEqual(h.calls.slice(2).map((c) => c.path), ["/api/last-seen/b"]);
  h.calls[2].resolve({ request_id: "b", status: "not_found", answer: "I have not seen that." });
  await flush();
  assert.equal(h.last().status, "not_found");
  assert.equal(h.last().query, "phone");
  // The replaced search's deadline never fires a timeout over the newer result.
  await h.timers.advance(SEARCH_TIMEOUT_MS * 2);
  assert.equal(h.last().status, "not_found");
});

test("after dispose nothing is emitted and in-flight requests are aborted", async () => {
  const h = harness();
  h.controller.search("keys");
  const before = h.views.length;
  h.controller.dispose();
  assert.equal(h.calls[0].aborted, true);
  h.calls[0].resolve({ request_id: "r" });
  await flush();
  await h.timers.advance(SEARCH_TIMEOUT_MS * 2);
  assert.equal(h.views.length, before);
  h.controller.search("again");
  assert.equal(h.calls.length, 1, "a disposed controller does not start searches");
});

/** A fetch whose headers arrive but whose body never finishes. */
function hangingBodyFetch() {
  return async (_path, init) => ({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    text: () =>
      new Promise((_resolve, reject) => {
        // Like a real stream, it only ends if the request is aborted... or never.
        void init;
        void reject;
      }),
  });
}

test("api client times out a response whose body never finishes", async () => {
  const api = createApiClient({ fetchImpl: hangingBodyFetch(), timeoutMs: 30 });
  await assert.rejects(api.request("/api/last-seen/r1"), (err) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.kind, "timeout");
    return true;
  });
});

test("api client lets the caller abort while the body is still arriving", async () => {
  const api = createApiClient({ fetchImpl: hangingBodyFetch(), timeoutMs: 60_000 });
  const controller = new AbortController();
  const pending = api.request("/api/last-seen/r1", { signal: controller.signal });
  setTimeout(() => controller.abort(), 10);
  await assert.rejects(pending, (err) => err?.name === "AbortError");
});

test("a found result carries the recorded neighbours, bounded and cleaned", async () => {
  const h = harness();
  h.controller.search("ketchup");
  h.calls[0].resolve({ request_id: "n1" });
  await flush();
  await h.timers.advance(POLL_INTERVAL_MS);
  h.calls[1].resolve({
    request_id: "n1", status: "found", answer: "Heinz ketchup, just now, next to mug.",
    matched_at: 5, neighbours: ["mug", "", 7, "cereal box", "bowl", "plate"],
  });
  await flush();
  assert.deepEqual(h.last().neighbours, ["mug", "cereal box", "bowl"]);
});
