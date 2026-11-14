// Live checks for the friendly-clarity redesign, through the real backend.
// Servers (fakes and demo inputs are labelled; nothing here is hardware evidence):
//   --fake     python -m app --fake vision namer storage audio            (default :8010)
//   --demo     SPEECH=1 CAMERA_GAP=15,30 tests/ui/friendly/demo_harness.py (default :8011)
//   --storage  REAL_STORAGE=1 tests/ui/friendly/demo_harness.py            (default :8012)
//   --hazard   python -m app --fake vision namer storage audio hazard     (default :8013)
import { loadPlaywright } from "../agent4/pw.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => (args.includes(`--${n}`) ? args[args.indexOf(`--${n}`) + 1] : d);
const FAKE = opt("fake", "http://localhost:8010");
const DEMO = opt("demo", "http://localhost:8011");
const STORAGE = opt("storage", "http://localhost:8012");
const HAZARD = opt("hazard", "http://localhost:8013");
const only = opt("only", null);
const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const results = [];
let failed = 0;
const check = (name, ok, info = "") => {
  results.push(`${ok ? "PASS" : "FAIL"} ${name}${info ? ` — ${info}` : ""}`);
  if (!ok) failed += 1;
};

async function open(base, { width = 1440, height = 900, reducedMotion = "no-preference", theme } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, reducedMotion });
  if (theme) await context.addInitScript((t) => localStorage.setItem("empyrean.theme", JSON.stringify(t)), theme);
  const page = await context.newPage();
  const errors = [];
  const foreign = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("request", (r) => !r.url().startsWith(base) && !r.url().startsWith("data:") && foreign.push(r.url()));
  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#touch-panel .experience-touch", { timeout: 10000 });
  return { page, context, errors, foreign };
}
const text = (page, sel) => page.locator(sel).innerText().catch(() => "");
async function waitText(page, sel, re, ms = 25000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (re.test(await text(page, sel))) return true;
    await page.waitForTimeout(120);
  }
  return false;
}
const box = (page, sel) => page.locator(sel).first().boundingBox();
const visiblePips = (page) =>
  page.evaluate(() =>
    [...document.querySelectorAll(".pip")]
      .filter((p) => p.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) && p.getBoundingClientRect().height > 0)
      .map((p) => ({ cls: p.className, h: Math.round(p.getBoundingClientRect().height) })),
  );

