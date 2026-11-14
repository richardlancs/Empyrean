// Time helpers shared by both features. Backend timestamps are Unix seconds (UTC)
// on the laptop's clock; the browser's clock may differ. Every state carries `now`
// (server seconds when it was sent), so server time is estimated as
//   state.now + (browser ms since it arrived) / 1000.
// Use these when rendering "4 s ago"; never announce the result.

/** Estimated server time in seconds for a store snapshot. */
export function serverNow(snapshot, browserNowMs = Date.now()) {
  const state = snapshot?.state;
  if (!state || typeof state.now !== "number" || typeof snapshot.receivedAt !== "number") {
    return browserNowMs / 1000;
  }
  return state.now + Math.max(0, browserNowMs - snapshot.receivedAt) / 1000;
}

/** Seconds since ts (never negative), or null if ts is not a number. */
export function ageSeconds(ts, snapshot, browserNowMs = Date.now()) {
  if (typeof ts !== "number" || !Number.isFinite(ts)) return null;
  return Math.max(0, serverNow(snapshot, browserNowMs) - ts);
}

/** "just now", "12 s ago", "3 min ago", "2 h ago"; "" for null. */
export function formatAge(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "";
  if (seconds < 2) return "just now";
  if (seconds < 60) return `${Math.floor(seconds)} s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return `${Math.floor(seconds / 3600)} h ago`;
}

/** Local wall-clock time "14:03:27" for a Unix-seconds timestamp; "" for null. */
export function formatClockTime(ts, locale = undefined) {
  if (typeof ts !== "number" || !Number.isFinite(ts)) return "";
  return new Date(ts * 1000).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** ISO string for a <time datetime> attribute; "" for null. */
export function isoTime(ts) {
  if (typeof ts !== "number" || !Number.isFinite(ts)) return "";
  return new Date(ts * 1000).toISOString();
}
