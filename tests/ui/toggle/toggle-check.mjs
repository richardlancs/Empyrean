// Live checks for the Regular | Demo control through the real backend and fake vision.
// Servers (fake vision: no detector runs, so these check the switching flow, not a model):
//   --ok       FAKE_DEMO_DETECTOR=ok      FAKE_DETECTOR_SWITCH_SECONDS=2 python -m app --fake vision namer storage audio (default :8020)
//   --missing  FAKE_DEMO_DETECTOR=missing FAKE_DETECTOR_SWITCH_SECONDS=2 python -m app --fake vision namer storage audio (default :8021)
import { loadPlaywright } from "../agent4/pw.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => (args.includes(`--${n}`) ? args[args.indexOf(`--${n}`) + 1] : d);
const OK = opt("ok", "http://localhost:8020");
const MISSING = opt("missing", "http://localhost:8021");
const SHOTS = opt("shots", null);
const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const results = [];
let failed = 0;
const check = (name, ok, info = "") => {
  results.push(`${ok ? "PASS" : "FAIL"} ${name}${info ? ` — ${info}` : ""}`);
  if (!ok) failed += 1;
};

async function open(base, { width = 1440, height = 900, theme, reducedMotion = "no-preference" } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, reducedMotion });
  if (theme) await context.addInitScript((t) => localStorage.setItem("empyrean.theme", JSON.stringify(t)), theme);
  const page = await context.newPage();
  const errors = [];
  const posts = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("request", (r) => r.method() === "POST" && r.url().endsWith("/api/mode") && posts.push(r.postData()));
  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".experience-segment", { timeout: 10000 });
  return { page, context, errors, posts };
}
const seg = (page, name) => page.locator(".experience-segment", { hasText: name });
const pressed = async (page) => {
  for (const name of ["Regular", "Demo"]) if ((await seg(page, name).getAttribute("aria-pressed")) === "true") return name;
  return null;
};
const statusText = (page) => page.locator(".experience-detector-status").innerText();
async function until(fn, ms = 10000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await fn()) return true;
    await new Promise((r) => setTimeout(r, 100));
  }
  return false;
}
async function reset(base) {
  const s = await (await fetch(`${base}/api/mode`)).json();
  if (s.active_mode !== "actual" || s.state === "switching") {
    await until(async () => (await (await fetch(`${base}/api/mode`)).json()).state !== "switching");
    await fetch(`${base}/api/mode`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "actual" }) });
    await until(async () => (await (await fetch(`${base}/api/mode`)).json()).active_mode === "actual");
  }
}

