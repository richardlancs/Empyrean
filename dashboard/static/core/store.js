// The one shared frontend store. Holds the latest backend state, the dashboard
// connection state and when the state arrived. The backend stays authoritative:
// the store never invents or edits touch, naming, hazard or audio data.
//
// Snapshot given to subscribers: { state, connection, receivedAt }
//   state       normalized backend state, or null before the first message
//   connection  "connecting" | "connected" | "reconnecting"
//   receivedAt  browser milliseconds when `state` arrived, or null
//
// Updates are coalesced: many socket messages inside one animation frame produce
// one notification carrying the newest snapshot.

export const CONNECTION_STATES = Object.freeze(["connecting", "connected", "reconnecting"]);

/** Report a listener error without stopping other listeners. */
export function reportError(error) {
  if (typeof globalThis.reportError === "function") {
    globalThis.reportError(error);
  } else {
    console.error(error);
  }
}

/**
 * Schedule fn for the next animation frame, with a timer fallback so updates still
 * flow when the tab is hidden (requestAnimationFrame pauses there).
 */
export function createFrameScheduler({
  requestFrame = globalThis.requestAnimationFrame?.bind(globalThis),
  cancelFrame = globalThis.cancelAnimationFrame?.bind(globalThis),
  setTimer = globalThis.setTimeout.bind(globalThis),
  clearTimer = globalThis.clearTimeout.bind(globalThis),
  fallbackMs = 250,
} = {}) {
  return function schedule(fn) {
    let done = false;
    let frame = null;
    let timer = null;
    const run = () => {
      if (done) return;
      done = true;
      if (frame !== null && cancelFrame) cancelFrame(frame);
      if (timer !== null) clearTimer(timer);
      fn();
    };
    if (requestFrame) frame = requestFrame(run);
    timer = setTimer(run, requestFrame ? fallbackMs : 0);
    return () => {
      done = true;
      if (frame !== null && cancelFrame) cancelFrame(frame);
      if (timer !== null) clearTimer(timer);
    };
  };
}

/** Run fn synchronously; used by tests and anywhere coalescing is not wanted. */
export function immediateScheduler(fn) {
  fn();
  return () => {};
}

/**
 * Create the store.
 * @param {object} [options]
 * @param {() => number} [options.now] browser clock in milliseconds
 * @param {(fn: () => void) => () => void} [options.schedule] coalescing scheduler
 * @param {(error: unknown) => void} [options.onListenerError]
 */
export function createStore({
  now = () => Date.now(),
  schedule = createFrameScheduler(),
  onListenerError = reportError,
} = {}) {
  let snapshot = Object.freeze({ state: null, connection: "connecting", receivedAt: null });
  const listeners = new Set();
  let cancelPending = null;
  let destroyed = false;

  function call(listener, value) {
    try {
      listener(value);
    } catch (error) {
      onListenerError(error);
    }
  }

  let pending = false;

  function flush() {
    pending = false;
    cancelPending = null;
    const value = snapshot;
    for (const entry of [...listeners]) {
      if (listeners.has(entry)) call(entry.listener, value);
    }
  }

  function changed(next) {
    if (destroyed) return;
    snapshot = Object.freeze(next);
    if (pending) return;
    pending = true;
    // A synchronous scheduler runs flush() before returning; only keep its
    // cancel function while the flush is still outstanding.
    const cancel = schedule(flush);
    if (pending) cancelPending = cancel;
  }

  return {
    /** The current snapshot (same object subscribers receive). */
    getSnapshot() {
      return snapshot;
    },

    /**
     * Call listener now with the current snapshot, then after every change.
     * Returns an idempotent unsubscribe function.
     */
    subscribe(listener) {
      if (typeof listener !== "function") throw new TypeError("subscribe needs a function");
      if (destroyed) return () => {};
      const entry = { listener };
      listeners.add(entry);
      call(listener, snapshot);
      return () => {
        listeners.delete(entry);
      };
    },

    /** Store a normalized backend state received now. */
    receiveState(state) {
      changed({ ...snapshot, state, receivedAt: now() });
    },

    /** Record the dashboard connection state; repeated values do not notify. */
    setConnection(connection) {
      if (!CONNECTION_STATES.includes(connection)) {
        throw new TypeError(`Unknown connection state: ${connection}`);
      }
      if (connection === snapshot.connection) return;
      changed({ ...snapshot, connection });
    },

    /** Number of active subscriptions; used to check cleanup. */
    listenerCount() {
      return listeners.size;
    },

    /** Drop every subscriber and any pending notification. */
    destroy() {
      destroyed = true;
      if (cancelPending) cancelPending();
      cancelPending = null;
      pending = false;
      listeners.clear();
    },
  };
}
