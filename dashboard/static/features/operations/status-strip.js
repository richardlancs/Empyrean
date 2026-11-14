// Compact system status: dashboard connection kept separate from engine module status,
// with plain-language details in a disclosure. Receives a model from selectHealth().

import { el, icon, setIcon, setText, uid } from "./dom.js";

const TONE_ICON = { ok: "ok", caution: "caution", error: "error", unknown: "unknown", neutral: "neutral" };

/** Build the status strip inside root; returns { update(model), destroy() }. */
export function createStatusStrip(root) {
  const headingId = uid("status-heading");
  // Friendly clarity: one compact line (connection, mode, summary); everything else is in
  // "System details". The heading stays for screen-reader navigation but is not drawn.
  const heading = el("h2", { className: "operations-heading operations-sr-only", text: "System status", attrs: { id: headingId } });
  const mode = el("span", { className: "operations-mode", text: "Fake inputs", attrs: { hidden: "" } });

  const connection = el("p", { className: "operations-connection" });
  const connectionText = el("span", { className: "operations-connection-text" });
  connection.append(icon("neutral"), connectionText);

  const chips = el("ul", { className: "operations-chips", attrs: { "aria-label": "Engine modules" } });
  const chipNodes = new Map();

  const summary = el("p", { className: "operations-status-summary" });

  const details = el("details", { className: "operations-disclosure operations-status-details" });
  const detailsSummary = el("summary", { className: "operations-disclosure-summary", text: "System details" });
  const list = el("dl", { className: "operations-status-list" });
  const connDetail = el("p", { className: "operations-status-note" });
  const caveat = el("p", {
    className: "operations-status-note",
    text: "A working connection only means this page is receiving updates. It does not show that the wearer heard anything.",
  });
  details.append(detailsSummary, connDetail, chips, list, caveat);
  const detailNodes = new Map();

  const line = el("div", { className: "operations-status-line", children: [connection, mode, summary, details] });
  const section = el("section", {
    className: "operations-status",
    attrs: { "aria-labelledby": headingId },
    children: [heading, line],
  });
  root.replaceChildren(section);

  function chip(m) {
    let node = chipNodes.get(m.id);
    if (!node) {
      const label = el("span", { className: "operations-chip-label", text: m.label });
      const status = el("span", { className: "operations-chip-status" });
      const li = el("li", { className: "operations-chip", children: [icon("unknown"), label, status] });
      node = { li, status, tone: null };
      chipNodes.set(m.id, node);
      chips.append(li);
    }
    if (node.tone !== m.tone) {
      node.li.dataset.tone = m.tone;
      setIcon(node.li, TONE_ICON[m.tone] || "unknown", "operations-icon");
      node.tone = m.tone;
    }
    setText(node.status, m.statusLabel);
  }

  function detailRow(m) {
    let node = detailNodes.get(m.id);
    if (!node) {
      const dt = el("dt", { className: "operations-status-term", text: m.label });
      const status = el("span", { className: "operations-status-value" });
      const detail = el("span", { className: "operations-status-detail" });
      const facts = el("span", { className: "operations-status-facts" });
      const dd = el("dd", { className: "operations-status-def", children: [status, detail, facts] });
      node = { dt, dd, status, detail, facts };
      detailNodes.set(m.id, node);
      list.append(dt, dd);
    }
    node.dd.dataset.tone = m.tone;
    setText(node.status, m.statusLabel);
    setText(node.detail, m.detail);
    setText(node.facts, m.facts.map((f) => `${f.label}: ${f.value}`).join(" · "));
  }

  let lastConnTone = null;
  return {
    update(model) {
      connection.dataset.tone = model.connection.tone;
      if (lastConnTone !== model.connection.tone) {
        setIcon(connection, TONE_ICON[model.connection.tone], "operations-icon");
        lastConnTone = model.connection.tone;
      }
      setText(connectionText, model.connection.label);
      setText(connDetail, model.connection.detail);
      for (const m of model.modules) {
        chip(m);
        detailRow(m);
      }
      if (model.detector) detailRow({ id: "detector", ...model.detector });
      setText(summary, model.summary);
      section.dataset.attention = String(model.attention);
      const demo = model.modules.some((m) => m.fake);
      if (demo) mode.removeAttribute("hidden");
      else mode.setAttribute("hidden", "");
    },
    destroy() {
      root.replaceChildren();
    },
  };
}