// ---------------- Fake run: hierarchy, first screen, demo audio, quiet controls ----------------
if (!only || only === "fake") {
  const f = await open(FAKE);
  check("touch, speech and camera are on the first 1440x900 screen", await (async () => {
    await waitText(f.page, "#touch-panel", /Touching now|Holding now/);
    const name = await box(f.page, "#touch-panel .experience-touch-name");
    const speech = await box(f.page, "#touch-panel .experience-speech");
    const cam = await box(f.page, "#camera-panel .experience-camera-frame");
    const visibleCam = cam ? Math.min(cam.y + cam.height, 900) - cam.y : 0;
    return name.y + name.height < 900 && speech.y < 900 && visibleCam >= 300;
  })());
  const health = await box(f.page, "#health-panel");
  check("system status is one compact line", health.height <= 64, `${Math.round(health.height)} px`);
  const warning = await box(f.page, "#warning-panel");
  check("an inactive warning is compact", warning.height <= 80, `${Math.round(warning.height)} px`);
  check("all diagnostics stay available under System details", await (async () => {
    await f.page.locator("#health-panel summary", { hasText: "System details" }).click();
    const t = await text(f.page, "#health-panel");
    await f.page.locator("#health-panel summary", { hasText: "System details" }).click();
    return ["Camera", "Object tracking", "Naming", "Storage", "Audio"].every((m) => t.includes(m)) && /fake/.test(t);
  })());
  check("fake inputs are marked in the status line", /Fake inputs/.test(await text(f.page, "#health-panel")));

  const sizes = await f.page.evaluate(() => {
    const px = (sel) => parseFloat(getComputedStyle(document.querySelector(sel)).fontSize);
    return { name: px("#touch-panel .experience-touch-name"), brand: px(".app-brand__name"), cam: px("#camera-panel .experience-heading") };
  });
  check("the object name is the largest text", sizes.name > sizes.brand * 1.5 && sizes.name > sizes.cam * 2, JSON.stringify(sizes));
  check("the touched object's thumbnail sits beside its name", await (async () => {
    for (let i = 0; i < 30; i++) {
      await waitText(f.page, "#touch-panel", /Touching now|Holding now/);
      const t = await box(f.page, "#touch-panel .experience-touch-thumb");
      const n = await box(f.page, "#touch-panel .experience-touch-name");
      if (t && n && t.height > 0 && Math.abs(t.y + t.height / 2 - (n.y + n.height / 2)) < 40 && t.x < n.x) return true;
      await f.page.waitForTimeout(200);
    }
    return false;
  })());

  const speech = await f.page.evaluate(() => {
    const s = document.querySelector("#touch-panel .experience-speech");
    const lead = s.querySelector(".experience-speech-lead");
    const title = s.querySelector(".experience-speech-title");
    return {
      lead: lead.hidden ? "" : lead.textContent,
      leadBeforeTitle: Boolean(lead.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING),
      leadSize: parseFloat(getComputedStyle(lead).fontSize),
      titleSize: parseFloat(getComputedStyle(title).fontSize),
      text: s.innerText,
    };
  });
  check("demo audio leads with 'Demo audio — no sound.'", speech.lead === "Demo audio — no sound." && speech.leadBeforeTitle && speech.leadSize > speech.titleSize, JSON.stringify({ lead: speech.lead, l: speech.leadSize, t: speech.titleSize }));
  check("demo audio never claims a completed sound", !/does not confirm it was heard/.test(speech.text) && !/^Completed$/m.test(speech.text));

  const alt = await f.page.locator("#camera-panel .experience-camera-img").getAttribute("alt");
  check("camera alt text says it is a recorded demo clip", /Recorded demo clip, not a live camera/.test(alt), alt);
  check("advanced camera controls are in View options (closed)", await f.page.evaluate(() => {
    const d = document.querySelector("#camera-panel .experience-camera-options");
    return Boolean(d && !d.open && d.querySelector("input[type=checkbox]") && d.querySelector(".experience-legend"));
  }));

  const controls = await f.page.evaluate(() => {
    const bg = (el) => getComputedStyle(el).backgroundColor;
    const filled = (el) => !/rgba\(0, 0, 0, 0\)|transparent/.test(bg(el));
    const search = document.querySelector("#find-panel .experience-button-primary");
    return {
      searchFilled: filled(search),
      findFilledButtons: [...document.querySelectorAll("#find-panel button")].filter((b) => !b.hidden && filled(b)).length,
      quiet: ["#events-panel .operations-button-quiet", "#camera-panel .experience-camera-top .experience-button"].map(
        (s) => [...document.querySelectorAll(s)].every((b) => !filled(b)),
      ),
    };
  });
  check("Search is the one filled action in its area", controls.searchFilled && controls.findFilledButtons === 1, JSON.stringify(controls));
  check("full screen, pause and clear are quiet controls", controls.quiet.every(Boolean));
  const find = await box(f.page, "#find-panel");
  check("search panel is sized to its content", find.height < 320, `${Math.round(find.height)} px`);
  check("no page-wide cage: the grid has no border or rule background", await f.page.evaluate(() => {
    const cs = getComputedStyle(document.querySelector(".app-layout"));
    return cs.borderTopWidth === "0px" && /rgba\(0, 0, 0, 0\)|transparent/.test(cs.backgroundColor);
  }));

  // No touch: pointing Pip beside the short instruction; at most one prominent mascot.
  await waitText(f.page, "#touch-panel", /Touch an object to hear its name\./);
  const pips = await visiblePips(f.page);
  check("pointing Pip appears beside the empty-touch instruction", pips.some((p) => /pip-point/.test(p.cls)));
  check("at most one prominent Pip (taller than 80 px) at a time", pips.filter((p) => p.h > 80).length <= 1, JSON.stringify(pips));
  check("Pip stays small (64-96 px) in ordinary panels", pips.every((p) => p.h >= 40 && p.h <= 96), JSON.stringify(pips));
  check("every Pip is decorative (empty alt)", await f.page.evaluate(() => [...document.querySelectorAll(".pip")].every((p) => p.getAttribute("alt") === "")));
  await waitText(f.page, "#touch-panel", /Touching now/);
  check("Pip steps aside while an object is touched", !(await visiblePips(f.page)).some((p) => /pip-point/.test(p.cls)));

  // Help sign: real HTML text.
  await f.page.locator("#touch-panel summary", { hasText: "How touch works" }).click();
  const sign = await f.page.locator("#touch-panel .pip-sign__text").innerText();
  check("the help sign's words are real text", /Let go and touch again/.test(sign));
  const signFit = await f.page.evaluate(() => {
    const t = document.querySelector(".pip-sign__text");
    return t.scrollHeight <= t.clientHeight + 1 && t.scrollWidth <= t.clientWidth + 1;
  });
  check("the help sign grows with its text (no overflow)", signFit);

  // Long name and repeated events, through the real store and renderer (injected display input).
  const longName = "Extra-large family-size organic unsweetened Greek-style yoghurt with honey";
  await f.page.evaluate((n) => {
    const store = globalThis.empyreanDashboard.store;
    const snap = store.getSnapshot().state;
    store.receiveState({ ...snap, current_touch: { object_id: 999, text: n, state: "touching", ts: snap.now } });
  }, longName);
  await f.page.waitForTimeout(150);
  const wrap = await f.page.evaluate(() => {
    const n = document.querySelector("#touch-panel .experience-touch-name");
    return { fits: n.scrollWidth <= n.clientWidth + 1, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
  });
  check("a long object name wraps without overflow (injected display input)", wrap.fits && wrap.overflow <= 0, JSON.stringify(wrap));
  check("repeated touches are grouped in activity", await waitText(f.page, "#events-panel", /× \d+/, 30000));
  check("no requests leave this server; no console errors", f.foreign.length === 0 && f.errors.length === 0, [...f.foreign, ...f.errors].join("; "));
  await f.context.close();

  // Widths, zoom, keyboard, reduced motion.
  for (const width of [360, 768, 1440]) {
    const v = await open(FAKE, { width, height: 900 });
    await v.page.waitForTimeout(1500);
    const over = await v.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(`no horizontal scroll at ${width}px`, over <= 0, `${over}`);
    await v.context.close();
  }
  const zoom = await open(FAKE, { width: 720, height: 900 });
  await zoom.page.waitForTimeout(1500);
  check("200% zoom (720 CSS px) reflows without page scroll", (await zoom.page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0);
  await zoom.context.close();
  const k = await open(FAKE);
  await k.page.keyboard.press("Tab");
  const first = await k.page.evaluate(() => document.activeElement?.textContent?.trim());
  check("keyboard: the first Tab reaches the skip link", /Skip to dashboard/.test(first || ""), first);
  const tabs = [];
  for (let i = 0; i < 12; i++) {
    await k.page.keyboard.press("Tab");
    tabs.push(await k.page.evaluate(() => {
      const a = document.activeElement;
      const cs = getComputedStyle(a);
      return { name: (a.textContent || a.getAttribute("aria-label") || a.tagName).trim().slice(0, 24), outline: cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2 };
    }));
  }
  check("keyboard: every focused control shows a strong focus ring", tabs.every((t) => t.outline), JSON.stringify(tabs.filter((t) => !t.outline)));
  await k.context.close();
  const rm = await open(FAKE, { reducedMotion: "reduce" });
  const dur = await rm.page.evaluate(() => getComputedStyle(document.querySelector(".operations-filters"), "::after").transitionDuration);
  check("reduced motion removes transitions", parseFloat(dur) < 0.01, dur);
  await rm.context.close();

  // Contrast of every visible text element, both themes.
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
        const r = el.getBoundingClientRect();
        if (cs.visibility === "hidden" || r.width === 0 || r.height === 0 || el.closest("[hidden],.operations-sr-only,.ui-visually-hidden,[data-announcer],.experience-camera-frame")) continue;
        const [a, b] = [lum(parse(cs.color)), lum(bgOf(el))].sort((x, y) => y - x);
        const ratio = (a + 0.05) / (b + 0.05);
        const size = parseFloat(cs.fontSize);
        const large = size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700);
        if (ratio < (large ? 3 : 4.5)) out.push(`${el.tagName}.${el.className} "${el.textContent.trim().slice(0, 24)}" ${ratio.toFixed(2)}`);
      }
      return out;
    });
    check(`${theme}: every visible text element meets WCAG AA contrast`, low.length === 0, low.slice(0, 5).join(" | "));
    await c.context.close();
  }
}

