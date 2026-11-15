// The pipeline diagram: an SVG of the modules, a stepper that walks one touch
// through them, and the parallel hazard path. Works without the 3D stage.

import { NODES, TOUCH_STEPS, HAZARD_STEPS } from "../content.js";
import { createStepper } from "./stepper.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_W = 130;
const NODE_H = 48;
const TOKEN_SECONDS = 0.8;

/** Centre of each node in the 1100 x 310 drawing. Outputs sit in a column on the right. */
const POSITIONS = Object.freeze({
  camera: [80, 50],
  vision: [300, 50],
  scene: [520, 50],
  namer: [760, 50],
  audio: [1000, 50],
  storage: [1000, 150],
  dashboard: [1000, 250],
  hazard: [300, 250],
});

/** Every drawn connection, keyed "from>to", as an SVG path. */
const EDGES = Object.freeze({
  "camera>vision": "M145 50 H235",
  "vision>scene": "M365 50 H455",
  "scene>namer": "M585 40 H695",
  "namer>scene": "M695 60 H585",
  "scene>audio": "M540 26 C560 -14 900 -14 935 42",
  "scene>storage": "M540 74 C560 150 800 142 935 142",
  "scene>dashboard": "M520 74 C520 242 800 242 935 242",
  "vision>hazard": "M300 74 V226",
  "hazard>dashboard": "M365 258 H935",
  "hazard>storage": "M365 258 H870 V160 H935",
  "hazard>audio": "M365 258 H870 V60 H935",
});

function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, className = "ui-button ui-button--secondary") {
  const node = document.createElement("button");
  node.type = "button";
  node.className = className;
  node.textContent = label;
  return node;
}

/**
 * Replace the static step list inside root with the interactive diagram.
 * Returns { selectStep(stepId), destroy() }.
 */
