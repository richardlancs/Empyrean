// Live checks for Pip, the camera companion, through the real backend (fakes, all labelled):
//   --ok      FAKE_DEMO_DETECTOR=ok FAKE_DETECTOR_SWITCH_SECONDS=3 python -m app --fake vision namer storage audio   (default :8030)
//   --missing FAKE_DEMO_DETECTOR=missing python -m app --fake vision namer storage audio                         (default :8031)
//   --hazard  python -m app --fake vision namer storage audio hazard                                             (default :8032)
//   --gap     CAMERA_GAP=6,30 tests/ui/friendly/demo_harness.py                                                  (default :8033)
// Optional --shots DIR saves screenshots.
import { loadPlaywright } from "../agent4/pw.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => (args.includes(`--${n}`) ? args[args.indexOf(`--${n}`) + 1] : d);
const OK = opt("ok", "http://localhost:8030");
const MISSING = opt("missing", "http://localhost:8031");
const HAZARD = opt("hazard", "http://localhost:8032");
const GAP = opt("gap", "http://localhost:8033");
const SHOTS = opt("shots", null);
const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const results = [];
let failed = 0;
const check = (name, ok, info = "") => {
  results.push(`${ok ? "PASS" : "FAIL"} ${name}${info ? ` — ${info}` : ""}`);
  if (!ok) failed += 1;
};
const shot = async (page, name, sel = ".experience-camera") => {
  if (SHOTS) await page.locator(sel).screenshot({ path: `${SHOTS}/${name}.png` });
};

async function open(base, { width = 1440, height = 900, scale = 1, theme, reducedMotion = "no-preference", touch = false, blockArt = false } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: scale, reducedMotion, hasTouch: touch, isMobile: false });
  if (theme) await context.addInitScript((t) => localStorage.setItem("empyrean.theme", JSON.stringify(t)), theme);
  if (blockArt) await context.route(/assets\/pip\/pip-(recline|peek-edge|wait|concerned|point)\.png/, (r) => r.abort());
  const page = await context.newPage();
  const errors = [];
  const requests = [];
  page.on("console", (m) => m.type() === "error" && !/pip-.*png|ERR_FAILED/.test(m.text()) && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("request", (r) => requests.push(`${r.method()} ${new URL(r.url()).pathname}`));
  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".pip-perch__button", { state: "attached", timeout: 10000 });
  return { page, context, errors, requests };
}
const pipButton = (page) => page.getByRole("button", { name: "Help with the camera." });
const pose = (page) => page.locator(".pip-perch").getAttribute("data-pose");
const box = (page, sel) => page.locator(sel).first().boundingBox();
async function until(fn, ms = 10000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await fn().catch(() => false)) return true;
    await new Promise((r) => setTimeout(r, 150));
  }
  return false;
}
const overlaps = (a, b) => a && b && a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
async function layoutChecks(page, label) {
  const pip = await box(page, ".pip-perch__button");
  const frame = await box(page, ".experience-camera-frame");
  check(`${label}: Pip sits above the picture`, pip && frame && pip.y + pip.height <= frame.y + 0.5, JSON.stringify({ pipBottom: pip && pip.y + pip.height, frameTop: frame?.y }));
  for (const sel of [".experience-segmented", ".experience-camera-state", ".experience-camera-top .experience-controls", ".experience-detector-status"]) {
    check(`${label}: Pip does not cover ${sel}`, !overlaps(pip, await box(page, sel)));
  }
  check(`${label}: target at least 44 × 44`, pip && pip.width >= 44 && pip.height >= 44, JSON.stringify(pip));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check(`${label}: no horizontal scroll`, overflow <= 0, String(overflow));
}
async function resetMode(base) {
  await until(async () => (await (await fetch(`${base}/api/mode`)).json()).state !== "switching", 8000);
  const s = await (await fetch(`${base}/api/mode`)).json();
  if (s.active_mode !== "actual") {
    await fetch(`${base}/api/mode`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "actual" }) });
    await until(async () => (await (await fetch(`${base}/api/mode`)).json()).active_mode === "actual", 8000);
  }
}

