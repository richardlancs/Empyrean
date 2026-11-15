// Camera view: MJPEG image, freshness state, overlay toggles, fit and
// fullscreen controls, legend and measurements. Leaf view: the controller
// decides the stream URL and options; this module only shows them and reports
// user intent and <img> load/error through callbacks.

import { createDetectorSwitch } from "./detector-switch.js";
import { createPipCompanion } from "./pip-companion.js";
import { el, setHidden, setText, uniqueId } from "./dom.js";

const LEGEND = [
  ["touching", "Touching", "thick green box"],
  ["held", "Holding", "yellow box"],
  ["idle", "In view", "white box with name"],
  ["new", "New", "thin grey box"],
  ["lost", "Temporarily lost", "dashed white box"],
  ["hand", "Fingertips", "blue dots on thumb and index finger"],
];

function fullscreenApi(node) {
  const request = node.requestFullscreen || node.webkitRequestFullscreen;
  const exit = document.exitFullscreen || document.webkitExitFullscreen;
  const current = () => document.fullscreenElement || document.webkitFullscreenElement || null;
  return { supported: Boolean(request && exit), request: () => request.call(node), exit: () => exit.call(document), current };
}

/**
 * Build the camera panel. Callbacks:
 * onStream(status) with "loading" | "loaded" | "error";
 * onOption(name, value) for boxes | hands | labels | fit;
 * onDetector(mode) when the Regular | Demo control is chosen.
 * onDemoAlert() requests a stairs HazardEvent through the live alarm path.
 */
