// Shared test helpers: a manual clock, deferred promises, records and a fake
// SpeechRecognition. Test-only; nothing here ships.

/** A manual timer queue: advance(ms) runs due callbacks in time order. */
export function createClock() {
  let now = 0;
  let nextId = 1;
  const timers = new Map();
  return {
    setTimer(fn, ms) {
      const id = nextId++;
      timers.set(id, { fn, at: now + ms });
      return id;
    },
    clearTimer(id) {
      timers.delete(id);
    },
    async advance(ms) {
      const end = now + ms;
      for (;;) {
        let due = null;
        for (const [id, t] of timers) if (t.at <= end && (!due || t.at < due[1].at)) due = [id, t];
        if (!due) break;
        timers.delete(due[0]);
        now = due[1].at;
        due[1].fn();
        await flush();
      }
      now = end;
      await flush();
    },
    pending: () => timers.size,
    get now() {
      return now;
    },
  };
}

/** Let queued promise callbacks run. */
export async function flush() {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}

export function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** A server question record with overrides. */
export function record(overrides = {}) {
  return {
    question_id: "q1",
    text: "What am I touching?",
    intent: "touch",
    target: null,
    status: "answered",
    answer: "You are touching a Heinz ketchup bottle.",
    answered_by: "dashboard",
    speech_requested: true,
    history_status: null,
    history_request_id: null,
    detail: "",
    asked_at: 100,
    answered_at: 100.2,
    ...overrides,
  };
}

/** A looking_up history record. */
export function lookingUp(overrides = {}) {
  return record({
    question_id: "h1",
    text: "Where did I last touch my keys?",
    intent: "history",
    target: "keys",
    status: "looking_up",
    answer: "Looking up the last touch of keys…",
    answered_by: null,
    speech_requested: false,
    history_request_id: "r1",
    detail: "Waiting for storage",
    answered_at: null,
    ...overrides,
  });
}

/** An ApiError-shaped rejection. */
export function apiError(kind, status = null, payload = null) {
  return Object.assign(new Error(kind), { name: "ApiError", kind, status, payload });
}

/** Fake SpeechRecognition: records every instance; tests drive the events. */
export function createFakeRecognition() {
  const instances = [];
  class FakeRecognition {
    constructor() {
      this.lang = "";
      this.continuous = null;
      this.interimResults = null;
      this.started = 0;
      this.stopped = 0;
      this.aborted = 0;
      this.onresult = null;
      this.onerror = null;
      this.onend = null;
      instances.push(this);
    }
    start() {
      this.started += 1;
    }
    stop() {
      this.stopped += 1;
    }
    abort() {
      this.aborted += 1;
    }
    // Test drivers
    emitResult(parts) {
      const results = parts.map(([transcript, isFinal]) => Object.assign([{ transcript }], { isFinal }));
      this.onresult?.({ resultIndex: 0, results });
    }
    emitError(error) {
      this.onerror?.({ error });
    }
    emitEnd() {
      this.onend?.();
    }
  }
  return { FakeRecognition, instances };
}
