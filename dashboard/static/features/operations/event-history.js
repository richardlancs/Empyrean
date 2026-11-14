// Recent activity: filters, pause, clear-this-view, grouped repeats with occurrence times.
// Receives a model and callbacks; every control here changes this browser view only.

import { createTimeToggle, el, icon, preservingFocus, setText, uid } from "./dom.js";

function buildFacts(rows) {
  const list = el("dl", { className: "operations-facts" });
  for (const row of rows) {
    list.append(el("dt", { text: row.label }));
    const dd = el("dd", { text: row.value });
    if (row.note) dd.append(el("span", { className: "operations-facts-note", text: row.note }));
    list.append(dd);
  }
  return list;
}

function buildGroup(group) {
  const time = createTimeToggle();
  const kind = el("span", { className: `operations-kind operations-kind-${group.tone}` });
  kind.append(icon(group.icon), el("span", { text: group.kindLabel }));
  const title = el("span", { className: "operations-event-title", text: group.title });
  const count = el("span", { className: "operations-count" });
  const head = el("div", { className: "operations-event-head", children: [kind, title, count, time.node] });
  const description = el("p", { className: "operations-event-desc" });

  const occurrences = el("details", { className: "operations-disclosure operations-occurrences" });
  const occSummary = el("summary", { className: "operations-disclosure-summary" });
  const occList = el("ol", { className: "operations-occurrence-list" });
  occurrences.append(occSummary, occList);

  const facts = el("details", { className: "operations-disclosure" });
  facts.append(el("summary", { className: "operations-disclosure-summary", text: "Source and confidence" }));
  let factsKey = "";

  const li = el("li", {
    className: `operations-event operations-event-${group.tone}`,
    children: [head, description, occurrences, facts],
  });
  return {
    node: li,
    update(g) {
      time.update(g.time.relative, g.time.exact);
      setText(description, g.description || "");
      description.hidden = !g.description;
      setText(count, g.count > 1 ? `× ${g.count}` : "");
      count.hidden = g.count <= 1;
      if (g.count > 1) count.setAttribute("aria-label", `${g.count} times`);
      occurrences.hidden = g.count <= 1;
      setText(occSummary, `Show all ${g.count} times`);
      const occText = g.occurrences.map((o) => `${o.exact} (${o.relative})`);
      if (occList.dataset.sig !== occText.join("\n")) {
        occList.replaceChildren(...occText.map((t) => el("li", { text: t })));
        occList.dataset.sig = occText.join("\n");
      }
      const sig = JSON.stringify(g.details);
      if (sig !== factsKey) {
        facts.querySelector("dl")?.remove();
        if (g.details.length) facts.append(buildFacts(g.details));
        factsKey = sig;
      }
      facts.hidden = g.details.length === 0;
    },
  };
}