// ---------------- Demo harness: real-mode speech states, log-only, camera gap ----------------
if (!only || only === "demo") {
  const d = await open(DEMO);
  const speechSel = "#touch-panel .experience-speech";
  for (const [label, re] of [["Queued", /…\s*Queued/], ["Speaking", /▶\s*Speaking/], ["Completed", /✓\s*Completed/], ["Failed", /!\s*Failed/]]) {
    const ok = await waitText(d.page, speechSel, re, 20000);
    const lead = await d.page.locator(`${speechSel} .experience-speech-lead`).isVisible();
    check(`real audio shows '${label}' plainly, with no demo lead`, ok && !lead);
    if (label === "Completed") {
      check("real 'Completed' still says it does not confirm anyone heard it", /does not confirm it was heard/.test(await text(d.page, speechSel)));
    }
  }
  check("log-only audio leads with the no-sound sentence", await waitText(d.page, speechSel, /No sound — the speech engine is unavailable/, 20000));
  // Camera gap, repeating: frames for 15 s, none for 30 s (stale, then offline), then recovery.
  await waitText(d.page, "#camera-panel", /Live/, 60000);
  check("camera goes stale when frames stop (demo gap)", await waitText(d.page, "#camera-panel", /out of date|offline/i, 60000));
  const staleAlt = await d.page.locator("#camera-panel .experience-camera-img").getAttribute("alt");
  check("stale or offline camera alt text says so", /Out-of-date camera picture|Camera unavailable/.test(staleAlt), staleAlt);
  check("camera recovers to live when frames return", await waitText(d.page, "#camera-panel", /Live/, 60000));
  check("no console errors (demo harness)", d.errors.length === 0, d.errors.join("; "));
  await d.context.close();
}

