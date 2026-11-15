// Compact question and response view. The server remains the answer authority.
import { MAX_QUESTION_CHARS, describeRecord, recentSummary } from "./model.js";
import { PRIVACY_NOTE, voiceStatusText } from "./voice.js";
import { el, setAttr, setHidden, setText, uniqueId } from "./dom.js";

/** Build the question controls and optional history disclosure. */
export function createQuestionsPanel(root, { onAsk, onMic }) {
  const doc = root.ownerDocument;
  const inputId = uniqueId("question");
  const privacyId = uniqueId("voice-privacy");
  const input = el(doc, "input", {
    id: inputId, class: "questions-input", type: "text", name: "question",
    maxlength: String(MAX_QUESTION_CHARS), autocomplete: "off", enterkeyhint: "send",
    placeholder: "What am I touching?",
  });
  const askButton = el(doc, "button", { type: "submit", class: "questions-button questions-button-primary", text: "Ask" });
  const form = el(doc, "form", { class: "questions-form" },
    el(doc, "label", { for: inputId, class: "questions-label", text: "Ask a question" }),
    el(doc, "div", { class: "questions-row" }, input, askButton));
  form.addEventListener("submit", (event) => { event.preventDefault(); onAsk(input.value); });

  const micLabel = el(doc, "span", { text: "Turn mic on" });
  const icon = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({ viewBox: "0 0 24 24", width: "20", height: "20", "aria-hidden": "true" })) icon.setAttribute(key, value);
  const path = doc.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M12 15a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v7a3 3 0 0 0 3 3Zm-7-4v1a7 7 0 0 0 6 6.93V21H8v2h8v-2h-3v-2.07A7 7 0 0 0 19 12v-1h-2v1a5 5 0 0 1-10 0v-1Z");
  path.setAttribute("fill", "currentColor");
  icon.append(path);
  const micButton = el(doc, "button", {
    type: "button", class: "questions-button questions-mic", "aria-pressed": "false", "aria-describedby": privacyId,
  }, icon, micLabel);
  micButton.addEventListener("click", onMic);
  const voiceStatus = el(doc, "p", { class: "questions-voice-status", role: "status" });
  const interim = el(doc, "p", { class: "questions-interim", hidden: true });
  const privacy = el(doc, "p", { id: privacyId, class: "questions-muted", text: PRIVACY_NOTE });
  const voice = el(doc, "div", { class: "questions-voice" },
    el(doc, "div", { class: "questions-row" }, micButton, voiceStatus), interim, privacy);

  const status = el(doc, "p", { class: "questions-status", role: "status", hidden: true });
  const askedText = el(doc, "p", { class: "questions-asked-text" });
  const resultBody = el(doc, "p", { class: "questions-result-body" });
  const resultDetail = el(doc, "p", { class: "questions-result-detail", hidden: true });
  const result = el(doc, "div", { class: "questions-result", hidden: true },
    el(doc, "p", { class: "questions-asked-label", text: "Your question" }), askedText,
    el(doc, "p", { class: "questions-asked-label", text: "Response" }), resultBody, resultDetail);
  const recentList = el(doc, "ol", { class: "questions-recent-list" });
  const recentSummaryText = el(doc, "span", { text: "History" });
  const recent = el(doc, "details", { class: "questions-recent", hidden: true },
    el(doc, "summary", {}, recentSummaryText), recentList);
  const unavailableNote = el(doc, "p", { class: "questions-notice", hidden: true });
  const connectionNote = el(doc, "p", { class: "questions-notice", hidden: true });
  const panel = el(doc, "div", { class: "questions-panel" }, unavailableNote, connectionNote,
    form, voice, status, result, recent);
  root.replaceChildren(panel);
  let recentKey = "";

  function update(view) {
    // Show the most recent shared answer after refresh, until this page asks one.
    const ask = view.ask.phase === "idle" && view.recent[0]
      ? { phase: view.recent[0].status, text: view.recent[0].text, record: view.recent[0] }
      : view.ask;
    const busy = ["submitting", "looking_up"].includes(view.ask.phase);
    input.readOnly = busy;
    askButton.disabled = busy || !view.availability.canAsk;
    panel.dataset.phase = ask.phase;
    setText(unavailableNote, view.availability.reason);
    setHidden(unavailableNote, view.availability.canAsk);
    setText(connectionNote, view.connectionNote);
    setHidden(connectionNote, !view.connectionNote);
    micButton.disabled = view.voice.phase === "unsupported" || (!view.voice.enabled && !view.availability.canAsk);
    setAttr(micButton, "aria-pressed", view.voice.enabled ? "true" : "false");
    setText(micLabel, view.voice.enabled ? "Turn mic off" : "Turn mic on");
    setText(voiceStatus, voiceStatusText(view.voice));
    voiceStatus.dataset.phase = view.voice.phase;
    setText(interim, view.voice.interim ? `Parsing: ${view.voice.interim}` : "");
    setHidden(interim, !view.voice.interim);
    setHidden(privacy, view.voice.phase === "unsupported");
    const pending = ["submitting", "looking_up"].includes(ask.phase);
    setText(status, pending ? "Parsing your question…" : "");
    setHidden(status, !pending);
    setHidden(result, !ask.text && !ask.message);
    setText(askedText, ask.text || "");
    const described = describeRecord(ask.record);
    result.dataset.tone = ask.phase === "error" ? "error" : described?.tone || "pending";
    setAttr(result, "aria-busy", pending ? "true" : "false");
    setText(resultBody, ask.phase === "error" ? ask.message
      : pending ? "Waiting for a response…" : [described?.title, described?.body].filter(Boolean).join(" "));
    setText(resultDetail, described?.detail || "");
    setHidden(resultDetail, !described?.detail);
    const key = JSON.stringify(view.recent);
    if (key !== recentKey) {
      recentKey = key;
      recentList.replaceChildren(...view.recent.map((record) => el(doc, "li", { class: "questions-recent-item" },
        el(doc, "span", { class: "questions-recent-q", text: record.text }),
        el(doc, "span", { class: "questions-recent-a", text: recentSummary(record) }))));
    }
    setText(recentSummaryText, `History (${view.recent.length})`);
    setHidden(recent, !view.recent.length);
  }

  return {
    update,
    fillInput(text, { focus = false } = {}) { input.value = text; if (focus) input.focus(); },
    get value() { return input.value; },
    destroy() { root.replaceChildren(); },
  };
}