// 1. Regular: button semantics, keyboard, bubble, layout, no engine requests.
await resetMode(OK);
{
  const { page, context, errors, requests } = await open(OK);
  await until(async () => (await pose(page)) === "recline");
  check("reclines on the frame when all is well", (await pose(page)) === "recline");
  check("artwork is decorative (alt empty)", (await page.locator(".pip-perch__art").getAttribute("alt")) === "");
  check("button starts collapsed", (await pipButton(page).getAttribute("aria-expanded")) === "false");
  await layoutChecks(page, "1440");
  await shot(page, "pip-regular-1440");

  // Keyboard: Tab from the Demo segment reaches Pip; Enter opens; Escape closes and returns focus.
  await page.locator(".experience-segment", { hasText: "Demo" }).focus();
  await page.keyboard.press("Tab");
  check("Tab reaches Pip after the detector control", await pipButton(page).evaluate((n) => n === document.activeElement));
  check("focus ring is visible on Pip", await pipButton(page).evaluate((n) => getComputedStyle(n).outlineStyle !== "none" && parseFloat(getComputedStyle(n).outlineWidth) >= 2));
  const before = requests.length;
  await page.keyboard.press("Enter");
  const bubble = page.locator(".pip-bubble");
  check("Enter opens the bubble", (await bubble.isVisible()) && (await pipButton(page).getAttribute("aria-expanded")) === "true");
  const text = await bubble.innerText();
  check("bubble states the fake clip honestly", /recorded test clip, so no detector is running\. The control is set to Regular/.test(text), text.split("\n")[1]);
  check("bubble has the camera tip", /Keep the object and your hand in view\./.test(text));
  check("bubble points to the Regular | Demo control (Pip does not switch)", /use the Regular \| Demo control/.test(text) && (await bubble.locator("button").count()) === 1);
  const bubbleBox = await box(page, ".pip-bubble");
  const frame = await box(page, ".experience-camera-frame");
  check("open bubble does not cover the picture", bubbleBox.y + bubbleBox.height <= frame.y + 0.5);
  await shot(page, "pip-help-open-1440");
  await page.keyboard.press("Escape");
  check("Escape closes the bubble", !(await bubble.isVisible()));
  check("focus returns to Pip after Escape", await pipButton(page).evaluate((n) => n === document.activeElement));
  await page.keyboard.press("Space");
  check("Space opens the bubble", await bubble.isVisible());
  await page.getByRole("button", { name: "Close help" }).click();
  check("Close help closes and returns focus", !(await bubble.isVisible()) && (await pipButton(page).evaluate((n) => n === document.activeElement)));
  await pipButton(page).click();
  await page.locator(".experience-heading").first().click();
  check("a click elsewhere closes the bubble", !(await bubble.isVisible()));
  await pipButton(page).hover();
  await page.waitForTimeout(400);
  const extra = requests.slice(before).filter((r) => !/assets\/pip|\/video/.test(r));
  check("hover and help send no requests to the engine", extra.length === 0, extra.join(", "));
  check("no live region inside Pip", (await page.locator(".pip-perch [aria-live], .pip-bubble [aria-live], .pip-bubble[role=status]").count()) === 0);

  // Switching: wait pose only while vision reports the switch; name never changes.
  await page.locator(".experience-segment", { hasText: "Demo" }).click();
  check("waits while the switch is pending", await until(async () => (await pose(page)) === "wait", 4000));
  await shot(page, "pip-waiting-1440");
  check("accessible name unchanged while waiting", (await pipButton(page).count()) === 1);
  check("back to reclining once Demo is confirmed", await until(async () => (await pose(page)) === "recline", 8000));
  await pipButton(page).click();
  check("bubble follows the confirmed mode (Demo, fake)", /control is set to Demo/.test(await bubble.innerText()));
  await shot(page, "pip-demo-help-1440");
  await page.keyboard.press("Escape");

  // Attentive while something is touched (the recorded clip touches objects periodically).
  check("attentive during a touch", await until(async () => (await pose(page)) === "attentive", 40000));
  await shot(page, "pip-attentive-1440");
  check("no console errors", errors.length === 0, errors.join(" | "));
  await context.close();
  await resetMode(OK);
}

// 2. Failed switch: concerned with a specific recovery; Regular stays.
await resetMode(MISSING);
{
  const { page, context } = await open(MISSING);
  await until(async () => (await page.locator(".experience-segment", { hasText: "Demo" }).getAttribute("aria-disabled")) === "false", 8000);
  await page.locator(".experience-segment", { hasText: "Demo" }).click();
  // The server may still show an earlier failure, so wait for this switch first.
  await until(async () => (await pose(page)) === "wait", 4000);
  check("concerned after a failed switch", await until(async () => (await pose(page)) === "concerned", 8000));
  await pipButton(page).click();
  const text = await page.locator(".pip-bubble").innerText();
  check("recovery says what failed", /did not finish\. No demo-trained checkpoint/.test(text), text.split("\n").slice(1, 3).join(" / "));
  await shot(page, "pip-failed-1440");
  await page.keyboard.press("Escape");
  await page.locator(".experience-segment", { hasText: "Demo" }).click();
  await until(async () => /Could not switch/.test(await page.locator(".experience-detector-status").innerText()), 6000);
  await context.close();
}

