// Screen-reader announcements through two visually hidden live regions.
//
// Policy (see docs/dashboard-redesign/design-system.md):
// - Announce actual new events only: a touch, a released-then-retouched object,
//   a new real warning, a finished lookup, a lost/restored connection.
// - Never announce timer ticks ("3 s ago") or full snapshots.
// - Pass a `key` that identifies the event (e.g. `touch:${event.id}`); a key is
//   announced at most once. Without a key, identical text is not repeated within
//   the dedupe window.
// - "assertive" is for real hazards and failures the user must act on. It is always
//   written first: polite messages queued around it wait until it has been read
//   (assertiveGapMs), whichever feature announced first. Nothing is dropped.

const PRIORITIES = new Set(["polite", "assertive"]);

/**
 * Create the announcer and append its live regions to container.
 * @param {object} options
 * @param {Element} options.container usually document.body
 */
export function createAnnouncer({
  container,
  doc = container.ownerDocument,
  now = () => Date.now(),
  setTimer = globalThis.setTimeout.bind(globalThis),
  clearTimer = globalThis.clearTimeout.bind(globalThis),
  dedupeWindowMs = 5_000,
  maxKeys = 500,
  writeDelayMs = 100,
  assertiveGapMs = 1_500,
} = {}) {
  let politeNotBefore = -Infinity; // polite text waits until an assertive one is read
  const seenKeys = new Set();
  const regions = {};
  const pending = { polite: [], assertive: [] };
  const timers = { polite: null, assertive: null };
  const lastText = { polite: { text: "", at: -Infinity }, assertive: { text: "", at: -Infinity } };

  for (const priority of PRIORITIES) {
    const region = doc.createElement("div");
    region.className = "ui-visually-hidden";
    region.setAttribute("aria-live", priority);
    region.setAttribute("aria-atomic", "true");
    region.setAttribute("role", priority === "assertive" ? "alert" : "status");
    region.setAttribute("data-announcer", priority);
    container.append(region);
    regions[priority] = region;
  }

  function rememberKey(key) {
    seenKeys.add(key);
    if (seenKeys.size > maxKeys) seenKeys.delete(seenKeys.values().next().value);
  }

  function cancel(priority) {
    if (timers[priority] !== null) clearTimer(timers[priority]);
    timers[priority] = null;
    pending[priority] = [];
  }

  function flush(priority) {
    timers[priority] = null;
    const text = pending[priority].join(" ");
    pending[priority] = [];
    regions[priority].textContent = text;
  }

  /**
   * Queue text for screen readers. Returns true if it will be announced.
   * @param {string} text
   * @param {{priority?: "polite"|"assertive", key?: string}} [options]
   */
  function announce(text, { priority = "polite", key } = {}) {
    if (!PRIORITIES.has(priority)) throw new TypeError(`announce priority must be polite or assertive, got ${priority}`);
    const clean = String(text ?? "").replace(/\s+/g, " ").trim();
    if (!clean) return false;
    if (key !== undefined && key !== null) {
      const id = String(key);
      if (seenKeys.has(id)) return false;
      rememberKey(id);
    } else {
      const last = lastText[priority];
      if (last.text === clean && now() - last.at < dedupeWindowMs) return false;
    }
    lastText[priority] = { text: clean, at: now() };

    // Empty the region first, then write after a short delay, so a repeated
    // message is still noticed as a change by screen readers.
    if (pending[priority].length === 0) regions[priority].textContent = "";
    if (!pending[priority].includes(clean)) pending[priority].push(clean);

    if (priority === "assertive") {
      politeNotBefore = now() + writeDelayMs + assertiveGapMs;
      regions.polite.textContent = "";
      if (pending.polite.length) reschedulePolite();
      if (timers.assertive === null) timers.assertive = setTimer(() => flush("assertive"), writeDelayMs);
    } else if (timers.polite === null) {
      timers.polite = setTimer(() => flush("polite"), Math.max(writeDelayMs, politeNotBefore - now()));
    }
    return true;
  }

  function reschedulePolite() {
    if (timers.polite !== null) clearTimer(timers.polite);
    timers.polite = setTimer(() => flush("polite"), Math.max(writeDelayMs, politeNotBefore - now()));
  }

  return {
    announce,
    /** Remove the live regions and cancel pending messages. */
    destroy() {
      cancel("polite");
      cancel("assertive");
      for (const region of Object.values(regions)) region.remove();
    },
  };
}
