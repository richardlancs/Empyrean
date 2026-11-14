// Experience feature: current touch, camera, recognized objects and
// last-touch search. Mounted by the shell as mountExperience(ctx).
//
// This module is the feature controller. It subscribes to the shared store,
// keeps local view preferences (presentation only), turns snapshots into view
// models with selectors.js, and hands them to leaf components. It never opens
// a socket; network requests go through ctx.request (last-seen search only).

import { createCameraPanel } from "./camera-panel.js";
import { createFindPanel } from "./find-panel.js";
import { createLastSeenController } from "./last-seen.js";
import { createObjectList } from "./object-list.js";
import { createTouchCard } from "./touch-card.js";
import { createSpeechSignal, signalShouldMove } from "../../components/speech-signal.js";
import {
  selectCamera,
  selectCurrentTouch,
  selectFindAvailability,
  selectObjects,
  selectSpeech,
  selectTouchCard,
  serverNow,
  videoUrl,
} from "./selectors.js";

/** Re-render ages and freshness this often. Presentation only. */
const TICK_MS = 1000;
const STREAM_RETRY_MIN_MS = 1000;
const STREAM_RETRY_MAX_MS = 10000;
const PREFS_KEY = "empyrean.experience.camera";

function loadCameraPrefs() {
  const defaults = { fit: "contain", boxes: true, hands: true, labels: true };
  try {
    const saved = JSON.parse(localStorage.getItem(PREFS_KEY) || "null");
    if (saved && typeof saved === "object") {
      return {
        fit: saved.fit === "actual" ? "actual" : "contain",
        boxes: saved.boxes !== false,
        hands: saved.hands !== false,
        labels: saved.labels !== false,
      };
    }
  } catch {
    // Storage may be blocked; defaults are fine.
  }
  return defaults;
}

function saveCameraPrefs(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore: preferences are a convenience.
  }
}

