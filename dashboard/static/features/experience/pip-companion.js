// Pip on the camera frame: a help button (accessible name "Help with the camera.")
// that perches on the frame's top edge, outside the picture, in space the panel
// reserves for it. Its pose follows confirmed state (selectPip); its bubble is a
// disclosure in the normal flow, so it never covers the video or the controls.
// Pip never switches detectors: the Regular | Demo control is the only way.

import { el, setHidden, setText, uniqueId } from "./dom.js";

const ASSET = "/static/assets/pip/";
// Wide screens show the full pose; narrow screens a smaller, peeking variant of reclining.
const POSES = {
  recline: { wide: "pip-recline.png", narrow: "pip-peek-edge.png" },
  attentive: { wide: "pip-point.png", narrow: "pip-point.png" },
  wait: { wide: "pip-wait.png", narrow: "pip-wait.png" },
  concerned: { wide: "pip-concerned.png", narrow: "pip-concerned.png" },
};

/** Build Pip inside root; returns { update(vm), destroy() }. */
export function createPipCompanion(root) {
  const bubbleId = uniqueId("pip-bubble");
  const titleId = uniqueId("pip-bubble-title");

  // Decorative picture: alt="" so the button's name is the only thing read.
  const source = el("source", { media: "(max-width: 30em)" });
  const img = el("img", { class: "pip pip-perch__art", alt: "", decoding: "async", draggable: "false" });
  const picture = el("picture", { class: "pip-perch__picture" }, source, img);
  // If the artwork cannot load, the button still says what it is.
  const fallback = el("span", { class: "pip-perch__fallback", "aria-hidden": "true", text: "Help" });
  const button = el(
    "button",
    {
      type: "button",
      class: "pip-perch__button",
      "aria-label": "Help with the camera.",
      "aria-expanded": "false",
      "aria-controls": bubbleId,
    },
    picture,
    fallback,
  );

  const modeLine = el("p", { class: "pip-bubble__mode" });
  const recovery = el("p", { class: "pip-bubble__recovery" });
  const tip = el("p", { class: "pip-bubble__tip" });
  const control = el("p", { class: "pip-bubble__note", text: "To change the detector, use the Regular | Demo control above." });
  const close = el("button", { type: "button", class: "pip-bubble__close", text: "Close help" });
  const bubble = el(
    "div",
    { id: bubbleId, class: "pip-bubble", role: "group", "aria-labelledby": titleId, hidden: true },
    el("p", { id: titleId, class: "pip-bubble__title", text: "Camera help" }),
    modeLine,
    recovery,
    tip,
    control,
    close,
  );
  const perch = el("div", { class: "pip-perch", dataset: { pose: "recline" } }, button);
  root.replaceChildren(perch);

  let open = false;
  let pose = null;
  let entrance = false; // set by a confirmed pose change, used once by the next image load
  let entranceTimer = null;

  function setOpen(next, { returnFocus = false } = {}) {
    open = next;
    button.setAttribute("aria-expanded", String(open));
    setHidden(bubble, !open);
    if (!open && returnFocus) button.focus();
  }

  const onButton = () => setOpen(!open);
  const onClose = () => setOpen(false, { returnFocus: true });
  const onKey = (event) => {
    if (event.key === "Escape" && open) {
      event.stopPropagation();
      setOpen(false, { returnFocus: true });
    }
  };
  // A press outside Pip and its bubble closes the bubble without moving focus.
  const onDocPointer = (event) => {
    if (open && !perch.contains(event.target) && !bubble.contains(event.target)) setOpen(false);
  };
  const onImgError = () => perch.classList.add("pip-perch--no-art");
  const onImgLoad = () => {
    perch.classList.remove("pip-perch--no-art");
    if (!entrance) return; // a breakpoint swap or first load: no reaction
    entrance = false;
    perch.classList.add("pip-perch--arrive");
    // Removed on a timer, not animationend, so an entrance hidden by a hazard warning
    // never replays when the warning clears.
    clearTimeout(entranceTimer);
    entranceTimer = setTimeout(() => perch.classList.remove("pip-perch--arrive"), 400);
  };
  button.addEventListener("click", onButton);
  close.addEventListener("click", onClose);
  perch.addEventListener("keydown", onKey);
  bubble.addEventListener("keydown", onKey);
  document.addEventListener("pointerdown", onDocPointer);
  img.addEventListener("error", onImgError);
  img.addEventListener("load", onImgLoad);

  /** Update the pose and the help text. Text changes are not announced (no live region). */
  function update(vm) {
    if (vm.pose !== pose) {
      entrance = pose !== null;
      perch.classList.remove("pip-perch--arrive");
      pose = vm.pose;
      const files = POSES[pose] || POSES.recline;
      perch.dataset.pose = pose;
      source.srcset = ASSET + files.narrow;
      img.src = ASSET + files.wide;
    }
    setText(modeLine, vm.mode);
    setText(recovery, vm.recovery);
    setHidden(recovery, !vm.recovery);
    setText(tip, vm.tip);
  }

  return {
    update,
    /** The bubble is placed by the panel, in flow under the perch row. */
    bubble,
    destroy() {
      clearTimeout(entranceTimer);
      document.removeEventListener("pointerdown", onDocPointer);
      root.replaceChildren();
      bubble.remove();
    },
  };
}