// ---------------- Real storage with no database: search unavailable, spoken and shown ----------------
if (!only || only === "storage") {
  const s = await open(STORAGE);
  const field = s.page.getByLabel("What are you looking for?");
  await field.fill("bottle");
  await field.press("Enter");
  check("search with storage down says unavailable, not 'not found'", await waitText(s.page, "#find-panel", /unavailable/i, 15000) && !/have not seen/i.test(await text(s.page, "#find-panel")));
  await s.context.close();
}

// ---------------- Hazard: Pip hidden, real warning first, simulation subordinate ----------------
if (!only || only === "hazard") {
  const h = await open(HAZARD);
  await waitText(h.page, "#warning-panel", /No recent warnings/, 15000);
  check("an active real hazard expands at once", await waitText(h.page, "#warning-panel", /Active warning/, 15000));
  check("Pip is hidden during an active real hazard", (await visiblePips(h.page)).length === 0, JSON.stringify(await visiblePips(h.page)));
  await h.page.locator("#demo-panel summary").first().click();
  await h.page.getByRole("button", { name: "Simulate alert" }).click();
  await h.page.waitForTimeout(250);
  const order = await h.page.evaluate(() => {
    const real = document.querySelector("#warning-panel .operations-warning-real");
    const sim = document.querySelector("#warning-panel .operations-warning-sim");
    if (!real) return "no-real";
    if (!sim) return "no-sim";
    return {
      realFirst: Boolean(real.compareDocumentPosition(sim) & Node.DOCUMENT_POSITION_FOLLOWING),
      realTaller: real.getBoundingClientRect().height > sim.getBoundingClientRect().height,
      simDashed: getComputedStyle(sim).borderTopStyle === "dashed",
    };
  });
  check("a later simulation stays below, smaller and dashed", typeof order === "object" && order.realFirst && order.realTaller && order.simDashed, JSON.stringify(order));
  await h.context.close();
}

console.log(results.join("\n"));
console.log(`${results.length - failed} passed, ${failed} failed`);
await browser.close();
process.exit(failed ? 1 : 0);
