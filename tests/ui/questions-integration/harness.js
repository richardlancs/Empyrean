// FIXTURE harness for the questions feature. Everything here is artificial.
// Mounts the real dashboard/static/features/questions/index.js with a fake ctx:
// a real core store driven by the controls, a fake request() that mimics
// POST /api/question and GET /api/question/{id}, and a fake SpeechRecognition.
//
// URL params set the initial controls, e.g.
//   harness.html?reply=history-poll&latency=300&voice=fake&mic=ok&cap=true&connection=connected

import { ApiError } from "../../../dashboard/static/core/api-client.js";
import { createStore, immediateScheduler } from "../../../dashboard/static/core/store.js";
import { mountQuestions } from "../../../dashboard/static/features/questions/index.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
for (const [param, id] of [["reply", "fx-reply"], ["latency", "fx-latency"], ["connection", "fx-connection"], ["cap", "fx-cap"], ["voice", "fx-voice"], ["mic", "fx-mic"]]) {
  if (params.has(param)) $(id).value = params.get(param);
}
if (params.get("contrast") === "1") $("fx-contrast").checked = true;
if (params.get("controls") === "open") $("fixture-controls").open = true;

const store = createStore({ schedule: immediateScheduler });
const records = new Map(); // question_id -> record (newest last)
let seq = 0;
let pollCounts = new Map();

function control(id) {
  return $(id).value;
}

function pushState() {
  const cap = control("fx-cap");
  const capabilities = { last_seen: true };
  if (cap !== "absent") capabilities.questions = cap === "true";
  const recent = [...records.values()].reverse().slice(0, 5).map((r) => ({ ...r }));
  const state = { now: Date.now() / 1000, capabilities };
  if (cap !== "absent") state.questions = { available: cap === "true", recent };
  store.receiveState(state);
}

function setConnection() {
  store.setConnection(control("fx-connection"));
}

function intentOf(text) {
  const t = text.toLowerCase();
  if (/\b(where|last)\b/.test(t)) return "history";
  if (/\bsee\b/.test(t)) return "scene";
  if (/\b(touch|touching|hold|holding)\b/.test(t)) return "touch";
  return "help";
}

function targetOf(text) {
  const match = /(?:my|the)\s+([a-z ]+?)\??$/i.exec(text.trim());
  return match ? match[1] : "it";
}

function base(text) {
  seq += 1;
  const intent = intentOf(text);
  return {
    question_id: `fx${seq}`,
    text,
    intent,
    target: intent === "history" ? targetOf(text) : null,
    status: "answered",
    answer: null,
    answered_by: null,
    speech_requested: false,
    history_status: null,
    history_request_id: null,
    detail: "",
    asked_at: Date.now() / 1000,
    answered_at: null,
  };
}

function immediateAnswer(record) {
  const answers = {
    scene: "I can see a Heinz ketchup bottle, a mug and a phone.",
    touch: "You are touching a Heinz ketchup bottle.",
    help: "Try: What do you see? What am I touching? Or: Where did I last touch the bottle?",
  };
  return { ...record, status: "answered", answer: answers[record.intent] || answers.help, answered_by: "dashboard", speech_requested: true, answered_at: Date.now() / 1000 };
}

function lookingUp(record) {
  return { ...record, intent: "history", status: "looking_up", answer: `Looking up the last touch of ${record.target}…`, history_request_id: `r${seq}`, detail: "Waiting for storage" };
}

function found(record) {
  return { ...record, status: "answered", answer: `You last touched your ${record.target} at 10:02, next to a mug.`, answered_by: "storage", speech_requested: false, history_status: "found", detail: "", answered_at: Date.now() / 1000 };
}