export function createCameraPanel(root, { onStream, onOption, onDetector = () => {}, onDemoAlert = () => {} }) {
  const headingId = uniqueId("experience-camera-heading");
  const stateTitle = el("span", { class: "experience-camera-state-title" });
  const stateDetail = el("span", { class: "experience-muted" });
  const stateLine = el("p", { class: "experience-camera-state", role: "status" }, stateTitle, " ", stateDetail);
  const heading = el("h2", { id: headingId, class: "experience-heading", text: "Camera" });

  // The alternative text is set from the camera state on every update (live, demo clip,
  // out of date or unavailable); this initial text is replaced on the first update.
  const img = el("img", {
    class: "experience-camera-img",
    alt: "Camera picture not available yet: waiting for the first frame.",
    decoding: "async",
  });
  const staleMark = el("div", { class: "experience-camera-stale-mark", "aria-hidden": "true" });
  const frame = el("div", { class: "experience-camera-frame" }, img, staleMark);

  const fitButton = el("button", { type: "button", class: "experience-button experience-button-quiet", "aria-pressed": "false" });
  const fsButton = el("button", { type: "button", class: "experience-button experience-button-quiet" });
  const demoStatusId = uniqueId("experience-demo-alert-status");
  const demoButton = el("button", {
    type: "button",
    class: "experience-button experience-button-primary experience-button-demo-alert",
    text: "Demo alert",
    title: "Play the stairs alarm and Stop. Stairs. through the speaker. Interrupts speech and logs a hazard.",
    "aria-describedby": demoStatusId,
  });
  const demoStatus = el("p", {
    id: demoStatusId,
    class: "experience-muted experience-demo-alert-status",
    role: "status",
    "aria-live": "polite",
  });
  demoStatus.hidden = true;
  let demoPending = false;
  let destroyed = false;
  const onDemoClick = async () => {
    if (demoPending || destroyed) return;
    demoPending = true;
    demoButton.setAttribute("aria-disabled", "true");
    demoButton.setAttribute("aria-busy", "true");
    demoStatus.hidden = false;
    setText(demoStatus, "Requesting the stairs alarm…");
    try {
      await onDemoAlert();
      if (!destroyed) setText(demoStatus, "Stairs alarm requested through the live hazard system.");
    } catch (error) {
      if (!destroyed) setText(demoStatus, error?.message || "Could not add the demo alert. Try again.");
    } finally {
      demoPending = false;
      if (!destroyed) {
        demoButton.setAttribute("aria-disabled", "false");
        demoButton.setAttribute("aria-busy", "false");
      }
    }
  };
  demoButton.addEventListener("click", onDemoClick);
  const fsFallback = el("a", {
    class: "experience-button experience-button-quiet",
    href: "/video",
    target: "_blank",
    rel: "noopener",
    text: "Open video in a new tab",
  });

  const toggles = {};
  const toggleRow = el("div", { class: "experience-toggle-row" });
  for (const [key, label] of [["boxes", "Boxes"], ["hands", "Hand markers"], ["labels", "Labels"]]) {
    const input = el("input", { type: "checkbox", class: "experience-checkbox" });
    input.addEventListener("change", () => onOption(key, input.checked));
    toggles[key] = input;
    toggleRow.append(el("label", { class: "experience-toggle" }, input, el("span", { text: label })));
  }
  const overlayNote = el("p", { class: "experience-muted" });
  const overlayGroup = el(
    "fieldset",
    { class: "experience-fieldset" },
    el("legend", { text: "Show on video (this screen only)" }),
    toggleRow,
    overlayNote,
  );

  const legendList = el(
    "ul",
    { class: "experience-legend" },
    ...LEGEND.map(([key, label, look]) =>
      el(
        "li",
        {},
        el("span", { class: `experience-swatch experience-swatch-${key}`, "aria-hidden": "true" }),
        el("span", { text: `${label}: ${look}` }),
      ),
    ),
  );
  const legend = el("details", { class: "experience-details" }, el("summary", { text: "What the boxes mean" }), legendList);

  const fps = el("dd");
  const age = el("dd");
  const size = el("dd");
  const footer = el(
    "dl",
    { class: "experience-camera-footer" },
    el("div", {}, el("dt", { text: "Frame rate" }), fps),
    el("div", {}, el("dt", { text: "Frame age" }), age),
    el("div", {}, el("dt", { text: "Frame size" }), size),
  );

  // Friendly clarity: the picture and its state first; full screen stays one quiet
  // click away; size, overlays and the legend live in "View options".
  const options = el(
    "details",
    { class: "experience-details experience-camera-options" },
    el("summary", { text: "View options" }),
    el("div", { class: "experience-controls" }, fitButton),
    overlayGroup,
    legend,
  );
  // Regular | Demo sits right under the heading; its badge stays beside the heading
  // for as long as vision reports the demo detector.
  const detectorMount = el("div", { class: "experience-detector-mount" });
  const detector = createDetectorSwitch(detectorMount, { onChoose: onDetector });
  const pipMount = el("div", { class: "experience-pip-mount" });
  const pip = createPipCompanion(pipMount);
  const card = el(
    "section",
    { class: "experience-card experience-camera", "aria-labelledby": headingId },
    el(
      "div",
      { class: "experience-camera-top" },
      el("div", { class: "experience-camera-title" }, heading, detector.badge),
      el("div", { class: "experience-controls" }, demoButton, fsButton, fsFallback),
    ),
    demoStatus,
    detectorMount,
    // Pip perches on the frame's top edge in this row, beside the camera state, so the
    // space is reserved and Pip never covers the picture, labels or controls.
    el("div", { class: "experience-camera-perch-row" }, stateLine, pipMount),
    pip.bubble,
    frame,
    footer,
    options,
  );
  root.replaceChildren(card);

  const fs = fullscreenApi(frame);
  setHidden(fsButton, !fs.supported);
  setHidden(fsFallback, fs.supported);

  let currentSrc = "";
  let fit = "contain";

  const onLoad = () => onStream("loaded");
  const onError = () => onStream("error");
  img.addEventListener("load", onLoad);
  img.addEventListener("error", onError);

  fitButton.addEventListener("click", () => onOption("fit", fit === "contain" ? "actual" : "contain"));
  fsButton.addEventListener("click", () => {
    if (fs.current() === frame) fs.exit()?.catch?.(() => {});
    else fs.request()?.catch?.(() => setHidden(fsFallback, false));
  });
  const onFsChange = () => {
    const active = fs.current() === frame;
    setText(fsButton, active ? "Exit full screen" : "Full screen");
    frame.classList.toggle("experience-is-fullscreen", active);
  };
  document.addEventListener("fullscreenchange", onFsChange);
  document.addEventListener("webkitfullscreenchange", onFsChange);
  onFsChange();

  /** Update from the camera view model plus local options. */
  function update(vm, options, src) {
    card.dataset.camera = vm.kind;
    if (img.alt !== vm.altText) img.alt = vm.altText;
    setText(stateTitle, vm.title);
    setText(stateDetail, vm.detail);
    frame.classList.toggle("experience-is-stale", !vm.isCurrent);
    setText(staleMark, vm.isCurrent ? "" : vm.kind === "live" ? "" : vm.title);

    if (src !== currentSrc) {
      currentSrc = src;
      onStream("loading");
      img.src = src;
    }
    fsFallback.href = src;

    fit = options.fit;
    frame.dataset.fit = fit;
    fitButton.setAttribute("aria-pressed", fit === "actual" ? "true" : "false");
    setText(fitButton, fit === "contain" ? "Show actual size" : "Fit to panel");

    for (const key of Object.keys(toggles)) {
      toggles[key].checked = options[key];
      toggles[key].disabled = !vm.overlaysSupported;
    }
    setText(
      overlayNote,
      vm.overlaysSupported
        ? "These switches change only this view. Detection keeps running."
        : "This laptop draws a fixed set of overlays, so these switches are unavailable.",
    );

    setText(fps, vm.footer.fps);
    setText(age, vm.footer.frameAge);
    setText(size, vm.footer.size);
  }

  return {
    update,
    updateDetector: detector.update,
    updatePip: pip.update,
    destroy() {
      destroyed = true;
      demoButton.removeEventListener("click", onDemoClick);
      detector.destroy();
      pip.destroy();
      img.removeEventListener("load", onLoad);
      img.removeEventListener("error", onError);
      document.removeEventListener("fullscreenchange", onFsChange);
      document.removeEventListener("webkitfullscreenchange", onFsChange);
      if (fs.current() === frame) fs.exit()?.catch?.(() => {});
      // Clearing src closes the MJPEG connection.
      img.removeAttribute("src");
      root.replaceChildren();
    },
  };
}