/** Build the activity panel inside root; returns { update(model), destroy() }. */
export function createEventHistory(root, { onFilter, onTogglePause, onClear, onRestore }) {
  const headingId = uid("events-heading");
  const heading = el("h2", { className: "operations-heading", text: "Recent activity", attrs: { id: headingId } });

  const filterGroup = el("div", { className: "operations-filters", attrs: { role: "group", "aria-label": "Show activity" } });
  const filterButtons = new Map();
  for (const f of [
    { id: "all", label: "All" },
    { id: "touch", label: "Touch" },
    { id: "hazard", label: "Warning" },
  ]) {
    const b = el("button", {
      className: "operations-filter",
      text: f.label,
      attrs: { type: "button", "aria-pressed": "false", "data-focus-key": `filter-${f.id}` },
    });
    b.addEventListener("click", () => onFilter(f.id));
    filterButtons.set(f.id, b);
    filterGroup.append(b);
  }

  const pauseButton = el("button", {
    className: "operations-button operations-button-quiet",
    attrs: { type: "button", "aria-pressed": "false", "data-focus-key": "pause" },
  });
  pauseButton.addEventListener("click", () => onTogglePause());
  const clearButton = el("button", {
    className: "operations-button operations-button-quiet",
    text: "Clear this view",
    attrs: { type: "button", "data-focus-key": "clear" },
  });
  clearButton.addEventListener("click", () => {
    if (clearButton.getAttribute("aria-disabled") !== "true") onClear();
  });
  const actions = el("div", { className: "operations-history-actions", children: [pauseButton, clearButton] });
  const toolbar = el("div", { className: "operations-toolbar", children: [filterGroup, actions] });

  const pausedNotice = el("p", { className: "operations-notice operations-notice-paused" });
  const pausedText = el("span");
  const resumeButton = el("button", {
    className: "operations-button operations-button-inline",
    text: "Resume",
    attrs: { type: "button", "data-focus-key": "resume" },
  });
  resumeButton.addEventListener("click", () => {
    onTogglePause();
    pauseButton.focus(); // the notice holding this button is about to hide
  });
  pausedNotice.append(icon("neutral"), pausedText, resumeButton);

  const clearedNotice = el("p", { className: "operations-notice" });
  const clearedText = el("span");
  const restoreButton = el("button", {
    className: "operations-button operations-button-inline",
    text: "Show cleared activity",
    attrs: { type: "button", "data-focus-key": "restore" },
  });
  restoreButton.addEventListener("click", () => {
    onRestore();
    clearButton.focus(); // the notice holding this button is about to hide
  });
  clearedNotice.append(icon("info"), clearedText, restoreButton);

  const scope = el("p", {
    className: "operations-muted operations-scope",
    text: "Pause and clear change only this view; detection, alarms and saved history keep running.",
  });

  const emptyText = el("p", { className: "operations-empty-text" });
  // Friendly clarity: a small seated Pip beside the empty-history sentence (decorative).
  const emptyArt = el("img", {
    className: "pip pip-sit operations-empty-art",
    attrs: { src: "/static/assets/pip/pip-sit.png", alt: "", "aria-hidden": "true", width: "68", height: "64" },
  });
  const empty = el("div", { className: "operations-empty", children: [emptyArt, emptyText] });
  const listId = uid("events-list");
  const list = el("ol", { className: "operations-events", attrs: { id: listId, "aria-labelledby": headingId } });

  const section = el("section", {
    className: "operations-history",
    attrs: { "aria-labelledby": headingId },
    children: [heading, toolbar, scope, pausedNotice, clearedNotice, empty, list],
  });
  root.replaceChildren(section);

  const groupNodes = new Map();

  function reconcile(groups) {
    const wanted = new Set(groups.map((g) => g.key));
    for (const [key, entry] of groupNodes) {
      if (!wanted.has(key)) {
        entry.node.remove();
        groupNodes.delete(key);
      }
    }
    let anchor = null;
    for (const g of groups) {
      let entry = groupNodes.get(g.key);
      if (!entry) {
        entry = buildGroup(g);
        groupNodes.set(g.key, entry);
      }
      entry.update(g);
      const expected = anchor ? anchor.nextSibling : list.firstChild;
      if (expected !== entry.node) list.insertBefore(entry.node, expected);
      anchor = entry.node;
    }
  }

  return {
    update(model) {
      preservingFocus(section, () => {
        for (const [id, b] of filterButtons) b.setAttribute("aria-pressed", String(model.filter === id));
        setText(pauseButton, model.paused ? "Resume activity view" : "Pause activity view");
        pauseButton.setAttribute("aria-pressed", String(model.paused));
        pausedNotice.hidden = !model.paused;
        setText(pausedText, model.pendingText);
        clearedNotice.hidden = !model.cleared;
        setText(clearedText, model.clearedText);
        // aria-disabled rather than disabled, so a focused button keeps focus when it greys out.
        clearButton.setAttribute("aria-disabled", String(!model.canClear));
        reconcile(model.groups);
        empty.hidden = model.groups.length > 0;
        setText(emptyText, model.emptyText);
        list.hidden = model.groups.length === 0;
      });
    },
    destroy() {
      root.replaceChildren();
    },
  };
}
