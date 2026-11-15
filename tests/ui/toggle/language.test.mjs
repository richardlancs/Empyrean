// Language picker: view model, voice filtering and the picker's request choice.
// Run: node --test tests/ui/toggle/
// All data here is artificial fixture data.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  languageRequestVoice,
  selectLanguage,
  selectVoice,
} from "../../../dashboard/static/features/experience/selectors.js";
import { createVoiceSwitch } from "../../../dashboard/static/features/experience/voice-switch.js";
import { FakeDocument } from "../agent1/js/fakes.mjs";

const OPTIONS = [
  { key: "ava", label: "Ava", installed: true, language: "en" },
  { key: "zoe", label: "Zoe", installed: true, language: "en" },
  { key: "claude", label: "Claude", installed: true, language: "es" },
  { key: "siwis_missing", label: "Gilles", installed: false, language: "fr" },
  { key: "siwis", label: "Siwis", installed: true, language: "fr" },
  { key: "huayan", label: "Huayan", installed: true, language: "zh" },
  { key: "priya", label: "Priya", installed: false, language: "hi" },
];
const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "zh", label: "中文" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "hi", label: "हिन्दी" },
];
const voice = (over = {}) => ({
  state: "active", active_voice: "ava", label: "Ava", quality: "premium", options: OPTIONS,
  language: "en", languages: LANGUAGES,
  switching_to: null, message: "", request_id: null, updated_ts: 100, ...over,
});
const snap = (v, connection = "connected", caps = { voice_switch: true }) => ({ connection, state: { capabilities: caps, voice: v } });
const idle = { sending: null, error: null, requestId: null, at: null };

test("language options follow the server's list and native labels", () => {
  const vm = selectLanguage(snap(voice()), idle);
  assert.deepEqual(vm.options, LANGUAGES);
  assert.equal(vm.value, "en");
  assert.equal(vm.locked, false);
  assert.equal(vm.visible, true);
  assert.equal(vm.statusText, "Voice: Ava (English)");
});

test("the voice list shows only the confirmed language's voices", () => {
  assert.deepEqual(selectVoice(snap(voice()), idle).options.map((o) => o.key), ["ava", "zoe"]);
  const fr = selectVoice(snap(voice({ active_voice: "siwis", label: "Siwis", language: "fr" })), idle);
  assert.deepEqual(fr.options.map((o) => o.key), ["siwis_missing", "siwis"]);
  assert.equal(fr.options[0].text, "Gilles (not installed)");
  assert.equal(fr.statusText, "Voice: Siwis (Français)");
});

test("fallback: English language keeps the confirmed voice listed and says fallback", () => {
  const vm = selectVoice(snap(voice({ active_voice: "priya", label: "Priya", quality: "fallback", language: "en" })), idle);
  assert.deepEqual(vm.options.map((o) => o.key), ["ava", "zoe", "priya"]);
  assert.equal(vm.statusText, "Voice: Priya (English, fallback voice)");
  assert.equal(selectLanguage(snap(voice({ active_voice: "priya", quality: "fallback", language: "en" })), idle).value, "en");
});

test("both pickers lock while a switch is pending", () => {
  const cases = [
    [snap(voice({ state: "switching", switching_to: "claude" })), idle, /Switching to Claude \(Español\)…/],
    [snap(voice()), { ...idle, sending: "claude", language: "es" }, /Asking to switch to Español \(Claude\)…/],
    [snap(voice(), "reconnecting"), idle, /Disconnected/],
  ];
  for (const [s, local, text] of cases) {
    const lang = selectLanguage(s, local);
    const v = selectVoice(s, local);
    assert.equal(lang.locked, true);
    assert.equal(v.locked, true);
    assert.match(lang.statusText, text);
    assert.equal(lang.value, "en");
  }
});

