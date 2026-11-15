// Questions feature: typed questions or automatic questions while the mic is on.
//
// Mount contract
// --------------
//   export function mountQuestions(ctx, options?) -> cleanup()
//
//   ctx      the shell's frozen feature context:
//            { roots, subscribe(cb) -> unsubscribe, request(path, {method, body, signal}), announce(text, {key}) }
//            Renders only into ctx.roots.questions (a <section aria-label="Ask a question">
//            the shell creates). Touches no other DOM; screen-reader output goes
//            through ctx.announce only. If the root is missing it mounts nothing.
//   options  { Recognition }  SpeechRecognition constructor to use. Defaults to
//            window.SpeechRecognition || window.webkitSpeechRecognition; pass null
//            to force the unsupported state. Tests inject a fake here.
//            { setTimer, clearTimer } optional timer injection for tests.
//   returns  cleanup(): aborts any recognition, stops polling, ignores late
//            answers, unsubscribes and empties the root. Safe to call twice.
//   styles   /static/features/questions/questions.css (scoped under .questions-panel)
//
// Backend: POST /api/question {text}, GET /api/question/{id}; pushed records in
// state.questions.recent; availability in state.capabilities.questions.
// Engine audio speaks answers; this page never uses browser text-to-speech.

import { errorMessageFrom } from "../../core/api-client.js";
import { createQuestionController } from "./controller.js";
import { announcementFor, announcementKey, isFinal, selectAvailability, selectConnectionNote, selectRecent } from "./model.js";
import { createQuestionsPanel } from "./panel.js";
import { createVoiceInput, defaultRecognition } from "./voice.js";
import { createPlaybackPause } from "./playback.js";

/** Mount the questions panel into ctx.roots.questions; returns a cleanup function. */
export function mountQuestions(ctx, options = {}) {
  const root = ctx?.roots?.questions;
  if (!root) return () => {};
  const win = root.ownerDocument?.defaultView || globalThis;
  const Recognition = "Recognition" in options ? options.Recognition : defaultRecognition(win);
  const announce = typeof ctx.announce === "function" ? ctx.announce : () => {};
  const timers = {
    setTimer: options.setTimer || ((fn, ms) => win.setTimeout(fn, ms)),
    clearTimer: options.clearTimer || ((id) => win.clearTimeout(id)),
  };

  let snapshot = { state: null, connection: "connecting", receivedAt: null };
  let disposed = false;

  const panel = createQuestionsPanel(root, {
    onAsk: (text) => ask(text),
    onMic: () => { if (voice.enabled || selectAvailability(snapshot.state).canAsk) voice.toggle(); },
  });

  const controller = createQuestionController({
    request: (path, requestOptions) => ctx.request(path, requestOptions),
    detailOf: errorMessageFrom,
    ...timers,
    onChange(view) {
      if (isFinal(view.record) && view.record.question_id === controller.trackedId && view.phase !== "error") {
        announce(announcementFor(view.record), { key: announcementKey(view.record) });
      }
      playback.update(view, snapshot.state, snapshot.connection);
      render();
    },
  });

  const voice = createVoiceInput({
    Recognition,
    ...timers,
    onChange: () => render(),
    onTranscript: (text) => {
      panel.fillInput(text, { focus: false });
      ask(text);
    },
  });

  const playback = createPlaybackPause({ ...timers, onChange: (paused) => voice.setPaused(paused) });

  function ask(text) {
    if (!selectAvailability(snapshot.state).canAsk) return;
    if (["submitting", "looking_up"].includes(controller.view.phase)) return;
    controller.ask(text);
  }

  function onKeydown(event) {
    if (event.key === "Escape" && voice.enabled) {
      event.preventDefault();
      voice.cancel();
    }
  }
  root.addEventListener("keydown", onKeydown);
  const onPageHide = () => voice.stop();
  win.addEventListener?.("pagehide", onPageHide);

  function render() {
    if (disposed) return;
    panel.update({
      ask: controller.view,
      voice: voice.view,
      availability: selectAvailability(snapshot.state),
      connectionNote: selectConnectionNote(snapshot.connection),
      recent: selectRecent(snapshot.state),
    });
  }

  const unsubscribe = ctx.subscribe((next) => {
    snapshot = next || snapshot;
    controller.receiveState(snapshot.state);
    playback.update(controller.view, snapshot.state, snapshot.connection);
    if (!selectAvailability(snapshot.state).canAsk && voice.enabled) voice.stop();
    render();
  });
  render();

  return function cleanup() {
    if (disposed) return;
    disposed = true;
    root.removeEventListener("keydown", onKeydown);
    win.removeEventListener?.("pagehide", onPageHide);
    playback.destroy();
    voice.destroy();
    controller.dispose();
    if (typeof unsubscribe === "function") unsubscribe();
    panel.destroy();
  };
}
