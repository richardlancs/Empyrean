// AGENT 1 PREVIEW STUB, not production. Agent 3 owns the real
// dashboard/static/features/operations/. Exercises the shell's warning-emphasis
// hook (data-emphasis on the warning mount), status primitives, and request().

import { ageSeconds, formatAge, formatClockTime } from "/static/core/clock.js";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const CONNECTION = {
  connecting: ["starting", "Connecting to the dashboard"],
  connected: ["active", "Dashboard connected"],
  reconnecting: ["offline", "Dashboard connection lost, reconnecting"],
};
const MODULES = [["camera", "Camera"], ["scene", "Touch"], ["naming", "Naming"], ["storage", "History"], ["audio", "Speaker"]];

function mountHealth(root) {
  const panel = el("div", "ui-panel operations-health");
  const list = el("ul", "operations-health__list");
  panel.append(el("h2", "ui-visually-hidden", "System status"), list);
  root.append(panel);
  return (snap) => {
    const [status, text] = CONNECTION[snap.connection];
    const items = [[status, text]];
    for (const [key, label] of MODULES) {
      const d = snap.state?.diagnostics?.[key];
      items.push([d?.status ?? "unknown", `${label}: ${d?.status ?? "unknown"}`]);
    }
    list.replaceChildren(...items.map(([s, t]) => {
      const li = el("li", "ui-status", t);
      li.dataset.status = s;
      return li;
    }));
  };
}

function mountWarning(root, ctx) {
  const panel = el("div", "ui-panel operations-warning");
  const title = el("p", "operations-warning__title");
  const meta = el("p", "ui-meta");
  panel.append(el("h2", "ui-visually-hidden", "Warnings"), title, meta);
  root.append(panel);
  let announced = null;
  return (snap) => {
    const s = snap.state;
    const active = (w) => w && ageSeconds(w.ts, snap) < (s?.hazard_active_seconds ?? 0);
    const real = s?.latest_real_warning;
    const sim = s?.latest_simulated_warning;
    let mode = "none";
    if (active(real)) mode = "urgent";
    else if (active(sim)) mode = "simulated";
    if (mode === "urgent") root.dataset.emphasis = "urgent";
    else if (mode === "simulated") root.dataset.emphasis = "simulated";
    else delete root.dataset.emphasis;
    panel.className = `ui-panel operations-warning ${mode === "urgent" ? "ui-panel--danger" : mode === "simulated" ? "ui-panel--sim" : ""}`;
    if (mode === "urgent") {
      title.textContent = `⚠︎ Warning: ${real.text}`;
      meta.textContent = `${formatClockTime(real.ts)} · ${real.detail}`;
      if (announced !== real.id) ctx.announce(`Warning: ${real.text}`, { priority: "assertive", key: `hazard:${real.id}` });
      announced = real.id;
    } else if (mode === "simulated") {
      title.textContent = `Simulated warning: ${sim.text}`;
      meta.textContent = "Shown on this page only. No alarm sounds and nothing is stored.";
    } else {
      title.textContent = "No active warning";
      const last = real ?? sim;
      meta.textContent = last
        ? `Last: ${last.text}${last.simulated ? " (simulated)" : ""}, ${formatAge(ageSeconds(last.ts, snap))}. Warnings can be missed.`
        : "Warnings can be missed; no warning does not mean the way is clear.";
    }
  };
}

function mountEvents(root) {
  const panel = el("div", "ui-panel");
  const list = el("ol", "ui-list");
  const empty = el("div", "ui-empty");
  empty.append(el("p", "ui-empty__title", "No activity yet"), el("p", "", "Touches and warnings appear here."));
  panel.append(el("h2", "ui-panel__title operations-heading", "Recent activity"), empty, list);
  root.append(panel);
  return (snap) => {
    const events = snap.state?.events ?? [];
    empty.hidden = events.length > 0;
    list.replaceChildren(...events.map((e) => {
      const li = el("li", "operations-event");
      const kind = e.kind === "hazard" ? (e.simulated ? ["sim", "Simulated"] : ["danger", "Warning"]) : ["touch", "Touch"];
      li.append(el("time", "ui-meta", formatClockTime(e.ts)), el("span", `ui-chip ui-chip--${kind[0]}`, kind[1]), el("span", "operations-event__text", e.text));
      return li;
    }));
  };
}

function mountDemo(root, ctx) {
  const panel = el("div", "ui-panel ui-stack");
  const button = el("button", "ui-button ui-button--sim", "Simulate alert");
  button.type = "button";
  const note = el("p", "ui-hint", "Adds a simulated stairs warning to this page only. No alarm sounds and nothing is stored.");
  const status = el("p", "ui-meta");
  status.setAttribute("role", "status");
  panel.append(el("h2", "ui-panel__title", "Demo tools"), note, el("div", "ui-row", ""), status);
  panel.querySelector(".ui-row").append(button);
  root.append(panel);
  button.addEventListener("click", async () => {
    button.setAttribute("aria-busy", "true");
    try {
      await ctx.request("/api/simulate-alert", { method: "POST" });
      status.textContent = "Simulated warning added.";
    } catch (error) {
      status.textContent = `Could not simulate: ${error.message}`;
    } finally {
      button.removeAttribute("aria-busy");
    }
  });
}

export function mountOperations(ctx) {
  const renderers = [mountHealth(ctx.roots.health), mountWarning(ctx.roots.warning, ctx), mountEvents(ctx.roots.events)];
  mountDemo(ctx.roots.demo, ctx);
  let last = null;
  const render = (snap) => {
    last = snap;
    for (const r of renderers) r(snap);
  };
  const unsubscribe = ctx.subscribe(render);
  // Re-render every second so warnings expire on time. Not announced.
  const timer = setInterval(() => last && render(last), 1000);
  return () => {
    clearInterval(timer);
    unsubscribe();
    delete ctx.roots.warning.dataset.emphasis;
  };
}