// 3. Camera gap: stale/offline -> concerned, then recovery -> reclining.
{
  const { page, context } = await open(GAP);
  check("concerned when the picture stops", await until(async () => (await pose(page)) === "concerned", 30000));
  await pipButton(page).click();
  check("recovery message for the camera", /picture stopped updating|camera is offline|video stream dropped/.test(await page.locator(".pip-bubble").innerText()));
  await shot(page, "pip-camera-stale-1440");
  await page.keyboard.press("Escape");
  check("recovers when frames return", await until(async () => ["recline", "attentive"].includes(await pose(page)), 45000));
  await context.close();
}

// 4. Active real hazard: Pip and its bubble step aside, and return afterwards.
{
  const { page, context } = await open(HAZARD);
  // Open help while the path is clear, so the check also covers the bubble stepping aside.
  if (await until(async () => page.locator(".pip-perch").isVisible(), 30000)) await pipButton(page).click({ timeout: 2000 }).catch(() => {});
  const urgent = await until(async () => (await page.locator('.app-slot--warning[data-emphasis="urgent"]').count()) > 0, 45000);
  check("a real hazard became active", urgent);
  check("Pip hidden during the hazard", urgent && !(await page.locator(".pip-perch").isVisible()) && !(await page.locator(".pip-bubble").isVisible()));
  if (SHOTS && urgent) await page.screenshot({ path: `${SHOTS}/pip-hazard-1440.png` });
  // The scripted fake repeats a hazard every HAZARD_COOLDOWN_SECONDS, so it never clears here;
  // the return is covered by the static CSS rule (test_friendly.py) and section 1 (no hazard).
  check("Pip stays hidden while hazards keep arriving", !(await page.locator(".pip-perch").isVisible()));
  await context.close();
}

// 5. Widths, 200 % zoom, touch, reduced motion, high contrast, missing artwork.
for (const [label, opts] of [["360", { width: 360, height: 800 }], ["768", { width: 768, height: 900 }], ["200% zoom", { width: 720, height: 450, scale: 2 }]]) {
  const { page, context } = await open(OK, opts);
  await until(async () => (await pose(page)) !== null);
  await layoutChecks(page, label);
  if (label === "360") {
    check("360: smaller peeking pose", /pip-peek-edge\.png/.test(await page.locator(".pip-perch__art").evaluate((n) => n.currentSrc)) || (await pose(page)) !== "recline");
  }
  await pipButton(page).click();
  const b = await box(page, ".pip-bubble");
  check(`${label}: bubble fits the screen`, b && b.x >= 0 && b.x + b.width <= opts.width + 0.5, JSON.stringify(b));
  await shot(page, `pip-${label.replace(/\W+/g, "")}-open`);
  await context.close();
}
{
  const { page, context } = await open(OK, { touch: true, width: 390, height: 844 });
  await pipButton(page).tap();
  check("tap opens help on a touch screen", await page.locator(".pip-bubble").isVisible());
  await context.close();
}
{
  const { page, context } = await open(OK, { reducedMotion: "reduce" });
  await pipButton(page).focus();
  const t = await page.locator(".pip-perch__picture").evaluate((n) => getComputedStyle(n).transform);
  const a = await page.locator(".pip-perch__art").evaluate((n) => getComputedStyle(n).animationName);
  check("reduced motion: no tilt and no entrance animation", t === "none" && a === "none", `${t} / ${a}`);
  await context.close();
}
{
  const { page, context } = await open(OK, { theme: "high-contrast" });
  await pipButton(page).click();
  const bg = await page.locator(".pip-bubble").evaluate((n) => getComputedStyle(n).backgroundColor);
  check("high contrast: white bubble with black edge", bg === "rgb(255, 255, 255)", bg);
  await shot(page, "pip-high-contrast-open");
  await context.close();
}
{
  const { page, context } = await open(OK, { blockArt: true });
  check("missing artwork: visible Help text", await until(async () => page.locator(".pip-perch__fallback").isVisible(), 5000));
  await pipButton(page).click();
  check("missing artwork: help still opens", await page.locator(".pip-bubble").isVisible());
  await context.close();
}

await browser.close();
console.log(results.join("\n"));
console.log(`\n${results.length - failed} / ${results.length} passed`);
process.exit(failed ? 1 : 0);
