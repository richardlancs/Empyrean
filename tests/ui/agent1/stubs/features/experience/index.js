// AGENT 1 PREVIEW STUB, not production. Agent 2 owns the real
// dashboard/static/features/experience/. This stub exists only so the foundation
// (shell, store, transport, announcer, styles) can be exercised in a browser.
// It also shows the intended use of the context: subscribe once, build DOM once,
// update text in place (so focus and form input survive snapshots), announce by
// event key only.

import { ageSeconds, formatAge } from "/static/core/clock.js";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const SPEECH_LABEL = {
  queued: ["Waiting to speak", "caution", "◔"],
  speaking: ["Speaking now", "touch", "▶︎"],
  completed: ["Spoken", "outline", "✓"],
  interrupted: ["Interrupted by a warning", "caution", "■"],
  failed: ["Could not be spoken", "danger", "✕"],
};

function mountTouch(root) {
  const panel = el("div", "ui-panel ui-panel--accent experience-touch");
  const label = el("p", "experience-touch__label", "Touching now");
  const name = el("p", "experience-touch__name");
  const chips = el("div", "ui-row");
  const stateChip = el("span", "ui-chip");
  const speechChip = el("span", "ui-chip");
  const meta = el("p", "ui-meta");
  chips.append(stateChip, speechChip);
  panel.append(el("h2", "ui-visually-hidden", "Current touch"), label, name, chips, meta, el("p", "ui-meta", "Preview stub: Agent 2 owns this panel."));
  root.append(panel);
  return (snap) => {
    const touch = snap.state?.current_touch;
    const speech = snap.state?.speech;
    panel.classList.toggle("ui-panel--accent", Boolean(touch));
    if (!snap.state) {
      label.textContent = "Waiting for the dashboard";
      name.textContent = "Connecting…";
      stateChip.hidden = speechChip.hidden = true;
      meta.textContent = "";
      return;
    }
    if (!touch) {
      label.textContent = "Nothing touched";
      name.textContent = "Touch an object to hear its name";
      stateChip.hidden = speechChip.hidden = true;
      meta.textContent = "";
      return;
    }
    label.textContent = touch.state === "held" ? "Holding" : "Touching now";
    name.textContent = touch.text;
    stateChip.hidden = false;
    stateChip.className = `ui-chip ${touch.state === "held" ? "ui-chip--caution" : "ui-chip--touch"}`;
    stateChip.dataset.icon = touch.state === "held" ? "✋︎" : "☝︎";
    stateChip.textContent = touch.state === "held" ? "Held" : "Touching";
    const [text, variant, icon] = SPEECH_LABEL[speech?.status] ?? ["Speech status unknown", "outline", "?"];
    speechChip.hidden = false;
    speechChip.className = `ui-chip ui-chip--${variant}`;
    speechChip.dataset.icon = icon;
    speechChip.textContent = speech?.mode === "fake" ? `${text} (fake speaker)` : text;
    meta.textContent = `Touched ${formatAge(ageSeconds(touch.ts, snap))}`;
  };
}

function mountCamera(root) {
  const panel = el("div", "ui-panel experience-camera");
  const head = el("div", "ui-panel__header");
  head.append(el("h2", "ui-panel__title", "Camera view"), el("span", "ui-meta experience-camera__meta"));
  const img = el("img", "experience-camera__feed");
  img.alt = "Camera view with boxes around objects and dots on the fingertips";
  img.width = 640;
  img.height = 360;
  img.src = "/video";
  panel.append(head, img);
  root.append(panel);
  let lastConnection = null;
  return (snap) => {
    const cam = snap.state?.diagnostics?.camera;
    const age = ageSeconds(cam?.last_frame_ts, snap);
    head.lastChild.textContent = cam?.fps ? `${cam.fps.toFixed(0)} frames per second` : age !== null && age > 3 ? `Last frame ${formatAge(age)}` : "";
    if (lastConnection === "reconnecting" && snap.connection === "connected") img.src = `/video?t=${Date.now()}`;
    lastConnection = snap.connection;
  };
}

