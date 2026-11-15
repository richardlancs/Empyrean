import test from "node:test";
import assert from "node:assert/strict";
import { createVoiceInput, voiceStatusText } from "../../../dashboard/static/features/questions/voice.js";
import { createPlaybackPause } from "../../../dashboard/static/features/questions/playback.js";
import { createClock, createFakeRecognition, record } from "./helpers.mjs";

function setup() {
  const clock = createClock();
  const { FakeRecognition, instances } = createFakeRecognition();
  const transcripts = [];
  const voice = createVoiceInput({ Recognition: FakeRecognition,
    onChange: () => {}, onTranscript: (text) => transcripts.push(text),
    setTimer: clock.setTimer, clearTimer: clock.clearTimer });
  return { clock, instances, transcripts, voice };
}

test("mic is off until enabled; final question submits once and listening resumes", async () => {
  const { clock, instances, transcripts, voice } = setup();
  assert.equal(instances.length, 0);
  voice.toggle();
  instances[0].emitResult([["what do you", false]]);
  assert.deepEqual(transcripts, []);
  instances[0].emitResult([["what do you see", true]]);
  instances[0].emitResult([["duplicate", true]]);
  instances[0].emitEnd();
  assert.deepEqual(transcripts, ["what do you see"]);
  await clock.advance(350);
  assert.equal(instances.length, 2);
  assert.equal(voice.enabled, true);
  assert.equal(voiceStatusText(voice.view), "Listening… ask your question.");
  voice.toggle();
  assert.equal(voice.enabled, false);
  assert.equal(instances[1].aborted, 1);
});

test("silence restarts, pause stops recognition, and stop cancels restart", async () => {
  const { clock, instances, voice } = setup();
  voice.start();
  instances[0].emitError("no-speech");
  await clock.advance(350);
  assert.equal(instances.length, 2);
  voice.setPaused(true);
  assert.equal(instances[1].aborted, 1);
  assert.equal(voice.view.phase, "paused");
  await clock.advance(1000);
  assert.equal(instances.length, 2);
  voice.setPaused(false);
  await clock.advance(350);
  assert.equal(instances.length, 3);
  voice.stop();
  instances[2].emitEnd();
  await clock.advance(1000);
  assert.equal(instances.length, 3);
});

test("mic permission or network failure turns off the session with a useful message", () => {
  for (const code of ["not-allowed", "network"]) {
    const { instances, voice } = setup();
    voice.start();
    instances[0].emitError(code);
    assert.equal(voice.enabled, false);
    assert.equal(voice.view.phase, "error");
    assert.match(voice.view.message, code === "network" ? /Google Chrome/ : /microphone access/);
  }
});

test("question and speaker completion gate microphone restart", async () => {
  const { clock, voice, instances } = setup();
  const gate = createPlaybackPause({ onChange: (paused) => voice.setPaused(paused),
    setTimer: clock.setTimer, clearTimer: clock.clearTimer });
  voice.start();
  const pending = record({ status: "looking_up", answer: null });
  gate.update({ phase: "looking_up", record: pending }, {}, "connected");
  assert.equal(voice.view.phase, "paused");
  const answer = record();
  gate.update({ phase: "answered", record: answer }, {}, "connected");
  assert.equal(voice.view.phase, "paused");
  gate.update({ phase: "answered", record: answer }, { speech: {
    text: answer.answer, ts: answer.asked_at + 1, status: "completed" } }, "connected");
  await clock.advance(350);
  assert.equal(instances.length, 2);
  gate.destroy();
  voice.destroy();
});
