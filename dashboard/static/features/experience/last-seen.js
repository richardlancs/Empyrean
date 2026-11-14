// Last-touch search controller.
//
// Flow: POST /api/last-seen {query} -> 202 {request_id}, then poll
// GET /api/last-seen/{request_id} until status is found, not_found or unavailable.
// Only the newest search may change what is shown: every search gets a
// generation number and results from older generations are dropped. Polling
// stops when a newer search starts, on timeout, and on dispose().

/** Milliseconds between polls of a pending request. */
export const POLL_INTERVAL_MS = 500;
/** Milliseconds before a search is reported as timed out. */
export const SEARCH_TIMEOUT_MS = 10000;
export const MAX_QUERY_CHARS = 80;

/**
 * Create a controller. `request(path, {method, body})` is ctx.request.
 * `onChange(view)` receives {status, query, answer, matchedAt, message}.
 * status: idle | loading | found | not_found | unavailable | timeout | error.
 */
export function createLastSeenController({
  request,
  onChange,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  nowMs = () => Date.now(),
}) {
  let generation = 0;
  let pollTimer = null;
  let disposed = false;
  let view = { status: "idle", query: "", answer: "", matchedAt: null, message: "" };

  function emit(next) {
    view = next;
    if (!disposed) onChange(view);
  }

  function stopPolling() {
    if (pollTimer !== null) {
      clearTimer(pollTimer);
      pollTimer = null;
    }
  }

  function finish(gen, next) {
    if (gen !== generation || disposed) return;
    stopPolling();
    emit(next);
  }

  async function poll(gen, query, requestId, deadline) {
    pollTimer = null;
    if (gen !== generation || disposed) return;
    if (nowMs() >= deadline) {
      finish(gen, {
        status: "timeout",
        query,
        answer: "",
        matchedAt: null,
        message: "No answer arrived in time. The history service may be busy.",
      });
      return;
    }
    let result;
    try {
      result = await request(`/api/last-seen/${encodeURIComponent(requestId)}`);
    } catch (err) {
      finish(gen, { status: "error", query, answer: "", matchedAt: null, message: errorMessage(err) });
      return;
    }
    if (gen !== generation || disposed) return;
    if (!result || result.request_id !== requestId) {
      // Not our request: treat as a transient mismatch and keep waiting.
      schedule(gen, query, requestId, deadline);
      return;
    }
    if (result.status === "pending") {
      schedule(gen, query, requestId, deadline);
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

  function schedule(gen, query, requestId, deadline) {
    if (gen !== generation || disposed) return;
    pollTimer = setTimer(() => poll(gen, query, requestId, deadline), POLL_INTERVAL_MS);
  }

  /** Start a new search; any earlier search is abandoned. */
  async function search(rawQuery) {
    const query = String(rawQuery ?? "").trim().slice(0, MAX_QUERY_CHARS);
    stopPolling();
    const gen = ++generation;
    if (!query) {
      emit({ status: "idle", query: "", answer: "", matchedAt: null, message: "Type what you are looking for." });
      return;
    }
    emit({ status: "loading", query, answer: "", matchedAt: null, message: "" });
    const deadline = nowMs() + SEARCH_TIMEOUT_MS;
    let accepted;
    try {
      accepted = await request("/api/last-seen", { method: "POST", body: { query } });
    } catch (err) {
      finish(gen, { status: "error", query, answer: "", matchedAt: null, message: errorMessage(err) });
      return;
    }
    if (gen !== generation || disposed) return;
    if (!accepted || typeof accepted.request_id !== "string" && typeof accepted.request_id !== "number") {
      finish(gen, {
        status: "error",
        query,
        answer: "",
        matchedAt: null,
        message: "The laptop did not accept the search.",
      });
      return;
    }
    schedule(gen, query, String(accepted.request_id), deadline);
  }

  /** Re-run the last query. */
  function retry() {
    return search(view.query);
  }

  /** Stop polling and ignore any late answers. */
  function dispose() {
    disposed = true;
    generation += 1;
    stopPolling();
  }

  return { search, retry, dispose, get view() { return view; } };
}

function errorMessage(err) {
  const status = err && typeof err.status === "number" ? err.status : null;
  if (status === 404 || status === 405) return "This laptop does not offer touch history search yet.";
  if (status === 503) return "Touch history is unavailable right now.";
  return "The search request failed. Check the dashboard connection and try again.";
}