function mountObjects(root) {
  const panel = el("div", "ui-panel");
  const list = el("ul", "ui-list");
  const empty = el("div", "ui-empty");
  empty.append(el("p", "ui-empty__title", "No objects in view"), el("p", "", "Objects the camera recognizes appear here."));
  panel.append(el("h2", "ui-panel__title experience-heading", "Recognized objects"), empty, list);
  root.append(panel);
  return (snap) => {
    const objects = snap.state?.objects ?? [];
    empty.hidden = objects.length > 0;
    list.replaceChildren(
      ...objects.map((o) => {
        const li = el("li", "experience-object");
        const chip = el("span", `ui-chip ${o.state === "touching" ? "ui-chip--touch" : o.state === "held" ? "ui-chip--caution" : ""}`, o.state);
        li.append(el("span", "experience-object__name", o.text), chip);
        if (o.naming_status === "pending") li.append(el("span", "ui-meta", "Naming…"));
        if (o.naming_status === "fallback") li.append(el("span", "ui-meta", "Specific name unavailable"));
        return li;
      }),
    );
  };
}

function mountFind(root, ctx) {
  const panel = el("div", "ui-panel");
  const form = el("form", "ui-stack");
  const field = el("div", "ui-field");
  const label = el("label", "ui-label", "Object to find");
  label.htmlFor = "experience-find-query";
  const input = el("input", "ui-input");
  input.id = "experience-find-query";
  input.name = "query";
  input.autocomplete = "off";
  const hint = el("p", "ui-hint", "Searches recorded touches, not locations. The answer is also spoken.");
  hint.id = "experience-find-hint";
  input.setAttribute("aria-describedby", hint.id);
  field.append(label, input, hint);
  const button = el("button", "ui-button", "Find last touch");
  button.type = "submit";
  const result = el("div", "experience-find__result");
  form.append(field, button);
  panel.append(el("h2", "ui-panel__title experience-heading", "Find a last touch"), form, result);
  root.append(panel);

  let seq = 0;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = input.value.trim();
    const mine = ++seq;
    button.setAttribute("aria-busy", "true");
    result.replaceChildren(el("p", "ui-meta", "Searching…"));
    try {
      const { request_id } = await ctx.request("/api/last-seen", { method: "POST", body: { query } });
      let answer;
      for (let i = 0; i < 10; i += 1) {
        await new Promise((r) => setTimeout(r, 400));
        answer = await ctx.request(`/api/last-seen/${encodeURIComponent(request_id)}`);
        if (answer.status !== "pending") break;
      }
      if (mine !== seq) return;
      const text = answer.status === "found" ? answer.answer : `No recorded touch matches “${query}”.`;
      const box = el("div", `ui-callout ${answer.status === "found" ? "ui-callout--touch" : ""}`);
      box.append(el("p", "ui-callout__title", answer.status === "found" ? "Last touch" : "Not found"), el("p", "", text));
      result.replaceChildren(box);
      ctx.announce(text, { key: `last-seen:${request_id}` });
    } catch (error) {
      if (mine !== seq) return;
      const box = el("div", "ui-callout ui-callout--danger");
      box.append(el("p", "ui-callout__title", "Search failed"), el("p", "", error.message));
      result.replaceChildren(box);
      ctx.announce(`Search failed. ${error.message}`, { priority: "assertive" });
    } finally {
      if (mine === seq) button.removeAttribute("aria-busy");
    }
  });
  return () => {};
}

export function mountExperience(ctx) {
  const renderers = [mountTouch(ctx.roots.touch), mountCamera(ctx.roots.camera), mountObjects(ctx.roots.objects)];
  mountFind(ctx.roots.find, ctx);
  let lastTouchKey = null;
  const unsubscribe = ctx.subscribe((snap) => {
    for (const render of renderers) render(snap);
    const touch = snap.state?.current_touch;
    const key = touch ? `touch:${touch.object_id}:${touch.ts}` : null;
    if (key && key !== lastTouchKey && touch.state === "touching") ctx.announce(`Touching ${touch.text}`, { key });
    lastTouchKey = key;
  });
  return unsubscribe;
}
