// Pure selectors and presenters for the experience feature.
//
// Every function here turns backend snapshot data (plus local view preferences)
// into plain view models. Nothing here touches the DOM, the network or timers,
// so the same code runs in the browser and under `node --test`.
//
// Honesty rules applied throughout:
// - Missing instrumentation means "unknown" or "unavailable", never success.
// - An open socket or a loaded image does not prove camera frames are current.
// - A TouchEvent does not prove speech played; only `state.speech` reports audio.

/** Seconds without a new camera frame before the image is marked stale. */
export const FRAME_STALE_SECONDS = 2;
/** Seconds without any snapshot before touch/object data is treated as old. */
export const SNAPSHOT_STALE_SECONDS = 3;
/** Names longer than this get a "Show full name" control. */
export const LONG_NAME_CHARS = 28;

export const OBJECT_STATE_LABELS = Object.freeze({
  new: "New",
  idle: "In view",
  touching: "Touching",
  held: "Holding",
  lost: "Temporarily lost",
});

// Friendly clarity: short, plain status words. "Completed" never claims anyone heard it.
export const SPEECH_STATUS_LABELS = Object.freeze({
  queued: "Queued",
  speaking: "Speaking",
  completed: "Completed",
  interrupted: "Interrupted",
  failed: "Failed",
});

/** Lead sentence when no sound can have played, shown before any status word. */
export const SPEECH_NO_SOUND_LEAD = Object.freeze({
  fake: "Demo audio — no sound.",
  unavailable: "No sound — the speech engine is unavailable, so phrases are only logged.",
});

/** Return the server's idea of "now", advanced by browser time since receipt. */
export function serverNow(state, receivedAt, browserNowMs) {
  if (!state || typeof state.now !== "number") return null;
  if (typeof receivedAt !== "number") return state.now;
  return state.now + Math.max(0, browserNowMs - receivedAt) / 1000;
}

/** Return seconds between `now` and `ts`, or null if either is unknown. */
export function ageSeconds(now, ts) {
  if (typeof now !== "number" || typeof ts !== "number") return null;
  return Math.max(0, now - ts);
}

