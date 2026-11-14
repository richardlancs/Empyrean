// Operations feature: system status, warnings, recent activity and demo tools.
// Controller only: it reads the shared store through ctx.subscribe, sends user intent through
// ctx.request, announces through ctx.announce, and hands plain models to the components.

import { createDemoTools } from "./demo-tools.js";
import { createEventHistory } from "./event-history.js";
import { createStatusStrip } from "./status-strip.js";
import { createWarningPanel } from "./warning-panel.js";
import {
  HistoryModel,
  MODULES,
  clockOffsetSeconds,
  emptyHistoryText,
  formatExact,
  formatRelative,
  groupEntries,
  hazardInfo,
  pendingText,
  selectHealth,
  selectWarnings,
  warningEmphasis,
  warningDetails,
} from "./selectors.js";

const ANNOUNCED_LIMIT = 300; // bounded memory of announced event keys
const TICK_MS = 1000; // relative-time refresh; never announced

const TOUCH_DETAIL = {
  "not named yet": "Plain object name. A specific name was not ready yet.",
};

function remember(set, key) {
  set.add(key);
  if (set.size > ANNOUNCED_LIMIT) set.delete(set.values().next().value);
}

/** Mount the operations feature into ctx.roots.{health,warning,events,demo}; returns cleanup. */
export function mountOperations(ctx) {
  const roots = ctx.roots || {};
  const history = new HistoryModel();
  const announced = new Set();
  const remembered = { real: null, sim: null };
  const moduleStatus = new Map();
  let snap = { state: null, connection: "connecting", receivedAt: null };
  let offset = 0;
  let localSim = null;
  let filter = "all";
  let demo = { status: "idle", message: "" };
  let counter = 0;
  let destroyed = false;

  const nowSeconds = () => Date.now() / 1000 + offset;
  const announce = (text, priority, key) => {
    if (typeof ctx.announce === "function") ctx.announce(text, { priority, key });
  };

  const strip = roots.health ? createStatusStrip(roots.health) : null;
  const warnings = roots.warning ? createWarningPanel(roots.warning) : null;
  const events = roots.events
    ? createEventHistory(roots.events, {
        onFilter(id) {
          filter = id;
          render();
        },
        onTogglePause() {
          counter += 1;
          if (history.paused) {
            history.resume();
            announce("Activity view resumed.", "polite", `activity-resume-${counter}`);
          } else {
            history.pause();
            announce("Activity view paused. Detection and alarms keep running.", "polite", `activity-pause-${counter}`);
          }
          render();
        },
        onClear() {
          counter += 1;
          history.clear(nowSeconds());
          announce("This view was cleared. Saved history is unchanged.", "polite", `activity-clear-${counter}`);
          render();
        },
        onRestore() {
          history.restore();
          render();
        },
      })
    : null;
  const demoTools = roots.demo ? createDemoTools(roots.demo, { onSimulate: simulate }) : null;

  function announceWarnings(selected) {
    for (const [d, real] of [
      [selected.real, true],
      [selected.sim, false],
    ]) {
      if (!d || announced.has(d.key)) continue;
      remember(announced, d.key);
      // A replayed or already-expired warning (page load, reconnect) is shown, not announced.
      if (!d.active) continue;
      const info = hazardInfo(d.warning.type, d.warning.text);
      if (real) announce(`Warning: ${info.label}. ${info.description}`, "assertive", d.key);
      else announce(`Simulated warning for testing: ${info.label}. No alarm sounded.`, "polite", d.key);
    }
  }

  function announceModules(state) {
    const health = selectHealth({ state, connection: "connected", nowSeconds: nowSeconds() });
    for (const m of health.modules) {
      const before = moduleStatus.get(m.id);
      moduleStatus.set(m.id, m.status);
      if (before && before !== m.status && (m.status === "offline" || m.status === "degraded")) {
        const ts = state?.diagnostics?.[m.id]?.last_update_ts ?? "";
        announce(`${m.label} is ${m.status}.`, "polite", `module|${m.id}|${m.status}|${ts}`);
      }
    }
  }

  // Connection changes are announced by the shell (app.js) only. This feature
  // shows the connection visibly in the status strip and never announces it.

  /** Set or clear the shell's warning emphasis hook on the warning mount. */
  function applyEmphasis(now) {
    const slot = roots.warning;
    if (!slot || !slot.dataset) return;
    const emphasis = warningEmphasis(
      selectWarnings({ state: snap.state, remembered, localSim, nowSeconds: now }),
    );
    if (emphasis) {
      if (slot.dataset.emphasis !== emphasis) slot.dataset.emphasis = emphasis;
    } else if ("emphasis" in slot.dataset) {
      delete slot.dataset.emphasis;
    }
  }

  /** Fold one state snapshot (from the socket or an HTTP result) into this view. */
  function ingest(state, receivedAtMs) {
    if (!state || typeof state !== "object") return;
    offset = clockOffsetSeconds(state, receivedAtMs);
    history.ingest(state.events, { retention: state.event_log_size });
    const selected = selectWarnings({ state, remembered, localSim, nowSeconds: nowSeconds() });
    if (selected.real) remembered.real = selected.real.warning;
    if (selected.sim) remembered.sim = selected.sim.warning;
    announceWarnings(selected);
    announceModules(state);
  }

  function warningModel(now) {
    const w = selectWarnings({ state: snap.state, remembered, localSim, nowSeconds: now });
    const cards = [];
    const previous = [];
    const time = (d) => ({ relative: formatRelative(d.ageSeconds), exact: formatExact(Number(d.warning.ts), now) });
    const realActive = Boolean(w.real?.active);
    if (w.real) {
      const info = hazardInfo(w.real.warning.type, w.real.warning.text);
      if (realActive) {
        cards.push({
          key: w.real.key,
          tone: "real",
          icon: info.icon,
          title: info.label,
          description: info.description,
          details: warningDetails(w.real.warning),
          time: time(w.real),
        });
      } else {
        previous.push({ key: w.real.key, tone: "real", icon: info.icon, label: "Previous warning", title: info.label, time: time(w.real) });
      }
    }
    if (w.sim) {
      const info = hazardInfo(w.sim.warning.type, w.sim.warning.text);
      if (w.sim.active) {
        // Listed after any active real warning, and compact beside it, so a test never displaces it.
        cards.push({
          key: w.sim.key,
          tone: "sim",
          compact: realActive,
          icon: info.icon,
          title: info.label,
          description: "Test warning added from Demo tools.",
          note: "No alarm sounded and nothing was saved.",
          details: [],
          time: time(w.sim),
        });
      } else {
        previous.push({ key: w.sim.key, tone: "sim", icon: info.icon, label: "Previous simulated warning", title: info.label, time: time(w.sim) });
      }
    }
    return { cards, previous };
  }

  function presentGroup(group, now) {
    const e = group.items[0].event;
    const hazard = e.kind === "hazard";
    const info = hazard ? hazardInfo(e.type, e.text) : null;
    const tone = hazard ? (e.simulated ? "sim" : "real") : "touch";
    let description = "";
    if (hazard && e.simulated) description = "Test only. No alarm sounded.";
    else if (!hazard && e.detail) description = TOUCH_DETAIL[e.detail] || e.detail;
    return {
      key: group.key,
      tone,
      icon: hazard ? info.icon : "touch",
      kindLabel: hazard ? (e.simulated ? "Simulated warning" : "Warning") : "Touch",
      title: hazard ? info.label : e.text || e.class_label || "Unnamed object",
      description,
      count: group.items.length,
      time: { relative: formatRelative(now - Number(e.ts)), exact: formatExact(Number(e.ts), now) },
      occurrences: group.items.map((x) => ({
        relative: formatRelative(now - Number(x.event.ts)),
        exact: formatExact(Number(x.event.ts), now),
      })),
      details: hazard ? warningDetails(e) : [],
    };
  }

  function historyModel(now) {
    const visible = history.visible();
    const groups = groupEntries(visible, filter).map((g) => presentGroup(g, now));
    const cleared = history.clearedAt !== null;
    return {
      filter,
      paused: history.paused,
      pendingText: pendingText(history.pendingCount, history.pendingInexact),
      cleared,
      clearedText: cleared
        ? `View cleared at ${formatExact(history.clearedAt, now)}. Saved history and other viewers are not affected.`
        : "",
      canClear: visible.length > 0,
      groups,
      emptyText: emptyHistoryText(filter, { cleared, paused: history.paused, totalKnown: history.entries.length }),
    };
  }

  function render() {
    if (destroyed) return;
    const now = nowSeconds();
    strip?.update(selectHealth({ state: snap.state, connection: snap.connection, nowSeconds: now }));
    warnings?.update(warningModel(now));
    applyEmphasis(now);
    events?.update(historyModel(now));
    demoTools?.update(demo);
  }

  async function simulate() {
    if (demo.status === "pending") return;
    demo = { status: "pending", message: "Adding a simulated warning to this dashboard…" };
    render();
    try {
      const result = await ctx.request("/api/simulate-alert", { method: "POST" });
      if (destroyed) return;
      const sim =
        result?.latest_simulated_warning || (result?.latest_warning?.simulated ? result.latest_warning : null);
      if (sim) localSim = sim;
      // Same path as socket updates; keys deduplicate the copy the socket also delivers.
      ingest(result, Date.now());
      demo = {
        status: "success",
        message: sim
          ? `Simulated warning added at ${formatExact(Number(sim.ts), nowSeconds())}. No alarm sounded.`
          : "Simulated warning added. No alarm sounded.",
      };
    } catch (err) {
      if (destroyed) return;
      const status = Number(err?.status ?? err?.response?.status);
      demo = Number.isFinite(status) && status > 0
        ? { status: "http_error", message: `The server refused the request (HTTP ${status}). No simulated warning was added.` }
        : { status: "network_error", message: "Could not reach the dashboard server. No simulated warning was added. Try again once it reconnects." };
      counter += 1;
      announce(demo.message, "polite", `demo-failed-${counter}`);
    }
    render();
  }

  const unsubscribe = ctx.subscribe(({ state, connection, receivedAt }) => {
    snap = { state: state ?? null, connection: connection || "connecting", receivedAt: receivedAt ?? null };
    ingest(snap.state, snap.receivedAt ?? Date.now());
    render();
  });
  const timer = setInterval(render, TICK_MS);
  render();

  return function cleanup() {
    destroyed = true;
    clearInterval(timer);
    if (roots.warning?.dataset) delete roots.warning.dataset.emphasis;
    if (typeof unsubscribe === "function") unsubscribe();
    strip?.destroy();
    warnings?.destroy();
    events?.destroy();
    demoTools?.destroy();
  };
}

export { MODULES };
