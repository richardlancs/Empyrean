// Composition only: mounts the pipeline, then the 3D stage. The page is already
// complete as static HTML; each part upgrades its own section and fails quietly.

import { HOTSPOTS } from "./content.js";

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const byId = (id) => document.getElementById(id);

/** Start the 3D stage. Returns null, leaving the poster and list, if it cannot run. */
async function startStage() {
  const section = byId("stage");
  try {
    const { createStage } = await import("./stage/scene.js");
    const stage = await createStage(byId("stage-canvas-host"), {
      reducedMotion,
      onFallback: (name) => console.warn(`How it works: using the simple ${name} model.`),
    });
    section.classList.add("has-stage");
    return stage;
  } catch (error) {
    console.warn("How it works: 3D view unavailable, showing the plain version.", error);
    return null;
  }
}

/** A short tap on phones that support it; silent everywhere else. */
function wireHaptics() {
  if (reducedMotion || typeof navigator.vibrate !== "function") return;
  document.addEventListener("click", (event) => {
    if (event.target.closest?.(".ui-button, .web-node, .how-sidebar__item, canvas")) navigator.vibrate(8);
  });
}

async function start() {
  wireHaptics();
  document.documentElement.dataset.js = "ready";
  let pipeline = null;
  try {
    const { mountPipeline } = await import("./pipeline/diagram.js");
    pipeline = mountPipeline(byId("pipeline"), { reducedMotion });
  } catch (error) {
    console.warn("How it works: pipeline diagram unavailable, showing the list.", error);
  }
  window.__howPipeline = pipeline; // for browser checks only
  const stage = await startStage();
  window.__howStage = stage; // for browser checks only
  if (stage) {
    try {
      const { mountHotspots } = await import("./stage/hotspots.js");
      window.__howSpots = await mountHotspots({
        stage,
        hotspots: HOTSPOTS,
        panel: byId("hotspot-panel"),
        onSeeStep: (stepId) => pipeline?.selectStep(stepId),
      });
      // Only now do the markers carry the explanations, so the plain list can go.
      byId("hotspot-list").hidden = true;
      byId("stage-hint").hidden = false;
    } catch (error) {
      console.warn("How it works: part details unavailable, keeping the plain list.", error);
    }
  }
}

start();
