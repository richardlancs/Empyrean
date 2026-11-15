// Pure logic for the questions panel: no DOM, no timers, no network.
// Everything here is unit tested in node (tests/ui/questions-integration/).
//
// The backend stays authoritative. These helpers only validate, correlate and
// describe the records the server sends; they never invent an answer.

/** Longest question the server accepts (POST /api/question). */
export const MAX_QUESTION_CHARS = 500;
/** Milliseconds between polls of a question that is still looking_up. */
export const POLL_INTERVAL_MS = 700;
/** Milliseconds after asking before a pending lookup is reported as still waiting. */
export const LOOKUP_TIMEOUT_MS = 15_000;

export const RECORD_STATUSES = Object.freeze(["answered", "looking_up", "unavailable"]);
const INTENTS = new Set(["scene", "touch", "history", "help"]);
const ANSWERED_BY = new Set(["dashboard", "namer", "storage"]);
const HISTORY_STATUSES = new Set(["found", "not_found", "unavailable"]);

export const HISTORY_UNAVAILABLE_TITLE = "Touch history is unavailable right now.";
export const SCENE_UNAVAILABLE_TITLE = "No answer is available right now.";
export const STILL_WAITING_MESSAGE =
  "Still waiting for an answer from touch history. It may be busy; you can ask again.";
export const QUESTIONS_OFF_REASON =
  "Questions are unavailable because the dashboard is running without the app. Start the app to ask questions.";
export const RECONNECTING_NOTE = "Dashboard connection lost. Reconnecting, so answers may be delayed.";

function isRecordObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function textOrNull(value) {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function finiteOrNull(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Return a clean question record, or null when the payload is not one.
 * Unknown optional values become null; unknown statuses make the record unusable.
 */
export function normalizeRecord(raw) {
  if (!isRecordObject(raw)) return null;
  const id = textOrNull(raw.question_id);
  if (!id || !RECORD_STATUSES.includes(raw.status)) return null;
  return Object.freeze({
    question_id: id.trim(),
    text: typeof raw.text === "string" ? raw.text : "",
    intent: INTENTS.has(raw.intent) ? raw.intent : null,
    target: textOrNull(raw.target),
    status: raw.status,
    answer: textOrNull(raw.answer),
    answered_by: ANSWERED_BY.has(raw.answered_by) ? raw.answered_by : null,
    speech_requested: raw.speech_requested === true,
    history_status: HISTORY_STATUSES.has(raw.history_status) ? raw.history_status : null,
    history_request_id: textOrNull(raw.history_request_id),
    detail: typeof raw.detail === "string" ? raw.detail.trim() : "",
    asked_at: finiteOrNull(raw.asked_at),
    answered_at: finiteOrNull(raw.answered_at),
  });
}

/** True when the record will not change any more (answered or unavailable). */
export function isFinal(record) {
  return Boolean(record) && record.status !== "looking_up";
}

/**
 * Should `incoming` replace `current` for the question this page is tracking?
 * Only the tracked id counts, and a final record never goes back to looking_up
 * (a stale socket snapshot or a slow poll cannot undo an answer).
 */
export function shouldReplace(current, incoming, trackedId) {
  if (!incoming || !trackedId || incoming.question_id !== trackedId) return false;
  if (!current || current.question_id !== trackedId) return true;
  if (isFinal(current) && !isFinal(incoming)) return false;
  return true;
}

/** The recent question records pushed in the shared state, newest first (max 5). */
export function selectRecent(state) {
  const recent = state?.questions?.recent;
  if (!Array.isArray(recent)) return [];
  const out = [];
  for (const raw of recent) {
    const record = normalizeRecord(raw);
    if (record) out.push(record);
    if (out.length === 5) break;
  }
  return out;
}

/** The pushed record for question id, or null. */
export function findPushedRecord(state, id) {
  if (!id) return null;
  return selectRecent(state).find((record) => record.question_id === id) || null;
}

/**
 * Can this page ask questions? Only an explicit "no" from the server turns asking
 * off: capabilities.questions === false, or questions.available === false.
 * Older servers that send neither are allowed; they answer 503 if they cannot.
 */
export function selectAvailability(state) {
  const capability = state?.capabilities?.questions;
  if (capability === true) return { canAsk: true, reason: "" };
  if (capability === false) return { canAsk: false, reason: QUESTIONS_OFF_REASON };
  if (isRecordObject(state?.questions) && state.questions.available === false) {
    return { canAsk: false, reason: QUESTIONS_OFF_REASON };
  }
  return { canAsk: true, reason: "" };
}

/** A short note about the dashboard connection, or "" when nothing needs saying. */
export function selectConnectionNote(connection) {
  return connection === "reconnecting" ? RECONNECTING_NOTE : "";
}

/** Trim the question and collapse whitespace, as the server does. */
export function cleanQuestion(text) {
  return String(text ?? "").replace(/\s+/g, " ").trim();
}

/** Validate a question before sending: {ok, text} or {ok: false, message}. */
export function validateQuestion(raw) {
  const text = cleanQuestion(raw);
  if (!text) return { ok: false, text, message: "Type a question first, or use the microphone." };
  if (text.length > MAX_QUESTION_CHARS) {
    return { ok: false, text, message: `Keep the question under ${MAX_QUESTION_CHARS} characters.` };
  }
  return { ok: true, text, message: "" };
}

/**
 * A plain sentence for a failed request. Prefers the server's own detail.
 * `error` is an ApiError-like {kind, status, payload}; `detailOf` is
 * core/api-client.js errorMessageFrom (injected so this file stays pure).
 */
export function requestErrorMessage(error, detailOf = () => null) {
  const detail = detailOf(error?.payload ?? null);
  if (error?.kind === "http" && detail) return detail;
  if (error?.kind === "http" && error.status === 404) return "That question is unknown or has expired. Ask again.";
  if (error?.kind === "http" && error.status === 503) return "Questions require the running app.";
  if (error?.kind === "http" && error.status === 422) return "The question was not accepted. Check the text and try again.";
  if (error?.kind === "timeout") return "The dashboard server did not answer in time. Try again.";
  if (error?.kind === "network") return "Could not reach the dashboard server. Check the connection and try again.";
  if (detail) return detail;
  return "The question could not be sent. Try again.";
}

/** The ask phase that matches a record's status. */
export function phaseForRecord(record) {
  if (!record) return "idle";
  return record.status; // answered | looking_up | unavailable
}

/**
 * Describe a record for display. Truthful by construction:
 * - looking_up is in progress (tone "pending"), never a final answer;
 * - unavailable is an unavailable message (tone "unavailable"), never "not found";
 * - speech is only ever "Sent to the speaker", never "Spoken" or "Heard".
 */
export function describeRecord(record) {
  if (!record) return null;
  // storage and namer speak their own answers, so speech_requested stays false for them.
  const speech =
    record.speech_requested || record.answered_by === "storage" || record.answered_by === "namer"
      ? "Sent to the speaker."
      : "";
  if (record.status === "looking_up") {
    return {
      tone: "pending",
      label: "Looking up…",
      title: "",
      body: record.answer || (record.target ? `Looking up the last touch of ${record.target}…` : "Looking up…"),
      detail: "",
      speech: "",
    };
  }
  if (record.status === "unavailable") {
    const title = record.intent === "history" ? HISTORY_UNAVAILABLE_TITLE : SCENE_UNAVAILABLE_TITLE;
    const body = record.answer && record.answer !== title ? record.answer : "";
    return {
      tone: "unavailable",
      label: "Unavailable",
      title,
      body,
      detail: record.detail ? `Reason: ${record.detail}.`.replace(/\.\.$/, ".") : "",
      speech,
    };
  }
  const fromHistory = record.answered_by === "storage" || record.intent === "history";
  return {
    tone: "answer",
    label: "Answered",
    title: "",
    body: record.answer || "The server answered without any text.",
    detail: fromHistory ? "From touch history. This is when it was last touched, not proof it is still there." : "",
    speech,
  };
}

/** Text to announce once for a final record ("" when there is nothing final). */
export function announcementFor(record) {
  if (!isFinal(record)) return "";
  const view = describeRecord(record);
  if (record.status === "unavailable") return [view.title, view.body].filter(Boolean).join(" ");
  return view.body;
}

/** Stable announcer key for a record's final status. */
export function announcementKey(record) {
  return `question:${record.question_id}:${record.status}`;
}

/** Short label for a record in the recent list. */
export function recentSummary(record) {
  if (record.status === "looking_up") return "Looking up…";
  if (record.status === "unavailable") {
    return record.intent === "history" ? HISTORY_UNAVAILABLE_TITLE : record.answer || SCENE_UNAVAILABLE_TITLE;
  }
  return record.answer || "Answered.";
}