/** Mount the four experience panels into ctx.roots; returns a cleanup function. */
export function mountExperience(ctx) {
  const { roots } = ctx;
  const announce = typeof ctx.announce === "function" ? ctx.announce : () => {};

  // Local, presentation-only preferences. Never sent to the engine except as
  // /video drawing options.
  const camera = loadCameraPrefs();
  const view = { selectedId: null, expanded: new Set() };
  let snapshot = { state: null, connection: "connecting", receivedAt: null };
  let streamStatus = "idle";
  let streamNonce = 0;
  let streamRetryMs = STREAM_RETRY_MIN_MS;
  let streamRetryTimer = null;
  let wasConnected = false;
  let disposed = false;

  let lastTouchKey = null;
  let lastSpeechKey = null;
  let lastCameraKind = null;
  let findView = { status: "idle", query: "", answer: "", matchedAt: null, message: "" };
  let findGeneration = 0;

  const touchCard = roots.touch ? createTouchCard(roots.touch) : null;
  // Moves only while telemetry says a real engine is speaking (never for fake or log-only audio).
  const signal = touchCard?.signalRoot ? createSpeechSignal(touchCard.signalRoot) : null;
  const cameraPanel = roots.camera
    ? createCameraPanel(roots.camera, {
        onStream(status) {
          streamStatus = status;
          if (status === "loaded") streamRetryMs = STREAM_RETRY_MIN_MS;
          if (status === "error") scheduleStreamRetry();
          render();
        },
        onOption(name, value) {
          camera[name] = value;
          saveCameraPrefs(camera);
          render();
        },
      })
    : null;
  const objectList = roots.objects
    ? createObjectList(roots.objects, {
        onSelect(id) {
          view.selectedId = id;
          render();
        },
        onToggleName(id) {
          if (view.expanded.has(id)) view.expanded.delete(id);
          else view.expanded.add(id);
          render();
        },
      })
    : null;
  const lastSeen = createLastSeenController({
    request: (path, options) => ctx.request(path, options),
    onChange(next) {
      if (next.status === "loading") findGeneration += 1;
      findView = next;
      if (["found", "not_found", "unavailable", "timeout", "error"].includes(next.status)) {
        const text = next.status === "found" || next.status === "not_found" ? next.answer || "No recorded touch matches." : next.message;
        announce(text, { priority: "polite", key: `find:${findGeneration}:${next.status}` });
      }
      render();
    },
  });
  const findPanel = roots.find
    ? createFindPanel(roots.find, {
        onSearch: (query) => lastSeen.search(query),
        onRetry: () => lastSeen.retry(),
      })
    : null;

  function scheduleStreamRetry() {
    if (streamRetryTimer !== null || disposed) return;
    streamRetryTimer = setTimeout(() => {
      streamRetryTimer = null;
      streamNonce += 1;
      render();
    }, streamRetryMs);
    streamRetryMs = Math.min(streamRetryMs * 2, STREAM_RETRY_MAX_MS);
  }

  function announceEvents(nowMs) {
    const state = snapshot.state;
    if (!state) return;
    const touch = selectCurrentTouch(state);
    const touchKey = touch ? `touch:${touch.objectId}:${touch.ts ?? touch.text}` : null;
    if (touchKey && touchKey !== lastTouchKey && touch.state !== "held") {
      announce(`Touching ${touch.text}`, { priority: "polite", key: touchKey });
    }
    lastTouchKey = touchKey;

    const speech = state.speech;
    const speechKey = speech ? `speech:${speech.ts}:${speech.status}` : null;
    if (speechKey && speechKey !== lastSpeechKey && speech.status === "failed") {
      announce(selectSpeech(state, null).title, { priority: "polite", key: speechKey });
    }
    lastSpeechKey = speechKey;

    const cam = selectCamera(snapshot, streamStatus, nowMs);
    // Integration (Agent 4): a lost dashboard connection is announced by the shell
    // only; the camera announces only its own problems while the page is connected.
    const connected = snapshot.connection === "connected";
    if (connected && cam.kind !== lastCameraKind && lastCameraKind !== null && (cam.kind === "stale" || cam.kind === "disconnected")) {
      const frameTs = state.diagnostics?.camera?.last_frame_ts ?? "none";
      announce(`Camera: ${cam.title}`, { priority: "polite", key: `camera:${cam.kind}:${frameTs}` });
    }
    lastCameraKind = cam.kind;
  }

  function render() {
    if (disposed) return;
    const nowMs = Date.now();
    const prefs = { selectedId: view.selectedId, expanded: view.expanded };
    const cam = selectCamera(snapshot, streamStatus, nowMs);

    touchCard?.update(selectTouchCard(snapshot, nowMs));
    signal?.update({ active: snapshot.connection === "connected" && signalShouldMove(snapshot.state?.speech) });
    cameraPanel?.update(
      cam,
      camera,
      videoUrl(
        {
          overlaysSupported: cam.overlaysSupported,
          boxes: camera.boxes,
          hands: camera.hands,
          labels: camera.labels,
          selectedId: view.selectedId,
        },
        streamNonce,
      ),
    );
    objectList?.update(selectObjects(snapshot, prefs, nowMs));
    findPanel?.update(
      selectFindAvailability(snapshot.state),
      findView,
      serverNow(snapshot.state, snapshot.receivedAt, nowMs),
    );
    announceEvents(nowMs);
  }

  const unsubscribe = ctx.subscribe((next) => {
    const connected = next.connection === "connected";
    // The old MJPEG stream usually dies with a server restart: reopen once
    // after a reconnect, not on every snapshot.
    if (connected && !wasConnected && snapshot.receivedAt !== null) streamNonce += 1;
    wasConnected = connected;
    snapshot = next;
    render();
  });
  const ticker = setInterval(render, TICK_MS);

  return function cleanup() {
    disposed = true;
    if (typeof unsubscribe === "function") unsubscribe();
    clearInterval(ticker);
    if (streamRetryTimer !== null) clearTimeout(streamRetryTimer);
    lastSeen.dispose();
    signal?.destroy();
    touchCard?.destroy();
    cameraPanel?.destroy();
    objectList?.destroy();
    findPanel?.destroy();
  };
}
