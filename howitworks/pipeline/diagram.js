// The pipeline as a graph view: modules are dots in a web of links. Hovering
// or focusing a dot lights its neighbours and fades the rest; dots drift
// gently and spring back when dragged. A stepper walks one touch through the
// web, and a second sequence shows the hazard path. Works without the 3D stage.

import { NODES, TOUCH_STEPS, HAZARD_STEPS } from "../content.js";
import { createStepper } from "./stepper.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const VIEW_W = 1000;
const VIEW_H = 420;
const TOKEN_MS = 800;
const TOKEN_REST = 0.6;
const DRIFT = 5;
const SPRING = 0.09;
const DAMPING = 0.8;
const DRAG_PIXELS = 5;

/** Resting place of each module in the web. */
const HOMES = Object.freeze({
  camera: [110, 130],
  vision: [290, 200],
  scene: [500, 160],
  namer: [620, 60],
  audio: [790, 130],
  storage: [740, 310],
  dashboard: [560, 350],
  hazard: [320, 350],
});

/** The same modules laid out as a left-to-right flow, outputs in a column. */
const FLOW_HOMES = Object.freeze({
  camera: [90, 200],
  vision: [270, 200],
  scene: [470, 200],
  namer: [470, 60],
  audio: [850, 80],
  storage: [850, 200],
  dashboard: [850, 320],
  hazard: [270, 350],
});

const LAYOUTS = Object.freeze({ web: HOMES, flow: FLOW_HOMES });
const LAYOUT_KEY = "empyrean.how.layout";
const BOX_W = 130;
const BOX_H = 44;

/** Undirected links between modules. */
const LINKS = Object.freeze([
  ["camera", "vision"], ["vision", "scene"], ["scene", "namer"], ["scene", "audio"],
  ["scene", "storage"], ["scene", "dashboard"], ["vision", "hazard"],
  ["hazard", "audio"], ["hazard", "storage"], ["hazard", "dashboard"],
]);

const linkKey = (a, b) => (a < b ? `${a}|${b}` : `${b}|${a}`);

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
 * Replace the static step list inside root with the interactive web.
 * Returns { selectStep(stepId), destroy() }.
 */
