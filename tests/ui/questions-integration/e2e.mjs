// Browser checks for the questions feature against the FIXTURE harness.
// Not part of `node --test` (needs a browser). Playwright is not a project
// dependency; this loads a local or global install.
//
//   python3 -m http.server 8794 --bind 127.0.0.1            # from the repo root
//   node tests/ui/questions-integration/e2e.mjs              # HARNESS_URL / SHOTS optional

import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch {
    const root = execSync("npm root -g").toString().trim();
    return createRequire(path.join(root, "noop.js"))("playwright");
  }
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.HARNESS_URL || "http://127.0.0.1:8794/tests/ui/questions-integration/harness.html";
const SHOTS = process.env.SHOTS ?? path.join(HERE, "screenshots");

const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const results = [];

async function check(name, fn) {
  try {
    await fn();
    results.push(`PASS ${name}`);
  } catch (err) {
    results.push(`FAIL ${name}: ${err.message.split("\n")[0]}`);
  }
}

async function open(query = "", { width = 1280, height = 900, forcedColors, reducedMotion } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, forcedColors, reducedMotion });
  const page = await context.newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && page.errors.push(m.text()));
  await page.goto(`${BASE}?${query}`);
  await page.waitForSelector(".questions-panel");
  return page;
}

const panel = (page) => page.locator(".questions-panel");
const statusText = (page) => page.locator(".questions-status").textContent();
const shot = (page, name) => SHOTS && page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
const noHorizontalScroll = (page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);

await check("typed question, Enter submits, answer shown with question and announced once", async () => {
  const page = await open("reply=answer&latency=200");
  const input = page.getByLabel("Your question");
  await input.fill("What am I touching?");
  await input.press("Enter");
  await page.waitForFunction(() => document.querySelector(".questions-status").textContent.startsWith("Asking"));
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "answered");
  assert.match(await page.locator(".questions-asked").textContent(), /What am I touching\?/);
  assert.match(await page.locator(".questions-result-body").textContent(), /Heinz ketchup/);
  assert.equal(await page.locator(".questions-result-speech").textContent(), "Sent to the speaker.");
  const ann = await page.evaluate(() => window.__fixture.announcements);
  assert.equal(ann.length, 1);
  assert.match(ann[0].key, /^question:fx\d+:answered$/);
  assert.match(await panel(page).textContent(), /Sent to the speaker/);
  assert.doesNotMatch(await panel(page).textContent(), /Spoken|Heard /);
  await shot(page, "answered-1280");
  assert.deepEqual(page.errors, []);
});

await check("Ask is aria-disabled while submitting and the input keeps focus", async () => {
  const page = await open("reply=answer&latency=800");
  const input = page.getByLabel("Your question");
  await input.fill("What can you see?");
  await input.press("Enter");
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "submitting");
  assert.equal(await page.getByRole("button", { name: "Ask", exact: true }).getAttribute("aria-disabled"), "true");
  assert.equal(await page.evaluate(() => document.activeElement?.className), "questions-input");
  await input.press("Enter"); // ignored
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "answered");
  const posts = await page.locator("#fx-requests li", { hasText: "POST" }).count();
  assert.equal(posts, 1, "no double submit");
});

