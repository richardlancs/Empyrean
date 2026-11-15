// Landing page behaviour: magnetic hopping button, warp transition, and the 3D glasses.

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const cta = document.getElementById("cta");
let stage = null;

// The button leans toward the pointer while it hops.
if (!reduced) {
  cta.addEventListener("pointermove", (event) => {
    const box = cta.getBoundingClientRect();
    const dx = event.clientX - (box.left + box.width / 2);
    const dy = event.clientY - (box.top + box.height / 2);
    cta.style.setProperty("--mx", `${dx * 0.25}px`);
    cta.style.setProperty("--my", `${dy * 0.35}px`);
  });
  cta.addEventListener("pointerleave", () => {
    cta.style.setProperty("--mx", "0px");
    cta.style.setProperty("--my", "0px");
  });
}

// Warp from the button into the dashboard, then navigate.
cta.addEventListener("click", (event) => {
  if (reduced || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
  event.preventDefault();
  const box = cta.getBoundingClientRect();
  const warp = document.querySelector(".warp");
  warp.style.setProperty("--x", `${box.left + box.width / 2}px`);
  warp.style.setProperty("--y", `${box.top + box.height / 2}px`);
  document.body.classList.add("leaving");
  stage?.warp();
  setTimeout(() => { window.location.href = cta.href; }, 900);
});

// Coming back with the browser's back button restores the page as it was.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    document.body.classList.remove("leaving");
    stage?.reset();
  }
});

// The model is decoration: if WebGL is unavailable the page still works.
import("./glasses.js")
  .then(({ mountGlasses }) => { stage = mountGlasses(document.getElementById("glasses"), { reduced }); })
  .catch((error) => { console.warn("Glasses model unavailable", error); });
