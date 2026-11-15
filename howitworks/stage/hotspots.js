// The parts of the 3D kit are the controls. Pointing at a part makes it grow,
// shows its name over it and its description in the panel; clicking pins it
// and flies the camera in. Visually hidden buttons give the same thing to
// keyboard and screen-reader users.

import { HOME_VIEW } from "../content.js";
import { createSelection } from "./selection.js";

const DRAG_PIXELS = 5;
const GROW = 1.14;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * Wire the stage's parts to the panel.
 * Returns { selection, hover(id|null), destroy() }.
 */
export async function mountHotspots({ stage, hotspots, panel, onSeeStep = () => {} }) {
  const { CSS2DObject } = await import("three/addons/renderers/CSS2DRenderer.js");
  const { THREE, gsap, targets, canvas } = stage;
  const byId = new Map(hotspots.map((spot) => [spot.id, spot]));
  const region = panel.parentElement;
  const view = canvas.parentElement.parentElement;
  const raycaster = new THREE.Raycaster();
  raycaster.params.Line.threshold = 0.03;
  const pointer = new THREE.Vector2();
  const labels = new Map();
  const buttons = new Map();
  let hovered = null;
  let returnFocus = true;

  // ----- panel -----
  function renderPanel(id, pinned, focus = false) {
    if (!id) {
      panel.hidden = true;
      panel.replaceChildren();
      return;
    }
    const spot = byId.get(id);
    const heading = el("h3", "", spot.label);
    heading.tabIndex = -1;
    const parts = [
      heading,
      el("p", "", spot.does),
      el("p", "how-meta", `Built with: ${spot.builtWith}`),
      el("p", "how-number", spot.number),
    ];
    if (pinned) {
      const see = el("button", "ui-button ui-button--secondary", "See it in the pipeline");
      see.type = "button";
      see.addEventListener("click", () => onSeeStep(spot.stepId));
      const close = el("button", "ui-button ui-button--quiet", "Close");
      close.type = "button";
      close.addEventListener("click", () => selection.close());
      const actions = el("div", "how-panel__actions");
      actions.append(see, close);
      parts.push(actions);
    } else {
      parts.push(el("p", "how-meta", "Click to keep this open."));
    }
    panel.replaceChildren(...parts);
    panel.hidden = false;
    panel.classList.toggle("is-pinned", pinned);
    if (pinned && focus) heading.focus({ preventScroll: true });
  }

  // ----- visual state: which part is grown and labelled -----
  function refresh(focus = false) {
    const shown = hovered ?? selection.current;
    for (const [id, object] of Object.entries(targets)) {
      const scale = id === shown ? GROW : 1;
      if (stage.reducedMotion) object.scale.setScalar(scale);
      else gsap.to(object.scale, { x: scale, y: scale, z: scale, duration: 0.45, ease: "back.out(2.2)", overwrite: true });
      labels.get(id).element.firstChild.classList.toggle("is-shown", id === shown);
      if (id === "hazard") object.material.opacity = id === shown ? 0.16 : 0.06;
    }
    for (const [id, button] of buttons) button.setAttribute("aria-expanded", id === selection.current ? "true" : "false");
    canvas.style.cursor = hovered ? "pointer" : "";
    renderPanel(shown, shown !== null && shown === selection.current, focus);
  }

  function hover(id) {
    if (id === hovered) return;
    hovered = id;
    refresh();
  }

  const selection = createSelection({
    ids: hotspots.map((spot) => spot.id),
    onChange(current, previous) {
      // Read this before the panel is rebuilt: closing it removes the focused heading.
      const wasInStage = region.contains(document.activeElement);
      hovered = null;
      refresh(true);
      if (current) {
        stage.flyTo(byId.get(current).view);
      } else {
        stage.flyTo(HOME_VIEW);
        if (returnFocus && wasInStage && buttons.get(previous)) {
          buttons.get(previous).focus({ preventScroll: true });
        }
      }
    },
  });

  // ----- labels over the parts, and hidden buttons for the keyboard -----
  const keys = el("div", "ui-visually-hidden");
  keys.setAttribute("role", "group");
  keys.setAttribute("aria-label", "Parts of the kit");
  for (const spot of hotspots) {
    // The renderer positions the outer element; the inner one is free to animate.
    const holder = el("div", "part-label-holder");
    holder.append(el("span", "part-label", spot.label));
    const label = new CSS2DObject(holder);
    label.position.set(...spot.anchor);
    stage.scene.add(label);
    labels.set(spot.id, label);

    const button = el("button", "", `${spot.label}: show details`);
    button.type = "button";
    button.dataset.hotspot = spot.id;
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("focus", () => hover(spot.id));
    button.addEventListener("blur", () => hover(null));
    button.addEventListener("click", () => selection.toggle(spot.id));
    keys.append(button);
    buttons.set(spot.id, button);
  }
  view.prepend(keys);

  // ----- pointing at parts -----
  function partAt(event) {
    const box = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1);
    raycaster.setFromCamera(pointer, stage.camera);
    let best = null;
    let bestDistance = Infinity;
    for (const [id, object] of Object.entries(targets)) {
      if (id === "hazard") continue; // the cone wraps other parts: it is the fallback
      const hit = raycaster.intersectObject(object, true)[0];
      if (hit && hit.distance < bestDistance) {
        best = id;
        bestDistance = hit.distance;
      }
    }
    if (!best && raycaster.intersectObject(targets.hazard, true).length) best = "hazard";
    return best;
  }

  let downAt = null;
  const onMove = (event) => {
    if (downAt && Math.hypot(event.clientX - downAt[0], event.clientY - downAt[1]) >= DRAG_PIXELS) return hover(null);
    if (event.pointerType === "touch") return undefined;
    return hover(partAt(event));
  };
  const onLeave = () => hover(null);
  const onDown = (event) => {
    downAt = [event.clientX, event.clientY];
  };
  const onUp = (event) => {
    if (!downAt) return;
    const moved = Math.hypot(event.clientX - downAt[0], event.clientY - downAt[1]);
    downAt = null;
    if (moved >= DRAG_PIXELS) return;
    const id = partAt(event);
    returnFocus = false;
    if (id) selection.toggle(id);
    else selection.close();
    returnFocus = true;
  };
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerleave", onLeave);
  canvas.addEventListener("pointerdown", onDown);
  canvas.addEventListener("pointerup", onUp);

  // Esc closes. Focus goes back to the part's button only when the person is
  // still in the stage; someone reading further down keeps their place.
  const onKey = (event) => {
    if (event.key !== "Escape" || !selection.current) return;
    selection.close();
  };
  document.addEventListener("keydown", onKey);

  return {
    selection,
    hover,
    destroy() {
      document.removeEventListener("keydown", onKey);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointerup", onUp);
      for (const label of labels.values()) {
        label.removeFromParent();
        label.element.remove();
      }
      for (const object of Object.values(targets)) object.scale.setScalar(1);
      keys.remove();
      renderPanel(null, false);
    },
  };
}
