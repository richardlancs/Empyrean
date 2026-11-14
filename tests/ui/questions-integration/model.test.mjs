// Pure selectors and descriptions for the questions panel (node --test).
import test from "node:test";
import assert from "node:assert/strict";

import { errorMessageFrom } from "../../../dashboard/static/core/api-client.js";
import {
  HISTORY_UNAVAILABLE_TITLE,
  MAX_QUESTION_CHARS,
  RECONNECTING_NOTE,
  announcementFor,
  announcementKey,
  describeRecord,
  findPushedRecord,
  normalizeRecord,
  requestErrorMessage,
  selectAvailability,
  selectConnectionNote,
  selectRecent,
  shouldReplace,
  validateQuestion,
} from "../../../dashboard/static/features/questions/model.js";
import { apiError, lookingUp, record } from "./helpers.mjs";

test("normalizeRecord keeps valid records and rejects unusable ones", () => {
  const r = normalizeRecord(record());
  assert.equal(r.question_id, "q1");
  assert.equal(r.status, "answered");
  assert.equal(normalizeRecord(record({ status: "pending" })), null);
  assert.equal(normalizeRecord(record({ question_id: "" })), null);
  assert.equal(normalizeRecord(null), null);
  assert.equal(normalizeRecord(record({ answered_by: "pip" })).answered_by, null);
});

test("shouldReplace: only the tracked id, and a final record never regresses", () => {
  const final = normalizeRecord(record());
  const pending = normalizeRecord(record({ status: "looking_up", answer: "Looking up…" }));
  const other = normalizeRecord(record({ question_id: "old" }));
  assert.equal(shouldReplace(null, final, "q1"), true);
  assert.equal(shouldReplace(null, other, "q1"), false, "another question is ignored");
  assert.equal(shouldReplace(final, other, "q1"), false);
  assert.equal(shouldReplace(final, pending, "q1"), false, "answered cannot go back to looking_up");
  assert.equal(shouldReplace(pending, final, "q1"), true);
  assert.equal(shouldReplace(null, final, null), false, "nothing tracked yet");
});

test("selectRecent and findPushedRecord read state.questions.recent safely", () => {
  assert.deepEqual(selectRecent(null), []);
  assert.deepEqual(selectRecent({ questions: null }), []);
  const state = { questions: { available: true, recent: [record({ question_id: "a" }), { bad: 1 }, record({ question_id: "b" })] } };
  assert.deepEqual(selectRecent(state).map((r) => r.question_id), ["a", "b"]);
  assert.equal(findPushedRecord(state, "b").question_id, "b");
  assert.equal(findPushedRecord(state, "zzz"), null);
  const many = { questions: { recent: Array.from({ length: 8 }, (_, i) => record({ question_id: `q${i}` })) } };
  assert.equal(selectRecent(many).length, 5);
});

test("capabilities.questions=false disables asking with a clear reason", () => {
  const off = selectAvailability({ capabilities: { questions: false } });
  assert.equal(off.canAsk, false);
  assert.match(off.reason, /unavailable/i);
  assert.equal(selectAvailability({ capabilities: { questions: true } }).canAsk, true);
  // questions.available=false also counts when the capability key is absent
  assert.equal(selectAvailability({ capabilities: {}, questions: { available: false, recent: [] } }).canAsk, false);
  // older backends that send neither may still ask (the server answers 503 if not)
  assert.equal(selectAvailability({ capabilities: {} }).canAsk, true);
  assert.equal(selectAvailability(null).canAsk, true);
});

test("reconnecting connection shows a delay note; others show none", () => {
  assert.equal(selectConnectionNote("reconnecting"), RECONNECTING_NOTE);
  assert.match(RECONNECTING_NOTE, /delayed/);
  assert.equal(selectConnectionNote("connected"), "");
  assert.equal(selectConnectionNote("connecting"), "");
});

test("unavailable is rendered as unavailable, never as not found", () => {
  const unavailable = normalizeRecord(
    lookingUp({ status: "unavailable", history_status: "unavailable", answer: HISTORY_UNAVAILABLE_TITLE, detail: "Storage is not running", speech_requested: true }),
  );
  const view = describeRecord(unavailable);
  assert.equal(view.tone, "unavailable");
  assert.equal(view.title, HISTORY_UNAVAILABLE_TITLE);
  assert.equal(view.body, "", "the same sentence is not repeated");
  assert.equal(view.detail, "Reason: Storage is not running.");
  assert.doesNotMatch(JSON.stringify(view), /not found|never touched|no record/i);

  const notFound = normalizeRecord(
    lookingUp({ status: "answered", history_status: "not_found", answered_by: "storage", answer: "I have no record of touching keys." }),
  );
  const nf = describeRecord(notFound);
  assert.equal(nf.tone, "answer", "a real negative answer is an answer");
  assert.equal(nf.body, "I have no record of touching keys.");
});

test("looking_up is in progress, not an answer", () => {
  const view = describeRecord(normalizeRecord(lookingUp()));
  assert.equal(view.tone, "pending");
  assert.equal(view.label, "Looking up…");
  assert.equal(view.body, "Looking up the last touch of keys…");
  assert.equal(view.speech, "");
  assert.equal(announcementFor(normalizeRecord(lookingUp())), "", "nothing is announced while looking up");
});

test("speech is only ever 'Sent to the speaker'", () => {
  assert.equal(describeRecord(normalizeRecord(record())).speech, "Sent to the speaker.");
  assert.equal(describeRecord(normalizeRecord(record({ speech_requested: false, answered_by: "storage" }))).speech, "Sent to the speaker.");
  assert.equal(describeRecord(normalizeRecord(record({ speech_requested: false, answered_by: "dashboard" }))).speech, "");
  for (const r of [record(), lookingUp(), lookingUp({ status: "unavailable" })]) {
    assert.doesNotMatch(JSON.stringify(describeRecord(normalizeRecord(r))), /spoken|heard/i);
  }
});

test("announcement text and key for final records", () => {
  const r = normalizeRecord(record());
  assert.equal(announcementFor(r), "You are touching a Heinz ketchup bottle.");
  assert.equal(announcementKey(r), "question:q1:answered");
  const u = normalizeRecord(lookingUp({ status: "unavailable", answer: HISTORY_UNAVAILABLE_TITLE }));
  assert.equal(announcementFor(u), HISTORY_UNAVAILABLE_TITLE);
});

test("validateQuestion trims and bounds the text", () => {
  assert.equal(validateQuestion("   ").ok, false);
  assert.deepEqual(validateQuestion("  what   can you see? "), { ok: true, text: "what can you see?", message: "" });
  assert.equal(validateQuestion("x".repeat(MAX_QUESTION_CHARS)).ok, true);
  assert.equal(validateQuestion("x".repeat(MAX_QUESTION_CHARS + 1)).ok, false);
});

test("requestErrorMessage prefers the server detail", () => {
  assert.equal(
    requestErrorMessage(apiError("http", 503, { detail: "Questions require the running app." }), errorMessageFrom),
    "Questions require the running app.",
  );
  assert.equal(requestErrorMessage(apiError("http", 422, { detail: "Please enter a question." }), errorMessageFrom), "Please enter a question.");
  assert.match(requestErrorMessage(apiError("network"), errorMessageFrom), /Could not reach/);
  assert.match(requestErrorMessage(apiError("timeout"), errorMessageFrom), /in time/);
  assert.match(requestErrorMessage(apiError("http", 404, null), errorMessageFrom), /expired/);
});
