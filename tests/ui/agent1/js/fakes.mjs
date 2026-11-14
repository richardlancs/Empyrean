// Test doubles for the foundation's Node tests: a tiny DOM, a scriptable
// WebSocket, manual timers and a fake fetch. Test-only; never shipped.

class FakeNode {
  constructor(doc) {
    this.ownerDocument = doc;
    this.parentNode = null;
    this.childNodes = [];
  }
  get children() {
    return this.childNodes.filter((n) => n instanceof FakeElement);
  }
  append(...nodes) {
    for (const node of nodes) {
      const child = typeof node === "string" ? this.ownerDocument.createTextNode(node) : node;
      child.remove?.();
      child.parentNode = this;
      this.childNodes.push(child);
    }
  }
  replaceChildren(...nodes) {
    for (const child of this.childNodes) child.parentNode = null;
    this.childNodes = [];
    this.append(...nodes);
  }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.childNodes = this.parentNode.childNodes.filter((n) => n !== this);
    this.parentNode = null;
  }
  get textContent() {
    return this.childNodes.map((n) => n.textContent).join("");
  }
  set textContent(value) {
    this.replaceChildren();
    if (value !== "" && value !== null && value !== undefined) this.append(String(value));
  }
}

class FakeText extends FakeNode {
  constructor(doc, text) {
    super(doc);
    this.data = text;
  }
  get textContent() {
    return this.data;
  }
  set textContent(value) {
    this.data = String(value);
  }
}

export class FakeElement extends FakeNode {
  constructor(doc, tag) {
    super(doc);
    this.tagName = tag.toUpperCase();
    this.attributes = new Map();
    this.listeners = new Map();
  }
  get className() {
    return this.getAttribute("class") ?? "";
  }
  set className(value) {
    this.setAttribute("class", value);
  }
  get id() {
    return this.getAttribute("id") ?? "";
  }
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }
  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }
  hasAttribute(name) {
    return this.attributes.has(name);
  }
  removeAttribute(name) {
    this.attributes.delete(name);
  }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }
  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }
  dispatch(type) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener({ type, target: this });
  }
  /** Depth-first descendants matching predicate. */
  findAll(predicate) {
    const out = [];
    const walk = (node) => {
      for (const child of node.children) {
        if (predicate(child)) out.push(child);
        walk(child);
      }
    };
    walk(this);
    return out;
  }
  find(predicate) {
    return this.findAll(predicate)[0] ?? null;
  }
}

export class FakeDocument {
  constructor() {
    this.documentElement = new FakeElement(this, "html");
    this.body = new FakeElement(this, "body");
    this.documentElement.append(this.body);
  }
  createElement(tag) {
    return new FakeElement(this, tag);
  }
  createTextNode(text) {
    return new FakeText(this, text);
  }
  getElementById(id) {
    return this.documentElement.find((el) => el.id === id);
  }
}

/** Timers you advance by hand. */
export class ManualTimers {
  constructor() {
    this.now = 0;
    this.queue = [];
    this.nextId = 1;
    this.setTimeout = (fn, ms = 0) => {
      const id = this.nextId++;
      this.queue.push({ id, at: this.now + ms, fn });
      return id;
    };
    this.clearTimeout = (id) => {
      this.queue = this.queue.filter((t) => t.id !== id);
    };
  }
  get pending() {
    return this.queue.length;
  }
  /** Advance the clock by ms, running due timers in order. */
  advance(ms) {
    const end = this.now + ms;
    for (;;) {
      this.queue.sort((a, b) => a.at - b.at || a.id - b.id);
      const next = this.queue[0];
      if (!next || next.at > end) break;
      this.queue.shift();
      this.now = next.at;
      next.fn();
    }
    this.now = end;
  }
  delays() {
    return this.queue.map((t) => t.at - this.now);
  }
}

/** WebSocket stand-in. Every instance is recorded on FakeWebSocket.instances. */
export class FakeWebSocket {
  static instances = [];
  static reset() {
    FakeWebSocket.instances = [];
  }
  static get last() {
    return FakeWebSocket.instances.at(-1);
  }
  constructor(url) {
    this.url = url;
    this.closed = false;
    this.closeArgs = null;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.onclose = null;
    FakeWebSocket.instances.push(this);
  }
  close(code, reason) {
    this.closed = true;
    this.closeArgs = [code, reason];
  }
  serverOpen() {
    this.onopen?.({});
  }
  serverSend(data) {
    this.onmessage?.({ data: typeof data === "string" ? data : JSON.stringify(data) });
  }
  serverClose() {
    this.closed = true;
    this.onerror?.({});
    this.onclose?.({ code: 1006 });
  }
}

/** fetch() stand-in answering from a route table: "METHOD /path" -> response spec or function. */
export function fakeFetch(routes) {
  const calls = [];
  async function fetchImpl(path, init = {}) {
    calls.push({ path, init });
    const route = routes[`${init.method ?? "GET"} ${path}`];
    if (!route) return makeResponse({ status: 404, json: { detail: "Not Found" } });
    const spec = typeof route === "function" ? await route(path, init) : route;
    return makeResponse(spec);
  }
  fetchImpl.calls = calls;
  return fetchImpl;
}

function makeResponse({ status = 200, json, text, contentType }) {
  const body = json !== undefined ? JSON.stringify(json) : text ?? "";
  const type = contentType ?? (json !== undefined ? "application/json" : "text/plain");
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: (name) => (name.toLowerCase() === "content-type" ? type : null) },
    text: async () => body,
  };
}

/** Wait for pending promise callbacks and zero-delay timers. */
export function flushAsync() {
  return new Promise((resolve) => setTimeout(resolve, 5));
}

/** A localStorage-like object; pass {throwing: true} to make every call throw. */
export function fakeStorage({ throwing = false } = {}) {
  const data = new Map();
  const guard = () => {
    if (throwing) throw new Error("SecurityError: storage disabled");
  };
  return {
    data,
    getItem: (k) => (guard(), data.has(k) ? data.get(k) : null),
    setItem: (k, v) => (guard(), data.set(k, String(v))),
    removeItem: (k) => (guard(), data.delete(k)),
  };
}
