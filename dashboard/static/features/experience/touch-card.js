// Current touch and speech activity. Leaf view: receives view models only.
//
// Friendly clarity: the object's name is the focal point, with its thumbnail and
// Touching/Holding state beside it. The previous touch is a quiet line. When
// nothing is touched, pointing Pip sits next to one short instruction. The longer
// explanation is in a "How touch works" disclosure, where sign-holding Pip carries
// it as real HTML text. Speech leads with "no sound" whenever no sound can play.

import { el, setHidden, setText, uniqueId } from "./dom.js";

const PIP = "/static/assets/pip";

/** Build the touch card inside `root`; returns {update(vm), destroy()}. */
export function createTouchCard(root) {
  const headingId = uniqueId("experience-touch-heading");
  const heading = el("h2", { id: headingId, class: "experience-heading", text: "Touching now" });
  const stateBadge = el("span", { class: "experience-badge" });

  const thumb = el("img", { class: "experience-touch-thumb", alt: "", width: "64", height: "64" });
  const name = el("p", { class: "experience-touch-name" });
  // Decorative: the sentence next to it says the same thing.
  const pip = el("img", {
    class: "pip pip-point",
    src: `${PIP}/pip-point.png`,
    alt: "",
    "aria-hidden": "true",
    width: "92",
    height: "84",
  });
  const hero = el("div", { class: "experience-touch-hero" }, thumb, pip, name);
  const since = el("p", { class: "experience-muted experience-touch-since" });
  const freshness = el("p", { class: "experience-notice", role: "status" });

  const lastText = el("span", { class: "experience-last-text" });
  const lastWhen = el("span", { class: "experience-muted" });
  const last = el("p", { class: "experience-last" }, el("span", { class: "experience-muted", text: "Previously " }), lastText, " ", lastWhen);

  const help = el(
    "details",
    { class: "experience-details experience-touch-help" },
    el("summary", { text: "How touch works" }),
    el(
      "figure",
      { class: "pip-sign" },
      el("img", { class: "pip pip-sign__art", src: `${PIP}/pip-peek.png`, alt: "", "aria-hidden": "true", width: "222", height: "94" }),
      el(
        "figcaption",
        { class: "pip-sign__text" },
        "Touching an object says its name once. Let go and touch again to hear it again.",
      ),
    ),
  );

  const speechHeading = el("h3", { class: "experience-subheading", text: "Speech" });
  const speechLead = el("p", { class: "experience-speech-lead" });
  const speechIcon = el("span", { class: "experience-speech-icon", "aria-hidden": "true" });
  const speechTitle = el("span", { class: "experience-speech-title" });
  const speechPhrase = el("q", { class: "experience-speech-phrase" });
  const speechTime = el("span", { class: "experience-muted" });
  const speechDetail = el("p", { class: "experience-muted experience-speech-detail" });
  const speech = el(
    "div",
    { class: "experience-speech" },
    speechHeading,
    speechLead,
    el("p", { class: "experience-speech-line" }, speechIcon, speechTitle),
    el("p", { class: "experience-speech-line" }, speechPhrase, " ", speechTime),
    speechDetail,
  );

  const card = el(
    "section",
    { class: "experience-card experience-touch", "aria-labelledby": headingId },
    el("div", { class: "experience-touch-top" }, heading, stateBadge),
    hero,
    since,
    freshness,
    last,
    speech,
    help,
  );
  root.replaceChildren(card);

  let shownThumb = "";

  function update(vm) {
    card.dataset.touch = vm.current ? vm.current.stateKey : "none";
    if (vm.loading) {
      setText(name, "Connecting…");
      card.dataset.touch = "loading";
    } else if (vm.current) {
      setText(name, vm.current.text);
    } else {
      setText(name, "Touch an object to hear its name.");
    }
    setText(heading, vm.current ? "Touching now" : "Current touch");
    setHidden(pip, Boolean(vm.current) || Boolean(vm.loading));
    setHidden(stateBadge, !vm.current);
    if (vm.current) {
      setText(stateBadge, vm.current.stateLabel);
      stateBadge.className = `experience-badge experience-badge-${vm.current.stateKey}`;
    }
    const thumbUrl = vm.current?.thumbnailUrl || "";
    if (thumbUrl !== shownThumb) {
      shownThumb = thumbUrl;
      if (thumbUrl) thumb.src = thumbUrl;
      else thumb.removeAttribute("src");
    }
    setHidden(thumb, !thumbUrl);
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
    speech.dataset.sound = s.lead ? "none" : "reported";
    setText(speechLead, s.lead || "");
    setHidden(speechLead, !s.lead);
    setText(speechTitle, s.lead ? `Speech engine: ${s.title}` : s.title);
    setText(speechIcon, SPEECH_ICONS[s.kind] || "–");
    setText(speechPhrase, s.phrase);
    setHidden(speechPhrase.parentElement, !s.phrase && !s.time);
    setText(speechTime, s.time);
    // With no sound, "completed by the audio system" adds nothing to the lead; keep it for real audio.
    setText(speechDetail, s.lead ? "" : s.detail);
    setHidden(speechDetail, !s.detail || Boolean(s.lead));
  }

  return {
    update,
    destroy() {
      thumb.removeAttribute("src");
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
