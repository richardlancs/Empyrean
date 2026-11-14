// The page frame: skip link, header (purpose, Prototype label, display options),
// the eight feature mounts in semantic order, and the footer.
// The shell owns these elements but never their contents once a feature mounts:
// each feature fills and updates its own mounts.

/** Mount areas in reading order. key -> element id and accessible region name. */
export const AREAS = Object.freeze([
  Object.freeze({ key: "health", id: "health-panel", label: "System status" }),
  Object.freeze({ key: "warning", id: "warning-panel", label: "Warnings" }),
  Object.freeze({ key: "touch", id: "touch-panel", label: "Current touch" }),
  Object.freeze({ key: "camera", id: "camera-panel", label: "Camera view" }),
  Object.freeze({ key: "objects", id: "objects-panel", label: "Recognized objects" }),
  Object.freeze({ key: "find", id: "find-panel", label: "Find a last touch" }),
  Object.freeze({ key: "events", id: "events-panel", label: "Recent activity" }),
  Object.freeze({ key: "demo", id: "demo-panel", label: "Demo tools" }),
]);

/** Create an element with attributes and children (strings become text nodes). */
function h(doc, tag, attrs = {}, children = []) {
  const el = doc.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === false || value === null || value === undefined) continue;
    if (name === "className") el.className = value;
    else if (name === "text") el.textContent = value;
    else el.setAttribute(name, value === true ? "" : String(value));
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    el.append(typeof child === "string" ? doc.createTextNode(child) : child);
  }
  return el;
}

function loadingPlaceholder(doc, label) {
  return h(doc, "div", { className: "ui-loading", "data-shell-placeholder": "" }, [
    h(doc, "span", { className: "ui-visually-hidden", text: `${label}: loading` }),
    h(doc, "div", { className: "ui-loading__bar", "aria-hidden": "true" }),
    h(doc, "div", { className: "ui-loading__bar", "aria-hidden": "true" }),
    h(doc, "div", { className: "ui-loading__bar", "aria-hidden": "true" }),
  ]);
}

/**
 * Build the shell inside root.
 * @param {object} options
 * @param {Element} options.root          usually <div id="app">
 * @param {"light"|"high-contrast"} options.theme
 * @param {(theme: string) => void} options.onThemeChange called when the user toggles contrast
 * @returns {{ roots: Readonly<Record<string, Element>>, main: Element,
 *            setTheme(theme: string): void, markMounted(keys: string[]): void,
 *            showFeatureError(keys: string[], error: Error): void, destroy(): void }}
 */
