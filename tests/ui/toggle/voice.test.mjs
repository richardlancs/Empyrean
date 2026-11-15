// Voice picker view model. Run: node --test tests/ui/toggle/
// All data here is artificial fixture data.

import assert from "node:assert/strict";
import { test } from "node:test";

import { selectVoice } from "../../../dashboard/static/features/experience/selectors.js";

const OPTIONS = [
  { key: "ava", label: "Ava", installed: true },
  { key: "zoe", label: "Zoe", installed: true },
  { key: "evan", label: "Evan", installed: true },
  { key: "jamie", label: "Jamie", installed: true },
  { key: "matilda", label: "Matilda", installed: false },
];
const voice = (over = {}) => ({
  state: "active", active_voice: "ava", label: "Ava", quality: "premium", options: OPTIONS,
  switching_to: null, message: "", request_id: null, updated_ts: 100, ...over,
});
const snap = (v, connection = "connected", caps = { voice_switch: true }) => ({ connection, state: { capabilities: caps, voice: v } });
const idle = { sending: null, error: null, requestId: null, at: null };

test("active voice: confirmed value, unlocked, plain status", () => {
  const vm = selectVoice(snap(voice()), idle);
  assert.equal(vm.value, "ava");
  assert.equal(vm.locked, false);
  assert.equal(vm.statusText, "Voice: Ava");
  assert.equal(vm.tone, "ok");
});

test("value stays on confirmed voice while switching", () => {
  const vm = selectVoice(snap(voice({ state: "switching", switching_to: "zoe" })), idle);
  assert.equal(vm.value, "ava");
  assert.equal(vm.locked, true);
  assert.equal(vm.tone, "busy");
  assert.equal(vm.statusText, "Switching to Zoe…");
});

test("a request in flight locks the picker and keeps the confirmed value", () => {
  const vm = selectVoice(snap(voice()), { ...idle, sending: "zoe" });
  assert.equal(vm.value, "ava");
  assert.equal(vm.locked, true);
  assert.match(vm.statusText, /Asking to switch to Zoe/);
});

test("not installed voices are marked", () => {
  const vm = selectVoice(snap(voice()), idle);
  assert.deepEqual(vm.options.map((o) => o.key), ["ava", "zoe", "evan", "jamie", "matilda"]);
  assert.equal(vm.options[0].text, "Ava");
  assert.equal(vm.options[4].text, "Matilda (not installed)");
  assert.equal(vm.options[4].label, "Matilda");
});

test("fallback quality shows in status", () => {
  const vm = selectVoice(snap(voice({ active_voice: "matilda", label: "Matilda", quality: "fallback" })), idle);
  assert.equal(vm.value, "matilda");
  assert.equal(vm.statusText, "Voice: Matilda (fallback voice)");
});

test("unknown state is locked with audio message", () => {
  const vm = selectVoice(snap(voice({ state: "unknown", active_voice: null, label: null, quality: null, options: [], message: "Audio has not reported a voice." })), idle);
  assert.equal(vm.locked, true);
  assert.equal(vm.value, null);
  assert.equal(vm.statusText, "Audio has not reported a voice.");
});

test("no capability locks the picker", () => {
  const vm = selectVoice(snap(voice(), "connected", { voice_switch: false }), idle);
  assert.equal(vm.locked, true);
  assert.equal(vm.value, null);
  assert.match(vm.statusText, /not available/);
  assert.equal(selectVoice(snap(null), idle).locked, true);
  assert.equal(selectVoice({ connection: "connecting", state: null }, idle).locked, true);
});

test("failure keeps the confirmed voice, unlocked, with the service message", () => {
  const message = "Audio did not confirm Zoe within 10 s. The page shows the voice audio last reported.";
  const vm = selectVoice(snap(voice({ state: "failed", message })), idle);
  assert.equal(vm.value, "ava");
  assert.equal(vm.locked, false);
  assert.equal(vm.tone, "error");
  assert.equal(vm.statusText, message);
});

test("disconnected: last known voice, locked, said in words", () => {
  const vm = selectVoice(snap(voice(), "reconnecting"), idle);
  assert.equal(vm.value, "ava");
  assert.equal(vm.locked, true);
  assert.match(vm.statusText, /Disconnected\. Ava was the voice/);
});

test("a page's own refusal shows until audio reports something newer", () => {
  const local = { ...idle, error: "A switch to Zoe is already in progress.", at: 100 };
  const vm = selectVoice(snap(voice()), local);
  assert.equal(vm.tone, "error");
  assert.match(vm.statusText, /already in progress\. Still using Ava\./);
  assert.equal(selectVoice(snap(voice({ updated_ts: 101 })), local).statusText, "Voice: Ava");
});

test("no text calls this a safety device", () => {
  const states = [voice(), voice({ state: "switching", switching_to: "zoe" }), voice({ quality: "fallback" })];
  for (const v of states) assert.doesNotMatch(selectVoice(snap(v), idle).statusText, /safety/i);
});
