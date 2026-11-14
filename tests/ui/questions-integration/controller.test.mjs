// Question controller: correlation, polling, pushed state, errors (node --test).
import test from "node:test";
import assert from "node:assert/strict";

import { errorMessageFrom } from "../../../dashboard/static/core/api-client.js";
import { createQuestionController } from "../../../dashboard/static/features/questions/controller.js";
import { LOOKUP_TIMEOUT_MS, POLL_INTERVAL_MS, STILL_WAITING_MESSAGE } from "../../../dashboard/static/features/questions/model.js";
import { apiError, createClock, deferred, flush, lookingUp, record } from "./helpers.mjs";

/** A controller whose request() is answered by `handler(path, options)`. */
function setup(handler) {
  const clock = createClock();
  const calls = [];
  const views = [];
  const controller = createQuestionController({
    request: (path, options = {}) => {
      calls.push({ path, method: options.method || "GET", body: options.body, signal: options.signal });
      return handler(path, options, calls.length);
    },
    onChange: (view) => views.push(view),
    detailOf: errorMessageFrom,
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });
  return { clock, calls, views, controller };
}

test("an immediate answer is shown with its question text", async () => {
  const { controller, calls } = setup(async () => record());
  await controller.ask("  What am I touching? ");
  assert.deepEqual(calls[0].body, { text: "What am I touching?" });
  assert.equal(calls[0].method, "POST");
  assert.equal(controller.view.phase, "answered");
  assert.equal(controller.view.text, "What am I touching?");
  assert.equal(controller.view.record.answer, "You are touching a Heinz ketchup bottle.");
});

test("submitting blocks a double submit", async () => {
  const post = deferred();
  const { controller, calls } = setup(() => post.promise);
  const first = controller.ask("What can you see?");
  assert.equal(controller.view.phase, "submitting");
  await controller.ask("What can you see?");
  assert.equal(calls.length, 1, "second ask ignored while submitting");
  post.resolve(record({ intent: "scene", text: "What can you see?" }));
  await first;
  assert.equal(controller.view.phase, "answered");
});

test("looking_up -> answered via poll", async () => {
  const final = lookingUp({ status: "answered", answered_by: "storage", answer: "You last touched keys at 10:02.", history_status: "found", answered_at: 120 });
  const { controller, calls, clock } = setup(async (path, options, n) => {
    if (options.method === "POST") return lookingUp();
    return n < 3 ? lookingUp() : final;
  });
  await controller.ask("Where did I last touch my keys?");
  assert.equal(controller.view.phase, "looking_up");
  assert.equal(controller.view.record.answer, "Looking up the last touch of keys…");
  await clock.advance(POLL_INTERVAL_MS);
  assert.equal(calls[1].path, "/api/question/h1");
  assert.equal(controller.view.phase, "looking_up");
  await clock.advance(POLL_INTERVAL_MS);
  assert.equal(controller.view.phase, "answered");
  assert.equal(controller.view.record.answer, "You last touched keys at 10:02.");
  const count = calls.length;
  await clock.advance(POLL_INTERVAL_MS * 5);
  assert.equal(calls.length, count, "polling stopped after the answer");
  assert.equal(clock.pending(), 0, "no timers left (deadline cleared)");
});

test("looking_up -> answered via pushed state stops polling", async () => {
  const { controller, calls, clock } = setup(async (path, options) => (options.method === "POST" ? lookingUp() : lookingUp()));
  await controller.ask("Where did I last touch my keys?");
  const final = lookingUp({ status: "answered", answered_by: "storage", answer: "Keys: 10:02, kitchen table.", answered_at: 121 });
  controller.receiveState({ questions: { available: true, recent: [final] } });
  assert.equal(controller.view.phase, "answered");
  assert.equal(controller.view.record.answer, "Keys: 10:02, kitchen table.");
  const count = calls.length;
  await clock.advance(POLL_INTERVAL_MS * 3);
  assert.equal(calls.length, count);
  // A stale looking_up copy pushed later cannot undo the answer.
  controller.receiveState({ questions: { recent: [lookingUp()] } });
  assert.equal(controller.view.phase, "answered");
});

test("a push that beats the POST reply is still applied", async () => {
  const post = deferred();
  const { controller } = setup((path, options) => (options.method === "POST" ? post.promise : Promise.resolve(lookingUp())));
  const asking = controller.ask("Where did I last touch my keys?");
  const final = lookingUp({ status: "answered", answered_by: "storage", answer: "Keys at 10:02." });
  controller.receiveState({ questions: { recent: [final] } }); // not tracked yet: ignored for now
  assert.equal(controller.view.phase, "submitting");
  post.resolve(lookingUp());
  await asking;
  assert.equal(controller.view.phase, "answered");
  assert.equal(controller.view.record.answer, "Keys at 10:02.");
});

test("an older question's late result never replaces a newer question's answer", async () => {
  const polls = [];
  const { controller, clock } = setup((path, options) => {
    if (options.method === "POST") {
      return Promise.resolve(
        options.body.text.includes("keys") ? lookingUp({ question_id: "old" }) : record({ question_id: "new", text: options.body.text }),
      );
    }
    const d = deferred();
    polls.push(d);
    return d.promise;
  });
  await controller.ask("Where did I last touch my keys?");
  await clock.advance(POLL_INTERVAL_MS); // a poll for "old" is now in flight
  assert.equal(polls.length, 1);
  await controller.ask("What am I touching?");
  assert.equal(controller.view.questionId, "new");
  // Late results for the old question, by poll and by push:
  polls[0].resolve(lookingUp({ question_id: "old", status: "answered", answered_by: "storage", answer: "OLD ANSWER" }));
  await flush();
  controller.receiveState({
    questions: { recent: [lookingUp({ question_id: "old", status: "answered", answer: "OLD ANSWER" }), record({ question_id: "new" })] },
  });
  assert.equal(controller.view.questionId, "new");
  assert.equal(controller.view.record.answer, "You are touching a Heinz ketchup bottle.");
  assert.equal(controller.view.phase, "answered");
});

