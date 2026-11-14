// Last-touch search controller.
//
// Flow: POST /api/last-seen {query} -> 202 {request_id}, then poll
// GET /api/last-seen/{request_id} until status is found, not_found or unavailable.
// Only the newest search may change what is shown: every search gets a
// generation number and results from older generations are dropped.
//
// Integration (Agent 4): each search has one overall deadline timer that fires
// even while a POST or GET is still hanging (including a body that never
// finishes); the in-flight request is aborted then. Once a search is settled
// (answered, failed, timed out, replaced or disposed) nothing late can change
// what is shown. Request ids are compared after normalising (string or number).

/** Milliseconds between polls of a pending request. */
export const POLL_INTERVAL_MS = 500;
/** Milliseconds before a search is reported as timed out, whatever is in flight. */
export const SEARCH_TIMEOUT_MS = 10000;
export const MAX_QUERY_CHARS = 80;

/** Return a request id as a non-empty string, or null if it is not usable. */
export function normalizeRequestId(value) {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.trim() !== "") return value.trim();
  return null;
}

/**
 * Create a controller. `request(path, {method, body, signal})` is ctx.request.
 * `onChange(view)` receives {status, query, answer, matchedAt, message}.
 * status: idle | loading | found | not_found | unavailable | timeout | error.
 * `nowMs` is accepted for older callers and no longer used: the deadline is a timer.
 */
export function createLastSeenController({
  request,
  onChange,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
}) {
  let generation = 0;
  let pollTimer = null;
  let deadlineTimer = null;
  let inFlight = null; // AbortController of the current search's request
  let settled = true; // the current generation can no longer change the view
  let disposed = false;
  let view = { status: "idle", query: "", answer: "", matchedAt: null, message: "" };

  function emit(next) {
    view = next;
    if (!disposed) onChange(view);
  }

  function stopAll() {
    if (pollTimer !== null) {
      clearTimer(pollTimer);
      pollTimer = null;
    }
    if (deadlineTimer !== null) {
      clearTimer(deadlineTimer);
      deadlineTimer = null;
    }
    if (inFlight) {
      inFlight.abort();
      inFlight = null;
    }
  }

  const live = (gen) => gen === generation && !settled && !disposed;

  function finish(gen, next) {
    if (!live(gen)) return;
    settled = true;
    stopAll();
    emit(next);
  }

  async function send(path, options) {
    const controller = new AbortController();
    inFlight = controller;
    try {
      return await request(path, { ...options, signal: controller.signal });
    } finally {
      if (inFlight === controller) inFlight = null;
    }
  }

  async function poll(gen, query, requestId) {
    pollTimer = null;
    if (!live(gen)) return;
    let result;
    try {
      result = await send(`/api/last-seen/${encodeURIComponent(requestId)}`, {});
    } catch (err) {
      finish(gen, { status: "error", query, answer: "", matchedAt: null, message: errorMessage(err) });
      return;
    }
    if (!live(gen)) return;
    if (!result || normalizeRequestId(result.request_id) !== requestId) {
      // Not our request: treat as a transient mismatch and keep waiting.
      schedule(gen, query, requestId);
      return;
    }
    if (result.status === "pending") {
      schedule(gen, query, requestId);
      return;
    }
    if (result.status === "found") {
      finish(gen, {
        status: "found",
        query,
        answer: result.answer || "",
        matchedAt: typeof result.matched_at === "number" ? result.matched_at : null,
        message: "",
      });
    } else if (result.status === "not_found") {
      finish(gen, {
        status: "not_found",
        query,
        answer: result.answer || "",
        matchedAt: null,
        message: "",
      });
    } else {
      finish(gen, {
        status: "unavailable",
        query,
        answer: "",
        matchedAt: null,
        message: "Touch history is unavailable right now.",
      });
    }
  }

  function schedule(gen, query, requestId) {
    if (!live(gen)) return;
    pollTimer = setTimer(() => poll(gen, query, requestId), POLL_INTERVAL_MS);
  }

  /** Start a new search; any earlier search is abandoned and can no longer change the view. */
  async function search(rawQuery) {
    if (disposed) return;
    const query = String(rawQuery ?? "").trim().slice(0, MAX_QUERY_CHARS);
    stopAll();
    const gen = ++generation;
    settled = false;
    if (!query) {
      settled = true;
      emit({ status: "idle", query: "", answer: "", matchedAt: null, message: "Type what you are looking for." });
      return;
    }
    emit({ status: "loading", query, answer: "", matchedAt: null, message: "" });
    deadlineTimer = setTimer(() => {
      deadlineTimer = null;
      finish(gen, {
        status: "timeout",
        query,
        answer: "",
        matchedAt: null,
        message: "No answer arrived in time. The history service may be busy.",
      });
    }, SEARCH_TIMEOUT_MS);
    let accepted;
    try {
      accepted = await send("/api/last-seen", { method: "POST", body: { query } });
    } catch (err) {
      finish(gen, { status: "error", query, answer: "", matchedAt: null, message: errorMessage(err) });
      return;
    }
    if (!live(gen)) return;
    const requestId = normalizeRequestId(accepted?.request_id);
    if (requestId === null) {
      finish(gen, {
        status: "error",
        query,
        answer: "",
        matchedAt: null,
        message: "The laptop did not accept the search.",
      });
      return;
    }
    schedule(gen, query, requestId);
  }

  /** Re-run the last query. */
  function retry() {
    return search(view.query);
  }

  /** Stop polling, abort what is in flight, and ignore any late answers. */
  function dispose() {
    disposed = true;
    settled = true;
    generation += 1;
    stopAll();
  }

  return { search, retry, dispose, get view() { return view; } };
}

function errorMessage(err) {
  const status = err && typeof err.status === "number" ? err.status : null;
  if (status === 404 || status === 405) return "This laptop does not offer touch history search yet.";
  if (status === 503) return "Touch history is unavailable right now.";
  return "The search request failed. Check the dashboard connection and try again.";
}
