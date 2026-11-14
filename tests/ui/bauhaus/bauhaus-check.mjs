// Browser checks for the Bauhaus redesign against LIVE servers (not fixtures).
//   fake run:    PORT=8002 python <launcher> vision namer storage audio      -> --fake http://localhost:8002
//   replay run:  PORT=8003 PYTHONPATH=. python tests/ui/bauhaus/launch_with_speech.py -> --replay http://localhost:8003
//   node tests/ui/bauhaus/bauhaus-check.mjs [--fake URL] [--replay URL]
import { loadPlaywright } from "../agent4/pw.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => (args.includes(`--${n}`) ? args[args.indexOf(`--${n}`) + 1] : d);
const FAKE = opt("fake", "http://localhost:8002");
const REPLAY = opt("replay", "http://localhost:8003");
const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const results = [];
let failed = 0;
const check = (name, ok, info = "") => {
  results.push(`${ok ? "PASS" : "FAIL"} ${name}${info ? ` — ${info}` : ""}`);
  if (!ok) failed += 1;
};

async function open(base, { width = 1440, height = 1000, reducedMotion = "no-preference", theme } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, reducedMotion });
  if (theme) await context.addInitScript((t) => localStorage.setItem("empyrean.theme", JSON.stringify(t)), theme);
  const page = await context.newPage();
  const errors = [];
  const foreign = [];
  const requests = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("request", (r) => {
    requests.push(r.url());
    if (!r.url().startsWith(base) && !r.url().startsWith("data:")) foreign.push(r.url());
  });
  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#touch-panel .speech-signal", { timeout: 10000 });
  return { page, context, errors, foreign, requests };
}
const signalState = (page) => page.evaluate(() => document.querySelector(".speech-signal")?.dataset.signal ?? null);
async function waitSignal(page, wanted, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (wanted.includes(await signalState(page))) return true;
    await page.waitForTimeout(100);
  }
  return false;
}

// 1. Real-mode speaking (replay harness): the signal moves, then stops.
{
  const r = await open(REPLAY);
  check("runtime loads after the page content", await waitSignal(r.page, ["ready", "playing"]));
  check("signal plays while telemetry says a real engine is speaking", await waitSignal(r.page, ["playing"], 10000));
  const painted = await r.page.evaluate(() => {
    const c = document.querySelector(".speech-signal__canvas");
    return Boolean(c && !c.hidden && c.width > 0);
  });
  check("the Rive canvas is shown instead of the still", painted);
  check("signal stops when the phrase completes", await waitSignal(r.page, ["ready"], 10000));

  // Performance while playing, with the MJPEG stream and /ws updates running.
  await waitSignal(r.page, ["playing"], 10000);
  const perf = await r.page.evaluate(async () => {
    const longTasks = [];
    const po = new PerformanceObserver((list) => longTasks.push(...list.getEntries().map((e) => e.duration)));
    try {
      po.observe({ type: "longtask", buffered: false });
    } catch {
      // not supported
    }
    const frames = [];
    let last = performance.now();
    await new Promise((resolve) => {
      const end = last + 3000;
      const tick = (t) => {
        frames.push(t - last);
        last = t;
        if (t < end) requestAnimationFrame(tick);
        else resolve();
      };
      requestAnimationFrame(tick);
    });
    po.disconnect();
    frames.sort((a, b) => a - b);
    return {
      frames: frames.length,
      p95: frames[Math.floor(frames.length * 0.95)],
      longTasks: longTasks.length,
      worstLongTask: Math.max(0, ...longTasks),
      state: document.querySelector(".speech-signal")?.dataset.signal,
    };
  });
  check("frame time p95 under 34 ms while Rive, video and updates run", perf.p95 < 34,
    `p95 ${perf.p95?.toFixed(1)} ms over ${perf.frames} frames, ${perf.longTasks} long tasks (worst ${perf.worstLongTask.toFixed(0)} ms), signal ${perf.state}`);
  check("no long task over 100 ms while playing", perf.worstLongTask < 100, `${perf.worstLongTask.toFixed(0)} ms`);

  // Offscreen and hidden page pause the animation.
  await waitSignal(r.page, ["playing"], 10000);
  await r.page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await r.page.waitForTimeout(400);
  check("animation pauses while the signal is offscreen", (await signalState(r.page)) === "ready");
  await r.page.evaluate(() => window.scrollTo(0, 0));
  await waitSignal(r.page, ["playing"], 10000);
  await r.page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  check("animation pauses while the page is hidden", (await signalState(r.page)) === "ready");
  await r.page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
    document.dispatchEvent(new Event("visibilitychange"));
  });

  check("every request stays on this server (runtime and WASM are local)", r.foreign.length === 0, r.foreign.join(", "));
  check("the runtime and WASM were fetched from /static/vendor/rive/",
    r.requests.some((u) => u.endsWith("/static/vendor/rive/rive.js")) && r.requests.some((u) => u.endsWith("/static/vendor/rive/rive.wasm")));
  await r.page.evaluate(() => globalThis.empyreanDashboard.destroy());
  const after = await r.page.evaluate(() => ({
    canvases: document.querySelectorAll(".speech-signal__canvas").length,
  }));
  check("destroy disposes of the Rive canvas", after.canvases === 0);
  check("no console errors in the replay run", r.errors.length === 0, r.errors.join("; "));
  await r.context.close();
}