test("other pages' questions do not change the main answer", async () => {
  const { controller } = setup(async () => record({ question_id: "mine" }));
  await controller.ask("What am I touching?");
  controller.receiveState({ questions: { recent: [record({ question_id: "someone-else", answer: "THEIRS" }), record({ question_id: "mine" })] } });
  assert.equal(controller.view.record.answer, "You are touching a Heinz ketchup bottle.");
});

test("a new question can be asked while a lookup is pending; the new one is tracked", async () => {
  const { controller, clock, calls } = setup(async (path, options) => {
    if (options.method === "POST") return options.body.text.includes("keys") ? lookingUp() : record({ question_id: "q2" });
    return lookingUp();
  });
  await controller.ask("Where did I last touch my keys?");
  assert.equal(controller.view.phase, "looking_up");
  await controller.ask("What am I touching?");
  assert.equal(controller.trackedId, "q2");
  const count = calls.length;
  await clock.advance(LOOKUP_TIMEOUT_MS * 2);
  assert.equal(calls.length, count, "old polling and deadline were cancelled");
  assert.equal(controller.view.phase, "answered");
});

test("after ~15 s of looking_up it reports still waiting, and a late push can still answer", async () => {
  const { controller, clock, calls } = setup(async () => lookingUp());
  await controller.ask("Where did I last touch my keys?");
  await clock.advance(LOOKUP_TIMEOUT_MS);
  assert.equal(controller.view.phase, "error");
  assert.equal(controller.view.message, STILL_WAITING_MESSAGE);
  const count = calls.length;
  await clock.advance(POLL_INTERVAL_MS * 5);
  assert.equal(calls.length, count, "no polls after the deadline");
  controller.receiveState({ questions: { recent: [lookingUp()] } });
  assert.equal(controller.view.phase, "error", "a looking_up push does not clear the message");
  controller.receiveState({ questions: { recent: [lookingUp({ status: "answered", answer: "Keys at 10:02." })] } });
  assert.equal(controller.view.phase, "answered");
});

test("unavailable history comes back as unavailable", async () => {
  const { controller } = setup(async () =>
    lookingUp({ status: "unavailable", history_status: "unavailable", answer: "Touch history is unavailable right now.", detail: "Storage is not running", speech_requested: true }),
  );
  await controller.ask("Where did I last touch my keys?");
  assert.equal(controller.view.phase, "unavailable");
});

test("503 and network errors show the server detail or a plain fallback", async () => {
  const a = setup(async () => {
    throw apiError("http", 503, { detail: "Questions require the running app." });
  });
  await a.controller.ask("What can you see?");
  assert.equal(a.controller.view.phase, "error");
  assert.equal(a.controller.view.message, "Questions require the running app.");
  assert.equal(a.controller.view.text, "What can you see?");

  const b = setup(async () => {
    throw apiError("network");
  });
  await b.controller.ask("What can you see?");
  assert.match(b.controller.view.message, /Could not reach the dashboard server/);
  // and asking again works afterwards
  assert.notEqual(b.controller.view.phase, "submitting");
});

test("a poll 404 ends the lookup; a network blip keeps polling", async () => {
  let mode = "network";
  const { controller, clock, calls } = setup(async (path, options) => {
    if (options.method === "POST") return lookingUp();
    if (mode === "network") throw apiError("network");
    throw apiError("http", 404, { detail: "That question is unknown or has expired. Ask again." });
  });
  await controller.ask("Where did I last touch my keys?");
  await clock.advance(POLL_INTERVAL_MS);
  await clock.advance(POLL_INTERVAL_MS);
  assert.equal(controller.view.phase, "looking_up");
  assert.equal(calls.length, 3);
  mode = "404";
  await clock.advance(POLL_INTERVAL_MS);
  assert.equal(controller.view.phase, "error");
  assert.equal(controller.view.message, "That question is unknown or has expired. Ask again.");
});

test("empty text is rejected locally without a request", async () => {
  const { controller, calls } = setup(async () => record());
  await controller.ask("   ");
  assert.equal(calls.length, 0);
  assert.equal(controller.view.phase, "error");
});

test("dispose stops polling, aborts in-flight requests and ignores late answers", async () => {
  const poll = deferred();
  let signal = null;
  const { controller, clock, views } = setup((path, options) => {
    if (options.method === "POST") return Promise.resolve(lookingUp());
    signal = options.signal;
    return poll.promise;
  });
  await controller.ask("Where did I last touch my keys?");
  await clock.advance(POLL_INTERVAL_MS);
  const seen = views.length;
  controller.dispose();
  assert.equal(signal.aborted, true);
  poll.resolve(lookingUp({ status: "answered", answer: "late" }));
  await flush();
  controller.receiveState({ questions: { recent: [lookingUp({ status: "answered", answer: "late" })] } });
  await clock.advance(LOOKUP_TIMEOUT_MS);
  assert.equal(views.length, seen, "nothing emitted after dispose");
  assert.equal(clock.pending(), 0);
});
