// Current-touch hero and speech activity. Leaf view: receives view models only.

import { el, setHidden, setText, uniqueId } from "./dom.js";

/** Build the touch card inside `root`; returns {update(vm), destroy()}. */
export function createTouchCard(root) {
  const headingId = uniqueId("experience-touch-heading");
  const heading = el("h2", { id: headingId, class: "experience-heading", text: "Touching now" });
  const stateBadge = el("span", { class: "experience-badge" });
  const name = el("p", { class: "experience-touch-name" });
  const since = el("p", { class: "experience-muted" });
  const freshness = el("p", { class: "experience-notice", role: "status" });
  const explain = el("p", {
    class: "experience-muted experience-touch-explain",
    text: "When the wearer's finger lands on an object, the speaker says its name. Holding it does not repeat the name; letting go and touching again does.",
  });

  const lastLabel = el("span", { class: "experience-label", text: "Last touched" });
  const lastText = el("span", { class: "experience-last-text" });
  const lastWhen = el("span", { class: "experience-muted" });
  const last = el("p", { class: "experience-last" }, lastLabel, " ", lastText, " ", lastWhen);

  // Bauhaus redesign: a geometric still while nothing is touched (decorative; the
  // sentence above says the same), and a mount for the Rive speech signal.
  const art = el("img", {
    class: "experience-touch-art",
    src: "/static/assets/illustrations/touch-idle.svg",
    alt: "",
    "aria-hidden": "true",
    width: "480",
    height: "200",
  });
  const signalRoot = el("div", { class: "experience-speech-signal speech-signal", "aria-hidden": "true" });

  const speechHeading = el("h3", { class: "experience-subheading", text: "Speech" });
  const speechIcon = el("span", { class: "experience-speech-icon", "aria-hidden": "true" });
  const speechTitle = el("span", { class: "experience-speech-title" });
  const speechPhrase = el("q", { class: "experience-speech-phrase" });
  const speechTime = el("span", { class: "experience-muted" });
  const speechDetail = el("p", { class: "experience-muted" });
  const speechMode = el("p", { class: "experience-badge experience-badge-demo" });
  const speech = el(
    "div",
    { class: "experience-speech" },
    signalRoot,
    speechHeading,
    el("p", { class: "experience-speech-line" }, speechIcon, speechTitle),
    el("p", { class: "experience-speech-line" }, speechPhrase, " ", speechTime),
    speechDetail,
    speechMode,
  );

  const card = el(
    "section",
    { class: "experience-card experience-touch", "aria-labelledby": headingId },
    el(
      "div",
      { class: "experience-touch-main" },
      el("div", { class: "experience-touch-top" }, heading, stateBadge),
      name,
      since,
      freshness,
      last,
      explain,
    ),
    art,
    speech,
  );
  root.replaceChildren(card);

  function update(vm) {
    card.dataset.touch = vm.current ? vm.current.stateKey : "none";
    if (vm.loading) {
      setText(name, "Connecting…");
      card.dataset.touch = "loading";
    } else if (vm.current) {
      setText(name, vm.current.text);
    } else {
      setText(name, "Touch an object to hear its name");
    }
    setText(heading, vm.current ? "Touching now" : "Current touch");
    setHidden(art, Boolean(vm.current) || Boolean(vm.loading));
    setHidden(stateBadge, !vm.current);
    if (vm.current) {
      setText(stateBadge, vm.current.stateLabel);
      stateBadge.className = `experience-badge experience-badge-${vm.current.stateKey}`;
    }
    setText(since, vm.current?.since || "");
    setHidden(since, !vm.current?.since);

    const stale = vm.freshness.kind === "old" || vm.freshness.kind === "disconnected";
    setText(freshness, stale ? vm.freshness.message : "");
    setHidden(freshness, !stale);
    card.classList.toggle("experience-is-stale", stale);

    setHidden(last, !vm.lastTouched);
    if (vm.lastTouched) {
      setText(lastText, vm.lastTouched.text);
      setText(lastWhen, vm.lastTouched.when);
    }

    const s = vm.speech;
    speech.dataset.status = s.kind;
    setText(speechTitle, s.title);
    setText(speechIcon, SPEECH_ICONS[s.kind] || "–");
    setText(speechPhrase, s.phrase);
    setHidden(speechPhrase.parentElement, !s.phrase && !s.time);
    setText(speechTime, s.time);
    setText(speechDetail, s.detail);
    setHidden(speechDetail, !s.detail);
    setText(speechMode, s.modeNote);
    setHidden(speechMode, !s.modeNote);
  }

  return {
    update,
    signalRoot,
    destroy() {
      root.replaceChildren();
    },
  };
}

// Text symbols accompany colour so status never relies on colour alone.
const SPEECH_ICONS = {
  queued: "…",
  speaking: "▶",
  completed: "✓",
  interrupted: "⏹",
  failed: "!",
  unknown: "?",
  unavailable: "–",
};