/** Calm, human wording for an age in seconds. Never shows decimals. */
export function humanAgo(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "Unknown";
  if (seconds < 5) return "just now";
  if (seconds < 60) return "less than a minute ago";
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`;
  }
  const hours = Math.floor(seconds / 3600);
  if (hours < 24) return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

/** Wall-clock time (local) for a Unix-seconds timestamp. */
export function clockTime(ts) {
  if (typeof ts !== "number") return "Unknown time";
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function objectText(obj) {
  if (!obj) return "";
  return obj.text || obj.name || obj.class_label || "Unknown object";
}

/**
 * Freshness of the snapshot data as a whole: connection plus how recent it is.
 * Returns {kind, message} where kind is "none" | "current" | "old" | "disconnected".
 */
export function selectDataFreshness({ state, connection, receivedAt }, browserNowMs) {
  if (!state) return { kind: "none", message: "Waiting for the first update from the laptop." };
  if (connection !== "connected") {
    return { kind: "disconnected", message: "Dashboard connection lost. What you see may be out of date." };
  }
  const age = typeof receivedAt === "number" ? (browserNowMs - receivedAt) / 1000 : null;
  if (age !== null && age > SNAPSHOT_STALE_SECONDS) {
    return { kind: "old", message: `No update from the laptop for ${Math.round(age)} s. Information may be out of date.` };
  }
  const frameTs = state.diagnostics?.camera?.last_frame_ts;
  const frameAge = ageSeconds(serverNow(state, receivedAt, browserNowMs), frameTs);
  if (frameAge !== null && frameAge > FRAME_STALE_SECONDS) {
    return { kind: "old", message: `No new camera frame for ${Math.round(frameAge)} s. Touch and object information may be out of date.` };
  }
  return { kind: "current", message: "" };
}

// ---------------------------------------------------------------------------
// Camera

/**
 * Camera view model from real frame timestamps.
 * `stream` is the local <img> status: "idle" | "loading" | "loaded" | "error".
 */
export function selectCamera(snapshot, stream, browserNowMs) {
  const { state, connection, receivedAt } = snapshot;
  const now = serverNow(state, receivedAt, browserNowMs);
  const cam = state?.diagnostics?.camera ?? null;
  const fps = typeof cam?.fps === "number" ? cam.fps : null;
  const width = typeof cam?.width === "number" ? cam.width : null;
  const height = typeof cam?.height === "number" ? cam.height : null;
  const lastFrameTs = typeof cam?.last_frame_ts === "number" ? cam.last_frame_ts : null;
  const frameAge = ageSeconds(now, lastFrameTs);
  const footer = {
    fps: fps === null ? "Unknown" : `${fps.toFixed(fps < 10 ? 1 : 0)} fps`,
    frameAge: frameAge === null ? "Unknown" : frameAge < 1 ? "under 1 s" : `${Math.round(frameAge)} s`,
    size: width && height ? `${width} × ${height}` : "Unknown",
  };

  let kind;
  let title;
  let detail = "";
  if (stream === "error") {
    kind = "disconnected";
    title = "Video stream disconnected";
    detail = "Trying to reconnect. The camera may still be running on the laptop.";
  } else if (!state) {
    kind = "starting";
    title = "Starting";
    detail = "Waiting for the first update from the laptop.";
  } else if (connection !== "connected") {
    kind = "stale";
    title = "Dashboard connection lost";
    detail = "The picture may be frozen until the connection returns.";
  } else if (!cam) {
    kind = "unknown";
    title = "Frame timing unavailable";
    detail = "The laptop does not report frame times, so this view cannot confirm the picture is current.";
  } else if (lastFrameTs === null) {
    kind = cam.status === "offline" ? "offline" : "waiting";
    title = cam.status === "offline" ? "Camera offline" : "Waiting for the first frame";
    detail = cam.detail || "";
  } else if (frameAge > FRAME_STALE_SECONDS) {
    kind = "stale";
    title = "Picture is out of date";
    detail = `No new frame for ${Math.round(frameAge)} s (last at ${clockTime(lastFrameTs)}).`;
  } else if (stream !== "loaded") {
    kind = "waiting";
    title = "Opening video";
    detail = "";
  } else {
    kind = "live";
    title = "Live";
    detail = cam.status === "degraded" ? cam.detail || "Camera reports reduced performance." : "";
    // Integration (Agent 4): a recorded clip is current, but it is not a camera.
    if (cam.mode === "fake") {
      // Friendly clarity: the title already says it; the alt text gives the long form.
      title = "Live (recorded clip, not a camera)";
    }
  }
  return {
    kind,
    title,
    detail,
    isCurrent: kind === "live",
    footer,
    overlaysSupported: state?.capabilities?.overlays === true,
    altText: cameraAltText(kind, cam, frameAge),
  };
}

/**
 * Friendly clarity: alternative text that says what the picture really is now:
 * a live camera, a recorded demo clip, an out-of-date frame, or nothing usable.
 */
export function cameraAltText(kind, cam, frameAge) {
  if (kind === "live") {
    return cam?.mode === "fake"
      ? "Recorded demo clip, not a live camera, with object boxes and fingertip markers drawn by the laptop."
      : "Live camera view from the glasses, with object boxes and fingertip markers drawn by the laptop.";
  }
  if (kind === "stale") {
    const age = typeof frameAge === "number" ? ` for ${Math.round(frameAge)} seconds` : "";
    return `Out-of-date camera picture: no new frame${age}. This is the last frame received.`;
  }
  if (kind === "disconnected") return "Camera video unavailable: the video stream disconnected.";
  if (kind === "offline") return "Camera unavailable: the camera is offline.";
  if (kind === "waiting" || kind === "starting") return "Camera picture not available yet: waiting for the first frame.";
  return "Camera picture of unknown freshness: the laptop does not report frame times.";
}

/**
 * Build the /video URL from presentation-only overlay options.
 * When overlays are not supported the plain /video URL is used, which keeps the
 * server's existing behaviour. `nonce` forces a deliberate reopen.
 */
export function videoUrl({ overlaysSupported, boxes, hands, labels, selectedId }, nonce = 0) {
  const params = new URLSearchParams();
  if (overlaysSupported) {
    params.set("boxes", boxes ? "1" : "0");
    params.set("hands", hands ? "1" : "0");
    params.set("labels", labels ? "1" : "0");
    if (selectedId !== null && selectedId !== undefined) params.set("selected_id", String(selectedId));
  }
  if (nonce) params.set("r", String(nonce));
  const query = params.toString();
  return query ? `/video?${query}` : "/video";
}

// ---------------------------------------------------------------------------
// Current touch

/** The real current touch: `current_touch`, or a touching/held object as a fallback. */
export function selectCurrentTouch(state) {
  if (!state) return null;
  if ("current_touch" in state) {
    const t = state.current_touch;
    if (!t) return null;
    return { objectId: t.object_id ?? null, text: t.text || "Unknown object", state: t.state, ts: t.ts ?? null };
  }
  // Older backend without current_touch: the scene's own object states are real data.
  const touched = (state.objects || []).find((o) => o.state === "touching" || o.state === "held");
  if (!touched) return null;
  return { objectId: touched.object_id, text: objectText(touched), state: touched.state, ts: null };
}

/** The most recent touch in the event log, for "Last touched". */
export function selectLastTouched(state) {
  const event = (state?.events || []).find((e) => e.kind === "touch");
  if (!event) return null;
  return { text: event.text || "Unknown object", ts: event.ts ?? null, detail: event.detail || "" };
}

function touchStateLabel(value) {
  if (value === "held") return "Holding";
  if (value === "touching") return "Touching";
  return value ? String(value) : "Touching";
}

/** Speech view model; only `state.speech` counts as audio evidence. */
export function selectSpeech(state, now) {
  const caps = state?.capabilities;
  const speech = state?.speech;
  if (!state || caps?.speech_status === false || !speech) {
    return {
      kind: "unavailable",
      title: "Audio status unavailable",
      detail: caps?.speech_status === false
        ? "This laptop does not report what the speaker is doing."
        : "No speech has been reported yet.",
      phrase: "",
      time: "",
      modeNote: "",
      lead: "",
    };
  }
  const status = SPEECH_STATUS_LABELS[speech.status] ? speech.status : "unknown";
  // Demo or log-only audio: the absence of sound leads; the status word follows quietly.
  const lead = SPEECH_NO_SOUND_LEAD[speech.mode] || "";
  const modeNote = lead;
  let detail = "";
  if (status === "interrupted") {
    const warning = state.latest_real_warning;
    const ts = typeof speech.ts === "number" ? speech.ts : null;
    if (warning && ts !== null && typeof warning.ts === "number" && warning.ts >= ts - 0.5) {
      detail = "A warning was raised at about this time. Alarms take priority over speech.";
    } else {
      detail = "Newer audio replaced it.";
    }
  } else if (status === "completed") {
    detail = "Completed by the laptop's audio system. This does not confirm it was heard.";
  } else if (status === "failed") {
    detail = "The audio system reported an error.";
  }
  const age = ageSeconds(now, speech.ts);
  return {
    kind: status,
    title: status === "unknown" ? "Audio status unknown" : SPEECH_STATUS_LABELS[status],
    detail,
    phrase: speech.text || "",
    time: typeof speech.ts === "number" ? `${clockTime(speech.ts)} · ${humanAgo(age)}` : "",
    modeNote,
    lead,
  };
}

/** The current object's recent crop, if the server offers one (never invented). */
function currentThumbnail(state, objectId) {
  if (state?.capabilities?.thumbnails !== true || objectId === null) return null;
  const obj = (state.objects || []).find((o) => o.object_id === objectId);
  return obj?.thumbnail_url || null;
}

/** Everything the touch card needs. */
export function selectTouchCard(snapshot, browserNowMs) {
  const { state } = snapshot;
  const now = serverNow(state, snapshot.receivedAt, browserNowMs);
  const current = selectCurrentTouch(state);
  const last = selectLastTouched(state);
  const freshness = selectDataFreshness(snapshot, browserNowMs);
  return {
    loading: !state,
    freshness,
    current: current
      ? {
          objectId: current.objectId,
          text: current.text,
          stateLabel: touchStateLabel(current.state),
          stateKey: current.state === "held" ? "held" : "touching",
          since: current.ts !== null ? `Since ${clockTime(current.ts)}` : "",
          thumbnailUrl: currentThumbnail(state, current.objectId),
        }
      : null,
    lastTouched:
      last && !(current && last.text === current.text)
        ? { text: last.text, when: last.ts !== null ? `${clockTime(last.ts)} · ${humanAgo(ageSeconds(now, last.ts))}` : "" }
        : null,
    speech: selectSpeech(state, now),
  };
}

// ---------------------------------------------------------------------------
// Objects

/** User-facing naming status, from `naming_status` when supplied. */
export function namingInfo(obj) {
  const status = obj.naming_status;
  if (status === "pending") return { key: "pending", label: "Naming in progress" };
  if (status === "named") return { key: "named", label: "" };
  if (status === "fallback") return { key: "fallback", label: "General name" };
  if (status === "failed") return { key: "failed", label: "Naming failed, showing general name" };
  if (obj.named === true) return { key: "named", label: "" };
  if (obj.state === "new") return { key: "unknown", label: "Not named yet" };
  return { key: "unknown", label: "No specific name" };
}

/** Rows plus counts for the object list. Order follows the backend. */
export function selectObjects(snapshot, prefs, browserNowMs) {
  const { state } = snapshot;
  const now = serverNow(state, snapshot.receivedAt, browserNowMs);
  const objects = state?.objects || [];
  const thumbsOn = state?.capabilities?.thumbnails === true;
  const rows = objects.map((obj) => {
    const text = objectText(obj);
    const age = ageSeconds(now, obj.last_seen_ts);
    return {
      id: obj.object_id,
      text,
      classLabel: obj.class_label || "",
      rawState: obj.state,
      stateLabel: OBJECT_STATE_LABELS[obj.state] || "Unknown state",
      naming: namingInfo(obj),
      lastSeen: `Last seen ${humanAgo(age)}`,
      lastSeenExact: typeof obj.last_seen_ts === "number" ? clockTime(obj.last_seen_ts) : "",
      isLong: text.length > LONG_NAME_CHARS,
      expanded: prefs.expanded.has(obj.object_id),
      selected: prefs.selectedId === obj.object_id,
      thumbnailUrl: thumbsOn && obj.thumbnail_url ? obj.thumbnail_url : null,
    };
  });
  const lost = rows.filter((r) => r.rawState === "lost").length;
  const inView = rows.length - lost;
  let summary;
  if (!state) summary = "Waiting for the first update.";
  else if (rows.length === 0) summary = "No objects recognized right now.";
  else {
    summary = `${inView} in view`;
    if (lost) summary += `, ${lost} temporarily lost (hidden from the camera for a moment)`;
  }
  const selectedMissing = prefs.selectedId !== null && !rows.some((r) => r.id === prefs.selectedId);
  const freshness = selectDataFreshness(snapshot, browserNowMs);
  const staleNote = freshness.kind === "old" || freshness.kind === "disconnected" ? freshness.message : "";
  return { rows, inView, lost, summary, selectedMissing, staleNote, thumbnailsSupported: thumbsOn };
}

// ---------------------------------------------------------------------------
// Find

/** Whether the last-seen search can be offered, with an honest reason if not. */
export function selectFindAvailability(state) {
  if (!state) return { enabled: false, reason: "Waiting for the laptop to connect." };
  if (state.capabilities && state.capabilities.last_seen === false) {
    return { enabled: false, reason: "Touch history search is not available on this laptop right now." };
  }
  return { enabled: true, reason: "" };
}

// ---------------------------------------------------------------------------
// Detector choice (Regular | Demo). The engine's DetectorStatus is the truth:
// a button reads as active only after vision confirms it; a request in flight,
// a switch in progress, a failure or a lost connection each say so in words.

const MODE_NAME = { actual: "Regular", demo: "Demo" };
const SUPPORT = {
  actual: "General-purpose object detection.",
  trained: "Custom model trained for our demo objects.",
  "prompt-fallback": "Fallback detector using visual prompts. This is not the demo-trained model.",
  fake: "Test clip: no detector runs, so this choice changes only the label.",
};
const BADGE = {
  trained: "Demo-trained model",
  "prompt-fallback": "Demo fallback, not trained",
  fake: "Demo label only (fake vision)",
};

/** The checkpoint's recorded training status, e.g. "experimental; NOT demo-ready", or "". */
export function checkpointStatus(checkpoint) {
  const match = /status: (.+)$/.exec(typeof checkpoint === "string" ? checkpoint : "");
  return match ? match[1].trim() : "";
}

/**
 * View model for the Regular | Demo control.
 * local = { sending, error, at } for this page's own request only: sending is the mode asked
 * for, error a refusal message, at the detector updated_ts when it was refused.
 */
export function selectDetector(snapshot, local = { sending: null, error: null }) {
  const state = snapshot?.state ?? null;
  const connected = snapshot?.connection === "connected";
  const d = state?.detector ?? null;
  const base = {
    visible: true,
    locked: true,
    pressed: null,
    busy: null,
    tone: "neutral",
    status: "",
    support: "",
    note: "",
    badge: null,
  };
  if (!state) return { ...base, status: "Waiting for the dashboard to connect." };
  if (!state.capabilities?.mode_switch || !d) {
    return { ...base, status: "Choosing a detector is not available on this server." };
  }
  if (d.state === "unknown" || !MODE_NAME[d.active_mode]) {
    return { ...base, status: "Vision has not reported which detector is running yet." };
  }

  const active = d.active_mode;
  const kind = active === "demo" ? d.demo_kind : null;
  const vm = {
    ...base,
    locked: false,
    pressed: active,
    support: active === "demo" ? SUPPORT[kind] || "Demo detector." : SUPPORT.actual,
    badge: active === "demo" && BADGE[kind] ? { kind, text: BADGE[kind] } : null,
    tone: "ok",
    status: `${MODE_NAME[active]} is active.`,
  };
  const recorded = kind === "trained" ? checkpointStatus(d.checkpoint) : "";
  if (recorded && !/^demo-ready$/i.test(recorded)) vm.note = `Checkpoint status: ${recorded}.`;
  if (d.fake && active === "actual") vm.note = "Test clip: no detector is running.";
  if (d.demo_available === false && active === "actual" && !d.fake) vm.note = "No demo-trained checkpoint is installed.";

  const other = active === "demo" ? "actual" : "demo";
  if (!connected) {
    return {
      ...vm,
      locked: true,
      tone: "neutral",
      status: `Disconnected. ${MODE_NAME[active]} was active when the page lost its connection; switching resumes after it reconnects.`,
    };
  }
  if (d.state === "switching") {
    const target = MODE_NAME[d.switching_to] ? d.switching_to : other;
    return {
      ...vm,
      locked: true,
      busy: target,
      tone: "busy",
      status: `Switching to ${MODE_NAME[target]}… ${MODE_NAME[active]} stays on until ${MODE_NAME[target]} is ready.`,
    };
  }
  if (local.sending) {
    return { ...vm, locked: true, busy: local.sending, tone: "busy", status: `Asking to switch to ${MODE_NAME[local.sending]}…` };
  }
  if (d.state === "failed") {
    const failed = MODE_NAME[d.failed_mode] || null;
    const lead = failed ? `Could not switch to ${failed}.` : "The last switch did not complete.";
    return {
      ...vm,
      tone: "error",
      status: `${lead} Still using ${MODE_NAME[active]}. ${d.message || ""}`.trim(),
    };
  }
  // This page's refused request, until the engine reports anything newer.
  if (local.error && (local.at ?? null) === (d.updated_ts ?? null)) {
    return { ...vm, tone: "error", status: `${local.error} Still using ${MODE_NAME[active]}.` };
  }
  return vm;
}

// ---------------------------------------------------------------------------
// Pip, the camera companion. Pose and help text come only from confirmed state:
// the camera view model, the detector view model (vision's DetectorStatus), the
// current touch and the warning. Pip never claims listening, recognition or sound.

export const PIP_TIP = "Keep the object and your hand in view.";
const CAMERA_TROUBLE = new Set(["offline", "disconnected", "stale", "unknown"]);

/** What Pip says about the detector, in Pip's voice, without overstating anything. */
function pipModeLine(d, detectorVm) {
  if (!d || d.state === "unknown" || !detectorVm?.pressed) {
    return "Vision has not said which detector is running yet.";
  }
  if (d.fake) {
    return `This is a recorded test clip, so no detector is running. The control is set to ${detectorVm.pressed === "demo" ? "Demo" : "Regular"}.`;
  }
  if (d.active_mode === "demo") {
    if (d.demo_kind === "trained") return "I’m using the model trained for our demo objects.";
    if (d.demo_kind === "prompt-fallback") return "I’m using a fallback detector, not the model trained for our demo objects.";
    return "I’m using a demo detector.";
  }
  return "I’m using the general-purpose detector.";
}

/**
 * Pip's view model.
 * cam: selectCamera() result. detectorVm: selectDetector() result. touch: selectCurrentTouch() result.
 * Returns { pose, mode, recovery, tip } where pose is
 * "recline" | "attentive" | "wait" | "concerned".
 */
export function selectPip(snapshot, cam, detectorVm, touch) {
  const state = snapshot?.state ?? null;
  const d = state?.detector ?? null;
  // An active real hazard hides Pip through layout.css (the warning slot's urgent
  // emphasis), the same switch that hides every other Pip, so there is one source of truth.
  const base = { pose: "recline", mode: pipModeLine(d, detectorVm), recovery: "", tip: PIP_TIP };

  if (cam && CAMERA_TROUBLE.has(cam.kind)) {
    const fix = {
      offline: "The camera is offline. Check that it is plugged in, then restart the app.",
      disconnected: "The video stream dropped. I’ll show the picture again when it reconnects.",
      stale: snapshot?.connection === "connected"
        ? "The picture stopped updating. Check the camera cable and that the app is still running."
        : "This page lost its connection to the laptop. It will reconnect on its own.",
      unknown: "The laptop does not report frame times, so I can’t tell whether the picture is current.",
    }[cam.kind];
    return { ...base, pose: "concerned", recovery: fix };
  }
  if (d?.state === "failed") {
    return { ...base, pose: "concerned", recovery: `The last detector switch did not finish. ${d.message || ""}`.trim() };
  }
  if (d && d.state === "switching" && detectorVm?.busy) {
    const target = detectorVm.busy === "demo" ? "Demo" : "Regular";
    return { ...base, pose: "wait", recovery: `Waiting for ${target} to load. The current detector keeps running until then.` };
  }
  if (touch) return { ...base, pose: "attentive" };
  return base;
}
