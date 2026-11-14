// Question controller: asks, polls and correlates. No DOM.
//
// Flow: POST /api/question {text} -> 200 (answered | unavailable) or 202 (looking_up).
// While looking_up it polls GET /api/question/{id} every POLL_INTERVAL_MS and also
// accepts the same record pushed in state.questions.recent over the socket,
// whichever comes first. Polling stops when the record is final, when a new
// question is asked, on dispose, or after LOOKUP_TIMEOUT_MS ("still waiting").
//
// Correlation: only the latest question THIS page asked may change the view.
// Asking clears the tracked id until the server returns the new id, so a late
// answer to an older question can never replace a newer one. A final record is
// never replaced by a stale looking_up copy (see model.shouldReplace).

import {
  LOOKUP_TIMEOUT_MS,
  POLL_INTERVAL_MS,
  findPushedRecord,
  isFinal,
  normalizeRecord,
  phaseForRecord,
  requestErrorMessage,
  shouldReplace,
  STILL_WAITING_MESSAGE,
  validateQuestion,
} from "./model.js";

const IDLE = Object.freeze({ phase: "idle", text: "", questionId: null, record: null, message: "" });

/**
 * Create the controller.
 * @param {object} options
 * @param {(path: string, options?: object) => Promise<any>} options.request ctx.request
 * @param {(view: object) => void} options.onChange receives {phase, text, questionId, record, message}
 * @param {(payload: any) => string|null} [options.detailOf] errorMessageFrom from core/api-client.js
 */
export function createQuestionController({
  request,
  onChange,
  detailOf = () => null,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  pollIntervalMs = POLL_INTERVAL_MS,
  lookupTimeoutMs = LOOKUP_TIMEOUT_MS,
}) {
  let view = IDLE;
  let generation = 0;
  let trackedId = null; // question_id of this page's latest question, once known
  let pollTimer = null;
  let deadlineTimer = null;
  let inFlight = null; // AbortController for the current request
  let lastState = null; // newest pushed state, to catch a push that beat the POST reply
  let disposed = false;

  function emit(next) {
    view = Object.freeze(next);
    if (!disposed) onChange(view);
  }

  function stopTimers() {
    if (pollTimer !== null) clearTimer(pollTimer);
    if (deadlineTimer !== null) clearTimer(deadlineTimer);
    pollTimer = null;
    deadlineTimer = null;
  }

  function abortInFlight() {
    if (inFlight) inFlight.abort();
    inFlight = null;
  }

  async function send(path, options = {}) {
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    inFlight = controller;
    try {
      return await request(path, controller ? { ...options, signal: controller.signal } : options);
    } finally {
      if (inFlight === controller) inFlight = null;
    }
  }

  /** Show `record` if it belongs to the tracked question; returns true if shown. */
  function apply(record) {
    if (disposed || !shouldReplace(view.record, record, trackedId)) return false;
    const timedOut = view.phase === "error" && view.record?.question_id === record.question_id;
    if (timedOut && !isFinal(record)) return false; // still waiting; keep the message
    emit({ phase: phaseForRecord(record), text: record.text || view.text, questionId: record.question_id, record, message: "" });
    if (isFinal(record)) {
      stopTimers();
      abortInFlight();
    }
    return true;
  }

  function schedulePoll(gen) {
    if (gen !== generation || disposed || pollTimer !== null) return;
    pollTimer = setTimer(() => {
      pollTimer = null;
      poll(gen);
    }, pollIntervalMs);
  }

  async function poll(gen) {
    if (gen !== generation || disposed || view.phase !== "looking_up") return;
    const id = trackedId;
    let raw;
    try {
      raw = await send(`/api/question/${encodeURIComponent(id)}`);
    } catch (error) {
      if (gen !== generation || disposed || view.phase !== "looking_up") return;
      if (error?.kind === "http") {
        // 404: the question expired. Any other refusal ends the lookup too.
        stopTimers();
        emit({ ...view, phase: "error", message: requestErrorMessage(error, detailOf) });
        return;
      }
      schedulePoll(gen); // network blip or timeout: keep trying until the deadline
      return;
    }
    if (gen !== generation || disposed) return;
    const record = normalizeRecord(raw);
    if (record && record.question_id === id) apply(record);
    if (view.phase === "looking_up") schedulePoll(gen);
  }

  /** Ask a question. Resolves when the POST has returned (not when a lookup ends). */
  async function ask(rawText) {
    if (disposed) return;
    if (view.phase === "submitting") return; // no double submit
    const check = validateQuestion(rawText);
    if (!check.ok) {
      emit({ ...IDLE, phase: "error", message: check.message });
      return;
    }
    stopTimers();
    abortInFlight();
    const gen = ++generation;
    trackedId = null; // nothing from an older question can match now
    emit({ phase: "submitting", text: check.text, questionId: null, record: null, message: "" });

    let raw;
    try {
      raw = await send("/api/question", { method: "POST", body: { text: check.text } });
    } catch (error) {
      if (gen !== generation || disposed) return;
      emit({ phase: "error", text: check.text, questionId: null, record: null, message: requestErrorMessage(error, detailOf) });
      return;
    }
    if (gen !== generation || disposed) return;
    const record = normalizeRecord(raw);
    if (!record) {
      emit({ phase: "error", text: check.text, questionId: null, record: null, message: "The server sent an answer that could not be read. Try again." });
      return;
    }
    trackedId = record.question_id;
    apply(record);
    // A socket push may have delivered a newer copy before the POST reply did.
    const pushed = findPushedRecord(lastState, trackedId);
    if (pushed) apply(pushed);
    if (view.phase === "looking_up") {
      deadlineTimer = setTimer(() => {
        deadlineTimer = null;
        if (gen !== generation || disposed || view.phase !== "looking_up") return;
        if (pollTimer !== null) clearTimer(pollTimer);
        pollTimer = null;
        abortInFlight();
        emit({ ...view, phase: "error", message: STILL_WAITING_MESSAGE });
      }, lookupTimeoutMs);
      schedulePoll(gen);
    }
  }

  /** Accept a pushed shared state (snapshot.state). */
  function receiveState(state) {
    lastState = state ?? null;
    if (!trackedId || disposed) return;
    const pushed = findPushedRecord(lastState, trackedId);
    if (pushed) apply(pushed);
  }

  /** Stop polling, abort what is in flight and ignore every late answer. */
  function dispose() {
    disposed = true;
    generation += 1;
    trackedId = null;
    stopTimers();
    abortInFlight();
  }

  return {
    ask,
    receiveState,
    dispose,
    get view() {
      return view;
    },
    get trackedId() {
      return trackedId;
    },
  };
}
