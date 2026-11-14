// Recognized objects. Rows are keyed by object_id and reused across snapshots
// so focus, expanded names and thumbnails stay put. Leaf view.

import { el, setHidden, setText, uniqueId } from "./dom.js";

/** Callbacks: onSelect(id|null), onToggleName(id). */
export function createObjectList(root, { onSelect, onToggleName }) {
  const headingId = uniqueId("experience-objects-heading");
  const summary = el("p", { class: "experience-muted experience-objects-summary" });
  const staleNote = el("p", { class: "experience-notice", role: "status" });
  const selectedNote = el("p", { class: "experience-notice" });
  const clearButton = el("button", { type: "button", class: "experience-button", text: "Clear selection" });
  clearButton.addEventListener("click", () => onSelect(null));
  const selectionBar = el("div", { class: "experience-selection-bar" }, selectedNote, clearButton);
  const list = el("ul", { class: "experience-object-list", "aria-labelledby": headingId });
  const empty = el("p", { class: "experience-empty" });
  const thumbNote = el("p", { class: "experience-muted experience-thumb-note" });

  const card = el(
    "section",
    { class: "experience-card experience-objects", "aria-labelledby": headingId },
    el("h2", { id: headingId, class: "experience-heading", text: "Objects in view" }),
    summary,
    staleNote,
    selectionBar,
    list,
    empty,
    thumbNote,
  );
  root.replaceChildren(card);

  /** object_id -> row parts */
  const rows = new Map();

  function makeRow(id) {
    const thumbImg = el("img", { class: "experience-thumb-img", alt: "", loading: "lazy", decoding: "async" });
    const thumbFallback = el("span", { class: "experience-thumb-fallback", "aria-hidden": "true" });
    const thumb = el("span", { class: "experience-thumb" }, thumbImg, thumbFallback);
    const nameId = uniqueId("experience-object-name");
    const name = el("span", { class: "experience-object-name", id: nameId });
    const stateBadge = el("span", { class: "experience-badge" });
    const naming = el("span", { class: "experience-object-naming" });
    const seen = el("span", { class: "experience-muted" });
    const select = el(
      "button",
      { type: "button", class: "experience-object-select", "aria-pressed": "false" },
      thumb,
      el("span", { class: "experience-object-body" }, name, el("span", { class: "experience-object-meta" }, stateBadge, naming, seen)),
    );
    select.addEventListener("click", () => onSelect(rows.get(id)?.selected ? null : id));
    const more = el("button", { type: "button", class: "experience-link-button", "aria-controls": nameId });
    more.addEventListener("click", () => onToggleName(id));
    const li = el("li", { class: "experience-object-row" }, select, more);

    const row = { li, select, more, name, stateBadge, naming, seen, thumbImg, thumbFallback, thumbSrc: null, thumbFailed: false, selected: false };
    thumbImg.addEventListener("error", () => {
      row.thumbFailed = true;
      thumbImg.removeAttribute("src");
      setHidden(thumbImg, true);
      setHidden(thumbFallback, false);
      setText(thumbFallback, "No image");
    });
    thumbImg.addEventListener("load", () => {
      setHidden(thumbImg, false);
      setHidden(thumbFallback, true);
    });
    return row;
  }

  function updateRow(row, vm, thumbsSupported) {
    row.li.dataset.state = vm.rawState;
    row.li.dataset.naming = vm.naming.key;
    row.li.classList.toggle("experience-is-selected", vm.selected);
    row.li.classList.toggle("experience-is-expanded", vm.expanded);
    row.selected = vm.selected;
    row.select.setAttribute("aria-pressed", vm.selected ? "true" : "false");
    setText(row.name, vm.text);
    row.name.title = vm.text;
    setText(row.stateBadge, vm.stateLabel);
    row.stateBadge.className = `experience-badge experience-badge-${vm.rawState}`;
    setText(row.naming, vm.naming.label);
    setHidden(row.naming, !vm.naming.label);
    setText(row.seen, vm.lastSeen);
    row.seen.title = vm.lastSeenExact ? `Last seen at ${vm.lastSeenExact}` : "";

    setHidden(row.more, !vm.isLong);
    setText(row.more, vm.expanded ? "Show less" : "Show full name");
    row.more.setAttribute("aria-expanded", vm.expanded ? "true" : "false");

    // Thumbnails: set src once per URL; never re-download on every snapshot.
    const want = thumbsSupported && vm.thumbnailUrl && !row.thumbFailed ? vm.thumbnailUrl : null;
    if (want !== row.thumbSrc) {
      row.thumbSrc = want;
      if (want) {
        row.thumbImg.alt = `Picture of ${vm.text}`;
        row.thumbImg.src = want;
      } else {
        row.thumbImg.removeAttribute("src");
        setHidden(row.thumbImg, true);
        setHidden(row.thumbFallback, false);
        setText(row.thumbFallback, row.thumbFailed ? "No image" : initial(vm.text));
      }
    }
    if (!thumbsSupported) {
      setHidden(row.thumbImg, true);
      setHidden(row.thumbFallback, false);
      setText(row.thumbFallback, initial(vm.text));
    }
  }

  function update(vm) {
    setText(summary, vm.summary);
    setText(staleNote, vm.staleNote);
    setHidden(staleNote, !vm.staleNote);
    card.classList.toggle("experience-is-stale", Boolean(vm.staleNote));
    setHidden(selectionBar, !vm.selectedMissing && !vm.rows.some((r) => r.selected));
    setText(selectedNote, vm.selectedMissing ? "The selected object is no longer in view." : "Selected object is highlighted on the camera when supported.");

    const active = document.activeElement;
    const seen = new Set();
    let previous = null;
    for (const rowVm of vm.rows) {
      seen.add(rowVm.id);
      let row = rows.get(rowVm.id);
      if (!row) {
        row = makeRow(rowVm.id);
        rows.set(rowVm.id, row);
      }
      updateRow(row, rowVm, vm.thumbnailsSupported);
      // Move only when out of place, so untouched rows keep focus.
      const expectedNext = previous ? previous.nextSibling : list.firstChild;
      if (expectedNext !== row.li) list.insertBefore(row.li, expectedNext);
      previous = row.li;
    }
    for (const [id, row] of rows) {
      if (!seen.has(id)) {
        row.thumbImg.removeAttribute("src");
        row.li.remove();
        rows.delete(id);
      }
    }
    if (active && active !== document.activeElement && card.contains(active)) active.focus({ preventScroll: true });

    setHidden(empty, vm.rows.length > 0);
    setText(empty, vm.summary);
    setHidden(summary, vm.rows.length === 0);
    setText(thumbNote, vm.thumbnailsSupported ? "" : "Object pictures are not available from this laptop.");
    setHidden(thumbNote, vm.thumbnailsSupported || vm.rows.length === 0);
  }

  return {
    update,
    destroy() {
      for (const row of rows.values()) row.thumbImg.removeAttribute("src");
      rows.clear();
      root.replaceChildren();
    },
  };
}

function initial(text) {
  const ch = (text || "?").trim().charAt(0);
  return ch ? ch.toUpperCase() : "?";
}
