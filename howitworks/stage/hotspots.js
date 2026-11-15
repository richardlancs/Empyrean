// Hotspot markers on the 3D stage and the detail panel they open.
// Markers are real buttons placed over the canvas, so they work by keyboard.

import { HOME_VIEW } from "../content.js";
import { createSelection } from "./selection.js";

const DRAG_PIXELS = 5;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * Add the markers to the stage and wire them to the panel.
 * Returns { selection, destroy() }.
 */
export async function mountHotspots({ stage, hotspots, panel, onSeeStep = () => {} }) {
  const { CSS2DObject } = await import("three/addons/renderers/CSS2DRenderer.js");
  const byId = new Map(hotspots.map((spot) => [spot.id, spot]));
  const buttons = new Map();
  const objects = [];

  function renderPanel(spot) {
    const heading = el("h3", "", spot.label);
    heading.tabIndex = -1;
    const see = el("button", "ui-button ui-button--secondary", "See it in the pipeline");
    see.type = "button";
    see.addEventListener("click", () => onSeeStep(spot.stepId));
    const close = el("button", "ui-button ui-button--quiet", "Close");
    close.type = "button";
    close.addEventListener("click", () => selection.close());
    const actions = el("div", "how-panel__actions");
    actions.append(see, close);
    panel.replaceChildren(
      heading,
      el("p", "", spot.does),
      el("p", "how-meta", `Built with: ${spot.builtWith}`),
      el("p", "how-number", spot.number),
      actions,
    );
    panel.hidden = false;
    heading.focus({ preventScroll: true });
  }

  function onChange(current, previous) {
    for (const [id, button] of buttons) {
      button.setAttribute("aria-expanded", id === current ? "true" : "false");
      button.classList.toggle("is-dimmed", current !== null && id !== current);
    }
    if (current) {
      renderPanel(byId.get(current));
      stage.flyTo(byId.get(current).view);
    } else {
      panel.hidden = true;
      panel.replaceChildren();
      stage.flyTo(HOME_VIEW);
      buttons.get(previous)?.focus({ preventScroll: true });
    }
  }

  const selection = createSelection({ ids: hotspots.map((spot) => spot.id), onChange });

  for (const spot of hotspots) {
    const button = el("button", "hotspot");
    button.type = "button";
    button.dataset.hotspot = spot.id;
    button.setAttribute("aria-label", `${spot.label}: show details`);
    button.setAttribute("aria-expanded", "false");
    button.append(el("span", "hotspot__label", spot.label));
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      selection.toggle(spot.id);
    });
    const object = new CSS2DObject(button);
    object.position.set(...spot.anchor);
    stage.scene.add(object);
    buttons.set(spot.id, button);
    objects.push(object);
  }

  // Esc closes; so does a click (not a drag) on empty canvas.
  const onKey = (event) => {
    if (event.key === "Escape" && selection.current) selection.close();
  };
  document.addEventListener("keydown", onKey);
  let downAt = null;
  const onDown = (event) => {
    downAt = [event.clientX, event.clientY];
  };
  const onUp = (event) => {
    if (!downAt) return;
    const moved = Math.hypot(event.clientX - downAt[0], event.clientY - downAt[1]);
    downAt = null;
    if (moved < DRAG_PIXELS && selection.current) selection.close();
  };
  stage.canvas.addEventListener("pointerdown", onDown);
  stage.canvas.addEventListener("pointerup", onUp);

  return {
    selection,
    destroy() {
      document.removeEventListener("keydown", onKey);
      stage.canvas.removeEventListener("pointerdown", onDown);
      stage.canvas.removeEventListener("pointerup", onUp);
      for (const object of objects) {
        object.removeFromParent();
        object.element.remove();
      }
      panel.hidden = true;
      panel.replaceChildren();
    },
  };
}
