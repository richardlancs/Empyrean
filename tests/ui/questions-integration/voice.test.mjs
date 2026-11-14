// Microphone lifecycle with a fake SpeechRecognition (node --test).
import test from "node:test";
import assert from "node:assert/strict";

import {
  PRIVACY_NOTE,
  UNSUPPORTED_MESSAGE,
  VOICE_FALLBACK_ERROR,
  createVoiceInput,
  defaultRecognition,
  voiceErrorMessage,
  voiceStatusText,
} from "../../../dashboard/static/features/questions/voice.js";
import { createFakeRecognition } from "./helpers.mjs";

function setup() {
  const { FakeRecognition, instances } = createFakeRecognition();
  const views = [];
  const transcripts = [];
  const voice = createVoiceInput({
    Recognition: FakeRecognition,
    onChange: (v) => views.push(v),
    onTranscript: (t) => transcripts.push(t),
  });
  return { voice, instances, views, transcripts };
}

test("nothing starts on creation (no auto-start, no hot mic)", () => {
  const { voice, instances } = setup();
  assert.equal(instances.length, 0);
  assert.equal(voice.view.phase, "idle");
});

test("a click starts exactly one recognition configured for one utterance", () => {
  const { voice, instances } = setup();
  voice.toggle();
  assert.equal(instances.length, 1);
  const rec = instances[0];
  assert.equal(rec.started, 1);
  assert.equal(rec.lang, "en-US");
  assert.equal(rec.continuous, false);
  assert.equal(rec.interimResults, true);
  assert.equal(voice.view.phase, "listening");
  assert.equal(voiceStatusText(voice.view), "Listening… speak your question.");
});

test("repeated starts never overlap; a second click stops the live one", () => {
  const { voice, instances } = setup();
  voice.start();
  voice.start();
  voice.start();
  assert.equal(instances.length, 1);
  voice.toggle(); // click while listening -> stop
  assert.equal(instances.length, 1);
  assert.equal(instances[0].stopped, 1);
  voice.toggle(); // still waiting for onend: stop again, no new recognition
  assert.equal(instances.length, 1);
});

test("interim text shows live; the final transcript fills the input without submitting", () => {
  const { voice, instances, transcripts } = setup();
  voice.toggle();
  const rec = instances[0];
  rec.emitResult([["where did I", false]]);
  assert.equal(voice.view.phase, "listening");
  assert.equal(voice.view.interim, "where did I");
  assert.deepEqual(transcripts, [], "interim text does not go into the input");
  rec.emitResult([["where did I last touch my keys", true]]);
  rec.emitEnd();
  assert.deepEqual(transcripts, ["where did I last touch my keys"]);
  assert.equal(voice.view.phase, "transcript");
  assert.equal(voiceStatusText(voice.view), "Check the text, then press Ask.");
});

test("no restart after onend", () => {
  const { voice, instances } = setup();
  voice.toggle();
  instances[0].emitResult([["what can you see", true]]);
  instances[0].emitEnd();
  assert.equal(instances.length, 1);
  assert.equal(instances[0].started, 1);
  assert.equal(voice.listening, false);
  // a new click starts a fresh, single recognition
  voice.toggle();
  assert.equal(instances.length, 2);
});

test("each error code maps to its message", () => {
  const cases = {
    "not-allowed": "Allow microphone access, then try again.",
    "service-not-allowed": "Allow microphone access, then try again.",
    "audio-capture": "No microphone available. Check sound input settings.",
    network: "Speech recognition service unavailable. Open this dashboard in Google Chrome, or type your question.",
    "no-speech": "Didn't hear anything. Try again or type your question.",
    "language-not-supported": VOICE_FALLBACK_ERROR,
    "bad-grammar": VOICE_FALLBACK_ERROR,
  };
  for (const [code, message] of Object.entries(cases)) {
    assert.equal(voiceErrorMessage(code), message, code);
    const { voice, instances } = setup();
    voice.toggle();
    instances[0].emitError(code);
    instances[0].emitEnd();
    assert.equal(voice.view.phase, "error", code);
    assert.equal(voiceStatusText(voice.view), message, code);
    assert.equal(instances.length, 1, `${code}: no restart`);
  }
});

test("aborted returns to idle silently", () => {
  const { voice, instances } = setup();
  voice.toggle();
  instances[0].emitError("aborted");
  instances[0].emitEnd();
  assert.equal(voice.view.phase, "idle");
  assert.equal(voice.view.message, "");
});

test("user stop with nothing heard shows stopped", () => {
  const { voice, instances } = setup();
  voice.toggle();
  voice.toggle();
  instances[0].emitEnd();
  assert.equal(voice.view.phase, "stopped");
});

test("cancel aborts and detaches handlers", () => {
  const { voice, instances, transcripts } = setup();
  voice.toggle();
  const rec = instances[0];
  voice.cancel();
  assert.equal(rec.aborted, 1);
  assert.equal(rec.onresult, null);
  assert.equal(rec.onerror, null);
  assert.equal(rec.onend, null);
  assert.equal(voice.view.phase, "idle");
  assert.deepEqual(transcripts, []);
});

test("destroy (unmount) aborts the live recognition and stops reporting", () => {
  const { voice, instances, views } = setup();
  voice.toggle();
  const rec = instances[0];
  const seen = views.length;
  voice.destroy();
  assert.equal(rec.aborted, 1);
  assert.equal(rec.onend, null);
  voice.toggle();
  assert.equal(instances.length, 1, "no start after destroy");
  assert.equal(views.length, seen);
});

test("unsupported browser: never constructs, shows the typed fallback message", () => {
  const views = [];
  const voice = createVoiceInput({ Recognition: null, onChange: (v) => views.push(v) });
  assert.equal(voice.supported, false);
  assert.equal(voice.view.phase, "unsupported");
  voice.toggle();
  assert.equal(voice.view.phase, "unsupported");
  assert.equal(voiceStatusText(voice.view), UNSUPPORTED_MESSAGE);
  assert.equal(UNSUPPORTED_MESSAGE, "Voice input isn't supported in this browser. Type your question instead.");
  assert.match(PRIVACY_NOTE, /may send audio/);
});

test("defaultRecognition prefers the standard name, then webkit, else null", () => {
  function A() {}
  function B() {}
  assert.equal(defaultRecognition({ SpeechRecognition: A, webkitSpeechRecognition: B }), A);
  assert.equal(defaultRecognition({ webkitSpeechRecognition: B }), B);
  assert.equal(defaultRecognition({}), null);
});

test("a start() that throws reports an error and leaves nothing live", () => {
  class Throwing {
    start() {
      throw new Error("InvalidStateError");
    }
    abort() {}
  }
  const voice = createVoiceInput({ Recognition: Throwing, onChange: () => {} });
  assert.equal(voice.start(), false);
  assert.equal(voice.listening, false);
  assert.equal(voice.view.phase, "error");
});
