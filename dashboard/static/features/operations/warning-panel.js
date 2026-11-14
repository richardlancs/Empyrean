// Warning panel: a small neutral line when nothing is active, a prominent card for an active
// real warning, a clearly purple simulated card, and compact "Previous warning" rows.
// Receives a model from the operations controller; never decides whether a hazard exists.

import { createTimeToggle, el, icon, uid } from "./dom.js";

function detailsDisclosure(rows) {
  if (!rows.length) return null;
  const list = el("dl", { className: "operations-facts" });
  for (const row of rows) {
    list.append(el("dt", { text: row.label }));
    const dd = el("dd", { text: row.value });
    if (row.note) dd.append(el("span", { className: "operations-facts-note", text: row.note }));
    list.append(dd);
  }
  return el("details", {
    className: "operations-disclosure",
    children: [el("summary", { className: "operations-disclosure-summary", text: "Source and confidence" }), list],
  });
}

function buildCard(card) {
  const time = createTimeToggle();
  const titleId = uid("warning-title");
  const badge =
    card.tone === "sim"
      ? el("span", { className: "operations-badge operations-badge-sim", children: [icon("flask"), el("span", { text: "Simulated" })] })
      : el("span", { className: "operations-badge operations-badge-real", text: "Active warning" });
  const node = el("article", {
    className: `operations-warning-card operations-warning-${card.tone}`,
    attrs: { "aria-labelledby": titleId },
    children: [
      el("div", { className: "operations-warning-icon", children: [icon(card.icon, "operations-icon-lg")] }),
      el("div", {
        className: "operations-warning-body",
        children: [
          badge,
          el("h3", { className: "operations-warning-title", text: card.title, attrs: { id: titleId } }),
          el("p", { className: "operations-warning-desc", text: card.description }),
          card.note ? el("p", { className: "operations-warning-note", text: card.note }) : null,
          el("p", { className: "operations-warning-meta", children: [el("span", { text: "Reported " }), time.node] }),
          detailsDisclosure(card.details),
        ],
      }),
    ],
  });
  return { node, time };
}

function buildRow(row) {
  const time = createTimeToggle();
  const node = el("li", {
    className: `operations-previous-row operations-previous-${row.tone}`,
    children: [
      icon(row.icon),
      el("span", { className: "operations-previous-label", text: row.label }),
      el("span", { className: "operations-previous-title", text: row.title }),
      row.tone === "sim" ? el("span", { className: "operations-badge operations-badge-sim operations-badge-sm", text: "Simulated" }) : null,
      time.node,
    ],
  });
  return { node, time };
}

/** Build the warning panel inside root; returns { update(model), destroy() }. */
export function createWarningPanel(root) {
  const headingId = uid("warning-heading");
  const heading = el("h2", { className: "operations-heading", text: "Warnings", attrs: { id: headingId } });
  const empty = el("p", {
    className: "operations-warning-empty",
    children: [
      icon("neutral"),
      el("span", { text: "No recent warnings." }),
      el("span", { className: "operations-muted", text: " This does not mean the path is clear." }),
    ],
  });
  const cards = el("div", { className: "operations-warning-cards" });
  const previous = el("ul", { className: "operations-previous", attrs: { "aria-label": "Previous warnings" } });
  const section = el("section", {
    className: "operations-warning",
    attrs: { "aria-labelledby": headingId },
    children: [heading, empty, cards, previous],
  });
  root.replaceChildren(section);

  const cardNodes = new Map();
  const rowNodes = new Map();

  function reconcile(container, store, items, build) {
    const wanted = new Set(items.map((i) => i.key));
    for (const [key, entry] of store) {
      if (!wanted.has(key)) {
        entry.node.remove();
        store.delete(key);
      }
    }
    let anchor = null;
    for (const item of items) {
      let entry = store.get(item.key);
      if (!entry) {
        entry = build(item);
        store.set(item.key, entry);
      }
      entry.time.update(item.time.relative, item.time.exact);
      entry.node.classList.toggle("operations-warning-compact", Boolean(item.compact));
      const expected = anchor ? anchor.nextSibling : container.firstChild;
      if (expected !== entry.node) container.insertBefore(entry.node, expected);
      anchor = entry.node;
    }
  }

  return {
    update(model) {
      const active = model.cards;
      reconcile(cards, cardNodes, active, buildCard);
      reconcile(previous, rowNodes, model.previous, buildRow);
      empty.hidden = active.length > 0;
      previous.hidden = model.previous.length === 0;
      section.dataset.state = active.some((c) => c.tone === "real") ? "real" : active.length ? "sim" : "idle";
    },
    destroy() {
      root.replaceChildren();
    },
  };
}