test("unknown, missing capability and older servers lock or hide the language picker", () => {
  const unknown = selectLanguage(snap(voice({ state: "unknown", active_voice: null })), idle);
  assert.equal(unknown.locked, true);
  assert.equal(unknown.value, null);
  const nocap = selectLanguage(snap(voice(), "connected", { voice_switch: false }), idle);
  assert.equal(nocap.locked, true);
  assert.equal(nocap.visible, false);
  const older = selectLanguage(snap(voice({ languages: undefined, language: undefined })), idle);
  assert.equal(older.visible, false);
  assert.equal(selectLanguage({ connection: "connecting", state: null }, idle).locked, true);
});

test("a new language requests that language's first installed voice", () => {
  const s = snap(voice());
  assert.equal(languageRequestVoice(s, "es"), "claude");
  assert.equal(languageRequestVoice(s, "fr"), "siwis");
  assert.equal(languageRequestVoice(s, "hi"), "priya");
  assert.equal(languageRequestVoice(s, "xx"), null);
});

test("no text calls this a safety device", () => {
  for (const v of [voice(), voice({ state: "switching", switching_to: "claude" })]) {
    assert.doesNotMatch(selectLanguage(snap(v), idle).statusText, /safety/i);
  }
});

// ---------------------------------------------------------------------------
// The picker view, on a tiny fake DOM.

function mount() {
  const doc = new FakeDocument();
  const createElement = doc.createElement.bind(doc);
  doc.createElement = (tag) => Object.assign(createElement(tag), { dataset: {}, hidden: false, value: "" });
  globalThis.document = doc;
  globalThis.Node = Object.getPrototypeOf(Object.getPrototypeOf(doc.body)).constructor;
  const root = doc.createElement("div");
  const chosen = { voice: [], language: [] };
  const view = createVoiceSwitch(root, {
    onChoose: (key) => chosen.voice.push(key),
    onChooseLanguage: (code) => chosen.language.push(code),
  });
  const selects = root.findAll((n) => n.tagName === "SELECT");
  const labels = root.findAll((n) => n.tagName === "LABEL");
  return { root, view, chosen, language: selects[0], voiceSelect: selects[1], labels };
}

function render(m, s, local = idle) {
  m.view.update(selectVoice(s, local), selectLanguage(s, local));
}

test("view: Language select above Voice, labelled, options carry lang", () => {
  const m = mount();
  render(m, snap(voice()));
  assert.deepEqual(m.labels.map((l) => l.textContent), ["Language", "Voice"]);
  assert.equal(m.labels[0].getAttribute("for"), m.language.id);
  const opts = m.language.children;
  assert.deepEqual(opts.map((o) => o.textContent), ["English", "中文", "Español", "Français", "हिन्दी"]);
  assert.deepEqual(opts.map((o) => o.getAttribute("lang")), ["en", "zh", "es", "fr", "hi"]);
  assert.equal(m.language.value, "en");
  assert.deepEqual(m.voiceSelect.children.map((o) => o.getAttribute("value")), ["ava", "zoe"]);
});

test("view: choosing a new language reports it; the current one sends nothing", () => {
  const m = mount();
  render(m, snap(voice()));
  m.language.value = "es";
  m.language.dispatch("change");
  assert.deepEqual(m.chosen.language, ["es"]);
  assert.equal(m.language.value, "en", "snaps back to the confirmed language");
  m.language.value = "en";
  m.language.dispatch("change");
  assert.deepEqual(m.chosen.language, ["es"]);
});

test("view: a locked language select undoes the change and sends nothing", () => {
  const m = mount();
  render(m, snap(voice()), { ...idle, sending: "claude", language: "es" });
  assert.equal(m.language.getAttribute("aria-disabled"), "true");
  assert.equal(m.voiceSelect.getAttribute("aria-disabled"), "true");
  m.language.value = "fr";
  m.language.dispatch("change");
  assert.deepEqual(m.chosen.language, []);
  assert.equal(m.language.value, "en");
});

test("view: an older server without languages hides the Language row", () => {
  const m = mount();
  render(m, snap(voice({ languages: undefined, language: undefined })));
  assert.equal(m.language.parentNode.hidden, true);
});
