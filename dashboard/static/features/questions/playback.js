// Pause recognition while a question is pending or the laptop is speaking.
const ACTIVE = new Set(["queued", "speaking"]);
const FINISHED = new Set(["completed", "interrupted", "failed"]);

/** Follow existing SpeechStatus messages, with a bounded fallback if none arrive. */
export function createPlaybackPause({ onChange, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let timer = null;
  let waiting = null;
  let lastAnswer = null;
  let latest = {};
  let disposed = false;

  function clearWait() {
    if (timer !== null) clearTimer(timer);
    timer = null;
    waiting = null;
  }

  function refresh() {
    if (disposed) return;
    const { ask, state, connection } = latest;
    const speech = state?.speech;
    if (waiting && speech?.text === waiting.answer && speech.ts >= waiting.asked_at && FINISHED.has(speech.status)) {
      clearWait();
    }
    const busy = ask?.phase === "submitting" || ask?.phase === "looking_up";
    onChange(Boolean(busy || waiting || ACTIVE.has(speech?.status) || connection === "reconnecting"));
  }

  return {
    update(ask, state, connection) {
      if (disposed) return;
      latest = { ask, state, connection };
      const record = ask.record;
      if (record && record.status !== "looking_up" && record.question_id !== lastAnswer) {
        lastAnswer = record.question_id;
        clearWait();
        if (record.answer && (record.speech_requested || ["namer", "storage"].includes(record.answered_by))) {
          waiting = record;
          // Older/unavailable audio may not report completion. This estimate is
          // only the fallback; actual completion releases the pause immediately.
          const duration = 2000 + record.answer.split(/\s+/).length * 500;
          timer = setTimer(() => { timer = null; waiting = null; refresh(); }, duration);
        }
      }
      refresh();
    },
    destroy() { disposed = true; clearWait(); },
  };
}