export function createAppShell({ root, theme = "light", onThemeChange }) {
  const doc = root.ownerDocument;
  const cleanups = [];

  const skipLink = h(doc, "a", { className: "skip-link", href: "#main" }, "Skip to dashboard");

  const contrastToggle = h(
    doc,
    "button",
    {
      type: "button",
      className: "ui-button ui-button--secondary ui-toggle",
      "aria-pressed": theme === "high-contrast" ? "true" : "false",
      "data-shell-control": "contrast",
    },
    "High contrast",
  );
  const onToggle = () => {
    const next = contrastToggle.getAttribute("aria-pressed") === "true" ? "light" : "high-contrast";
    onThemeChange?.(next);
  };
  contrastToggle.addEventListener("click", onToggle);
  cleanups.push(() => contrastToggle.removeEventListener("click", onToggle));

  const header = h(doc, "header", { className: "app-header" }, [
    h(doc, "div", { className: "app-container app-header__inner" }, [
      h(doc, "div", { className: "app-brand" }, [
        h(doc, "span", { className: "app-brand__mark", "aria-hidden": "true" }),
        h(doc, "h1", { className: "app-brand__name" }, "Empyrean"),
        h(doc, "span", { className: "ui-chip ui-chip--outline" }, "Prototype"),
      ]),
      h(doc, "div", { className: "app-header__purpose" }, [
        h(doc, "p", { className: "app-header__tagline" }, "Touch an object. Hear its name."),
        h(
          doc,
          "p",
          { className: "app-header__explainer" },
          "This page mirrors what the glasses see, which object is being touched, and what the speaker says.",
        ),
      ]),
      h(doc, "div", { className: "app-header__tools", role: "group", "aria-label": "Display options" }, [contrastToggle]),
    ]),
  ]);

  const roots = {};
  const slots = AREAS.map((area) => {
    const slot = h(doc, "section", {
      id: area.id,
      className: `app-slot app-slot--${area.key}`,
      "aria-label": area.label,
      "aria-busy": "true",
      "data-area": area.key,
      tabindex: "-1",
    });
    slot.append(loadingPlaceholder(doc, area.label));
    roots[area.key] = slot;
    return slot;
  });

  const main = h(doc, "main", { id: "main", className: "app-main", tabindex: "-1" }, [
    h(doc, "div", { className: "app-container app-layout" }, slots),
  ]);

  // Bauhaus redesign: a compact camera -> touch -> speech strip. The picture is
  // decorative; the three steps are real text.
  const howItWorks = h(doc, "figure", { className: "app-how" }, [
    h(doc, "img", {
      className: "app-how__art",
      src: "/static/assets/illustrations/how-it-works.svg",
      alt: "",
      "aria-hidden": "true",
      width: "600",
      height: "120",
    }),
    h(doc, "figcaption", { className: "app-how__steps" }, [
      h(doc, "ol", {}, [
        h(doc, "li", {}, "The camera sees objects and hands."),
        h(doc, "li", {}, "A fingertip lands on an object."),
        h(doc, "li", {}, "The speaker says its name."),
      ]),
    ]),
  ]);

  const footer = h(doc, "footer", { className: "app-footer" }, [
    h(doc, "div", { className: "app-container app-footer__inner" }, [
      howItWorks,
      h(
        doc,
        "p",
        { className: "app-footer__note" },
        "Research prototype. Names and warnings can be missed or wrong, so a quiet page does not mean the way ahead is clear.",
      ),
    ]),
  ]);

  root.replaceChildren(skipLink, header, main, footer);

  return {
    roots: Object.freeze(roots),
    main,

    /** Reflect the active theme in the contrast toggle. */
    setTheme(next) {
      contrastToggle.setAttribute("aria-pressed", next === "high-contrast" ? "true" : "false");
    },

    /** Clear loading placeholders and aria-busy once a feature has mounted. */
    markMounted(keys) {
      for (const key of keys) {
        const slot = roots[key];
        if (!slot) continue;
        slot.removeAttribute("aria-busy");
        for (const child of [...slot.children]) {
          if (child.hasAttribute("data-shell-placeholder")) child.remove();
        }
      }
    },

    /** Replace a failed feature's mounts with an understandable message. */
    showFeatureError(keys, error) {
      keys.forEach((key, index) => {
        const slot = roots[key];
        if (!slot) return;
        const area = AREAS.find((a) => a.key === key);
        slot.removeAttribute("aria-busy");
        const technical = [error?.message, error?.cause?.message].filter(Boolean).join(": ");
        slot.replaceChildren(
          h(doc, "div", { className: "ui-feature-error", role: index === 0 ? "alert" : null }, [
            h(doc, "p", { className: "ui-feature-error__title" }, `Could not show ${area.label.toLowerCase()}`),
            h(
              doc,
              "p",
              {},
              "This part of the dashboard did not start. The rest of the page still works. Reload the page to try again.",
            ),
            technical
              ? h(doc, "details", {}, [h(doc, "summary", {}, "Technical details"), h(doc, "code", {}, technical)])
              : null,
          ]),
        );
      });
    },

    /** Remove listeners and the shell's elements. */
    destroy() {
      for (const cleanup of cleanups.splice(0)) cleanup();
      root.replaceChildren();
    },
  };
}
