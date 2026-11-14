// Unit tests for the last-seen search controller, with a manual clock.
// All data here is artificial fixture data.

import assert from "node:assert/strict";
import { test } from "node:test";

import { createLastSeenController, POLL_INTERVAL_MS, SEARCH_TIMEOUT_MS } from "../../../dashboard/static/features/experience/last-seen.js";

function harness(handler) {
  let now = 0;
  const timers = new Map();
  let nextId = 1;
  const views = [];
  const calls = [];
  const controller = createLastSeenController({
    request: (path, opts) => {
      calls.push([path, opts]);
      return handler(path, opts);
    },
    onChange: (v) => views.push(v),
    setTimer: (fn, ms) => {
      const id = nextId++;
      timers.set(id, { fn, at: now + ms });
      return id;
    },
    clearTimer: (id) => timers.delete(id),
    nowMs: () => now,
  });
  async function advance(ms) {
    now += ms;
    for (const [id, t] of [...timers]) {
      if (t.at <= now) {
        timers.delete(id);
        await t.fn();
      }
    }
    await flush();
  }
  return { controller, views, calls, advance, timers, last: () => views.at(-1) };
}
const flush = () => new Promise((r) => setTimeout(r, 0));

test("pending then found", async () => {
  let polls = 0;
  const h = harness(async (path) => {
    if (path === "/api/last-seen") return { request_id: "r1" };
    polls += 1;
    return polls < 2
      ? { request_id: "r1", status: "pending", answer: null, matched_at: null }
      : { request_id: "r1", status: "found", answer: "FIXTURE mug, 4 minutes ago, next to bowl.", matched_at: 1000 };
  });
  await h.controller.search("  mug ");
  assert.equal(h.last().status, "loading");
  assert.equal(h.calls[0][1].body.query, "mug");
  await h.advance(POLL_INTERVAL_MS);
  assert.equal(h.last().status, "loading");
  await h.advance(POLL_INTERVAL_MS);
  assert.equal(h.last().status, "found");
  assert.equal(h.last().matchedAt, 1000);
  assert.equal(h.timers.size, 0, "polling stops once answered");
});

test("not found and unavailable", async () => {
  const h = harness(async (path) =>
    path === "/api/last-seen" ? { request_id: "a" } : { request_id: "a", status: "not_found", answer: "I have not seen that.", matched_at: null },
  );
  await h.controller.search("zebra");
  await h.advance(POLL_INTERVAL_MS);
  assert.equal(h.last().status, "not_found");
  assert.equal(h.last().answer, "I have not seen that.");

  const u = harness(async (path) => (path === "/api/last-seen" ? { request_id: "b" } : { request_id: "b", status: "unavailable" }));
  await u.controller.search("x");
  await u.advance(POLL_INTERVAL_MS);
  assert.equal(u.last().status, "unavailable");
});

test("timeout stops polling and retry starts again", async () => {
  const h = harness(async (path) => (path === "/api/last-seen" ? { request_id: "t" } : { request_id: "t", status: "pending" }));
  await h.controller.search("cup");
  for (let elapsed = 0; elapsed <= SEARCH_TIMEOUT_MS; elapsed += POLL_INTERVAL_MS) await h.advance(POLL_INTERVAL_MS);
  assert.equal(h.last().status, "timeout");
  assert.equal(h.timers.size, 0);
  await h.controller.retry();
  assert.equal(h.last().status, "loading");
  assert.equal(h.last().query, "cup");
});

test("a newer search wins over a slower older answer", async () => {
  let releaseFirst;
  const h = harness((path, opts) => {
    if (path === "/api/last-seen") return Promise.resolve({ request_id: opts.body.query === "old" ? "r-old" : "r-new" });
    if (path.endsWith("r-old")) return new Promise((r) => (releaseFirst = () => r({ request_id: "r-old", status: "found", answer: "OLD", matched_at: 1 })));
    return Promise.resolve({ request_id: "r-new", status: "found", answer: "NEW", matched_at: 2 });
  });
  await h.controller.search("old");
  const firstPoll = h.advance(POLL_INTERVAL_MS); // old poll in flight
  await flush();
  await h.controller.search("new");
  await h.advance(POLL_INTERVAL_MS);
  assert.equal(h.last().answer, "NEW");
  releaseFirst();
  await firstPoll;
  await flush();
  assert.equal(h.last().answer, "NEW", "old answer must not replace the newer one");
});

test("mismatched request_id is ignored", async () => {
  let n = 0;
  const h = harness(async (path) => {
    if (path === "/api/last-seen") return { request_id: "mine" };
    n += 1;
    return n === 1 ? { request_id: "other", status: "found", answer: "WRONG" } : { request_id: "mine", status: "found", answer: "RIGHT", matched_at: 5 };
  });
  await h.controller.search("x");
  await h.advance(POLL_INTERVAL_MS);
  assert.equal(h.last().status, "loading");
  await h.advance(POLL_INTERVAL_MS);
  assert.equal(h.last().answer, "RIGHT");
});

test("request failure reports an error; dispose stops everything", async () => {
  const h = harness(async () => {
    const err = new Error("nope");
    err.status = 404;
    throw err;
  });
  await h.controller.search("x");
  assert.equal(h.last().status, "error");
  assert.match(h.last().message, /does not offer/);

  const d = harness(async (path) => (path === "/api/last-seen" ? { request_id: "z" } : { request_id: "z", status: "pending" }));
  await d.controller.search("x");
  const count = d.views.length;
  d.controller.dispose();
  await d.advance(POLL_INTERVAL_MS * 3);
  assert.equal(d.views.length, count);
  assert.equal(d.timers.size, 0);
});
