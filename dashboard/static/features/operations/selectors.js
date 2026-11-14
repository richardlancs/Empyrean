// Pure presenters for the operations feature: warnings, module status, activity history.
// Nothing here touches the DOM or the network, so it can be unit tested with `node --test`.
// The backend stays authoritative: these functions only choose what to show and how to word it.

export const DEFAULT_ACTIVE_SECONDS = 3; // used only when the server omits hazard_active_seconds
export const DEFAULT_CAMERA_STALE_SECONDS = 2; // presentation only; server may send stale_after_seconds
export const DEFAULT_SERVER_EVENT_RETENTION = 10; // SPEC.md 4.9 "last 10 touch and hazard events"
export const CLIENT_HISTORY_LIMIT = 100; // bounded browser memory for this view
export const GROUP_WINDOW_SECONDS = 120; // repeats closer together than this are shown as one row

export const HAZARD_INFO = {
  stairs_down: {
    label: "Stairs down",
    description: "The hazard check reported possible stairs going down ahead.",
    icon: "stairs",
  },
  drop_off: {
    label: "Drop ahead",
    description: "The hazard check reported a possible drop or edge ahead.",
    icon: "drop",
  },
  vehicle: {
    label: "Vehicle",
    description: "The hazard check reported a possible vehicle approaching.",
    icon: "vehicle",
  },
  obstacle: {
    label: "Obstacle",
    description: "The hazard check reported a possible obstacle in the walking path.",
    icon: "obstacle",
  },
};

const SOURCE_LABELS = {
  yolo: "Local vehicle detector (YOLO)",
  grok: "Grok vision check",
};

/** Describe a hazard type in plain words; unknown types degrade to a generic warning. */
export function hazardInfo(type, fallbackText) {
  return (
    HAZARD_INFO[type] || {
      label: fallbackText || "Warning",
      description: "The hazard check reported a warning.",
      icon: "obstacle",
    }
  );
}

// ---------------------------------------------------------------- identity

/** Stable identity for a warning, independent of server-side counters that reset on restart. */
export function warningKey(w) {
  if (!w) return "";
  return ["hazard", w.simulated ? "sim" : "real", w.type ?? "", Number(w.ts), w.source ?? ""].join("|");
}

/** Stable identity for any activity entry (touch or hazard). */
export function eventKey(e) {
  if (!e) return "";
  if (e.kind === "hazard") return warningKey(e);
  return ["touch", Number(e.ts), e.object_id ?? "", e.text ?? ""].join("|");
}

// ---------------------------------------------------------------- time

/** Server seconds minus browser seconds, so ages use the server's clock. */
export function clockOffsetSeconds(state, receivedAt) {
  if (!state || typeof state.now !== "number" || typeof receivedAt !== "number") return 0;
  return state.now - receivedAt / 1000;
}

/** Short relative time such as "just now", "12 s ago" or "3 min ago". */
export function formatRelative(ageSeconds) {
  if (!Number.isFinite(ageSeconds)) return "time unknown";
  const age = Math.max(0, ageSeconds);
  if (age < 5) return "just now";
  if (age < 60) return `${Math.floor(age)} s ago`;
  if (age < 3600) return `${Math.floor(age / 60)} min ago`;
  if (age < 86400) return `${Math.floor(age / 3600)} h ago`;
  return `${Math.floor(age / 86400)} d ago`;
}

/** Exact local clock time for a Unix-seconds timestamp, with the date when it is not today. */
export function formatExact(ts, nowSeconds = Date.now() / 1000) {
  if (!Number.isFinite(ts)) return "Time not reported";
  const when = new Date(ts * 1000);
  const time = when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const sameDay = new Date(nowSeconds * 1000).toDateString() === when.toDateString();
  return sameDay ? time : `${when.toLocaleDateString()} ${time}`;
}

// ---------------------------------------------------------------- warnings

function newest(candidates) {
  let best = null;
  for (const c of candidates) {
    if (c && Number.isFinite(Number(c.ts)) && (!best || Number(c.ts) > Number(best.ts))) best = c;
  }
  return best;
}

/**
 * Pick the latest real and latest simulated warning to show.
 *
 * Prefers latest_real_warning / latest_simulated_warning from the server, and falls back to
 * latest_warning, the event log and what this view already remembered, so an older server that
 * only keeps one latest_warning cannot let a simulation hide a still-active real warning.
 */
/**
 * Integration (Agent 4): the shell's warning emphasis hook (design-system.md section 2).
 * "urgent" while a real warning is active (even if a simulation came later),
 * "simulated" while only a simulation is active, null otherwise.
 */