// 1. Regular -> Demo -> Regular, with a second client watching.
await reset(OK);
{
  const a = await open(OK);
  const b = await open(OK);
  await until(async () => (await pressed(a.page)) === "Regular");
  check("starts on Regular (confirmed by vision)", (await pressed(a.page)) === "Regular");
  check("Regular support text", /General-purpose object detection\./.test(await a.page.locator(".experience-detector-support").innerText()));
  check("no badge on Regular", !(await a.page.locator(".experience-detector-badge").isVisible()));
  check("fake vision is said plainly on Regular", /no detector is running/.test(await a.page.locator(".experience-detector").innerText()));
  if (SHOTS) await a.page.screenshot({ path: `${SHOTS}/regular-1440.png` });

  // Rapid triple click: one request only.
  const demo = seg(a.page, "Demo");
  await demo.click();
  await demo.click({ force: true }).catch(() => {});
  await demo.click({ force: true }).catch(() => {});
  const sawSwitching = await until(async () => /Switching to Demo… Regular stays on until Demo is ready\./.test(await statusText(a.page)), 3000);
  check("switching is shown in words", sawSwitching, await statusText(a.page));
  check("Regular stays pressed while switching", (await pressed(a.page)) === "Regular");
  check("Demo is marked busy while switching", (await demo.getAttribute("aria-busy")) === "true");
  check("both choices locked while switching", (await seg(a.page, "Regular").getAttribute("aria-disabled")) === "true");
  check("second client also sees the switch", await until(async () => /Switching to Demo/.test(await statusText(b.page)), 3000));
  if (SHOTS) await a.page.screenshot({ path: `${SHOTS}/switching-1440.png` });
  const bReply = await b.page.evaluate(async () => (await fetch("/api/mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "demo" }) })).status);
  check("a second client's duplicate request is refused (409)", bReply === 409, String(bReply));

  check("Demo confirmed after vision answers", await until(async () => (await pressed(a.page)) === "Demo", 8000));
  check("rapid clicks sent exactly one request", a.posts.length === 1, String(a.posts.length));
  const badge = a.page.locator(".experience-detector-badge");
  check("fake demo badge does not claim a trained model", (await badge.isVisible()) && /fake vision/.test(await badge.innerText()) && !/Demo-trained/.test(await badge.innerText()), await badge.innerText());
  check("second client shows Demo too", await until(async () => (await pressed(b.page)) === "Demo", 3000));
  check("camera source still labelled as the recorded clip", /clip|recorded|test/i.test(await a.page.locator(".experience-camera-img").getAttribute("alt")));
  if (SHOTS) await a.page.screenshot({ path: `${SHOTS}/demo-fake-1440.png` });

  // System details carries the detector identity.
  await a.page.locator(".operations-status-details > summary").click();
  const details = await a.page.locator(".operations-status-details").innerText();
  check("System details names the detector", /Detector/.test(details) && /No detector: scripted test clip \(fake vision\)/.test(details), details.split("\n").filter((l) => /Detector|detector/.test(l)).join(" | "));
  await a.page.locator(".operations-status-details > summary").click();

  // Keyboard: Tab to Regular and press Enter.
  await seg(a.page, "Regular").focus();
  await a.page.keyboard.press("Enter");
  check("keyboard switch back to Regular", await until(async () => (await pressed(a.page)) === "Regular", 8000));
  check("focus stays on the control after switching", await a.page.evaluate(() => document.activeElement?.classList.contains("experience-segment")));
  const unexpected = [...a.errors, ...b.errors.filter((e) => !/409/.test(e))];
  check("no console errors (besides the deliberate 409)", unexpected.length === 0, unexpected.join(" | "));

  // Refresh shows the engine's state, not a remembered one.
  await a.page.reload({ waitUntil: "domcontentloaded" });
  await a.page.waitForSelector(".experience-segment");
  check("after refresh the confirmed mode is shown", await until(async () => (await pressed(a.page)) === "Regular", 5000));
  await a.context.close();
  await b.context.close();
}

// 2. Missing checkpoint: failure explained, Regular kept.
await reset(MISSING);
{
  const a = await open(MISSING);
  await until(async () => (await pressed(a.page)) === "Regular");
  check("missing checkpoint is noted before trying", /No demo-trained checkpoint is installed|no detector is running/.test(await a.page.locator(".experience-detector").innerText()));
  await seg(a.page, "Demo").click();
  check("failure is explained", await until(async () => /Could not switch to Demo\. Still using Regular\./.test(await statusText(a.page)), 8000), await statusText(a.page));
  check("Regular still pressed after failure", (await pressed(a.page)) === "Regular");
  check("failure is not colour-only", /⚠|Could not/.test(await a.page.locator(".experience-detector").innerText()));
  if (SHOTS) await a.page.screenshot({ path: `${SHOTS}/failed-1440.png` });
  await a.context.close();
}

// 3. Layout: 360 px and 768 px, no horizontal scroll, 44 px targets; high contrast; reduced motion.
for (const width of [360, 768]) {
  const a = await open(OK, { width, height: 800 });
  const overflow = await a.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check(`${width} px: no horizontal scroll`, overflow <= 0, String(overflow));
  const box = await seg(a.page, "Demo").boundingBox();
  check(`${width} px: Demo target at least 44 px tall`, box && box.height >= 44, JSON.stringify(box));
  if (SHOTS) await a.page.locator(".experience-camera").screenshot({ path: `${SHOTS}/camera-${width}.png` });
  await a.context.close();
}
{
  const a = await open(OK, { theme: "high-contrast", reducedMotion: "reduce" });
  const pressedStyle = await seg(a.page, "Regular").evaluate((n) => getComputedStyle(n).backgroundColor);
  check("high contrast: pressed segment uses the high-contrast accent", pressedStyle === "rgb(15, 53, 145)", pressedStyle);
  check("pressed segment carries a check mark", await seg(a.page, "Regular").evaluate((n) => getComputedStyle(n.querySelector(".experience-segment-mark"), "::before").content.includes("✓")));
  await a.context.close();
}

await browser.close();
console.log(results.join("\n"));
console.log(`\n${results.length - failed} / ${results.length} passed`);
process.exit(failed ? 1 : 0);
