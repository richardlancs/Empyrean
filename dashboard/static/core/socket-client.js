// The only module that opens the dashboard WebSocket (/ws).
// Parses and normalizes each message, reports bad ones, and reconnects with
// capped exponential backoff. An open socket proves only that this page can reach
// the dashboard server; it says nothing about the camera, speaker or wearer.

import { normalizeState } from "./normalize.js";
import { reportError } from "./store.js";

export const SOCKET_PATH = "/ws";

/** ws:// or wss:// URL for /ws on the page's own host. */
export function dashboardSocketUrl(location = globalThis.location) {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}${SOCKET_PATH}`;
}

/** Parse one message's text into normalized state; throws on bad input. */
export function parseStateMessage(text) {
  if (typeof text !== "string") throw new TypeError("Dashboard update was not text");
  return normalizeState(JSON.parse(text));
}

/**
 * Create the socket client. Nothing connects until start().
 * @param {object} options
 * @param {(state: object) => void} options.onState normalized state for each message
 * @param {(connection: string) => void} options.onConnectionChange
 *        "connecting" before the first open, "connected", then "reconnecting"
 * @param {(error: Error) => void} [options.onError] malformed messages, constructor failures
 */
export function createSocketClient({
  url = dashboardSocketUrl(),
  onState,
  onConnectionChange,
  onError = reportError,
  WebSocketImpl = globalThis.WebSocket,
  setTimer = globalThis.setTimeout.bind(globalThis),
  clearTimer = globalThis.clearTimeout.bind(globalThis),
  random = Math.random,
  minDelayMs = 500,
  maxDelayMs = 10_000,
} = {}) {
  let socket = null;
  let timer = null;
  let attempt = 0;
  let started = false;
  let stopped = false;
  let everOpened = false;
  let connection = null;

  function setConnection(next) {
    if (next === connection) return;
    connection = next;
    onConnectionChange?.(next);
  }

  function detach(ws) {
    ws.onopen = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
  }

  function nextDelay() {
    const base = Math.min(maxDelayMs, minDelayMs * 2 ** attempt);
    attempt += 1;
    return Math.round(base * (0.8 + 0.4 * random())); // +/-20% jitter
  }

  function scheduleReconnect() {
    if (stopped || timer !== null) return;
    timer = setTimer(() => {
      timer = null;
      connect();
    }, nextDelay());
  }

  function connect() {
    if (stopped) return;
    setConnection(everOpened || attempt > 0 ? "reconnecting" : "connecting");
    let ws;
    try {
      ws = new WebSocketImpl(url);
    } catch (error) {
      onError(new Error(`Could not open the dashboard connection to ${url}`, { cause: error }));
      scheduleReconnect();
      return;
    }
    socket = ws;
    ws.onopen = () => {
      attempt = 0;
      everOpened = true;
      setConnection("connected");
    };
    ws.onmessage = (event) => {
      let state;
      try {
        state = parseStateMessage(event.data);
      } catch (error) {
        onError(new Error("Ignored a dashboard update that was not valid state JSON", { cause: error }));
        return;
      }
      onState?.(state);
    };
    ws.onerror = () => {
      // The browser always follows an error with close; reconnect happens there.
    };
    ws.onclose = () => {
      detach(ws);
      if (socket === ws) socket = null;
      if (stopped) return;
      setConnection("reconnecting");
      scheduleReconnect();
    };
  }

  return {
    /** Open the connection (once). */
    start() {
      if (started) return;
      started = true;
      connect();
    },

    /** Skip the backoff wait, e.g. when the browser reports it is back online. */
    reconnectNow() {
      if (!started || stopped || socket !== null) return;
      if (timer !== null) {
        clearTimer(timer);
        timer = null;
      }
      connect();
    },

    /** Close for good: no further reconnects or callbacks. */
    stop() {
      stopped = true;
      if (timer !== null) {
        clearTimer(timer);
        timer = null;
      }
      if (socket) {
        const ws = socket;
        socket = null;
        detach(ws);
        try {
          ws.close(1000, "page closed");
        } catch (error) {
          onError(error);
        }
      }
    },

    /** Current connection state, or null before start(). */
    get connection() {
      return connection;
    },
  };
}