export function warningEmphasis(selected) {
  if (selected?.real?.active) return "urgent";
  if (selected?.sim?.active) return "simulated";
  return null;
}

export function selectWarnings({ state, remembered = {}, localSim = null, nowSeconds }) {
  const activeSeconds = Number.isFinite(state?.hazard_active_seconds)
    ? state.hazard_active_seconds
    : DEFAULT_ACTIVE_SECONDS;
  const events = Array.isArray(state?.events) ? state.events : [];
  const hazards = events.filter((e) => e && e.kind === "hazard");
  const lw = state?.latest_warning || null;

  const real = newest([
    state?.latest_real_warning,
    lw && !lw.simulated ? lw : null,
    ...hazards.filter((e) => !e.simulated),
    remembered.real,
  ]);
  const sim = newest([
    state?.latest_simulated_warning,
    lw && lw.simulated ? lw : null,
    ...hazards.filter((e) => e.simulated),
    remembered.sim,
    localSim,
  ]);

  const describe = (w) => {
    if (!w) return null;
    const ageSeconds = Math.max(0, nowSeconds - Number(w.ts));
    return { warning: w, key: warningKey(w), ageSeconds, active: ageSeconds < activeSeconds };
  };
  return { real: describe(real), sim: describe(sim), activeSeconds };
}

/** Plain-language source and confidence rows for a warning's optional details. */
export function warningDetails(w) {
  const rows = [];
  let source = w?.source;
  let confidence = Number.isFinite(w?.confidence) ? w.confidence : null;
  // Older servers fold both into detail, e.g. "grok, 82%".
  if ((!source || confidence === null) && typeof w?.detail === "string") {
    const m = /^\s*([a-z]+)\s*,\s*(\d+(?:\.\d+)?)\s*%\s*$/i.exec(w.detail);
    if (m) {
      source = source || m[1].toLowerCase();
      if (confidence === null) confidence = Number(m[2]) / 100;
    } else if (w.detail) {
      rows.push({ label: "Detail", value: w.detail });
    }
  }
  if (w?.simulated) {
    rows.push({ label: "Source", value: "Demo tools on this dashboard (simulated)" });
  } else if (source) {
    rows.push({ label: "Source", value: SOURCE_LABELS[source] || source });
  }
  if (confidence !== null) {
    rows.push({
      label: "Model confidence",
      value: `${Math.round(confidence * 100)}%`,
      note: "How sure the detector was about this report. It is not the chance that the area is safe or dangerous.",
    });
  }
  return rows;
}

// ---------------------------------------------------------------- module status

export const MODULES = [
  { id: "camera", label: "Camera" },
  { id: "scene", label: "Object tracking" },
  { id: "naming", label: "Naming" },
  { id: "storage", label: "Storage" },
  { id: "audio", label: "Audio" },
];

const STATUS_LABELS = {
  starting: "Starting",
  active: "Active",
  degraded: "Degraded",
  offline: "Offline",
  unknown: "Unknown",
};

const STATUS_TONE = {
  starting: "neutral",
  active: "ok",
  degraded: "caution",
  offline: "error",
  unknown: "unknown",
};

const DEFAULT_DETAIL = {
  camera: {
    active: "Frames are arriving from the camera.",
    starting: "Waiting for the first camera frame.",
    degraded: "Frames are arriving slowly or irregularly.",
    offline: "No camera frames are arriving.",
    unknown: "The server has not reported camera status.",
  },
  scene: {
    active: "Objects and hands are being tracked.",
    starting: "Object tracking is starting.",
    degraded: "Object tracking is running with problems.",
    offline: "Object tracking is not running.",
    unknown: "The server has not reported object tracking status.",
  },
  naming: {
    active: "Ready. New objects are named when they first appear; quiet periods are normal.",
    starting: "Naming is starting.",
    degraded: "Some naming requests are failing; plain object names are used instead.",
    offline: "Naming is unavailable; plain object names are used instead.",
    unknown: "The server has not reported naming status.",
  },
  storage: {
    active: "Touches and warnings are being recorded.",
    starting: "Connecting to storage.",
    degraded: "Some records may not be saved.",
    offline: "Nothing is being recorded right now. Last-touch search may not work.",
    unknown: "The server has not reported storage status.",
  },
  audio: {
    active: "The speaker output is ready. This does not confirm anyone heard it.",
    starting: "Audio is starting.",
    degraded: "Audio is running with problems.",
    offline: "Audio output is unavailable.",
    unknown: "The server has not reported audio status.",
  },
};

