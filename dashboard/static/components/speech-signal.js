// Speech signal: a small Rive animation (circles and arcs) that moves only
// while the audio telemetry says a real speech engine is speaking.
//
// It is decoration that mirrors a fact, never the fact itself: the speech
// status text next to it is always present and always updated first. The
// still image is shown immediately; the Rive runtime is loaded afterwards,
// when the browser is idle, and only if reduced motion is not requested. If
// the runtime or the file fails, the still image stays. Playback pauses while
// the signal is offscreen or the page is hidden, and destroy() disposes of
// everything.
//
// Asset: assets/rive/speech_signal.riv, recoloured from rive-android's
// progress.riv (MIT). Runtime: @rive-app/canvas 2.47.1 (MIT), vendored in
// vendor/rive/. See docs/dashboard-redesign/bauhaus/README.md.

export const RIVE_RUNTIME_VERSION = "2.47.1";
export const RIVE_SCRIPT_URL = "/static/vendor/rive/rive.js";
export const RIVE_WASM_URL = "/static/vendor/rive/rive.wasm";
export const SIGNAL_RIV_URL = "/static/assets/rive/speech_signal.riv";
export const SIGNAL_STILL_URL = "/static/assets/illustrations/speech-signal-still.svg";
export const SIGNAL_ANIMATION = "activate";

let runtimePromise = null;

/** Load the vendored Rive runtime once (classic script), with local WASM only. */
export function loadRiveRuntime({ doc = globalThis.document, win = globalThis } = {}) {
  if (runtimePromise) return runtimePromise;
  runtimePromise = new Promise((resolve, reject) => {
    const ready = () => {
      const rive = win.rive;
      if (!rive?.Rive || !rive?.RuntimeLoader) {
        reject(new Error("Rive runtime did not load"));
        return;
      }
      rive.RuntimeLoader.setWasmUrl(RIVE_WASM_URL);
      // Never fall back to a CDN: if the local WASM fails, the still image stays.
      rive.RuntimeLoader.setWasmFallbackUrl?.(null);
      resolve(rive);
    };
    if (win.rive?.Rive) {
      ready();
      return;
    }
    const script = doc.createElement("script");
    script.src = RIVE_SCRIPT_URL;
    script.async = true;
    script.dataset.riveRuntime = RIVE_RUNTIME_VERSION;
    script.addEventListener("load", ready, { once: true });
    script.addEventListener("error", () => reject(new Error("Rive runtime failed to load")), { once: true });
    doc.head.append(script);
  });
  runtimePromise.catch(() => {
    runtimePromise = null; // a later mount may try again
  });
  return runtimePromise;
}

/** Whether speech telemetry justifies motion: real engine, speaking now. */
export function signalShouldMove(speech) {
  return Boolean(speech && speech.status === "speaking" && speech.mode === "real");
}

/**
 * Mount the signal into `root`. Returns {update({active}), destroy()}.
 * root.dataset.signal is "still", "loading", "ready", "playing" or "fallback".
 */
export function createSpeechSignal(root, options = {}) {
  const {
    doc = globalThis.document,
    win = globalThis,
    loadRuntime = () => loadRiveRuntime({ doc, win }),
    reducedMotion = () => Boolean(win.matchMedia?.("(prefers-reduced-motion: reduce)").matches),
    scheduleIdle = (fn) =>
      win.requestIdleCallback ? win.requestIdleCallback(fn, { timeout: 2000 }) : win.setTimeout(fn, 300),
    cancelIdle = (id) => (win.cancelIdleCallback ? win.cancelIdleCallback(id) : win.clearTimeout(id)),
  } = options;

  const still = doc.createElement("img");
  still.className = "speech-signal__still";
  still.src = SIGNAL_STILL_URL;
  still.alt = ""; // decorative: the speech status text carries the meaning
  still.setAttribute("aria-hidden", "true");
  const canvas = doc.createElement("canvas");
  canvas.className = "speech-signal__canvas";
  canvas.width = 160;
  canvas.height = 160;
  canvas.hidden = true;
  canvas.setAttribute("aria-hidden", "true");
  root.append(still, canvas);
  root.dataset.signal = "still";

  let rive = null;
  let instance = null;
  let destroyed = false;
  let wantActive = false;
  let visible = true;
  let pageVisible = !doc.hidden;
  let idleId = null;
  let observer = null;

  const canMove = () => wantActive && visible && pageVisible && !reducedMotion();

  function apply() {
    if (!instance || destroyed) return;
    if (canMove()) {
      instance.play(SIGNAL_ANIMATION);
      root.dataset.signal = "playing";
    } else {
      instance.pause(SIGNAL_ANIMATION);
      root.dataset.signal = "ready";
    }
  }

  function fallBack() {
    if (destroyed) return;
    canvas.hidden = true;
    still.hidden = false;
    root.dataset.signal = "fallback";
    try {
      instance?.cleanup();
    } catch {
      // already gone
    }
    instance = null;
  }

  function start() {
    idleId = null;
    if (destroyed || reducedMotion()) return;
    root.dataset.signal = "loading";
    loadRuntime()
      .then((runtime) => {
        if (destroyed) return;
        rive = runtime;
        instance = new rive.Rive({
          src: SIGNAL_RIV_URL,
          canvas,
          autoplay: false,
          animations: SIGNAL_ANIMATION,
          onLoad: () => {
            if (destroyed) return;
            instance.resizeDrawingSurfaceToCanvas?.();
            canvas.hidden = false;
            still.hidden = true;
            root.dataset.signal = "ready";
            apply();
          },
          onLoadError: fallBack,
          // The source animation plays once; keep it going only while still justified.
          onStop: () => {
            if (!destroyed && canMove()) instance?.play(SIGNAL_ANIMATION);
          },
        });
      })
      .catch(fallBack);
  }

  const onVisibility = () => {
    pageVisible = !doc.hidden;
    apply();
  };
  doc.addEventListener("visibilitychange", onVisibility);
  if (typeof win.IntersectionObserver === "function") {
    observer = new win.IntersectionObserver((entries) => {
      visible = entries.some((e) => e.isIntersecting);
      apply();
    });
    observer.observe(root);
  }
  // Essential content first: the runtime loads only when the browser is idle.
  idleId = scheduleIdle(start);

  return {
    /** active: speech telemetry says a real engine is speaking right now. */
    update({ active }) {
      wantActive = Boolean(active);
      apply();
    },
    destroy() {
      destroyed = true;
      if (idleId !== null) cancelIdle(idleId);
      doc.removeEventListener("visibilitychange", onVisibility);
      observer?.disconnect();
      try {
        instance?.cleanup();
      } catch {
        // nothing left to free
      }
      instance = null;
      still.remove();
      canvas.remove();
      delete root.dataset.signal;
    },
  };
}
