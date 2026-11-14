// One-utterance voice input over the browser's SpeechRecognition. No DOM.
//
// Rules: user-initiated only. One recognition per click (continuous = false),
// never auto-started, never restarted after it ends, no hot mic. The final
// transcript is handed to onTranscript for the user to check; it is never
// submitted from here. A click while listening stops it; cancel() and
// destroy() abort it and detach every handler.

export const VOICE_PHASES = Object.freeze(["unsupported", "idle", "listening", "stopped", "transcript", "error"]);

export const UNSUPPORTED_MESSAGE = "Voice input isn't supported in this browser. Type your question instead.";
export const PRIVACY_NOTE = "Voice input uses your browser's speech service, which may send audio to it.";

export const VOICE_ERROR_MESSAGES = Object.freeze({
  "not-allowed": "Allow microphone access, then try again.",
  "service-not-allowed": "Allow microphone access, then try again.",
  "audio-capture": "No microphone available. Check sound input settings.",
  network:
    "Speech recognition service unavailable. Open this dashboard in Google Chrome, or type your question.",
  "no-speech": "Didn't hear anything. Try again or type your question.",
});
export const VOICE_FALLBACK_ERROR = "Voice input stopped. Try again or type your question.";

/** Message for a SpeechRecognition error code; null for "aborted" (user cancelled). */
export function voiceErrorMessage(code) {
  if (code === "aborted") return null;
  return VOICE_ERROR_MESSAGES[code] || VOICE_FALLBACK_ERROR;
}

/** Status line for a voice view. */
export function voiceStatusText(voice) {
  switch (voice.phase) {
    case "unsupported":
      return UNSUPPORTED_MESSAGE;
    case "listening":
      return "Listening… speak your question.";
    case "stopped":
      return "Stopped listening. Nothing was heard.";
    case "transcript":
      return "Check the text, then press Ask.";
    case "error":
      return voice.message || VOICE_FALLBACK_ERROR;
    default:
      return "Press the microphone to speak one question.";
  }
}

/** The browser's SpeechRecognition constructor, or null. */
export function defaultRecognition(win = globalThis) {
  return win?.SpeechRecognition || win?.webkitSpeechRecognition || null;
}

/**
 * Create the voice input.
 * @param {object} options
 * @param {Function|null} options.Recognition SpeechRecognition constructor (null = unsupported)
 * @param {(voice: object) => void} options.onChange receives {phase, interim, transcript, message}
 * @param {(text: string) => void} [options.onTranscript] final transcript, for the input
 */
export function createVoiceInput({ Recognition, onChange, onTranscript = () => {}, lang = "en-US" }) {
  const supported = typeof Recognition === "function";
  let view = Object.freeze({ phase: supported ? "idle" : "unsupported", interim: "", transcript: "", message: "" });
  let active = null; // the one live recognition, if any
  let session = null; // what the live recognition has produced
  let destroyed = false;

  function emit(next) {
    view = Object.freeze({ interim: "", transcript: "", message: "", ...next });
    if (!destroyed) onChange(view);
  }

  function detach(rec) {
    rec.onresult = null;
    rec.onerror = null;
    rec.onend = null;
    rec.onnomatch = null;
  }

  function finish(rec) {
    if (rec !== active) return;
    detach(rec);
    active = null;
    const done = session;
    session = null;
    if (done.aborted) {
      emit({ phase: "idle" });
    } else if (done.error) {
      emit({ phase: "error", message: done.error });
    } else if (done.final) {
      emit({ phase: "transcript", transcript: done.final });
      onTranscript(done.final);
    } else if (done.interim) {
      // Ended with only interim words: hand them over too; the user checks before Ask.
      emit({ phase: "transcript", transcript: done.interim });
      onTranscript(done.interim);
    } else {
      emit({ phase: done.stopped ? "stopped" : "error", message: done.stopped ? "" : VOICE_ERROR_MESSAGES["no-speech"] });
    }
  }

  /** Start one recognition. Does nothing while one is running or when unsupported. */
  function start() {
    if (destroyed || !supported || active) return false;
    let rec;
    try {
      rec = new Recognition();
    } catch {
      emit({ phase: "error", message: VOICE_FALLBACK_ERROR });
      return false;
    }
    rec.lang = lang;
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    session = { final: "", interim: "", error: null, aborted: false, stopped: false };
    active = rec;
    rec.onresult = (event) => {
      if (rec !== active) return;
      let final = "";
      let interim = "";
      const results = event?.results || [];
      for (let i = 0; i < results.length; i += 1) {
        const text = results[i]?.[0]?.transcript || "";
        if (results[i]?.isFinal) final += text;
        else interim += text;
      }
      session.final = final.replace(/\s+/g, " ").trim();
      session.interim = interim.replace(/\s+/g, " ").trim();
      emit({ phase: "listening", interim: [session.final, session.interim].filter(Boolean).join(" ") });
    };
    rec.onerror = (event) => {
      if (rec !== active) return;
      const message = voiceErrorMessage(event?.error);
      if (message === null) session.aborted = true;
      else session.error = message;
    };
    rec.onend = () => finish(rec);
    emit({ phase: "listening" });
    try {
      rec.start();
    } catch {
      detach(rec);
      active = null;
      session = null;
      emit({ phase: "error", message: VOICE_FALLBACK_ERROR });
      return false;
    }
    return true;
  }

  /** Ask the live recognition to stop; its final result (if any) still arrives. */
  function stop() {
    if (!active) return;
    session.stopped = true;
    try {
      active.stop();
    } catch {
      cancel();
    }
  }

  /** Mic button: start when idle, stop while listening. */
  function toggle() {
    if (active) stop();
    else start();
  }

  /** Abort the live recognition, detach its handlers, and go back to idle. */
  function cancel() {
    const rec = active;
    if (!rec) return;
    detach(rec);
    active = null;
    session = null;
    try {
      rec.abort();
    } catch {
      // Already ended; nothing to abort.
    }
    emit({ phase: "idle" });
  }

  /** Clear a finished state (transcript, stopped, error) back to idle. */
  function reset() {
    if (active || !supported) return;
    if (view.phase !== "idle") emit({ phase: "idle" });
  }

  /** Abort and stop reporting. Safe to call twice. */
  function destroy() {
    if (active) {
      const rec = active;
      detach(rec);
      active = null;
      session = null;
      try {
        rec.abort();
      } catch {
        // Already ended.
      }
    }
    destroyed = true;
  }

  return {
    supported,
    start,
    stop,
    toggle,
    cancel,
    reset,
    destroy,
    get listening() {
      return active !== null;
    },
    get view() {
      return view;
    },
  };
}