const CONNECTION = {
  connected: { label: "Dashboard connected", tone: "ok", detail: "This page is receiving updates from the laptop." },
  connecting: { label: "Connecting to dashboard", tone: "neutral", detail: "Waiting for the first update from the laptop." },
  reconnecting: {
    label: "Dashboard disconnected, reconnecting",
    tone: "error",
    detail: "This page lost its connection. Everything below shows the last known values.",
  },
};

/**
 * Build the status strip model from real telemetry.
 * Missing diagnostics mean "unknown", never "working". The only thing the browser adds is
 * freshness: how long ago the last camera frame or module update arrived.
 */
export function selectHealth({ state, connection, nowSeconds }) {
  const conn = CONNECTION[connection] || CONNECTION.connecting;
  const connected = connection === "connected";
  const diagnostics = state && typeof state.diagnostics === "object" ? state.diagnostics : null;

  const modules = MODULES.map(({ id, label }) => {
    const entry = diagnostics && diagnostics[id] && typeof diagnostics[id] === "object" ? diagnostics[id] : null;
    let status = entry && STATUS_LABELS[entry.status] ? entry.status : "unknown";
    let detail = (entry && typeof entry.detail === "string" && entry.detail) || DEFAULT_DETAIL[id][status];
    if (!state) detail = "Waiting for the first update.";
    else if (!entry) detail = diagnostics ? DEFAULT_DETAIL[id].unknown : "This server version does not report module status.";
    let tone = STATUS_TONE[status];
    let statusLabel = STATUS_LABELS[status];
    const facts = [];

    if (id === "camera" && entry) {
      const frameTs = Number(entry.last_frame_ts);
      const staleAfter = Number.isFinite(entry.stale_after_seconds)
        ? entry.stale_after_seconds
        : DEFAULT_CAMERA_STALE_SECONDS;
      if (Number.isFinite(frameTs) && entry.last_frame_ts !== null) {
        const age = nowSeconds - frameTs;
        facts.push({ label: "Last frame", value: formatRelative(age), ts: frameTs });
        if (status === "active" && age > staleAfter) {
          tone = "caution";
          statusLabel = "No recent frames";
          detail = `The last camera frame arrived ${formatRelative(age)}. The picture may be frozen.`;
        }
      } else {
        facts.push({ label: "Last frame", value: "Not reported" });
      }
      if (Number.isFinite(entry.fps)) facts.push({ label: "Frame rate", value: `${entry.fps.toFixed(1)} fps` });
      if (Number.isFinite(entry.width) && Number.isFinite(entry.height)) {
        facts.push({ label: "Size", value: `${entry.width} × ${entry.height}` });
      }
    }
    if (entry && Number.isFinite(entry.last_update_ts) && entry.last_update_ts !== null) {
      facts.push({ label: "Last update", value: formatRelative(nowSeconds - entry.last_update_ts), ts: entry.last_update_ts });
    }
    // Integration (Agent 4): a module running as a fake must never read as the real thing.
    const fake = Boolean(entry && entry.mode === "fake");
    if (fake) statusLabel = `${statusLabel} (fake)`;
    if (!connected && state) {
      statusLabel = `${statusLabel} (last known)`;
      if (tone === "ok") tone = "neutral";
    }
    return { id, label, status, statusLabel, tone, detail, facts, fake };
  });

  const counts = { active: 0, attention: 0, unknown: 0, fake: 0 };
  for (const m of modules) {
    if (m.fake) counts.fake += 1;
    if (m.tone === "ok") counts.active += 1;
    else if (m.tone === "caution" || m.tone === "error") counts.attention += 1;
    else if (m.status === "unknown") counts.unknown += 1;
  }
  const parts = [];
  if (!state) parts.push("Waiting for module status");
  else if (!connected) parts.push("Module status not live while disconnected");
  else {
    parts.push(`${counts.active} of ${modules.length} modules active`);
    if (counts.attention) parts.push(`${counts.attention} need${counts.attention === 1 ? "s" : ""} attention`);
    if (counts.unknown) parts.push(`${counts.unknown} not reported`);
    if (counts.fake) parts.push(`${counts.fake} running as fake${counts.fake === 1 ? "" : "s"}`);
  }
  return {
    connection: { state: connection, label: conn.label, tone: conn.tone, detail: conn.detail },
    modules,
    summary: parts.join(" · "),
    attention: counts.attention > 0 || conn.tone === "error",
  };
}

// ---------------------------------------------------------------- activity history

/**
 * Browser-only view of the activity log. It accumulates server snapshots (which keep only the
 * last few events) into a bounded list, and supports pause, a new-event count, and clear.
 * None of this reaches the server, storage, other viewers or the alarm.
 */