export function mountPipeline(root, { reducedMotion = false } = {}) {
  const controlsHost = root.querySelector("#pipeline-controls");
  const diagramHost = root.querySelector("#pipeline-diagram");
  const caption = root.querySelector("#pipeline-caption");
  const title = root.querySelector("#pipeline-title");

  // ----- model -----
  const degree = Object.fromEntries(NODES.map((node) => [node.id, 0]));
  const neighbours = Object.fromEntries(NODES.map((node) => [node.id, new Set([node.id])]));
  for (const [a, b] of LINKS) {
    degree[a] += 1;
    degree[b] += 1;
    neighbours[a].add(b);
    neighbours[b].add(a);
  }
  const bodies = new Map(NODES.map((node, i) => {
    const [x, y] = HOMES[node.id];
    return [node.id, {
      x, y, vx: 0, vy: 0, homeX: x, homeY: y,
      radius: 9 + degree[node.id] * 2.2,
      phase: i * 1.7, speed: 0.5 + (i % 3) * 0.13,
      dragging: false,
    }];
  }));

  // ----- drawing -----
  const drawing = svg("svg", { viewBox: `0 0 ${VIEW_W} ${VIEW_H}`, class: "web", role: "group", "aria-label": "Modules and the messages between them" });
  const linkLayer = svg("g");
  const tokenLayer = svg("g", { "aria-hidden": "true" });
  const nodeLayer = svg("g");
  drawing.append(linkLayer, tokenLayer, nodeLayer);

  const linkEls = new Map();
  for (const [a, b] of LINKS) {
    const line = svg("line", { class: "web-link" });
    line.dataset.a = a;
    line.dataset.b = b;
    linkLayer.append(line);
    linkEls.set(linkKey(a, b), line);
  }

  const nodeEls = new Map();
  for (const node of NODES) {
    const body = bodies.get(node.id);
    const group = svg("g", { class: "web-node", role: "button", tabindex: 0, "aria-label": `${node.label}: go to its step` });
    const dot = svg("g", { class: "web-node__dot" });
    dot.append(svg("circle", { r: body.radius + 8, class: "web-node__halo" }), svg("circle", { r: body.radius, class: "web-node__core" }));
    const label = svg("text", { class: "web-node__label" }, node.label);
    label.style.setProperty("--label-y", `${body.radius + 20}px`);
    group.append(svg("rect", { x: -BOX_W / 2, y: -BOX_H / 2, width: BOX_W, height: BOX_H, rx: 12, class: "web-node__box" }), dot, label);
    nodeLayer.append(group);
    nodeEls.set(node.id, group);
  }

  // ----- controls -----
  const play = button("Play", "ui-button");
  const back = button("Back");
  const next = button("Next");
  const swap = button("What about hazards?");
  const view = button("", "ui-button ui-button--quiet");
  const count = document.createElement("span");
  count.className = "how-meta";
  controlsHost.append(play, back, next, count, swap, view);

  // ----- stepping -----
  const sequences = {};
  function makeSequence(name, steps) {
    sequences[name] = {
      name,
      steps,
      stepper: createStepper({
        steps,
        onChange: () => render(true),
        onPlayingChange: (playing) => { play.textContent = playing ? "Pause" : "Play"; },
      }),
    };
  }
  makeSequence("touch", TOUCH_STEPS);
  makeSequence("hazard", HAZARD_STEPS);
  let active = sequences.touch;
  let tokens = [];

  function useSequence(name) {
    if (active.name !== name) {
      active.stepper.pause();
      active = sequences[name];
    }
    title.textContent = name === "hazard" ? "The hazard path" : "Follow one touch";
    swap.textContent = name === "hazard" ? "Back to one touch" : "What about hazards?";
  }

  function render(animate) {
    const step = active.steps[active.stepper.index];
    const alarm = step.id === "hazard-event";
    const lit = new Set([step.from, ...step.to]);
    for (const [id, group] of nodeEls) {
      group.classList.toggle("is-active", lit.has(id) && !(alarm && id === "audio"));
      group.classList.toggle("is-alarm", alarm && id === "audio");
    }
    tokenLayer.replaceChildren();
    tokens = [];
    for (const [key, line] of linkEls) {
      const to = step.to.find((id) => linkKey(step.from, id) === key);
      line.classList.toggle("is-active", Boolean(to) && !alarm);
      line.classList.toggle("is-alarm", Boolean(to) && alarm);
      if (!to || !step.message) continue;
      const width = step.message.length * 7.2 + 16;
      const el = svg("g", { class: alarm ? "web-token is-alarm" : "web-token" });
      el.append(svg("rect", { x: -width / 2, y: -11, width, height: 22, rx: 11 }), svg("text", {}, step.message));
      tokenLayer.append(el);
      tokens.push({ el, from: step.from, to, start: animate && !reducedMotion ? performance.now() : -Infinity });
    }
    caption.textContent = step.caption;
    count.textContent = `Step ${active.stepper.index + 1} of ${active.steps.length}`;
    // aria-disabled, not disabled: the button keeps keyboard focus at the ends.
    back.setAttribute("aria-disabled", active.stepper.index === 0 ? "true" : "false");
    next.setAttribute("aria-disabled", active.stepper.index === active.steps.length - 1 ? "true" : "false");
    // On a narrow screen the drawing scrolls sideways: keep the sender in view.
    if (diagramHost.scrollWidth > diagramHost.clientWidth) {
      const centre = (bodies.get(step.from).homeX / VIEW_W) * diagramHost.scrollWidth;
      diagramHost.scrollLeft = Math.max(0, centre - diagramHost.clientWidth / 2);
    }
    draw(performance.now());
  }

  // ----- layout: the same modules as a drifting web or a tidy flow -----
  let layout = "web";
  function setLayout(name, { remember = true } = {}) {
    layout = name === "flow" ? "flow" : "web";
    for (const [id, body] of bodies) {
      [body.homeX, body.homeY] = LAYOUTS[layout][id];
      if (reducedMotion) {
        body.x = body.homeX;
        body.y = body.homeY;
      }
    }
    // The spring in simulate() carries every dot to its new home: no cut.
    drawing.classList.toggle("is-flow", layout === "flow");
    view.textContent = layout === "flow" ? "Show as web" : "Show as flow";
    if (remember) {
      try {
        window.localStorage.setItem(LAYOUT_KEY, layout);
      } catch {
        // Storage blocked: the choice simply lasts for this visit.
      }
    }
    draw(performance.now());
  }

  // ----- motion -----
  function simulate(now) {
    const t = now / 1000;
    const drift = layout === "flow" ? 0 : DRIFT;
    for (const body of bodies.values()) {
      if (body.dragging) continue;
      const targetX = body.homeX + Math.sin(t * body.speed + body.phase) * drift;
      const targetY = body.homeY + Math.cos(t * body.speed * 0.8 + body.phase) * drift;
      body.vx = (body.vx + (targetX - body.x) * SPRING) * DAMPING;
      body.vy = (body.vy + (targetY - body.y) * SPRING) * DAMPING;
      body.x += body.vx;
      body.y += body.vy;
    }
  }

  function draw(now) {
    for (const [id, group] of nodeEls) {
      const body = bodies.get(id);
      group.setAttribute("transform", `translate(${body.x.toFixed(1)} ${body.y.toFixed(1)})`);
    }
    for (const line of linkEls.values()) {
      const a = bodies.get(line.dataset.a);
      const b = bodies.get(line.dataset.b);
      line.setAttribute("x1", a.x.toFixed(1));
      line.setAttribute("y1", a.y.toFixed(1));
      line.setAttribute("x2", b.x.toFixed(1));
      line.setAttribute("y2", b.y.toFixed(1));
    }
    for (const token of tokens) {
      const a = bodies.get(token.from);
      const b = bodies.get(token.to);
      const progress = Math.min(1, (now - token.start) / TOKEN_MS);
      const eased = 1 - (1 - progress) ** 3;
      const at = TOKEN_REST * eased;
      token.el.setAttribute("transform", `translate(${(a.x + (b.x - a.x) * at).toFixed(1)} ${(a.y + (b.y - a.y) * at).toFixed(1)})`);
    }
  }

  let running = false;
  let frameId = 0;
  let onScreen = false;
  function loop(now) {
    if (!running) return;
    simulate(now);
    draw(now);
    frameId = requestAnimationFrame(loop);
  }
  function syncRunning() {
    const should = !reducedMotion && onScreen && !document.hidden;
    if (should && !running) {
      running = true;
      frameId = requestAnimationFrame(loop);
    } else if (!should && running) {
      running = false;
      cancelAnimationFrame(frameId);
    }
  }
  const viewObserver = new IntersectionObserver(([entry]) => {
    onScreen = entry.isIntersecting;
    syncRunning();
  });
  viewObserver.observe(diagramHost);
  document.addEventListener("visibilitychange", syncRunning);

  // ----- hover, focus, drag, click -----
  function setHover(id) {
    drawing.classList.toggle("has-hover", id !== null);
    for (const [nodeId, group] of nodeEls) {
      group.classList.toggle("is-hover", nodeId === id);
      group.classList.toggle("is-near", id !== null && neighbours[id].has(nodeId));
    }
    for (const line of linkEls.values()) {
      line.classList.toggle("is-near", id !== null && (line.dataset.a === id || line.dataset.b === id));
    }
  }

  function toView(event) {
    const box = drawing.getBoundingClientRect();
    return [((event.clientX - box.left) / box.width) * VIEW_W, ((event.clientY - box.top) / box.height) * VIEW_H];
  }

  for (const node of NODES) {
    const group = nodeEls.get(node.id);
    const body = bodies.get(node.id);
    const involves = (sequence) => sequence.steps.some((step) => step.from === node.id || step.to.includes(node.id));
    const jump = () => {
      // A module that plays no part in the current sequence opens the other one.
      if (!involves(active)) {
        const other = Object.values(sequences).find((sequence) => sequence !== active && involves(sequence));
        if (other) useSequence(other.name);
      }
      active.stepper.jumpToNode(node.id);
      render(true);
    };
    let down = null;
    group.addEventListener("pointerenter", () => setHover(node.id));
    group.addEventListener("pointerleave", () => { if (!body.dragging) setHover(null); });
    group.addEventListener("focus", () => setHover(node.id));
    group.addEventListener("blur", () => setHover(null));
    group.addEventListener("pointerdown", (event) => {
      down = { x: event.clientX, y: event.clientY, moved: false };
      group.setPointerCapture(event.pointerId);
    });
    group.addEventListener("pointermove", (event) => {
      if (!down) return;
      if (!down.moved && Math.hypot(event.clientX - down.x, event.clientY - down.y) < DRAG_PIXELS) return;
      down.moved = true;
      if (reducedMotion) return;
      body.dragging = true;
      const [x, y] = toView(event);
      body.x = Math.min(VIEW_W - 20, Math.max(20, x));
      body.y = Math.min(VIEW_H - 30, Math.max(20, y));
      body.vx = 0;
      body.vy = 0;
    });
    const release = (event) => {
      if (!down) return;
      const wasClick = !down.moved;
      down = null;
      body.dragging = false; // the spring carries it home with a small bounce
      if (group.hasPointerCapture(event.pointerId)) group.releasePointerCapture(event.pointerId);
      if (wasClick && event.type === "pointerup") jump();
    };
    group.addEventListener("pointerup", release);
    group.addEventListener("pointercancel", release);
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        jump();
      }
    });
  }

  play.addEventListener("click", () => (active.stepper.playing ? active.stepper.pause() : active.stepper.play()));
  back.addEventListener("click", () => active.stepper.back());
  next.addEventListener("click", () => active.stepper.next());
  swap.addEventListener("click", () => {
    useSequence(active.name === "hazard" ? "touch" : "hazard");
    active.stepper.goTo(0);
    render(true);
  });

  view.addEventListener("click", () => setLayout(layout === "flow" ? "web" : "flow"));

  diagramHost.replaceChildren(drawing);
  let saved = null;
  try {
    saved = window.localStorage.getItem(LAYOUT_KEY);
  } catch {
    saved = null;
  }
  if (saved === "flow") {
    // Start in place rather than animating in from the web.
    for (const [id, body] of bodies) [body.x, body.y] = FLOW_HOMES[id];
  }
  setLayout(saved, { remember: false });
  render(false);
  syncRunning();

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
      running = false;
      cancelAnimationFrame(frameId);
      viewObserver.disconnect();
      document.removeEventListener("visibilitychange", syncRunning);
      for (const sequence of Object.values(sequences)) sequence.stepper.destroy();
      controlsHost.replaceChildren();
      drawing.remove();
    },
  };
}
