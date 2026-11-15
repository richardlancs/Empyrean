// Voice and language pickers. Leaf view: shows selectLanguage()'s and selectVoice()'s
// models in two labelled native <select>s (Language above Voice) and reports the
// user's choice through onChooseLanguage(code) and onChoose(key). Both selects always
// show what audio has confirmed. A locked select stays focusable (aria-disabled, not
// disabled) so keyboard focus is never lost mid-switch; a change while locked is undone.
// One status line describes both. Language names are native and carry `lang`; the
// rest of the page stays English.

import { el, setText, uniqueId } from "./dom.js";

/** Build the pickers inside root; returns { update(voiceVm, languageVm?), destroy() }. */
export function createVoiceSwitch(root, { onChoose, onChooseLanguage = () => {} }) {
  const selectId = uniqueId("experience-voice-select");
  const languageId = uniqueId("experience-language-select");
  const statusId = uniqueId("experience-voice-status");
  const select = el("select", { id: selectId, class: "experience-voice-select", "aria-describedby": statusId });
  const languageSelect = el("select", {
    id: languageId,
    class: "experience-voice-select experience-language-select",
    "aria-describedby": statusId,
  });
  const status = el("p", { id: statusId, class: "experience-voice-status", role: "status", "aria-live": "polite" });
  const languageRow = el(
    "div",
    { class: "experience-voice-row experience-language-row" },
    el("label", { class: "experience-voice-label", for: languageId, text: "Language" }),
    languageSelect,
  );
  languageRow.hidden = true;
  const box = el(
    "div",
    { class: "experience-voice" },
    languageRow,
    el(
      "div",
      { class: "experience-voice-row" },
      el("label", { class: "experience-voice-label", for: selectId, text: "Voice" }),
      select,
    ),
    status,
  );
  root.replaceChildren(box);

  let current = { value: null, locked: true };
  let currentLanguage = { value: null, locked: true };
  let optionsKey = "";
  let languageKey = "";

  select.addEventListener("change", () => {
    const chosen = select.value;
    // Snap back to the confirmed voice; only audio's VoiceStatus moves it.
    select.value = current.value ?? "";
    if (current.locked || !chosen || chosen === current.value) return;
    onChoose(chosen);
  });

  languageSelect.addEventListener("change", () => {
    const chosen = languageSelect.value;
    // Snap back to the confirmed language; only audio's VoiceStatus moves it.
    languageSelect.value = currentLanguage.value ?? "";
    if (currentLanguage.locked || !chosen || chosen === currentLanguage.value) return;
    onChooseLanguage(chosen);
  });

  function renderOptions(options, value) {
    // With no confirmed voice, a placeholder is shown instead of claiming one.
    const list = value ? [...options] : [{ key: "", text: "Not reported" }, ...options];
    // A voice audio confirmed but did not list still shows as selected.
    if (value && !list.some((o) => o.key === value)) list.push({ key: value, text: value });
    const key = JSON.stringify(list.map((o) => [o.key, o.text]));
    if (key === optionsKey) return;
    optionsKey = key;
    select.replaceChildren(...list.map((o) => el("option", { value: o.key, text: o.text })));
  }

  function renderLanguages(options, value) {
    const list = value ? [...options] : [{ code: "", label: "Not reported", english: true }, ...options];
    if (value && !list.some((o) => o.code === value)) list.push({ code: value, label: value });
    const key = JSON.stringify(list.map((o) => [o.code, o.label]));
    if (key === languageKey) return;
    languageKey = key;
    languageSelect.replaceChildren(
      ...list.map((o) => el("option", { value: o.code, text: o.label, lang: o.english ? null : o.code })),
    );
  }

  function update(vm, languageVm = null) {
    current = { value: vm.value, locked: vm.locked };
    renderOptions(vm.options, vm.value);
    const value = vm.value ?? "";
    if (select.value !== value) select.value = value;
    select.setAttribute("aria-disabled", vm.locked ? "true" : "false");
    if (vm.tone === "busy") select.setAttribute("aria-busy", "true");
    else select.removeAttribute("aria-busy");

    const showLanguage = Boolean(languageVm?.visible);
    if (languageRow.hidden === showLanguage) languageRow.hidden = !showLanguage;
    if (showLanguage) {
      currentLanguage = { value: languageVm.value, locked: languageVm.locked };
      renderLanguages(languageVm.options, languageVm.value);
      const code = languageVm.value ?? "";
      if (languageSelect.value !== code) languageSelect.value = code;
      languageSelect.setAttribute("aria-disabled", languageVm.locked ? "true" : "false");
      if (vm.tone === "busy") languageSelect.setAttribute("aria-busy", "true");
      else languageSelect.removeAttribute("aria-busy");
    } else {
      currentLanguage = { value: null, locked: true };
    }

    box.dataset.tone = vm.tone;
    setText(status, vm.statusText);
  }

  return {
    update,
    destroy() {
      root.replaceChildren();
    },
  };
}
