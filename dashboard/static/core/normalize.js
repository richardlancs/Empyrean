// Turns a raw /ws or /api/state payload into the shape every feature can rely on.
//
// Rules:
// - Required arrays (events, objects) are always arrays.
// - Optional objects (warnings, current_touch, speech) are an object or null.
// - Missing instrumentation is reported as "unknown" / false, never as healthy.
// - Older servers that only send latest_warning still get latest_real_warning and
//   latest_simulated_warning, derived from its `simulated` flag.
// - Item fields inside objects/events are passed through untouched; features treat
//   their optional fields (naming_status, thumbnail_url, ...) as optional.
// The result is deeply frozen so no feature can mutate shared state.

export const DIAGNOSTIC_KEYS = Object.freeze(["camera", "scene", "naming", "storage", "audio"]);
export const DIAGNOSTIC_STATUSES = Object.freeze(["starting", "active", "degraded", "offline", "unknown"]);
export const CAPABILITY_KEYS = Object.freeze(["last_seen", "thumbnails", "overlays", "speech_status", "mode_switch"]);
const CAMERA_MEASUREMENTS = Object.freeze(["last_frame_ts", "fps", "width", "height"]);

/** True for a non-null, non-array object. */
export function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteOrNull(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function recordOrNull(value) {
  return isRecord(value) ? value : null;
}

function textOrNull(value) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function normalizeDiagnostic(key, raw) {
  const entry = isRecord(raw) ? raw : {};
  const status = DIAGNOSTIC_STATUSES.includes(entry.status) ? entry.status : "unknown";
  const out = {
    ...entry,
    status,
    detail: textOrNull(entry.detail),
    last_update_ts: finiteOrNull(entry.last_update_ts),
  };
  if (key === "camera") {
    for (const field of CAMERA_MEASUREMENTS) out[field] = finiteOrNull(entry[field]);
  }
  return out;
}

/** Every diagnostics key present, each with a valid status ("unknown" when not reported). */
export function normalizeDiagnostics(raw) {
  const source = isRecord(raw) ? raw : {};
  const out = { ...source };
  for (const key of DIAGNOSTIC_KEYS) out[key] = normalizeDiagnostic(key, source[key]);
  return out;
}

/** Every capability key present; only an explicit `true` counts as available. */
export function normalizeCapabilities(raw) {
  const source = isRecord(raw) ? raw : {};
  const out = {};
  for (const key of CAPABILITY_KEYS) out[key] = source[key] === true;
  return out;
}

function splitWarnings(raw) {
  const hasNewFields = "latest_real_warning" in raw || "latest_simulated_warning" in raw;
  if (hasNewFields) {
    return {
      real: recordOrNull(raw.latest_real_warning),
      simulated: recordOrNull(raw.latest_simulated_warning),
    };
  }
  const latest = recordOrNull(raw.latest_warning);
  if (!latest) return { real: null, simulated: null };
  return latest.simulated === true ? { real: null, simulated: latest } : { real: latest, simulated: null };
}

function deepFreeze(value) {
  if (typeof value !== "object" || value === null || Object.isFrozen(value)) return value;
  for (const key of Object.keys(value)) deepFreeze(value[key]);
  return Object.freeze(value);
}

/**
 * Normalize one dashboard state payload. Throws TypeError if it is not an object,
 * so the transport can report and drop it instead of rendering garbage.
 */
export function normalizeState(raw) {
  if (!isRecord(raw)) throw new TypeError("Dashboard state must be a JSON object");
  const warnings = splitWarnings(raw);
  const state = {
    ...raw,
    now: finiteOrNull(raw.now),
    hazard_active_seconds: finiteOrNull(raw.hazard_active_seconds),
    events: Array.isArray(raw.events) ? raw.events.filter(isRecord) : [],
    objects: Array.isArray(raw.objects) ? raw.objects.filter(isRecord) : [],
    latest_warning: recordOrNull(raw.latest_warning),
    latest_real_warning: warnings.real,
    latest_simulated_warning: warnings.simulated,
    current_touch: recordOrNull(raw.current_touch),
    speech: recordOrNull(raw.speech),
    detector: recordOrNull(raw.detector),
    diagnostics: normalizeDiagnostics(raw.diagnostics),
    capabilities: normalizeCapabilities(raw.capabilities),
  };
  return deepFreeze(structuredClone(state));
}
