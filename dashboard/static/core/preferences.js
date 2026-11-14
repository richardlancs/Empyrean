// Local view preferences for this browser only (theme, and anything a feature
// wants to remember about its own presentation). Kept apart from the store:
// nothing here is sent to the server or changes what the engine does.
//
// Storage can be missing or throw (private windows, blocked site data). Reads then
// fall back to defaults and writes to memory for this page, with one warning.

export const PREFERENCE_PREFIX = "empyrean.";
export const THEME_PREFERENCE = "theme";
export const THEMES = Object.freeze(["light", "high-contrast"]);

/** window.localStorage, or null if the browser refuses access to it. */
export function safeLocalStorage(win = globalThis) {
  try {
    return win.localStorage ?? null;
  } catch {
    return null;
  }
}

/**
 * Create a preference store.
 * @param {object} [options]
 * @param {Storage|null} [options.storage]
 * @param {(message: string, error?: unknown) => void} [options.onWarning]
 */
export function createPreferences({ storage = safeLocalStorage(), onWarning = (m, e) => console.warn(m, e) } = {}) {
  const memory = new Map();
  const listeners = new Map();
  let warned = false;

  function warnOnce(error) {
    if (warned) return;
    warned = true;
    onWarning("Display preferences cannot be saved in this browser; they will reset when the page reloads.", error);
  }

  if (!storage) warnOnce();

  function read(name) {
    if (memory.has(name)) return memory.get(name);
    if (!storage) return undefined;
    let raw;
    try {
      raw = storage.getItem(PREFERENCE_PREFIX + name);
    } catch (error) {
      warnOnce(error);
      return undefined;
    }
    if (raw === null) return undefined;
    try {
      return JSON.parse(raw);
    } catch {
      return raw; // a plain string written by an older page
    }
  }

  return {
    /** Stored value for name, or fallback. */
    get(name, fallback = undefined) {
      const value = read(name);
      return value === undefined ? fallback : value;
    },

    /** Save value for name (memory always; storage when possible) and notify. */
    set(name, value) {
      memory.set(name, value);
      if (storage) {
        try {
          storage.setItem(PREFERENCE_PREFIX + name, JSON.stringify(value));
        } catch (error) {
          warnOnce(error);
        }
      }
      for (const listener of [...(listeners.get(name) ?? [])]) listener(value);
    },

    /** Call listener(value) whenever name is set; returns unsubscribe. */
    subscribe(name, listener) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(listener);
      return () => listeners.get(name)?.delete(listener);
    },
  };
}

/**
 * Theme to use: the saved choice, else high contrast if the OS asks for more
 * contrast, else light. Mirrors core/theme-boot.js, which runs before first paint.
 */
export function resolveTheme(preferences, matchMedia = globalThis.matchMedia?.bind(globalThis)) {
  const saved = preferences.get(THEME_PREFERENCE);
  if (THEMES.includes(saved)) return saved;
  try {
    if (matchMedia?.("(prefers-contrast: more)").matches) return "high-contrast";
  } catch {
    // matchMedia unsupported: fall through to the default
  }
  return "light";
}

/** Apply a theme to <html data-theme>. Unknown values fall back to light. */
export function applyTheme(rootElement, theme) {
  rootElement.setAttribute("data-theme", THEMES.includes(theme) ? theme : "light");
}