// 2. Fake audio: telemetry says "fake", so the signal never moves.
{
  const f = await open(FAKE);
  await waitSignal(f.page, ["ready", "fallback"], 10000);
  const seen = new Set();
  const end = Date.now() + 12000;
  while (Date.now() < end) {
    seen.add(await signalState(f.page));
    await f.page.waitForTimeout(150);
  }
  check("fake (printed) speech never animates the signal", !seen.has("playing"), [...seen].join(","));
  check("no console errors in the fake run", f.errors.length === 0, f.errors.join("; "));
  await f.context.close();
}

// 3. Reduced motion: the runtime is never loaded; the still stays.
{
  const m = await open(REPLAY, { reducedMotion: "reduce" });
  await m.page.waitForTimeout(6000);
  check("reduced motion keeps the still and never loads the runtime",
    (await signalState(m.page)) === "still" && !m.requests.some((u) => u.includes("/vendor/rive/")));
  const dur = await m.page.evaluate(() => getComputedStyle(document.querySelector(".operations-filters"), "::after").transitionDuration);
  check("reduced motion removes interface transitions", parseFloat(dur) < 0.01, dur);
  await m.context.close();
}

// 4. Runtime failure: the still image stays and the page carries on.
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route("**/static/vendor/rive/rive.js", (route) => route.fulfill({ status: 404, body: "" }));
  const page = await context.newPage();
  await page.goto(`${REPLAY}/`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#touch-panel .speech-signal");
  const end = Date.now() + 8000;
  let state = null;
  while (Date.now() < end && state !== "fallback") {
    state = await signalState(page);
    await page.waitForTimeout(150);
  }
  const still = await page.evaluate(() => !document.querySelector(".speech-signal__still").hidden);
  check("a failed runtime falls back to the still image", state === "fallback" && still, state);
  const text = await page.locator("#touch-panel").innerText();
  check("speech status text is still shown without the animation", /Speech/.test(text) && /Speaking now|speech|Last/i.test(text));
  await context.close();
}

// 5. Adapted 21st.dev interactions.
{
  const i = await open(FAKE);
  const search = i.page.locator("#find-panel .experience-button-primary");
  await search.hover();
  await i.page.waitForTimeout(300);
  const arrow = await search.evaluate((b) => getComputedStyle(b, "::after").opacity);
  check("search: arrow slides in on hover (cnippet sliding)", arrow === "1", arrow);
  check("search: the accessible name is unchanged", (await search.innerText()).trim() === "Search");
  const secondary = i.page.locator("#camera-panel .experience-button").first();
  await secondary.hover();
  await i.page.waitForTimeout(300);
  const flood = await secondary.evaluate((b) => getComputedStyle(b, "::before").transform);
  const color = await secondary.evaluate((b) => getComputedStyle(b).color);
  check("secondary: circle grows to fill on hover (Magic UI)", flood !== "none" && !/matrix\(1, 0, 0, 1/.test(flood), flood);
  check("secondary: text colour does not change during the fill", color === "rgb(23, 23, 23)", color);
  await i.page.locator(".operations-filter", { hasText: /^Touch$/ }).click();
  await i.page.waitForTimeout(350);
  const bar = await i.page.evaluate(() => getComputedStyle(document.querySelector(".operations-filters"), "::after").transform);
  check("filters: the bar moves to the selected segment (segmented)", /matrix\(1, 0, 0, 1, [1-9]/.test(bar), bar);
  await i.context.close();
}

// 6. Contrast of every visible text element, both themes.
for (const theme of ["light", "high-contrast"]) {
  const c = await open(FAKE, { theme });
  await c.page.waitForTimeout(2500);
  const low = await c.page.evaluate(() => {
    const parse = (s) => (s.match(/[\d.]+/g) || []).map(Number);
    const lum = ([r, g, b]) => {
      const f = (v) => {
        const x = v / 255;
        return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const bgOf = (el) => {
      for (let n = el; n; n = n.parentElement) {
        const c = parse(getComputedStyle(n).backgroundColor);
        if (c.length >= 3 && (c.length < 4 || c[3] > 0.9)) return c;
      }
      return [255, 255, 255];
    };
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const seen = new Set();
    while (walker.nextNode()) {
      const el = walker.currentNode.parentElement;
      if (!el || seen.has(el) || !walker.currentNode.textContent.trim()) continue;
      seen.add(el);
      const cs = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      if (cs.visibility === "hidden" || rect.width === 0 || rect.height === 0 || el.closest("[hidden],.ui-visually-hidden,[data-announcer]")) continue;
      if (el.closest(".experience-camera-frame")) continue; // text drawn over the live image is checked separately
      const fg = parse(cs.color);
      const [a, b] = [lum(fg), lum(bgOf(el))].sort((x, y) => y - x);
      const ratio = (a + 0.05) / (b + 0.05);
      const size = parseFloat(cs.fontSize);
      const large = size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700);
      if (ratio < (large ? 3 : 4.5)) out.push(`${el.tagName}.${el.className} "${el.textContent.trim().slice(0, 30)}" ${ratio.toFixed(2)}`);
    }
    return out;
  });
  check(`${theme}: every visible text element meets WCAG AA contrast`, low.length === 0, low.slice(0, 6).join(" | "));
  await c.context.close();
}

console.log(results.join("\n"));
console.log(`${results.length - failed} passed, ${failed} failed`);
await browser.close();
process.exit(failed ? 1 : 0);