await check("example button fills and asks; 202 looking_up is busy, then answered via poll", async () => {
  const page = await open("reply=history-poll&latency=150");
  await page.getByRole("button", { name: "Where did I last touch my keys?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "looking_up");
  assert.equal(await page.getByLabel("Your question").inputValue(), "Where did I last touch my keys?");
  assert.equal(await page.locator(".questions-result").getAttribute("aria-busy"), "true");
  assert.equal(await page.locator(".questions-result").getAttribute("data-tone"), "pending");
  assert.match(await statusText(page), /Looking up/);
  await shot(page, "looking-up-1280");
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "answered", null, { timeout: 8000 });
  assert.equal(await page.locator(".questions-result").getAttribute("aria-busy"), "false");
  assert.match(await page.locator(".questions-result-body").textContent(), /10:02/);
});

await check("202 answered by socket push", async () => {
  const page = await open("reply=history-push&latency=100");
  await page.getByRole("button", { name: "Where did I last touch my keys?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "answered", null, { timeout: 6000 });
});

await check("unavailable history is shown as unavailable, not as not found", async () => {
  const page = await open("reply=history-unavailable&latency=100");
  await page.getByRole("button", { name: "Where did I last touch my keys?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "unavailable");
  assert.equal(await page.locator(".questions-result").getAttribute("data-tone"), "unavailable");
  const text = await page.locator(".questions-result").textContent();
  assert.match(text, /Touch history is unavailable right now\./);
  assert.match(text, /Reason: Storage is not running/);
  assert.doesNotMatch(text, /no record|not found/i);
  await shot(page, "unavailable-1280");
});

await check("503 shows the server detail", async () => {
  const page = await open("reply=503&latency=100");
  await page.getByRole("button", { name: "What can you see?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "error");
  assert.equal(await statusText(page), "Questions require the running app.");
});

await check("network error shows a plain fallback and asking again works", async () => {
  const page = await open("reply=network&latency=100");
  await page.getByRole("button", { name: "What can you see?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "error");
  assert.match(await statusText(page), /Could not reach the dashboard server/);
  await shot(page, "error-1280");
  await page.evaluate(() => window.__fixture.set("reply", "answer"));
  await page.getByRole("button", { name: "What can you see?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "answered");
});

await check("capabilities.questions=false disables Ask and examples with a visible reason", async () => {
  const page = await open("cap=false");
  assert.equal(await page.getByRole("button", { name: "Ask", exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole("button", { name: "What can you see?" }).isDisabled(), true);
  assert.equal(await page.getByLabel("Your question").isEditable(), true, "typing still works");
  assert.match(await page.locator(".questions-notice").first().textContent(), /unavailable/);
  await shot(page, "questions-off-1280");
  await page.evaluate(() => window.__fixture.set("cap", "true"));
  assert.equal(await page.getByRole("button", { name: "Ask", exact: true }).isDisabled(), false);
});

await check("reconnecting shows a delay note, which clears on reconnect", async () => {
  const page = await open("connection=reconnecting");
  assert.match(await panel(page).textContent(), /answers may be delayed/);
  await page.evaluate(() => window.__fixture.set("connection", "connected"));
  assert.doesNotMatch(await panel(page).textContent(), /answers may be delayed/);
});

await check("mic: one utterance fills the input (not submitted), aria-pressed tracks listening", async () => {
  const page = await open("voice=fake&mic=ok");
  const mic = page.getByRole("button", { name: "Speak a question" });
  assert.equal(await mic.getAttribute("aria-pressed"), "false");
  await mic.click();
  assert.equal(await mic.getAttribute("aria-pressed"), "true");
  assert.match(await page.locator(".questions-voice-status").textContent(), /Listening/);
  await page.waitForSelector(".questions-interim:not([hidden])");
  await shot(page, "listening-1280");
  await page.waitForFunction(() => document.querySelector(".questions-voice-status").dataset.phase === "transcript", null, { timeout: 5000 });
  assert.equal(await page.getByLabel("Your question").inputValue(), "where did I last touch my keys");
  assert.equal(await page.evaluate(() => document.activeElement?.className), "questions-input");
  assert.equal(await page.locator("#fx-requests li").count(), 0, "not auto-submitted");
  assert.equal(await page.evaluate(() => window.__fixture.recognitions.length), 1);
  await page.waitForTimeout(800);
  assert.equal(await page.evaluate(() => window.__fixture.recognitions.length), 1, "no restart");
  await shot(page, "transcript-1280");
});

await check("mic: Escape cancels (abort), no transcript", async () => {
  const page = await open("voice=fake&mic=silence");
  await page.getByRole("button", { name: "Speak a question" }).click();
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => window.__fixture.recognitions[0].aborted), true);
  assert.equal(await page.getByRole("button", { name: "Speak a question" }).getAttribute("aria-pressed"), "false");
  assert.equal(await page.locator(".questions-voice-status").getAttribute("data-phase"), "idle");
});

await check("mic: not-allowed maps to the permission message", async () => {
  const page = await open("voice=fake&mic=not-allowed");
  await page.getByRole("button", { name: "Speak a question" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-voice-status").dataset.phase === "error");
  assert.equal(await page.locator(".questions-voice-status").textContent(), "Allow microphone access, then try again.");
});

await check("mic: unmount aborts a live recognition", async () => {
  const page = await open("voice=fake&mic=silence");
  await page.getByRole("button", { name: "Speak a question" }).click();
  await page.evaluate(() => window.__fixture.unmount());
  assert.equal(await page.evaluate(() => window.__fixture.recognitions[0].aborted), true);
  assert.equal(await page.locator("#questions-root").innerHTML(), "");
});

await check("unsupported: mic disabled with visible typed-fallback text", async () => {
  const page = await open("voice=unsupported");
  assert.equal(await page.getByRole("button", { name: "Speak a question" }).isDisabled(), true);
  assert.match(await panel(page).textContent(), /Voice input isn't supported in this browser\. Type your question instead\./);
});

await check("other pages' questions appear only in the labelled recent list", async () => {
  const page = await open("reply=answer&latency=50");
  await page.getByRole("button", { name: "What am I touching?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "answered");
  await page.evaluate(() => document.getElementById("fx-push-other").click());
  assert.match(await page.locator(".questions-result-body").textContent(), /Heinz ketchup/);
  assert.match(await page.locator(".questions-recent summary").textContent(), /Recent questions from all open pages \(2\)/);
});

await check("320 px: no horizontal scroll; screenshots", async () => {
  const page = await open("reply=history-poll&latency=100&voice=unsupported", { width: 320, height: 900 });
  assert.equal(await noHorizontalScroll(page), true);
  await shot(page, "idle-320");
  await page.getByRole("button", { name: "Where did I last touch my keys?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "answered", null, { timeout: 8000 });
  assert.equal(await noHorizontalScroll(page), true);
  await shot(page, "answered-320");
});

await check("200% zoom equivalent (640 css px at 1280 window): no horizontal scroll", async () => {
  const page = await open("reply=answer", { width: 640, height: 900 });
  await page.evaluate(() => (document.documentElement.style.fontSize = "200%"));
  assert.equal(await noHorizontalScroll(page), true);
  await shot(page, "text-200pct-640");
});

await check("forced colors and high-contrast theme render", async () => {
  const page = await open("reply=history-unavailable&contrast=1", { forcedColors: "active" });
  await page.getByRole("button", { name: "Where did I last touch my keys?" }).click();
  await page.waitForFunction(() => document.querySelector(".questions-panel").dataset.phase === "unavailable");
  await shot(page, "forced-colors-1280");
  const hc = await open("contrast=1");
  await shot(hc, "high-contrast-1280");
});

await check("keyboard tab order: input, Ask, mic, examples", async () => {
  const page = await open("voice=fake");
  await page.getByLabel("Your question").focus();
  const order = [];
  for (let i = 0; i < 4; i += 1) {
    await page.keyboard.press("Tab");
    order.push(await page.evaluate(() => document.activeElement.textContent.trim() || document.activeElement.tagName));
  }
  assert.deepEqual(order, ["Ask", "Speak a question", "What can you see?", "What am I touching?"]);
});

await browser.close();
console.log(results.join("\n"));
const failed = results.filter((r) => r.startsWith("FAIL")).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
