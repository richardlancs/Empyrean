// Unit tests for experience selectors. Run: node --test tests/ui/agent2/
// All data here is artificial fixture data.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  humanAgo,
  namingInfo,
  selectCamera,
  selectCurrentTouch,
  selectFindAvailability,
  selectObjects,
  selectSpeech,
  selectTouchCard,
  videoUrl,
} from "../../../dashboard/static/features/experience/selectors.js";

const NOW = 1_800_000_000;
const RECEIVED = 5_000_000;

function snap(state, extra = {}) {
  return { state: { now: NOW, events: [], objects: [], ...state }, connection: "connected", receivedAt: RECEIVED, ...extra };
}
const prefs = { selectedId: null, expanded: new Set() };

test("humanAgo uses calm wording without decimals", () => {
  assert.equal(humanAgo(0.3), "just now");
  assert.equal(humanAgo(12.7), "less than a minute ago");
  assert.equal(humanAgo(61), "1 minute ago");
  assert.equal(humanAgo(240), "4 minutes ago");
  assert.equal(humanAgo(null), "Unknown");
});

test("no active touch shows the prompt and keeps the old touch separate", () => {
  const s = snap({
    current_touch: null,
    events: [{ kind: "touch", text: "FIXTURE mug", ts: NOW - 30, detail: "" }],
  });
  const vm = selectTouchCard(s, RECEIVED);
  assert.equal(vm.current, null);
  assert.equal(vm.lastTouched.text, "FIXTURE mug");
});

test("touch -> hold -> release -> retouch transitions", () => {
  const touching = selectTouchCard(snap({ current_touch: { object_id: 3, text: "FIXTURE ketchup", state: "touching", ts: NOW } }), RECEIVED);
  assert.equal(touching.current.stateLabel, "Touching");
  const held = selectTouchCard(snap({ current_touch: { object_id: 3, text: "FIXTURE ketchup", state: "held", ts: NOW } }), RECEIVED);
  assert.equal(held.current.stateLabel, "Holding");
  assert.equal(held.current.stateKey, "held");
  const released = selectTouchCard(
    snap({ current_touch: null, events: [{ kind: "touch", text: "FIXTURE ketchup", ts: NOW - 1 }] }),
    RECEIVED,
  );
  assert.equal(released.current, null);
  assert.equal(released.lastTouched.text, "FIXTURE ketchup");
  const retouch = selectCurrentTouch({ now: NOW, current_touch: { object_id: 3, text: "FIXTURE ketchup", state: "touching", ts: NOW + 2 } });
  assert.equal(retouch.ts, NOW + 2);
});

test("older backend without current_touch falls back to object states", () => {
  const t = selectCurrentTouch({ now: NOW, objects: [{ object_id: 1, text: "FIXTURE cup", state: "held" }] });
  assert.equal(t.text, "FIXTURE cup");
  assert.equal(t.state, "held");
});

test("speech is never inferred from a touch event", () => {
  const s = selectSpeech({ now: NOW, events: [{ kind: "touch", text: "x", ts: NOW }] }, NOW);
  assert.equal(s.kind, "unavailable");
  assert.equal(s.title, "Audio status unavailable");
});

test("speech statuses and modes", () => {
  const done = selectSpeech({ speech: { text: "FIXTURE mug", status: "completed", ts: NOW - 2, mode: "real" } }, NOW);
  assert.equal(done.title, "Completed"); // friendly clarity: plain status words
  assert.match(done.detail, /does not confirm/);
  const fake = selectSpeech({ speech: { text: "bottle", status: "completed", ts: NOW, mode: "fake" } }, NOW);
  assert.equal(fake.lead, "Demo audio — no sound."); // friendly clarity: no-sound leads
  const interrupted = selectSpeech(
    {
      speech: { text: "FIXTURE mug", status: "interrupted", ts: NOW - 1, mode: "real" },
      latest_real_warning: { ts: NOW - 0.8, kind: "hazard", text: "Stairs" },
    },
    NOW,
  );
  assert.equal(interrupted.title, "Interrupted");
  assert.match(interrupted.detail, /Alarms take priority/);
  const off = selectSpeech({ capabilities: { speech_status: false }, speech: null }, NOW);
  assert.equal(off.kind, "unavailable");
});

test("camera: live only with a recent frame timestamp and a loaded stream", () => {
  const cam = { status: "active", last_frame_ts: NOW - 0.2, fps: 9.6, width: 640, height: 360 };
  const live = selectCamera(snap({ diagnostics: { camera: cam } }), "loaded", RECEIVED);
  assert.equal(live.kind, "live");
  assert.equal(live.footer.size, "640 × 360");
  assert.equal(live.footer.fps, "9.6 fps");
  // Browser time moves on, no new frames arrive: stale.
  const stale = selectCamera(snap({ diagnostics: { camera: cam } }), "loaded", RECEIVED + 5000);
  assert.equal(stale.kind, "stale");
  assert.equal(stale.isCurrent, false);
});

