// Demo tools: a secondary disclosure holding "Simulate alert", its explanation and its result.
// Receives status from the controller and calls onSimulate(); performs no network calls itself.

import { el, icon, setIcon, setText, uid } from "./dom.js";

export const DEMO_EXPLANATION =
  "Adds a simulated warning to this dashboard only. No alarm sounds and nothing is saved to touch history.";

const STATUS_ICON = { idle: "info", pending: "neutral", success: "ok", http_error: "error", network_error: "error" };

/** Build the demo tools inside root; returns { update(model), destroy() }. */
export function createDemoTools(root, { onSimulate }) {
  const explanationId = uid("demo-explanation");
  const details = el("details", { className: "operations-disclosure operations-demo" });
  const summary = el("summary", { className: "operations-disclosure-summary operations-demo-summary" });
  summary.append(icon("flask"), el("span", { text: "Demo tools" }));
  const explanation = el("p", { className: "operations-demo-explanation", text: DEMO_EXPLANATION, attrs: { id: explanationId } });
  const button = el("button", {
    className: "operations-button operations-button-demo",
    text: "Simulate alert",
    attrs: { type: "button", "aria-describedby": explanationId, "data-focus-key": "simulate" },
  });
  const status = el("p", { className: "operations-demo-status" });
  const statusText = el("span");
  status.append(icon("info"), statusText);
  button.addEventListener("click", () => {
    if (button.getAttribute("aria-disabled") === "true") return;
    onSimulate();
  });
  details.append(summary, explanation, button, status);
  const section = el("section", { className: "operations-demo-section", attrs: { "aria-label": "Demo tools" }, children: [details] });
  root.replaceChildren(section);

  let lastStatus = null;
  return {
    update({ status: s, message }) {
      const pending = s === "pending";
      // aria-disabled keeps focus on the button while the request runs.
      button.setAttribute("aria-disabled", String(pending));
      button.setAttribute("aria-busy", String(pending));
      setText(button, pending ? "Adding simulated warning…" : "Simulate alert");
      status.dataset.status = s;
      status.hidden = s === "idle";
      if (lastStatus !== s) {
        setIcon(status, STATUS_ICON[s] || "info", "operations-icon");
        lastStatus = s;
      }
      setText(statusText, message || "");
    },
    destroy() {
      root.replaceChildren();
    },
  };
}
