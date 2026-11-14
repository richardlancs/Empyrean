// Tiny DOM helpers for the questions feature (same style as the experience
// feature's dom.js; features do not import from each other). Text always goes
// through textContent, so questions and answers can never inject markup.

/** Create an element with attributes, properties and child nodes or strings. */
export function el(doc, tag, attrs = {}, ...children) {
  const node = doc.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(typeof child === "string" ? doc.createTextNode(child) : child);
  }
  return node;
}

/** Set text only when it changed, to avoid needless layout and screen-reader churn. */
export function setText(node, text) {
  const value = text ?? "";
  if (node.textContent !== value) node.textContent = value;
}

/** Toggle `hidden` only when it changed. */
export function setHidden(node, hidden) {
  if (node.hidden !== hidden) node.hidden = hidden;
}

/** Set or remove an attribute only when it changed. */
export function setAttr(node, name, value) {
  if (value === null || value === undefined || value === false) {
    if (node.hasAttribute(name)) node.removeAttribute(name);
    return;
  }
  const text = value === true ? "" : String(value);
  if (node.getAttribute(name) !== text) node.setAttribute(name, text);
}

let uid = 0;
/** Unique id for label/aria wiring. */
export function uniqueId(prefix) {
  uid += 1;
  return `${prefix}-${uid}`;
}
