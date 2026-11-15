// Composition only: mounts the pipeline, then the 3D stage. The page is already
// complete as static HTML; each part upgrades its own section and fails quietly.

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
    byId("hotspot-list").hidden = true;
    byId("stage-hint").hidden = false;
    return stage;
  } catch (error) {
    console.warn("How it works: 3D view unavailable, showing the plain version.", error);
    return null;
  }
}

async function start() {
  document.documentElement.dataset.js = "ready";
  const stage = await startStage();
  window.__howStage = stage; // for browser checks only
}

start();