function notFound(record) {
  return { ...record, status: "answered", answer: `I have no record of touching ${record.target}.`, answered_by: "storage", speech_requested: false, history_status: "not_found", detail: "", answered_at: Date.now() / 1000 };
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function logRequest(text) {
  const li = document.createElement("li");
  li.textContent = text;
  $("fx-requests").prepend(li);
}

/** Fake ctx.request mimicking the dashboard API, with ApiError rejections. */
async function request(path, { method = "GET", body, signal } = {}) {
  const latency = Math.max(0, Number(control("fx-latency")) || 0);
  const reply = control("fx-reply");
  logRequest(`${method} ${path}${body ? ` ${JSON.stringify(body)}` : ""}`);
  await wait(latency);
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  if (reply === "network") throw new ApiError("Could not reach the dashboard server", { kind: "network", path });

  if (method === "POST" && path === "/api/question") {
    if (reply === "503") throw new ApiError("Questions require the running app.", { kind: "http", status: 503, path, payload: { detail: "Questions require the running app." } });
    if (reply === "422") throw new ApiError("Please enter a question.", { kind: "http", status: 422, path, payload: { detail: "Please enter a question." } });
    let record = base(body.text);
    if (record.intent !== "history") {
      record = reply === "scene-unavailable"
        ? { ...record, status: "unavailable", answer: "I do not have a current camera view.", answered_by: "dashboard", speech_requested: true, detail: "No camera scene in the last few seconds", answered_at: Date.now() / 1000 }
        : immediateAnswer(record);
    } else if (reply === "history-unavailable") {
      record = { ...record, status: "unavailable", answer: "Touch history is unavailable right now.", answered_by: "dashboard", speech_requested: true, history_status: "unavailable", detail: "Storage is not running in this launch", answered_at: Date.now() / 1000 };
    } else if (reply === "answer") {
      record = found(record);
    } else {
      record = lookingUp(record);
      if (reply === "history-push") {
        const id = record.question_id;
        setTimeout(() => {
          records.set(id, found(records.get(id)));
          pushState();
        }, 2000);
      }
    }
    records.set(record.question_id, record);
    pushState();
    return { ...record };
  }

  const match = /^\/api\/question\/(.+)$/.exec(path);
  if (method === "GET" && match) {
    const id = decodeURIComponent(match[1]);
    const record = records.get(id);
    if (!record) throw new ApiError("That question is unknown or has expired. Ask again.", { kind: "http", status: 404, path, payload: { detail: "That question is unknown or has expired. Ask again." } });
    if (record.status === "looking_up" && (reply === "history-poll" || reply === "history-notfound")) {
      const n = (pollCounts.get(id) || 0) + 1;
      pollCounts.set(id, n);
      if (n >= 3) {
        records.set(id, reply === "history-poll" ? found(record) : notFound(record));
        pushState();
      }
    }
    return { ...records.get(id) };
  }
  throw new ApiError("Not found", { kind: "http", status: 404, path, payload: { detail: "Not Found" } });
}

/** Fake SpeechRecognition driven by the "Fake mic outcome" control. */
class FakeRecognition {
  constructor() {
    this.lang = "";
    this.continuous = null;
    this.interimResults = null;
    this.timers = [];
    window.__fixture.recognitions.push(this);
  }
  later(ms, fn) {
    this.timers.push(setTimeout(fn, ms));
  }
  result(parts) {
    const results = parts.map(([transcript, isFinal]) => Object.assign([{ transcript }], { isFinal }));
    this.onresult?.({ resultIndex: 0, results });
  }
  start() {
    this.startedAt = Date.now();
    const outcome = control("fx-mic");
    if (outcome === "ok") {
      this.later(500, () => this.result([["where did I", false]]));
      this.later(1100, () => this.result([["where did I last touch my keys", false]]));
      this.later(1600, () => this.result([["where did I last touch my keys", true]]));
      this.later(1700, () => this.onend?.());
    } else if (outcome !== "silence") {
      this.later(600, () => this.onerror?.({ error: outcome }));
      this.later(650, () => this.onend?.());
    }
  }
  stop() {
    this.later(150, () => this.onend?.());
  }
  abort() {
    this.aborted = true;
    for (const t of this.timers) clearTimeout(t);
    this.later(50, () => this.onerror?.({ error: "aborted" }));
    this.later(60, () => this.onend?.());
  }
}

function recognitionOption() {
  const mode = control("fx-voice");
  if (mode === "unsupported") return null;
  if (mode === "browser") return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  return FakeRecognition;
}

const announcements = [];
const ctx = Object.freeze({
  roots: Object.freeze({ questions: $("questions-root") }),
  subscribe: (cb) => store.subscribe(cb),
  request,
  announce(text, { key } = {}) {
    if (key && announcements.some((a) => a.key === key)) return false;
    announcements.push({ text, key });
    const li = document.createElement("li");
    li.textContent = `${text}  [key ${key}]`;
    $("fx-announcements").append(li);
    return true;
  },
});

let cleanup = null;
function mount() {
  cleanup?.();
  cleanup = mountQuestions(ctx, { Recognition: recognitionOption() });
}

function applyContrast() {
  document.documentElement.dataset.theme = $("fx-contrast").checked ? "high-contrast" : "light";
}

$("fx-cap").addEventListener("change", pushState);
$("fx-connection").addEventListener("change", setConnection);
$("fx-voice").addEventListener("change", mount);
$("fx-contrast").addEventListener("change", applyContrast);
$("fx-remount").addEventListener("click", mount);
$("fx-push-other").addEventListener("click", () => {
  const r = immediateAnswer(base("What can you see? (asked on another page)"));
  records.set(r.question_id, { ...r, intent: "scene" });
  pushState();
});

window.__fixture = {
  store,
  records,
  announcements,
  recognitions: [],
  pushState,
  set(name, value) {
    $(`fx-${name}`).value = value;
    $(`fx-${name}`).dispatchEvent(new Event("change"));
  },
  unmount() {
    cleanup?.();
    cleanup = null;
  },
  mount,
};

applyContrast();
setConnection();
pushState();
mount();
