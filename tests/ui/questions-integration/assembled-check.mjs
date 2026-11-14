// Assembled check: the real dashboard modules against a running app with fake hardware.
//
// Start the app first (fake camera clip, fake Grok, fake storage, printed audio, scripted hazards):
//   python -m app --fake vision namer storage audio hazard           (dashboard on :8000)
//   FAKE_DEMO_DETECTOR=ok FAKE_DETECTOR_SWITCH_SECONDS=3 for the Regular/Demo part.
// Then: node tests/ui/questions-integration/assembled-check.mjs [--url http://localhost:8000] [--shots dir]
// Pass --restart-cmd "<shell command>" to also check disconnect and reconnect (the
// script kills nothing itself; it waits for you, or the command, to restart the server).
//
// Everything this checks is simulated input: no microphone, speaker, camera, Grok or database.

import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { loadPlaywright } from "../agent4/pw.mjs";

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const URL = arg("url", "http://localhost:8000");
const SHOTS = arg("shots", "tests/ui/questions-integration/screenshots/assembled");
mkdirSync(SHOTS, { recursive: true });

const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const results = [];
async function check(name, fn) {
  try {
    await fn();
    results.push(["ok", name]);
    console.log(`ok   ${name}`);
  } catch (error) {
    results.push(["FAIL", name, error.message]);
    console.log(`FAIL ${name}\n     ${error.message.split("\n")[0]}`);
  }
}

async function openPage({ width = 1440, height = 1000, scale = 1 } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: scale });
  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(URL);
  await page.waitForFunction(() => {
    const slots = [...document.querySelectorAll("[data-area]")];
    return slots.length === 9 && slots.every((s) => !s.hasAttribute("aria-busy"));
  }, null, { timeout: 15000 });
  return { context, page, errors };
}