export function mountPipeline(root, { reducedMotion = false } = {}) {
  const controlsHost = root.querySelector("#pipeline-controls");
  const diagramHost = root.querySelector("#pipeline-diagram");
  const caption = root.querySelector("#pipeline-caption");
  const title = root.querySelector("#pipeline-title");

  let gsap = null;
  if (!reducedMotion) {
    import("gsap").then((module) => { gsap = module.gsap; }).catch(() => { gsap = null; });
  }

  // ----- drawing -----
  const drawing = svg("svg", { viewBox: "0 -20 1100 310", role: "group", "aria-label": "Modules and the messages between them" });
  const edgeLayer = svg("g");
  const nodeLayer = svg("g");
  const tokenLayer = svg("g", { "aria-hidden": "true" });
  drawing.append(edgeLayer, nodeLayer, tokenLayer);

  const edgeEls = new Map();
  for (const [key, d] of Object.entries(EDGES)) {
    const path = svg("path", { d, class: "pipe-edge" });
    edgeLayer.append(path);
    edgeEls.set(key, path);
  }

  const nodeEls = new Map();
  for (const node of NODES) {
    const [x, y] = POSITIONS[node.id];
    const group = svg("g", { class: "pipe-node", role: "button", tabindex: 0, "aria-label": `${node.label}: go to its step` });
    group.append(
      svg("rect", { x: x - NODE_W / 2, y: y - NODE_H / 2, width: NODE_W, height: NODE_H, rx: 10 }),
      svg("text", { x, y }, node.label),
    );
    const jump = () => active.stepper.jumpToNode(node.id);
    group.addEventListener("click", jump);
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        jump();
      }
    });
    nodeLayer.append(group);
    nodeEls.set(node.id, group);
  }

  // ----- controls -----
  const play = button("Play", "ui-button");
  play.setAttribute("aria-pressed", "false");
  const back = button("Back");
  const next = button("Next");
  const swap = button("What about hazards?");
  const count = document.createElement("span");
  count.className = "how-meta";
  controlsHost.append(play, back, next, count, swap);

  // ----- state -----
  let tweens = [];
  const sequences = {};
  function makeSequence(name, steps) {
    sequences[name] = {
      name,
      steps,
      stepper: createStepper({
        steps,
        onChange: () => render(true),
        onPlayingChange: (playing) => {
          play.textContent = playing ? "Pause" : "Play";
          play.setAttribute("aria-pressed", playing ? "true" : "false");
        },
      }),
    };
  }
  makeSequence("touch", TOUCH_STEPS);
  makeSequence("hazard", HAZARD_STEPS);
  let active = sequences.touch;

  function clearTokens() {
    for (const tween of tweens) tween.kill();
    tweens = [];
    tokenLayer.replaceChildren();
  }

  function sendToken(path, message, alarm, animate) {
    const width = message.length * 7.2 + 16;
    const token = svg("g", { class: alarm ? "pipe-token is-alarm" : "pipe-token" });
    token.append(
      svg("rect", { x: -width / 2, y: -11, width, height: 22, rx: 6 }),
      svg("text", { x: 0, y: 0 }, message),
    );
    tokenLayer.append(token);
    const length = path.getTotalLength();
    // Short links: rest in the middle. Long ones: rest near the receiver.
    const rest = length < 160 ? 0.5 : 0.88;
    const place = (t) => {
      const point = path.getPointAtLength(length * t);
      token.setAttribute("transform", `translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})`);
    };
    if (animate && gsap && !reducedMotion) {
      const progress = { t: 0 };
      place(0);
      tweens.push(gsap.to(progress, { t: rest, duration: TOKEN_SECONDS, ease: "power2.out", onUpdate: () => place(progress.t) }));
    } else {
      place(rest);
    }
  }

  function render(animate) {
    const step = active.steps[active.stepper.index];
    const alarm = step.id === "hazard-event";
    const lit = new Set([step.from, ...step.to]);
    for (const [id, group] of nodeEls) {
      group.classList.toggle("is-active", lit.has(id) && !(alarm && id === "audio"));
      group.classList.toggle("is-alarm", alarm && id === "audio");
    }
    clearTokens();
    for (const [key, path] of edgeEls) {
      const [from, to] = key.split(">");
      const on = from === step.from && step.to.includes(to);
      path.classList.toggle("is-active", on && !alarm);
      path.classList.toggle("is-alarm", on && alarm);
      if (on && step.message) sendToken(path, step.message, alarm, animate);
    }
    caption.textContent = step.caption;
    count.textContent = `Step ${active.stepper.index + 1} of ${active.steps.length}`;
    back.disabled = active.stepper.index === 0;
    next.disabled = active.stepper.index === active.steps.length - 1;
  }

  function useSequence(name) {
    if (active.name !== name) {
      active.stepper.pause();
      active = sequences[name];
    }
    title.textContent = name === "hazard" ? "The hazard path" : "Follow one touch";
    swap.textContent = name === "hazard" ? "Back to one touch" : "What about hazards?";
  }

  play.addEventListener("click", () => (active.stepper.playing ? active.stepper.pause() : active.stepper.play()));
  back.addEventListener("click", () => active.stepper.back());
  next.addEventListener("click", () => active.stepper.next());
  swap.addEventListener("click", () => {
    useSequence(active.name === "hazard" ? "touch" : "hazard");
    active.stepper.goTo(0);
    render(true);
  });

  diagramHost.replaceChildren(drawing);
  render(false);

  return {
    /** Show the step with this id (in either sequence) and scroll to the diagram. */
    selectStep(stepId) {
      for (const sequence of Object.values(sequences)) {
        const index = sequence.steps.findIndex((step) => step.id === stepId);
        if (index < 0) continue;
        useSequence(sequence.name);
        sequence.stepper.goTo(index);
        render(true);
        root.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
        title.tabIndex = -1;
        title.focus({ preventScroll: true });
        return;
      }
    },
    destroy() {
      clearTokens();
      for (const sequence of Object.values(sequences)) sequence.stepper.destroy();
      controlsHost.replaceChildren();
      drawing.remove();
    },
  };
}
