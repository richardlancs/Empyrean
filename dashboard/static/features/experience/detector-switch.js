// Regular | Demo detector control. Leaf view: shows selectDetector()'s model and
// reports the user's choice through onChoose(mode). A button reads as pressed only
// for the mode vision has confirmed. Locked buttons stay focusable (aria-disabled)
// so keyboard focus is never lost mid-switch.

import { el, setHidden, setText, uniqueId } from "./dom.js";

const OPTIONS = [
  ["actual", "Regular"],
  ["demo", "Demo"],
];

/** Build the control inside root; returns { update(vm), badge, destroy() }. */
export function createDetectorSwitch(root, { onChoose }) {
  const labelId = uniqueId("experience-detector-label");
  const statusId = uniqueId("experience-detector-status");
  const buttons = {};
  const group = el("div", { class: "experience-segmented", role: "group", "aria-labelledby": labelId });
  for (const [mode, label] of OPTIONS) {
    const button = el(
      "button",
      { type: "button", class: "experience-segment", "aria-pressed": "false", "aria-describedby": statusId, dataset: { mode } },
      el("span", { class: "experience-segment-mark", "aria-hidden": "true" }),
      el("span", { class: "experience-segment-label", text: label }),
    );
    button.addEventListener("click", () => {
      if (button.getAttribute("aria-disabled") === "true" || button.getAttribute("aria-pressed") === "true") return;
      onChoose(mode);
    });
    buttons[mode] = button;
    group.append(button);
  }
  const support = el("p", { class: "experience-detector-support" });
  const note = el("p", { class: "experience-muted experience-detector-note" });
  const status = el("p", { id: statusId, class: "experience-detector-status", role: "status" });
  const box = el(
    "div",
    { class: "experience-detector" },
    el("div", { class: "experience-detector-row" }, el("span", { id: labelId, class: "experience-detector-label", text: "Detector" }), group),
    support,
    note,
    status,
  );
  root.replaceChildren(box);

  // The persistent badge beside the camera heading; the panel places it.
  const badge = el("span", { class: "experience-detector-badge", hidden: true });

  function update(vm) {
    setHidden(box, !vm.visible);
    box.dataset.tone = vm.tone;
    for (const [mode, button] of Object.entries(buttons)) {
      const pressed = vm.pressed === mode;
      const busy = vm.busy === mode;
      button.setAttribute("aria-pressed", pressed ? "true" : "false");
      button.setAttribute("aria-disabled", vm.locked ? "true" : "false");
      if (busy) button.setAttribute("aria-busy", "true");
      else button.removeAttribute("aria-busy");
      button.dataset.state = busy ? "busy" : pressed ? "active" : "idle";
    }
    setText(support, vm.support);
    setText(note, vm.note);
    setHidden(note, !vm.note);
    setText(status, vm.status);
    if (vm.badge) {
      badge.dataset.kind = vm.badge.kind;
      setText(badge, vm.badge.text);
    }
    setHidden(badge, !vm.badge);
  }

  return {
    update,
    badge,
    destroy() {
      root.replaceChildren();
    },
  };
}
