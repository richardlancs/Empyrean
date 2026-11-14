// The one HTTP client for the dashboard. Same-origin JSON only.
// request(path, { method, body }) resolves with the parsed response body and
// rejects with ApiError on network failure, timeout, or a non-2xx status.

const METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
export const DEFAULT_TIMEOUT_MS = 10_000;

/** A failed dashboard request. kind: "network" | "timeout" | "http" | "parse". */
export class ApiError extends Error {
  constructor(message, { kind, status = null, path, payload = null, cause } = {}) {
    super(message, cause === undefined ? undefined : { cause });
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.path = path;
    this.payload = payload;
  }
}

/** Human-readable message from a FastAPI-style error body, if any. */
export function errorMessageFrom(payload) {
  if (!payload) return null;
  if (typeof payload === "string") return payload.trim() || null;
  const detail = payload.detail ?? payload.message ?? payload.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length && typeof detail[0]?.msg === "string") return detail[0].msg;
  return null;
}

function assertSameOriginPath(path) {
  if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) {
    throw new TypeError(`request() needs a same-origin path starting with "/", got ${JSON.stringify(path)}`);
  }
}

async function readBody(response, path) {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  const type = response.headers.get("content-type") || "";
  if (!type.includes("json")) return text;
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new ApiError("The dashboard server sent a response that could not be read", {
      kind: "parse",
      status: response.status,
      path,
      cause: error,
    });
  }
}

/** A promise that rejects when signal aborts (fetch bodies may ignore the signal). */
function aborted(signal) {
  return new Promise((_, reject) => {
    const fail = () => reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
    if (signal.aborted) fail();
    else signal.addEventListener("abort", fail, { once: true });
  });
}

/**
 * Create the API client.
 * @param {object} [options]
 * @param {typeof fetch} [options.fetchImpl]
 * @param {number} [options.timeoutMs]
 */
export function createApiClient({
  fetchImpl = globalThis.fetch?.bind(globalThis),
  timeoutMs = DEFAULT_TIMEOUT_MS,
  setTimer = globalThis.setTimeout.bind(globalThis),
  clearTimer = globalThis.clearTimeout.bind(globalThis),
} = {}) {
  /**
   * Send one JSON request to this dashboard server.
   * @param {string} path e.g. "/api/state"
   * @param {{method?: string, body?: object, signal?: AbortSignal, timeoutMs?: number}} [options]
   */
  async function request(path, { method = "GET", body, signal, timeoutMs: perCall = timeoutMs } = {}) {
    assertSameOriginPath(path);
    const verb = String(method).toUpperCase();
    if (!METHODS.has(verb)) throw new TypeError(`Unsupported method ${method}`);
    if (body !== undefined && verb === "GET") throw new TypeError("GET requests cannot have a body");

    const headers = { Accept: "application/json" };
    const init = { method: verb, headers, credentials: "same-origin", cache: "no-store" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimer(() => {
      timedOut = true;
      controller.abort();
    }, perCall);
    const forwardAbort = () => controller.abort();
    if (signal) {
      if (signal.aborted) controller.abort();
      else signal.addEventListener("abort", forwardAbort, { once: true });
    }
    init.signal = controller.signal;

    // Integration (Agent 4): the timeout and the caller's signal stay armed until
    // the body has been read, so a response whose body never finishes still ends.
    let response;
    let payload;
    try {
      try {
        response = await fetchImpl(path, init);
      } catch (error) {
        if (timedOut) {
          throw new ApiError("The dashboard server did not answer in time", { kind: "timeout", path, cause: error });
        }
        if (signal?.aborted) throw error; // caller cancelled: pass the AbortError through
        throw new ApiError("Could not reach the dashboard server", { kind: "network", path, cause: error });
      }
      try {
        payload = await Promise.race([readBody(response, path), aborted(controller.signal)]);
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (timedOut) {
          throw new ApiError("The dashboard server did not finish its answer in time", {
            kind: "timeout",
            path,
            cause: error,
          });
        }
        if (signal?.aborted) throw error;
        throw new ApiError("The connection dropped while reading the answer", { kind: "network", path, cause: error });
      }
    } finally {
      clearTimer(timer);
      signal?.removeEventListener("abort", forwardAbort);
    }
    if (!response.ok) {
      const message = errorMessageFrom(payload) || `The dashboard server refused the request (HTTP ${response.status})`;
      throw new ApiError(message, { kind: "http", status: response.status, path, payload });
    }
    return payload;
  }

  return { request };
}
