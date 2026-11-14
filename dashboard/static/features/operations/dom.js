// Small DOM helpers shared by the operations components. Text always goes in via textContent.

const SVG_NS = "http://www.w3.org/2000/svg";

/** Create an element with a class, attributes and text or children. */
export function el(tag, { className, text, attrs, children } = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (attrs) for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) node.setAttribute(k, v);
  if (children) node.append(...children.filter(Boolean));
  return node;
}

let idCounter = 0;
/** A unique id for aria wiring inside this feature. */
export function uid(prefix) {
  idCounter += 1;
  return `operations-${prefix}-${idCounter}`;
}

const ICON_PATHS = {
  // Steps going down to the right.
  stairs: ["M3 6h5v4h4v4h4v4h5"],
  // A ledge with an arrow pointing down past it.
  drop: ["M3 8h9", "M16 4v13", "M12.5 13.5 16 17l3.5-3.5"],
  // A simple car side view with two wheels.
  vehicle: ["M3 15V11l3-5h10l3 5v4z", "M7.5 18.5a1.5 1.5 0 1 0 0-.01", "M16.5 18.5a1.5 1.5 0 1 0 0-.01"],
  // Warning triangle with exclamation mark.
  obstacle: ["M12 3 2 20h20z", "M12 10v4", "M12 17v.01"],
  // Finger tip touching a dot.
  touch: ["M9 11V5a2 2 0 0 1 4 0v6", "M13 9a2 2 0 0 1 4 0v4c0 4-2.5 7-6 7s-5-2-6-5l-1-3a1.6 1.6 0 0 1 3-1l1 2"],
  info: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 11v5", "M12 8v.01"],
  ok: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M8 12.5l2.5 2.5L16 9.5"],
  caution: ["M12 3 2 20h20z", "M12 10v4", "M12 17v.01"],
  error: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M9 9l6 6", "M15 9l-6 6"],
  unknown: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6", "M12 17v.01"],
  neutral: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M12 7v5l3 2"],
  flask: ["M9 3h6", "M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3", "M7 15h10"],
};

/** A decorative stroke icon; meaning is always also given in text. */
export function icon(name, className = "operations-icon") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", className);
  for (const d of ICON_PATHS[name] || ICON_PATHS.info) {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
  }
  return svg;
}

/** Replace an element's icon child in place. */
export function setIcon(container, name, className) {
  const next = icon(name, className);
  const current = container.querySelector(":scope > svg");
  if (current) current.replaceWith(next);
  else container.prepend(next);
}

/** Set text only when it changed, so screen readers and selection are not disturbed. */
export function setText(node, text) {
  const value = text === undefined || text === null ? "" : String(text);
  if (node.textContent !== value) node.textContent = value;
}

/**
 * A relative time that shows the exact time on hover, on keyboard focus, and when clicked
 * (useful for touch screens). The accessible name always contains the exact time.
 */
export function createTimeToggle() {
  const wrap = el("span", { className: "operations-time" });
  const button = el("button", {
    className: "operations-time-button",
    attrs: { type: "button", "aria-expanded": "false" },
  });
  const rel = el("span", { className: "operations-time-relative" });
  const exact = el("span", { className: "operations-time-exact" });
  button.append(rel);
  wrap.append(button, exact);
  button.addEventListener("click", () => {
    const open = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", String(open));
    wrap.classList.toggle("operations-time-pinned", open);
  });
  return {
    node: wrap,
    update(relativeText, exactText) {
      setText(rel, relativeText);
      setText(exact, exactText);
      button.title = exactText;
      // The accessible name uses only the exact time so it stays stable as the relative text
      // ticks; a focused control whose name changes every second would be re-read.
      const label = `At ${exactText}`;
      if (button.getAttribute("aria-label") !== label) button.setAttribute("aria-label", label);
    },
  };
}

/** Run render() and put keyboard focus back on the same logical control if it was replaced. */
export function preservingFocus(root, render) {
  const active = document.activeElement;
  const key = active && root.contains(active) ? active.dataset.focusKey : null;
  render();
  if (key && !root.contains(document.activeElement)) {
    const again = root.querySelector(`[data-focus-key="${CSS.escape(key)}"]`);
    if (again) again.focus({ preventScroll: true });
  }
}
