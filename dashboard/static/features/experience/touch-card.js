// Current touch context inside the shared conversation card.
import { el, setHidden, setText } from "./dom.js";

/** Show the touched object without duplicating the question response or speech status. */
export function createTouchCard(root) {
  const thumb = el("img", { class: "experience-touch-thumb", alt: "", width: "48", height: "48" });
  const name = el("p", { class: "experience-touch-name" });
  const state = el("span", { class: "experience-badge" });
  const freshness = el("p", { class: "experience-notice", role: "status", hidden: true });
  const card = el("div", { class: "experience-card experience-touch" },
    el("div", { class: "experience-touch-top" }, el("h3", { class: "experience-subheading", text: "Current touch" }), state),
    el("div", { class: "experience-touch-hero" }, thumb, name), freshness);
  root.replaceChildren(card);
  let shownThumb = "";
  return {
    update(vm) {
      card.dataset.touch = vm.current?.stateKey || "none";
      setText(name, vm.loading ? "Connecting…" : vm.current?.text || "No object being touched");
      setText(state, vm.current?.stateLabel || "");
      setHidden(state, !vm.current);
      const url = vm.current?.thumbnailUrl || "";
      if (url !== shownThumb) {
        shownThumb = url;
        if (url) thumb.src = url;
        else thumb.removeAttribute("src");
      }
      setHidden(thumb, !url);
      const stale = ["old", "disconnected"].includes(vm.freshness.kind);
      setText(freshness, stale ? vm.freshness.message : "");
      setHidden(freshness, !stale);
    },
    destroy() { thumb.removeAttribute("src"); root.replaceChildren(); },
  };
}
