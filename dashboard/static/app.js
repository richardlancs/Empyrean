// Composition root. Wires the store, the transport clients, the announcer, the
// shell and the three feature modules together. Holds no feature logic.
//
// Dependency direction:  app.js -> components/, core/, features/*/index.js
//                        features -> core/ helpers (optional) and the context only
//                        core -> nothing outside core/

import { createAnnouncer } from "./core/announcer.js";
import { createApiClient } from "./core/api-client.js";
import { loadFeature } from "./core/feature-loader.js";
import {
  THEME_PREFERENCE,
  applyTheme,
  createPreferences,
  resolveTheme,
  safeLocalStorage,
} from "./core/preferences.js";
import { createSocketClient, dashboardSocketUrl } from "./core/socket-client.js";
import { createStore, reportError } from "./core/store.js";
import { createAppShell } from "./components/app-shell.js";

/** The feature entry modules and the mounts each one owns. */
export const FEATURES = Object.freeze([
  Object.freeze({
    name: "experience",
    url: "/static/features/experience/index.js",
    exportName: "mountExperience",
    areas: Object.freeze(["touch", "camera", "objects"]),
  }),
  Object.freeze({
    name: "operations",
    url: "/static/features/operations/index.js",
    exportName: "mountOperations",
    areas: Object.freeze(["health", "warning", "events", "demo"]),
  }),
  Object.freeze({
    name: "questions",
    url: "/static/features/questions/index.js",
    exportName: "mountQuestions",
    areas: Object.freeze(["questions"]),
  }),
]);

/**
 * Build the feature context. Each feature gets its own copy so its subscriptions
 * can be released even if its cleanup function forgets one.
 */
function createFeatureContext({ roots, store, api, announcer }) {
  const unsubscribers = new Set();
  const context = Object.freeze({
    roots,
    subscribe(callback) {
      const unsubscribe = store.subscribe(callback);
      const release = () => {
        unsubscribers.delete(release);
        unsubscribe();
      };
      unsubscribers.add(release);
      return release;
    },
    request: (path, options) => api.request(path, options),
    announce: (text, options) => announcer.announce(text, options),
  });
  return {
    context,
    releaseAll() {
      for (const release of [...unsubscribers]) release();
    },
  };
}

/**
 * Start the dashboard in root. Returns a handle with ready (resolves when both
 * features have loaded or failed) and destroy().
 */
export function startDashboard({
  win = window,
  doc = win.document,
  root = doc.getElementById("app"),
  features = FEATURES,
  importModule,
  socketUrl = dashboardSocketUrl(win.location),
} = {}) {
  if (!root) throw new Error('startDashboard needs a root element (<div id="app">)');

  const preferences = createPreferences({ storage: safeLocalStorage(win) });
  const theme = resolveTheme(preferences, win.matchMedia?.bind(win));
  applyTheme(doc.documentElement, theme);

  const store = createStore();
  const announcer = createAnnouncer({ container: doc.body });
  const api = createApiClient({ fetchImpl: win.fetch.bind(win) });

  const shell = createAppShell({
    root,
    theme,
    onThemeChange(next) {
      preferences.set(THEME_PREFERENCE, next);
      applyTheme(doc.documentElement, next);
      shell.setTheme(next);
    },
  });

  // Connection transitions are announced here, once each, so features do not
  // need to (and must not) announce them too.
  let wasConnected = false;
  let losses = 0;
  function onConnectionChange(connection) {
    store.setConnection(connection);
    if (connection === "reconnecting" && wasConnected) {
      losses += 1;
      announcer.announce("Dashboard connection lost. Reconnecting.", { key: `connection-lost:${losses}` });
    } else if (connection === "connected" && losses > 0) {
      announcer.announce("Dashboard connection restored.", { key: `connection-restored:${losses}` });
    }
    wasConnected = connection === "connected";
  }

  const socket = createSocketClient({
    url: socketUrl,
    WebSocketImpl: win.WebSocket,
    onState: (state) => store.receiveState(state),
    onConnectionChange,
    onError: reportError,
  });

  const onOnline = () => socket.reconnectNow();
  win.addEventListener("online", onOnline);

  const mounted = [];
  const ready = Promise.all(
    features.map(async (spec) => {
      const feature = createFeatureContext({ roots: shell.roots, store, api, announcer });
      const result = await loadFeature(spec, {
        context: feature.context,
        importModule,
        onError(error) {
          console.error(error); // keep the cause visible in the console during development
          feature.releaseAll();
          shell.showFeatureError(spec.areas, error);
        },
      });
      if (result.status === "mounted") {
        shell.markMounted(spec.areas);
        mounted.push({ ...result, releaseAll: feature.releaseAll });
      }
      return result;
    }),
  );

  socket.start();

  let destroyed = false;
  return {
    store,
    socket,
    ready,
    /** Unmount features, close the socket and remove the shell. */
    destroy() {
      if (destroyed) return;
      destroyed = true;
      win.removeEventListener("online", onOnline);
      socket.stop();
      for (const feature of mounted.splice(0)) {
        try {
          feature.cleanup?.();
        } catch (error) {
          reportError(error);
        }
        feature.releaseAll();
      }
      announcer.destroy();
      store.destroy();
      shell.destroy();
    },
  };
}

// Start automatically on the real page. Tests import this module with no #app root.
if (typeof document !== "undefined" && document.getElementById("app")) {
  globalThis.empyreanDashboard = startDashboard();
}