export class HistoryModel {
  constructor({ limit = CLIENT_HISTORY_LIMIT } = {}) {
    this.limit = limit;
    this.entries = []; // newest first, unique by key
    this.keys = new Set();
    this.paused = false;
    this.frozen = null;
    this.pendingCount = 0;
    this.pendingInexact = false;
    this.hidden = null; // Set of keys hidden by "Clear this view"
    this.clearedAt = null;
  }

  /** Merge one snapshot's events (newest first); returns the keys that were new to this view. */
  ingest(events, { retention } = {}) {
    if (!Array.isArray(events)) return [];
    const serverLimit = Number.isFinite(retention) ? retention : DEFAULT_SERVER_EVENT_RETENTION;
    const hadAny = this.entries.length > 0;
    const fresh = [];
    let overlap = false;
    for (const e of events) {
      if (!e || typeof e !== "object") continue;
      const key = eventKey(e);
      if (this.keys.has(key)) overlap = true;
      else fresh.push({ key, event: e });
    }
    if (!fresh.length) return [];
    // A full server log with nothing we already knew may mean events slipped past between updates.
    const gap = hadAny && !overlap && events.length >= serverLimit;
    for (const f of fresh) this.keys.add(f.key);
    this.entries = [...fresh, ...this.entries].sort((a, b) => Number(b.event.ts) - Number(a.event.ts));
    while (this.entries.length > this.limit) {
      const dropped = this.entries.pop();
      this.keys.delete(dropped.key);
      if (this.hidden) this.hidden.delete(dropped.key);
    }
    if (this.paused) {
      this.pendingCount += fresh.length;
      if (gap) this.pendingInexact = true;
    }
    return fresh.map((f) => f.key);
  }

  pause() {
    if (this.paused) return;
    this.paused = true;
    this.frozen = this.entries.slice();
    this.pendingCount = 0;
    this.pendingInexact = false;
  }

  resume() {
    this.paused = false;
    this.frozen = null;
    this.pendingCount = 0;
    this.pendingInexact = false;
  }

  /** Hide everything currently known from this browser view only. */
  clear(atSeconds) {
    this.hidden = new Set(this.keys);
    this.clearedAt = atSeconds;
    if (this.paused) this.frozen = this.entries.slice();
    this.pendingCount = 0;
    this.pendingInexact = false;
  }

  restore() {
    this.hidden = null;
    this.clearedAt = null;
  }

  /** Entries this view should display, newest first. */
  visible() {
    const list = this.paused && this.frozen ? this.frozen : this.entries;
    return this.hidden ? list.filter((x) => !this.hidden.has(x.key)) : list;
  }
}

export const FILTERS = [
  { id: "all", label: "All" },
  { id: "touch", label: "Touch" },
  { id: "hazard", label: "Warning" },
];

function signature(e) {
  return [e.kind, e.kind === "hazard" ? e.type : e.text, e.simulated ? 1 : 0].join("|");
}

/**
 * Filter, then group consecutive repeats (same kind, type or name, and real/simulated) that are
 * within GROUP_WINDOW_SECONDS of each other. Every underlying event stays in the group.
 */
export function groupEntries(entries, filter = "all", windowSeconds = GROUP_WINDOW_SECONDS) {
  const filtered = entries.filter((x) => filter === "all" || x.event.kind === filter);
  const groups = [];
  for (const item of filtered) {
    const last = groups[groups.length - 1];
    const prev = last && last.items[last.items.length - 1];
    if (
      last &&
      signature(last.items[0].event) === signature(item.event) &&
      Math.abs(Number(prev.event.ts) - Number(item.event.ts)) <= windowSeconds
    ) {
      last.items.push(item);
    } else {
      // Group identity follows its oldest occurrence so it does not change as repeats arrive.
      groups.push({ items: [item] });
    }
  }
  for (const g of groups) g.key = g.items[g.items.length - 1].key;
  return groups;
}

export function emptyHistoryText(filter, { cleared, paused, totalKnown }) {
  if (cleared && totalKnown) return "This view was cleared. New activity will appear here.";
  if (filter === "touch") return paused ? "No touches in the paused view." : "No touches yet.";
  if (filter === "hazard") return paused ? "No warnings in the paused view." : "No warnings in recent activity.";
  return paused ? "No activity in the paused view." : "No activity yet.";
}

export function pendingText(count, inexact) {
  if (inexact) return `At least ${count} new events since pausing. Some may have been missed while paused.`;
  if (count === 0) return "No new events since pausing.";
  return `${count} new event${count === 1 ? "" : "s"} since pausing.`;
}
