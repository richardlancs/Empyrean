// User-enabled microphone sessions. Final utterances submit once; normal browser
// session endings restart listening until the user turns the microphone off.
export const UNSUPPORTED_MESSAGE = "Voice input isn't supported in this browser. Type your question instead.";
export const PRIVACY_NOTE = "Voice input uses your browser's speech service, which may send audio to it.";
export const VOICE_ERROR_MESSAGES = Object.freeze({
  "not-allowed": "Allow microphone access, then try again.",
  "service-not-allowed": "Allow microphone access, then try again.",
  "audio-capture": "No microphone available. Check sound input settings.",
  network: "Speech recognition service unavailable. Open this dashboard in Google Chrome, or type your question.",
  "no-speech": "Didn't hear anything. Try again or type your question.",
});
export const VOICE_FALLBACK_ERROR = "Voice input stopped. Try again or type your question.";

/** Describe a browser recognition error. */
export function voiceErrorMessage(code) {
  return code === "aborted" ? null : VOICE_ERROR_MESSAGES[code] || VOICE_FALLBACK_ERROR;
}

/** Describe the microphone's current activity. */
export function voiceStatusText(voice) {
  switch (voice.phase) {
    case "unsupported": return UNSUPPORTED_MESSAGE;
    case "listening": return "Listening… ask your question.";
    case "paused": return "Mic on · listening resumes after the response.";
    case "transcript": return "Parsing your question…";
    case "error": return voice.message || VOICE_FALLBACK_ERROR;
    default: return "Turn on the mic to ask questions automatically.";
  }
}

/** Find the browser's speech recognition implementation. */
export function defaultRecognition(win = globalThis) {
  return win?.SpeechRecognition || win?.webkitSpeechRecognition || null;
}

/** Create a microphone toggle with automatic utterance delivery and playback pause. */
export function createVoiceInput({ Recognition, onChange, onTranscript = () => {}, lang = "en-US",
  setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = (id) => clearTimeout(id) }) {
  const supported = typeof Recognition === "function";
  let enabled = false;
  let paused = false;
  let active = null;
  let restart = null;
  let destroyed = false;
  let view = Object.freeze({ phase: supported ? "idle" : "unsupported", enabled, interim: "", transcript: "", message: "" });

  function emit(next) {
    view = Object.freeze({ enabled, interim: "", transcript: "", message: "", ...next });
    if (!destroyed) onChange(view);
  }

  function clearRestart() {
    if (restart !== null) clearTimer(restart);
    restart = null;
  }

  function detach(rec) {
    rec.onresult = rec.onerror = rec.onend = rec.onnomatch = null;
    if (rec === active) active = null;
  }

  function abort() {
    if (!active) return;
    const rec = active;
    detach(rec);
    try { rec.abort(); } catch { /* Already ended. */ }
  }

  function schedule() {
    if (!enabled || paused || destroyed || restart !== null || active) return;
    // Give the previous browser session and speaker output time to settle.
    restart = setTimer(() => { restart = null; listen(); }, 350);
  }

  function fail(message) {
    enabled = false;
    clearRestart();
    abort();
    emit({ phase: "error", message });
  }

  function listen() {
    if (!enabled || paused || destroyed || active) return false;
    let rec;
    try { rec = new Recognition(); } catch { fail(VOICE_FALLBACK_ERROR); return false; }
    active = rec;
    rec.lang = lang;
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      if (rec !== active || !enabled || paused) return;
      const finals = [], interim = [];
      for (const result of Array.from(event?.results || [])) {
        (result.isFinal ? finals : interim).push(result[0]?.transcript || "");
      }
      const text = finals.join(" ").replace(/\s+/g, " ").trim();
      if (!text) {
        emit({ phase: "listening", interim: interim.join(" ").trim() });
        return;
      }
      // Detach before delivery: duplicate final/onend callbacks cannot submit twice.
      abort();
      emit({ phase: "transcript", transcript: text });
      onTranscript(text);
      schedule();
    };
    rec.onerror = (event) => {
      if (rec !== active) return;
      if (event?.error === "no-speech" || event?.error === "aborted") {
        abort();
        schedule();
      } else fail(voiceErrorMessage(event?.error));
    };
    rec.onend = () => {
      if (rec !== active) return;
      detach(rec);
      schedule(); // Interim-only words are never submitted.
    };
    emit({ phase: "listening" });
    try { rec.start(); } catch { fail(VOICE_FALLBACK_ERROR); return false; }
    return true;
  }

  function start() {
    if (destroyed || !supported || enabled) return false;
    enabled = true;
    if (paused) { emit({ phase: "paused" }); return true; }
    return listen();
  }

  function stop() {
    enabled = false;
    clearRestart();
    abort();
    if (supported && !destroyed) emit({ phase: "idle" });
  }

  function setPaused(next) {
    if (paused === Boolean(next)) return;
    paused = Boolean(next);
    if (!enabled || destroyed) return;
    if (paused) {
      clearRestart();
      abort();
      emit({ phase: "paused" });
    } else {
      emit({ phase: "listening" });
      schedule();
    }
  }

  return {
    supported, start, stop, cancel: stop, setPaused,
    toggle() { if (enabled) stop(); else start(); },
    reset() { if (!enabled && supported && !destroyed) emit({ phase: "idle" }); },
    destroy() { destroyed = true; stop(); },
    get listening() { return active !== null; },
    get enabled() { return enabled; },
    get view() { return view; },
  };
}
