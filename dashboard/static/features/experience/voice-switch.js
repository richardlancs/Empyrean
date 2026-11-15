// Voice picker. Leaf view: shows selectVoice()'s model in a labelled native <select>
// and reports the user's choice through onChoose(key). The select always shows the
// voice audio has confirmed. A locked select stays focusable (aria-disabled, not
// disabled) so keyboard focus is never lost mid-switch; a change while locked is undone.

import { el, setText, uniqueId } from "./dom.js";

/** Build the picker inside root; returns { update(vm), destroy() }. */
export function createVoiceSwitch(root, { onChoose }) {
  const selectId = uniqueId("experience-voice-select");
  const statusId = uniqueId("experience-voice-status");
  const select = el("select", { id: selectId, class: "experience-voice-select", "aria-describedby": statusId });
  const status = el("p", { id: statusId, class: "experience-voice-status", role: "status", "aria-live": "polite" });
  const box = el(
    "div",
    { class: "experience-voice" },
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
  let optionsKey = "";

  select.addEventListener("change", () => {
    const chosen = select.value;
    // Snap back to the confirmed voice; only audio's VoiceStatus moves it.
    select.value = current.value ?? "";
    if (current.locked || !chosen || chosen === current.value) return;
    onChoose(chosen);
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

  function update(vm) {
    current = { value: vm.value, locked: vm.locked };
    renderOptions(vm.options, vm.value);
    const value = vm.value ?? "";
    if (select.value !== value) select.value = value;
    select.setAttribute("aria-disabled", vm.locked ? "true" : "false");
    if (vm.tone === "busy") select.setAttribute("aria-busy", "true");
    else select.removeAttribute("aria-busy");
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
