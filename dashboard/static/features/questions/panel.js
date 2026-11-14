// Questions panel view. Leaf component: renders the view the controller gives
// it and reports user intent through callbacks. Holds no question state.

import { EXAMPLE_QUESTIONS, MAX_QUESTION_CHARS, askStatusText, describeRecord, recentSummary } from "./model.js";
import { PRIVACY_NOTE, voiceStatusText } from "./voice.js";
import { el, setAttr, setHidden, setText, uniqueId } from "./dom.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const MIC_PATH =
  "M12 15a3.5 3.5 0 0 0 3.5-3.5v-6a3.5 3.5 0 1 0-7 0v6A3.5 3.5 0 0 0 12 15Zm6-3.5a1 1 0 1 0-2 0 4 4 0 0 1-8 0 1 1 0 1 0-2 0 6 6 0 0 0 5 5.91V20H8.5a1 1 0 1 0 0 2h7a1 1 0 1 0 0-2H13v-2.59a6 6 0 0 0 5-5.91Z";

/** Decorative microphone icon, built without parsing HTML. */
function micIcon(doc) {
  const svg = doc.createElementNS(SVG_NS, "svg");
  for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: "20", height: "20", "aria-hidden": "true", focusable: "false" })) {
    svg.setAttribute(k, v);
  }
  const path = doc.createElementNS(SVG_NS, "path");
  path.setAttribute("fill", "currentColor");
  path.setAttribute("d", MIC_PATH);
  svg.append(path);
  return svg;
}

