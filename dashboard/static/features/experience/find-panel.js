// "Find a previously touched item" form. Leaf view: reports submit/retry
// through callbacks and renders the controller's view model.

import { MAX_QUERY_CHARS } from "./last-seen.js";
import { clockTime, humanAgo } from "./selectors.js";
import { el, setHidden, setText, uniqueId } from "./dom.js";

const STATUS_TITLES = {
  loading: "Searching touch history…",
  found: "Found in touch history",
  not_found: "No recorded touch matches",
  unavailable: "Touch history unavailable",
  timeout: "Search timed out",
  error: "Search failed",
};

/** Callbacks: onSearch(query), onRetry(). */
export function createFindPanel(root, { onSearch, onRetry }) {
  const headingId = uniqueId("experience-find-heading");
  const inputId = uniqueId("experience-find-input");
  const helpId = uniqueId("experience-find-help");
  const input = el("input", {
    id: inputId,
    type: "search",
    class: "experience-input",
    maxlength: String(MAX_QUERY_CHARS),
    autocomplete: "off",
    placeholder: "For example: ketchup",
    "aria-describedby": helpId,
  });
  // The label sits in its own span so the hover nudge (21st.dev "sliding") moves only the text.
  const submit = el(
    "button",
    { type: "submit", class: "experience-button experience-button-primary" },
    el("span", { class: "experience-button-label", text: "Search" }),
  );
  const form = el(
    "form",
    { class: "experience-find-form", role: "search" },
    el("label", { for: inputId, class: "experience-label", text: "What are you looking for?" }),
    el("div", { class: "experience-find-row" }, input, submit),
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onSearch(input.value);
  });

  const help = el("p", {
    id: helpId,
    class: "experience-muted",
    text: "Searches what the wearer has touched. The answer may also be spoken.",
  });
  const disabledNote = el("p", { class: "experience-notice" });

  const resultTitle = el("p", { class: "experience-find-title" });
  const resultAnswer = el("p", { class: "experience-find-answer" });
  const resultMeta = el("p", { class: "experience-muted" });
  const resultNeighbours = el("p", { class: "experience-muted" });
  const resultCaveat = el("p", {
    class: "experience-muted",
    text: "This is when it was last touched, not a guarantee it is still there.",
  });
  const retry = el("button", { type: "button", class: "experience-button", text: "Try again" });
  retry.addEventListener("click", () => onRetry());
  const result = el("div", { class: "experience-find-result", role: "status" }, resultTitle, resultAnswer, resultMeta, resultNeighbours, resultCaveat, retry);

  const card = el(
    "section",
    { class: "experience-card experience-find", "aria-labelledby": headingId },
    el("h2", { id: headingId, class: "experience-heading", text: "Find a previously touched item" }),
    help,
    disabledNote,
    form,
    result,
  );
  root.replaceChildren(card);

  /** availability: {enabled, reason}; view: last-seen controller view; now: server seconds. */
  function update(availability, view, now) {
    const busy = view.status === "loading";
    input.disabled = !availability.enabled;
    submit.disabled = !availability.enabled || busy;
    submit.toggleAttribute("data-loading", busy);
    card.setAttribute("aria-busy", busy ? "true" : "false");
    setText(disabledNote, availability.enabled ? "" : availability.reason);
    setHidden(disabledNote, availability.enabled);

    card.dataset.status = view.status;
    const showResult = view.status !== "idle" || Boolean(view.message);
    setHidden(result, !showResult);
    setText(resultTitle, view.status === "idle" ? view.message : STATUS_TITLES[view.status] || "");
    const answer =
      view.status === "found" || view.status === "not_found"
        ? view.answer || (view.status === "not_found" ? `Nothing matching “${view.query}” has been touched.` : "")
        : view.status === "idle"
          ? ""
          : view.message;
    setText(resultAnswer, answer);
    setHidden(resultAnswer, !answer);
    const meta =
      view.status === "found" && typeof view.matchedAt === "number"
        ? `Recorded at ${clockTime(view.matchedAt)} · ${humanAgo(typeof now === "number" ? Math.max(0, now - view.matchedAt) : null)}`
        : view.status === "loading"
          ? `Looking for “${view.query}”.`
          : "";
    setText(resultMeta, meta);
    setHidden(resultMeta, !meta);
    // Integration (Agent 4): the recorded neighbours, as data, never an invented place.
    const near = view.status === "found" && Array.isArray(view.neighbours) ? view.neighbours : [];
    const nearText = near.length ? `Recorded next to: ${near.join(", ")}.` : "";
    setText(resultNeighbours, nearText);
    setHidden(resultNeighbours, !nearText);
    setHidden(resultCaveat, view.status !== "found");
    setHidden(retry, !["timeout", "error", "unavailable"].includes(view.status) || !availability.enabled);
  }

  return {
    update,
    destroy() {
      root.replaceChildren();
    },
  };
}