test("camera: a loaded image without timing data is not called live", () => {
  const vm = selectCamera(snap({}), "loaded", RECEIVED);
  assert.equal(vm.kind, "unknown");
  assert.equal(vm.footer.fps, "Unknown");
});

test("camera: startup, first-frame wait, disconnect", () => {
  assert.equal(selectCamera({ state: null, connection: "connecting", receivedAt: null }, "idle", 0).kind, "starting");
  const waiting = selectCamera(snap({ diagnostics: { camera: { status: "starting", last_frame_ts: null } } }), "loaded", RECEIVED);
  assert.equal(waiting.kind, "waiting");
  assert.equal(selectCamera(snap({}), "error", RECEIVED).kind, "disconnected");
  const lost = selectCamera(snap({ diagnostics: { camera: { last_frame_ts: NOW } } }, { connection: "reconnecting" }), "loaded", RECEIVED);
  assert.equal(lost.kind, "stale");
});

test("video URL keeps plain /video when overlays are unsupported", () => {
  assert.equal(videoUrl({ overlaysSupported: false, boxes: false, hands: true, labels: true, selectedId: 4 }), "/video");
  assert.equal(
    videoUrl({ overlaysSupported: true, boxes: true, hands: false, labels: true, selectedId: 4 }),
    "/video?boxes=1&hands=0&labels=1&selected_id=4",
  );
});

test("object list: labels, counts, lost items, long names", () => {
  const long = "FIXTURE Extremely long brand product name that wraps";
  const vm = selectObjects(
    snap({
      capabilities: { thumbnails: true },
      objects: [
        { object_id: 1, text: "FIXTURE mug", state: "touching", last_seen_ts: NOW, naming_status: "named", thumbnail_url: "/t/1" },
        { object_id: 2, text: long, state: "idle", last_seen_ts: NOW },
        { object_id: 3, text: "bottle", state: "lost", last_seen_ts: NOW - 1.5, naming_status: "pending" },
      ],
    }),
    { selectedId: 9, expanded: new Set([2]) },
    RECEIVED,
  );
  assert.deepEqual(vm.rows.map((r) => r.stateLabel), ["Touching", "In view", "Temporarily lost"]);
  assert.deepEqual(vm.rows.map((r) => r.rawState), ["touching", "idle", "lost"]);
  assert.equal(vm.inView, 2);
  assert.match(vm.summary, /2 in view, 1 temporarily lost/);
  assert.equal(vm.rows[1].isLong, true);
  assert.equal(vm.rows[1].expanded, true);
  assert.equal(vm.rows[0].thumbnailUrl, "/t/1");
  assert.equal(vm.rows[0].lastSeen, "Last seen just now");
  assert.equal(vm.selectedMissing, true);
});

test("naming states: an empty name alone is not 'in progress'", () => {
  assert.equal(namingInfo({ named: false, state: "idle" }).key, "unknown");
  assert.equal(namingInfo({ naming_status: "pending" }).label, "Naming in progress");
  assert.equal(namingInfo({ naming_status: "fallback" }).label, "General name");
  assert.match(namingInfo({ naming_status: "failed" }).label, /failed/);
});

test("find availability is honest", () => {
  assert.equal(selectFindAvailability(null).enabled, false);
  assert.equal(selectFindAvailability({ capabilities: { last_seen: false } }).enabled, false);
  assert.equal(selectFindAvailability({ capabilities: { last_seen: true } }).enabled, true);
  assert.equal(selectFindAvailability({}).enabled, true);
});

test("old data is flagged when the connection drops", () => {
  const vm = selectTouchCard(snap({ current_touch: { object_id: 1, text: "x", state: "touching", ts: NOW } }, { connection: "reconnecting" }), RECEIVED);
  assert.equal(vm.freshness.kind, "disconnected");
});

test("stopped camera frames mark touch and object data as possibly old", () => {
  const s = snap({
    current_touch: { object_id: 1, text: "FIXTURE mug", state: "touching", ts: NOW - 20 },
    objects: [{ object_id: 1, text: "FIXTURE mug", state: "touching", last_seen_ts: NOW - 20 }],
    diagnostics: { camera: { status: "active", last_frame_ts: NOW - 20 } },
  });
  assert.equal(selectTouchCard(s, RECEIVED).freshness.kind, "old");
  assert.match(selectObjects(s, prefs, RECEIVED).staleNote, /No new camera frame for 20 s/);
});