function clock(seconds) {
  if (typeof seconds !== "number") return "";
  try {
    return new Date(seconds * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

/**
 * Render the panel into root.
 * Callbacks: onAsk(text), onExample(text), onMic(), onCancelVoice(), onInput().
 */
export function createQuestionsPanel(root, { onAsk, onExample, onMic, onCancelVoice, onInput }) {
  const doc = root.ownerDocument;
  const ids = {
    heading: uniqueId("questions-heading"),
    input: uniqueId("questions-input"),
    hint: uniqueId("questions-hint"),
    privacy: uniqueId("questions-privacy"),
    examples: uniqueId("questions-examples"),
    answer: uniqueId("questions-answer"),
  };

  const input = el(doc, "input", {
    id: ids.input,
    type: "text",
    class: "questions-input",
    name: "question",
    maxlength: String(MAX_QUESTION_CHARS),
    autocomplete: "off",
    spellcheck: "true",
    enterkeyhint: "send",
    placeholder: "For example: What am I touching?",
    "aria-describedby": ids.hint,
  });
  input.addEventListener("input", () => onInput?.());
  const askButton = el(doc, "button", { type: "submit", class: "questions-button questions-button-primary", text: "Ask" });
  const form = el(
    doc,
    "form",
    { class: "questions-form", novalidate: true },
    el(doc, "label", { for: ids.input, class: "questions-label", text: "Your question" }),
    el(doc, "div", { class: "questions-row" }, input, askButton),
    el(doc, "p", { id: ids.hint, class: "questions-muted", text: "Type a question and press Enter or Ask." }),
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onAsk(input.value);
  });

  const micButton = el(doc, "button", {
    type: "button",
    class: "questions-button questions-mic",
    "aria-pressed": "false",
    "aria-describedby": ids.privacy,
  });
  micButton.append(micIcon(doc), el(doc, "span", { text: "Speak a question" }));
  micButton.addEventListener("click", () => onMic());
  const cancelButton = el(doc, "button", { type: "button", class: "questions-button", text: "Cancel", hidden: true });
  cancelButton.addEventListener("click", () => onCancelVoice());
  const voiceStatus = el(doc, "p", { class: "questions-voice-status", role: "status" });
  const interim = el(doc, "p", { class: "questions-interim", "aria-live": "off", hidden: true });
  const privacy = el(doc, "p", { id: ids.privacy, class: "questions-muted", text: PRIVACY_NOTE });
  const voice = el(
    doc,
    "div",
    { class: "questions-voice", role: "group", "aria-label": "Voice input" },
    el(doc, "div", { class: "questions-row" }, micButton, cancelButton),
    voiceStatus,
    interim,
    privacy,
  );

  const exampleButtons = EXAMPLE_QUESTIONS.map((text) => {
    const button = el(doc, "button", { type: "button", class: "questions-button questions-example", text });
    button.addEventListener("click", () => {
      if (button.getAttribute("aria-disabled") === "true") return;
      input.value = text;
      onExample(text);
    });
    return button;
  });
  const examples = el(
    doc,
    "div",
    { class: "questions-examples", role: "group", "aria-labelledby": ids.examples },
    el(doc, "p", { id: ids.examples, class: "questions-label", text: "Examples (each one asks right away)" }),
    el(doc, "ul", { class: "questions-example-list" }, ...exampleButtons.map((b) => el(doc, "li", {}, b))),
  );

  const status = el(doc, "p", { class: "questions-status", role: "status" });
  const askedText = el(doc, "q", { class: "questions-asked-text" });
  const asked = el(doc, "p", { class: "questions-asked" }, el(doc, "span", { class: "questions-asked-label", text: "You asked: " }), askedText);
  const resultLabel = el(doc, "p", { class: "questions-result-label" });
  const resultTitle = el(doc, "p", { class: "questions-result-title" });
  const resultBody = el(doc, "p", { class: "questions-result-body" });
  const resultDetail = el(doc, "p", { class: "questions-result-detail" });
  const resultSpeech = el(doc, "p", { class: "questions-result-speech" });
  const result = el(
    doc,
    "div",
    { class: "questions-result", hidden: true, "aria-busy": "false" },
    asked,
    resultLabel,
    resultTitle,
    resultBody,
    resultDetail,
    resultSpeech,
  );
  const answer = el(
    doc,
    "div",
    { class: "questions-answer" },
    el(doc, "h3", { id: ids.answer, class: "questions-subheading", text: "Answer" }),
    status,
    result,
  );

  const recentList = el(doc, "ol", { class: "questions-recent-list" });
  const recentSummaryText = el(doc, "span");
  const recent = el(
    doc,
    "details",
    { class: "questions-recent", hidden: true },
    el(doc, "summary", {}, recentSummaryText),
    el(doc, "p", { class: "questions-muted", text: "Questions asked from any open dashboard page, newest first." }),
    recentList,
  );

  const unavailableNote = el(doc, "p", { class: "questions-notice", hidden: true });
  const connectionNote = el(doc, "p", { class: "questions-notice", hidden: true });

  const panel = el(
    doc,
    "div",
    { class: "questions-panel", "data-phase": "idle" },
    el(doc, "h2", { id: ids.heading, class: "questions-heading", text: "Ask a question" }),
    el(doc, "p", {
      class: "questions-muted",
      text: "Ask what the camera sees, what you are touching or holding, or where you last touched something. Answers appear here and are also sent to the speaker.",
    }),
    unavailableNote,
    connectionNote,
    form,
    voice,
    examples,
    answer,
    recent,
  );
  root.replaceChildren(panel);

  let recentKey = "";

  /**
   * view: { ask, voice, availability: {canAsk, reason}, connectionNote, recent: record[] }
   */
  function update(view) {
    const { ask, availability } = view;
    const submitting = ask.phase === "submitting";
    panel.dataset.phase = ask.phase;

    setText(unavailableNote, availability.canAsk ? "" : availability.reason);
    setHidden(unavailableNote, availability.canAsk);
    setText(connectionNote, view.connectionNote || "");
    setHidden(connectionNote, !view.connectionNote);

    // The input stays usable; it is only read-only while a question is being sent
    // (read-only keeps keyboard focus where it is, unlike disabled).
    input.readOnly = submitting;
    setAttr(input, "aria-busy", submitting ? "true" : null);
    askButton.disabled = !availability.canAsk;
    setAttr(askButton, "aria-disabled", submitting ? "true" : null);
    for (const button of exampleButtons) {
      button.disabled = !availability.canAsk;
      setAttr(button, "aria-disabled", submitting ? "true" : null);
    }

    // Voice
    const listening = view.voice.phase === "listening";
    micButton.disabled = view.voice.phase === "unsupported";
    setAttr(micButton, "aria-pressed", listening ? "true" : "false");
    setHidden(cancelButton, !listening);
    setText(voiceStatus, voiceStatusText(view.voice));
    voiceStatus.dataset.phase = view.voice.phase;
    setText(interim, listening && view.voice.interim ? `Heard so far: ${view.voice.interim}` : "");
    setHidden(interim, !(listening && view.voice.interim));
    setHidden(privacy, view.voice.phase === "unsupported");

    // Answer for this page's latest question
    setText(status, askStatusText(ask));
    status.dataset.phase = ask.phase;
    const described = describeRecord(ask.record);
    const showResult = Boolean(ask.text) && ask.phase !== "idle";
    setHidden(result, !showResult);
    setText(askedText, ask.text || "");
    let tone = described ? described.tone : ask.phase === "error" ? "error" : "pending";
    if (ask.phase === "error") tone = "error";
    result.dataset.tone = tone;
    const busy = ask.phase === "submitting" || ask.phase === "looking_up";
    result.setAttribute("aria-busy", busy ? "true" : "false");
    const label = ask.phase === "submitting" ? "Asking…" : ask.phase === "error" ? "Not answered" : described?.label || "";
    setText(resultLabel, label);
    setHidden(resultLabel, !label);
    const title = ask.phase === "error" ? ask.message : described?.title || "";
    setText(resultTitle, title);
    setHidden(resultTitle, !title);
    // After "still waiting", the last placeholder is kept but clearly marked.
    const body = ask.phase === "error" && described?.tone === "pending" ? `Last update: ${described.body}` : described?.body || "";
    setText(resultBody, body);
    setHidden(resultBody, !body);
    setText(resultDetail, described?.detail || "");
    setHidden(resultDetail, !described?.detail);
    setText(resultSpeech, described?.speech || "");
    setHidden(resultSpeech, !described?.speech);

    // Recent questions from every page
    const key = view.recent.map((r) => `${r.question_id}:${r.status}`).join("|");
    if (key !== recentKey) {
      recentKey = key;
      recentList.replaceChildren(
        ...view.recent.map((r) =>
          el(
            doc,
            "li",
            { class: "questions-recent-item", "data-status": r.status },
            el(doc, "span", { class: "questions-recent-q", text: r.text || "(no text)" }),
            el(doc, "span", { class: "questions-recent-a", text: recentSummary(r) }),
            r.asked_at ? el(doc, "span", { class: "questions-muted questions-recent-time", text: `Asked at ${clock(r.asked_at)}` }) : null,
          ),
        ),
      );
    }
    setText(recentSummaryText, `Recent questions from all open pages (${view.recent.length})`);
    setHidden(recent, view.recent.length === 0);
  }

  return {
    update,
    /** Put text into the input (voice transcript) and move focus there to check it. */
    fillInput(text, { focus = true } = {}) {
      input.value = text;
      if (focus) {
        input.focus();
        try {
          input.setSelectionRange(text.length, text.length);
        } catch {
          // Some input types do not support selection; harmless.
        }
      }
    },
    get value() {
      return input.value;
    },
    destroy() {
      root.replaceChildren();
    },
  };
}