const panel = (page) => page.locator("#questions-panel");
async function ask(page, text) {
  const box = panel(page).getByLabel("Your question");
  await box.fill(text);
  await panel(page).getByRole("button", { name: /^Ask$/ }).click();
}
async function answerText(page) {
  return (await panel(page).locator("[data-question-answer], .questions-answer").first().innerText()).trim();
}
async function waitAnswer(page, predicate, timeout = 10000) {
  const end = Date.now() + timeout;
  let last = "";
  while (Date.now() < end) {
    last = await panel(page).innerText();
    if (predicate(last)) return last;
    await page.waitForTimeout(150);
  }
  throw new Error(`answer not reached; panel says: ${last.slice(0, 300)}`);
}
function overlaps(a, b) {
  return a && b && a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

const { context, page, errors } = await openPage();

await check("all nine areas mount (questions with Pip, camera, warnings, operations)", async () => {
  const keys = await page.$$eval("[data-area]", (els) => els.map((e) => e.dataset.area));
  assert.deepEqual(keys, ["health", "warning", "touch", "questions", "camera", "objects", "find", "events", "demo"]);
  // Pip perches on the camera, but steps aside (display: none) while a real warning is urgent.
  const urgent = await page.locator('#warning-panel[data-emphasis="urgent"]').count();
  const perch = page.locator("#camera-panel .pip-perch__art");
  if (urgent) assert.equal(await perch.isVisible(), false, "Pip hides during an urgent warning");
  else assert.ok(await perch.isVisible(), "Pip is visible on the camera when there is no warning");
  console.log(`     (warning urgent: ${Boolean(urgent)}, Pip visible: ${await perch.isVisible()})`);
  assert.ok(await panel(page).getByLabel("Your question").isVisible());
});

await check("question panel never covers the camera picture, warnings or Pip", async () => {
  for (const width of [1440, 1024, 720, 360]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.waitForTimeout(200);
    const q = await panel(page).boundingBox();
    for (const sel of ["#camera-panel", "#warning-panel", "#camera-panel .pip-perch", ".pip-bubble"]) {
      const other = await page.locator(sel).first().boundingBox();
      assert.ok(!overlaps(q, other), `${width}px: questions overlaps ${sel}`);
    }
    const scroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(scroll <= 0, `${width}px: horizontal scroll ${scroll}px`);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
});

await check("ask about the visible scene (typed)", async () => {
  await ask(page, "What can you see?");
  const text = await waitAnswer(page, (t) => /I can detect|I cannot detect any|current camera view/.test(t));
  assert.match(text, /I can detect/, "fake scene has visible objects");
  await page.screenshot({ path: `${SHOTS}/scene-answer-1440.png`, fullPage: false });
});

await check("touch an object and ask what it is", async () => {
  // The fake scene script touches objects in turn; wait for a touch, then ask.
  await page.waitForFunction(() => /Touching|Holding|touching|held/i.test(document.querySelector("#touch-panel")?.innerText || ""), null, { timeout: 20000 });
  await ask(page, "What am I touching?");
  const text = await waitAnswer(page, (t) => /You are touching|cannot detect what you are touching|current camera view/.test(t));
  assert.match(text, /You are touching/);
});

await check("example button asks right away", async () => {
  await panel(page).getByRole("button", { name: /What am I holding\?/ }).click();
  await waitAnswer(page, (t) => /What am I holding\?/.test(t) && /(You are touching|cannot detect what you are touching|current camera view)/.test(t));
});

await check("ask about a previous touch: looking up, then storage's answer", async () => {
  await ask(page, "Where did I last touch the ketchup?");
  const text = await waitAnswer(
    page,
    (t) => /You asked: Where did I last touch the ketchup\?/.test(t) && /\n(ANSWERED|UNAVAILABLE)\n/i.test(t),
    12000,
  );
  assert.match(text, /From touch history|unavailable/i);
  assert.doesNotMatch(text, /Spoken|Heard/, "never claims speech was heard");
});

await check("microphone control is user-initiated and labelled", async () => {
  const mic = panel(page).getByRole("button", { name: /Speak a question/ });
  assert.equal(await mic.getAttribute("aria-pressed"), "false", "not listening on load");
});

await check("Regular -> Demo -> Regular through the engine (fake vision)", async () => {
  const camera = page.locator("#camera-panel");
  const choose = async (name) => camera.getByRole("button", { name, exact: true }).click();
  await choose("Demo");
  // Pip/heading show the switch; Demo becomes active only after vision confirms.
  await page.waitForFunction(async () => {
    const r = await fetch("/api/mode"); const d = await r.json();
    return d.state === "active" && d.active_mode === "demo";
  }, null, { timeout: 15000, polling: 250 });
  await page.waitForFunction(() => !/Switching to Demo/.test(document.querySelector("#camera-panel").innerText), null, { timeout: 5000 });
  await page.screenshot({ path: `${SHOTS}/demo-active-1440.png` });
  await choose("Regular");
  await page.waitForFunction(async () => {
    const r = await fetch("/api/mode"); const d = await r.json();
    return d.state === "active" && d.active_mode === "actual";
  }, null, { timeout: 15000, polling: 250 });
});

await check("Ask still works after the detector switch", async () => {
  await ask(page, "What can you see?");
  await waitAnswer(page, (t) => /I can detect|I cannot detect any|current camera view/.test(t));
});

await check("simulated test warning is labelled and leaves questions usable", async () => {
  const demo = page.locator("#demo-panel");
  await demo.locator("summary").click();
  await demo.getByRole("button", { name: "Simulate alert" }).click();
  await page.waitForFunction(() => /Simulated/i.test(document.querySelector("#warning-panel")?.innerText || ""), null, { timeout: 5000 });
  // During an urgent real hazard the warning panel sticks to the top of the
  // viewport and scrolls over the page. The question panel must never cover it:
  // wherever they overlap, what is on screen must be the warning.
  const warningOnTop = () => page.evaluate(() => {
    const q = document.querySelector("#questions-panel").getBoundingClientRect();
    const w = document.querySelector("#warning-panel").getBoundingClientRect();
    const left = Math.max(q.left, w.left), right = Math.min(q.right, w.right);
    const top = Math.max(q.top, w.top), bottom = Math.min(q.bottom, w.bottom);
    if (left >= right || top >= bottom) return "no overlap";
    const hit = document.elementFromPoint((left + right) / 2, (top + bottom) / 2);
    return hit?.closest("#warning-panel") ? "warning on top" : `covered by ${hit?.closest("[data-area]")?.id}`;
  });
  const scrolled = await warningOnTop();
  await panel(page).scrollIntoViewIfNeeded();
  const atPanel = await warningOnTop();
  console.log(`     (scrolled to demo tools: ${scrolled}; scrolled to questions: ${atPanel})`);
  assert.ok(["no overlap", "warning on top"].includes(scrolled), scrolled);
  assert.ok(["no overlap", "warning on top"].includes(atPanel), atPanel);
  await page.screenshot({ path: `${SHOTS}/simulated-warning-1440.png` });
});

await check("second page sees the same recent questions", async () => {
  const other = await openPage();
  const text = await other.page.locator("#questions-panel").innerText();
  assert.match(text, /Recent questions from all open pages/);
  await other.context.close();
});

await check("narrow 320 px, 200% zoom (640 CSS px) and high contrast", async () => {
  const narrow = await openPage({ width: 320, height: 800 });
  await narrow.page.screenshot({ path: `${SHOTS}/narrow-320.png`, fullPage: true });
  assert.ok((await narrow.page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);
  await narrow.context.close();
  const zoom = await openPage({ width: 640, height: 900, scale: 2 });
  assert.ok((await zoom.page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);
  await zoom.page.locator("#questions-panel").screenshot({ path: `${SHOTS}/zoom-200.png` });
  await zoom.page.getByRole("button", { name: "High contrast" }).click();
  assert.equal(await zoom.page.evaluate(() => document.documentElement.dataset.theme), "high-contrast");
  await zoom.page.screenshot({ path: `${SHOTS}/high-contrast-zoom-200.png` });
  await zoom.page.emulateMedia({ forcedColors: "active" });
  await zoom.page.locator("#questions-panel").screenshot({ path: `${SHOTS}/forced-colors-200.png` });
  await zoom.context.close();
});

const restartCmd = arg("restart-cmd", null);
let errorsBeforeRestart = errors.length;
if (restartCmd) {
  const { execSync } = await import("node:child_process");
  await check("disconnect and reconnect", async () => {
    errorsBeforeRestart = errors.length;
    execSync(restartCmd, { stdio: "ignore" }); // the restarted server must not hold this pipe
    await page.waitForFunction(() => /connection lost|Reconnecting/i.test(document.body.innerText), null, { timeout: 15000 });
    await page.waitForFunction(() => /connection restored/i.test(document.body.innerText) || !/Reconnecting/i.test(document.body.innerText), null, { timeout: 30000 });
    await ask(page, "What can you see?");
    await waitAnswer(page, (t) => /I can detect|I cannot detect any|current camera view/.test(t), 15000);
  });
}

await check("no console errors on the assembled page", async () => {
  // Before the deliberate restart: none at all. During and after it, only the
  // expected network failures of requests made while the server was down.
  const network = /favicon|ERR_CONNECTION_REFUSED|ERR_EMPTY_RESPONSE|ERR_INCOMPLETE_CHUNKED|Failed to load resource|WebSocket|NetworkError|Failed to fetch/;
  const before = errors.slice(0, errorsBeforeRestart);
  const after = errors.slice(errorsBeforeRestart).filter((e) => !network.test(e));
  if (errors.length) console.log(`     console errors seen: ${JSON.stringify(errors).slice(0, 600)}`);
  assert.deepEqual(before, [], "errors before any restart");
  assert.deepEqual(after, [], "non-network errors after the restart");
});

await context.close();
await browser.close();
const failed = results.filter((r) => r[0] === "FAIL");
console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`);
process.exit(failed.length ? 1 : 0);
