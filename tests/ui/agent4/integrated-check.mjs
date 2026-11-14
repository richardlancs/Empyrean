// Browser checks against the LIVE assembled app (not fixtures).
//
// Start the app first, for example:
//   python -m app --fake vision namer storage audio            (scenario "normal")
//   python -m app --fake vision namer storage audio hazard     (scenario "hazard")
//   python -m app --only dashboard --fake scene                (scenario "unavailable")
// then:  node tests/ui/agent4/integrated-check.mjs <scenario> [base-url]
//
// Playwright is loaded from a local or global install; it is not a project dependency.
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadPlaywright } from "./pw.mjs";

const scenario = process.argv[2] || "normal";
const base = process.argv[3] || "http://localhost:8000";
const here = path.dirname(fileURLToPath(import.meta.url));
const shots = path.resolve(here, "../../../docs/dashboard-redesign/screenshots");
const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const results = [];
let failed = 0;

function check(name, ok, info = "") {
  results.push(`${ok ? "PASS" : "FAIL"} ${name}${info ? ` — ${info}` : ""}`);
  if (!ok) failed += 1;
}

async function open(viewport = { width: 1440, height: 1000 }, options = {}) {
  const context = await browser.newContext({ viewport, ...options });
  // Record every message written to the shell's live regions.
  await context.addInitScript(() => {
    window.__announcements = [];
    new MutationObserver(() => {
      for (const region of document.querySelectorAll("[data-announcer]")) {
        const t = region.textContent.trim();
        const last = region.__last || "";
        if (t && t !== last) window.__announcements.push(`${region.dataset.announcer}: ${t}`);
        region.__last = t;
      }
    }).observe(document, { subtree: true, childList: true, characterData: true });
  });
  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  // The MJPEG <img> never finishes loading, so never wait for "load".
  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#touch-panel", { timeout: 10000 });
  return { page, errors, context };
}

const text = (page, id) => page.locator(`#${id}`).innerText();
const emphasis = (page) => page.evaluate(() => document.getElementById("warning-panel")?.dataset.emphasis ?? null);
const announcements = (page) => page.evaluate(() => window.__announcements.slice());

/** WCAG contrast ratio of two rgb()/rgba() strings. */
function contrast(fg, bg) {
  const lum = (c) => {
    const [r, g, b] = c.match(/[\d.]+/g).slice(0, 3).map(Number).map((v) => {
      const x = v / 255;
      return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

/** Computed colours of feature elements next to the shell's own token values. */
function themeSample(page) {
  return page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const probe = document.createElement("div");
    document.body.append(probe);
    const resolve = (name) => {
      probe.style.color = `var(${name})`;
      return getComputedStyle(probe).color;
    };
    const tokens = Object.fromEntries(
      ["--color-text", "--color-accent", "--color-border-control", "--color-surface", "--color-page"].map(
        (n) => [n, resolve(n)],
      ),
    );
    probe.remove();
    const css = (sel, prop) => {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el)[prop] : null;
    };
    return {
      theme: document.documentElement.dataset.theme,
      tokens,
      touchText: css("#touch-panel .experience-card", "color"),
      // The background actually behind the text: modules may be transparent on the page grid.
      touchBg: (() => {
        for (let n = document.querySelector("#touch-panel .experience-card"); n; n = n.parentElement) {
          const c = getComputedStyle(n).backgroundColor;
          if (c && c !== "transparent" && !/rgba\([^)]*,\s*0\)$/.test(c)) return c;
        }
        return getComputedStyle(document.body).backgroundColor;
      })(),
      searchButton: css("#find-panel .experience-button-primary", "backgroundColor"),
      searchButtonText: css("#find-panel .experience-button-primary", "color"),
      inputBorder: css("#find-panel .experience-input", "borderTopColor"),
      inputBorderWidth: css("#find-panel .experience-input", "borderTopWidth"),
      filterOn: css('#events-panel .operations-filter[aria-pressed="true"]', "backgroundColor"),
      healthText: css("#health-panel .operations-status", "color"),
      mutedText: css("#find-panel .experience-muted", "color"),
      pageBg: getComputedStyle(document.body).backgroundColor,
      rootAccentDeclared: root.getPropertyValue("--color-accent").trim(),
    };
  });
}
const overflow = (page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const api = async (page, p) => page.evaluate(async (u) => (await fetch(u)).json(), p);

async function waitText(page, id, pattern, timeout = 20000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const t = await text(page, id).catch(() => "");
    if (pattern.test(t)) return t;
    await page.waitForTimeout(150);
  }
  return null;
}

if (scenario === "normal") {
  const a = await open();
  const theme = await a.page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.color = "var(--color-page)";
    document.body.append(probe);
    const page = getComputedStyle(probe).color;
    probe.remove();
    return [document.documentElement.dataset.theme, getComputedStyle(document.body).backgroundColor, page];
  });
  // Compared with the shell's own --color-page token, not a literal, so a palette change stays valid.
  check("light mode is the default", theme[0] === "light" && theme[1] === theme[2], theme.join(" "));

  // Engine -> read model -> /ws -> store -> touch card.
  await waitText(a.page, "camera-panel", /Live/, 15000);
  await waitText(a.page, "touch-panel", /Touch an object/, 20000); // wait for the next touch cycle
  const touchText = await waitText(a.page, "touch-panel", /(Touching|Holding) now/);
  await a.page.screenshot({ path: `${shots}/normal-touch-1440.png` });
  check("a real touch from the engine reaches the touch card", touchText !== null);
  const state = await api(a.page, "/api/state");
  const backendTouch = state.current_touch || state.last_touch;
  const shown = await text(a.page, "touch-panel");
  check("touch card shows the backend's touched object", Boolean(backendTouch) && shown.includes(backendTouch.text),
    backendTouch ? `${backendTouch.text} (${backendTouch.state})` : "none");
  const camera = await waitText(a.page, "camera-panel", /Live|recorded clip/, 10000);
  check("recorded clip is labelled, not shown as a camera", /recorded clip/.test(camera || ""));
  const health = await text(a.page, "health-panel");
  // Fakes are labelled either per module "(fake)" or by a visible "Fake inputs" tag plus the count.
  check("fake modules are labelled fake", (/\(fake\)/.test(health) || /Fake inputs/.test(health)) && /running as fake/.test(health));
  const touch = await waitText(a.page, "touch-panel", /Demo audio — no sound/, 15000);
  check("fake audio is never shown as real playback", touch !== null);
  const objects = await text(a.page, "objects-panel");
  check("objects list renders engine objects", /in view/.test(objects), objects.split("\n")[0]);
  const thumbs = await a.page.evaluate(() =>
    [...document.querySelectorAll("#objects-panel img")].filter((i) => i.naturalWidth > 0).length);
  check("thumbnails load from /api/objects/{id}/thumbnail", thumbs > 0, `${thumbs} loaded`);

  // Reverse path: find panel -> API -> service -> bus -> store -> result.
  const label = state.current_touch?.class_label || state.last_touch?.class_label || "bottle";
  const field = a.page.getByLabel("What are you looking for?");
  await field.fill(label);
  await field.press("Enter");
  const found = await waitText(a.page, "find-panel", /Recorded at/, 10000);
  check("last-touch search through the UI is found with its touch time", found !== null, label);
  check("the found result lists the recorded neighbours", /Recorded next to: /.test(found || ""), label);
  await a.page.locator("#find-panel").screenshot({ path: `${shots}/last-touch-found-1440.png` });
  await field.fill("zebra");
  await field.press("Enter");
  const missing = await waitText(a.page, "find-panel", /not (found|seen)|No recorded|have not seen/i, 10000);
  check("an unmatched search says not found", missing !== null);

  // Two clients: view-only controls stay in their own browser.
  const b = await open();
  // Overlay switches may sit in a "View options" disclosure (friendly clarity); open it if so.
  const viewOptions = a.page.locator("#camera-panel summary", { hasText: "View options" });
  if (await viewOptions.count()) await viewOptions.click();
  await a.page.getByLabel("Boxes").uncheck();
  await a.page.waitForTimeout(500);
  const srcA = await a.page.locator("#camera-panel img").first().getAttribute("src");
  const srcB = await b.page.locator("#camera-panel img").first().getAttribute("src");
  check("overlay toggle changes only this viewer's /video", /boxes=0/.test(srcA) && /boxes=1/.test(srcB),
    `${srcA} | ${srcB}`);
  await a.page.getByRole("button", { name: /Pause activity view/ }).click();
  const pausedA = await text(a.page, "events-panel");
  const pausedB = await text(b.page, "events-panel");
  check("pausing activity affects only this browser", /Resume|paused/i.test(pausedA) && !/paused/i.test(pausedB));
  const stateAfterPause = await api(b.page, "/api/state");
  check("pausing the view does not pause detection", stateAfterPause.diagnostics.camera.status === "active");

  // Simulation: page-only, labelled, never a real warning.
  await a.page.locator("#demo-panel summary").first().click();
  await a.page.getByRole("button", { name: "Simulate alert" }).click();
  const simA = await waitText(a.page, "warning-panel", /Simulated/, 5000);
  const simState = await api(a.page, "/api/state");
  check("simulated warning is shown and labelled", simA !== null);
  check("simulation leaves latest_real_warning empty", simState.latest_real_warning === null);
  await a.page.screenshot({ path: `${shots}/simulated-warning-1440.png` });

  // Simulation only: emphasis "simulated", removed when it expires.
  const simEmphasis = await emphasis(a.page);
  check("simulation alone sets warning emphasis to simulated", simEmphasis === "simulated", String(simEmphasis));
  await a.page.waitForTimeout((simState.hazard_active_seconds + 1.5) * 1000);
  check("emphasis is removed once nothing is active", (await emphasis(a.page)) === null);

  // Item 3: features follow the shell's tokens in both themes.
  const t = await open();
  for (const sel of [
    "#touch-panel .experience-card",
    "#find-panel .experience-button-primary",
    "#find-panel .experience-input",
    '#events-panel .operations-filter[aria-pressed="true"]',
    "#health-panel .operations-status",
  ]) {
    await t.page.waitForSelector(sel, { timeout: 10000 });
  }
  const light = await themeSample(t.page);
  await t.page.getByRole("button", { name: "High contrast" }).click();
  await t.page.waitForTimeout(200);
  const high = await themeSample(t.page);
  check("high contrast is applied through data-theme", light.theme === "light" && high.theme === "high-contrast");
  for (const [label, sample] of [["light", light], ["high contrast", high]]) {
    check(`${label}: touch card text uses --color-text`, sample.touchText === sample.tokens["--color-text"], sample.touchText);
    check(`${label}: search button uses --color-accent`, sample.searchButton === sample.tokens["--color-accent"], sample.searchButton);
    check(`${label}: active filter uses --color-accent`, sample.filterOn === sample.tokens["--color-accent"], sample.filterOn);
    check(`${label}: input border uses --color-border-control`,
      sample.inputBorder === sample.tokens["--color-border-control"], sample.inputBorder);
    check(`${label}: status strip text uses --color-text`, sample.healthText === sample.tokens["--color-text"], sample.healthText);
    for (const [fg, bg, name] of [
      [sample.touchText, sample.touchBg, "card text"],
      [sample.mutedText, sample.touchBg, "secondary text"],
      [sample.searchButtonText, sample.searchButton, "button text"],
    ]) {
      const ratio = contrast(fg, bg);
      check(`${label}: ${name} contrast ≥ 4.5`, ratio >= 4.5, ratio.toFixed(2));
    }
  }
  check("high contrast changes the feature colours", light.searchButton !== high.searchButton && light.inputBorderWidth !== high.inputBorderWidth,
    `${light.searchButton} → ${high.searchButton}, border ${light.inputBorderWidth} → ${high.inputBorderWidth}`);
  await t.page.screenshot({ path: `${shots}/high-contrast-1440.png` });
  await t.page.getByRole("button", { name: "High contrast" }).click(); // leave the saved theme on light
  await t.context.close();

  // Item 4: hanging POST and GET end at the search deadline in the real UI.
  for (const [what, hang] of [
    ["POST", (route) => (route.request().method() === "POST" ? null : route.continue())],
    ["GET", (route) => (route.request().method() === "GET" ? null : route.continue())],
  ]) {
    const h = await open();
    await h.page.route(/\/api\/last-seen(\/.*)?$/, (route) => hang(route)); // null = never answered
    const box = h.page.getByLabel("What are you looking for?");
    await box.fill("bottle");
    await box.press("Enter");
    const timedOut = await waitText(h.page, "find-panel", /No answer arrived in time/, 14000);
    check(`a hanging ${what} ends with the timeout message`, timedOut !== null);
    await h.context.close();
  }

  // Keyboard and widths.
  const fresh = await open();
  await fresh.page.keyboard.press("Tab");
  const first = await fresh.page.evaluate(() => {
    const el = document.activeElement;
    return { tag: el?.tagName, text: el?.textContent?.trim(), href: el?.getAttribute("href") };
  });
  check("first Tab reaches the skip link", first.tag === "A" && /skip/i.test(first.text || ""),
    JSON.stringify(first));
  const ring = await fresh.page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.color = "var(--color-focus)";
    document.body.append(probe);
    const token = getComputedStyle(probe).color;
    probe.remove();
    return [getComputedStyle(document.activeElement).outlineColor, token];
  });
  check("focused control shows the focus ring colour", ring[0] === ring[1], ring.join(" vs "));
  await fresh.context.close();
  for (const width of [360, 768, 1440]) {
    const v = await open({ width, height: 900 });
    await waitText(v.page, "objects-panel", /in view/, 10000);
    check(`no horizontal scroll at ${width}px`, (await overflow(v.page)) <= 0);
    if (width === 360) await v.page.screenshot({ path: `${shots}/mobile-360.png`, fullPage: true });
    check(`no console errors at ${width}px`, v.errors.length === 0, v.errors.join("; "));
    await v.context.close();
  }
  const zoom = await open({ width: 720, height: 900 }, { deviceScaleFactor: 2 });
  check("no horizontal scroll at 200% zoom (720 CSS px)", (await overflow(zoom.page)) <= 0);
  const reduced = await open({ width: 1440, height: 900 }, { reducedMotion: "reduce" });
  check("reduced motion loads without errors", reduced.errors.length === 0);
  check("no console errors in either client", a.errors.length === 0 && b.errors.length === 0,
    [...a.errors, ...b.errors].join("; "));
}

if (scenario === "hazard") {
  const a = await open();
  await waitText(a.page, "camera-panel", /Live/, 15000);
  await waitText(a.page, "warning-panel", /No recent warnings/, 15000); // catch the next one fresh
  const active = await waitText(a.page, "warning-panel", /Active warning/, 15000);
  check("a real HazardEvent becomes an active warning", active !== null);
  await a.page.screenshot({ path: `${shots}/hazard-active-1440.png` });
  check("an active real warning sets emphasis to urgent", (await emphasis(a.page)) === "urgent");
  const state = await api(a.page, "/api/state");
  check("backend marks it real", state.latest_real_warning && state.latest_real_warning.simulated === false);
  await a.page.locator("#demo-panel summary").first().click();
  await a.page.getByRole("button", { name: "Simulate alert" }).click();
  await a.page.waitForTimeout(300);
  const after = await api(a.page, "/api/state");
  const panel = await text(a.page, "warning-panel");
  const realFirst = !after.latest_real_warning?.active || panel.indexOf("Simulated") > panel.indexOf("Active warning");
  check("an active real warning keeps priority over a later simulation", realFirst);
  const both = await emphasis(a.page);
  check("emphasis stays urgent (not simulated) while the real warning is active",
    !after.latest_real_warning?.active || both === "urgent", String(both));
  const speech = await waitText(a.page, "touch-panel", /Stop\.|Interrupted|interrupted/, 15000);
  check("hazard speech or interruption is visible in speech status", speech !== null);
  const mobile = await open({ width: 360, height: 800 });
  await waitText(mobile.page, "warning-panel", /Active warning/, 15000);
  await mobile.page.screenshot({ path: `${shots}/hazard-active-360.png` });
  check("no console errors", a.errors.length === 0, a.errors.join("; "));
  await waitText(a.page, "warning-panel", /Active warning/, 15000);
  await a.page.evaluate(() => globalThis.empyreanDashboard.destroy());
  check("cleanup removes the warning emphasis", (await emphasis(a.page)) === null);
}

if (scenario === "unavailable") {
  const a = await open();
  await a.page.waitForTimeout(3000);
  const camera = await text(a.page, "camera-panel");
  check("no camera frames reads as offline/waiting, not live", !/\bLive\b/.test(camera), camera.split("\n")[1]);
  const health = await text(a.page, "health-panel");
  check("modules not started are not shown as active", !/5 of 5 modules active/.test(health));
  const find = await text(a.page, "find-panel");
  check("search panel renders", find.length > 0);
  await a.page.screenshot({ path: `${shots}/unavailable-1440.png` });
  check("no console errors", a.errors.length === 0, a.errors.join("; "));
}

if (scenario === "disconnect") {
  // Run while the app is being stopped: the page must say the connection is lost.
  const a = await open();
  console.log("READY_TO_STOP");
  const lost = await waitText(a.page, "health-panel", /disconnected|reconnecting/i, 30000);
  check("a stopped server reads as disconnected, statuses as last known", lost !== null);
  await a.page.screenshot({ path: `${shots}/disconnected-1440.png` });
  console.log("READY_TO_RESTART");
  const back = await waitText(a.page, "health-panel", /Dashboard connected/, 40000);
  check("the page reconnects by itself when the server returns", back !== null);
  const camera = await waitText(a.page, "camera-panel", /Live/, 20000);
  check("the video stream reopens after reconnecting", camera !== null);
  // Polite messages are delayed by the announcer; give "restored" a moment to land.
  for (let i = 0; i < 30 && !(await announcements(a.page)).some((m) => /restored/.test(m)); i++) {
    await a.page.waitForTimeout(100);
  }
  const said = await announcements(a.page);
  const lostSaid = said.filter((m) => /connection lost/i.test(m));
  check("no feature repeats the connection loss (for example the camera)",
    !said.some((m) => /Camera: Dashboard connection lost/.test(m)), JSON.stringify(said));
  const restored = said.filter((m) => /connection restored|reconnected/i.test(m));
  check("connection loss is announced exactly once", lostSaid.length === 1, JSON.stringify(said));
  check("reconnection is announced exactly once, by the shell", restored.length === 1 && /restored/.test(restored[0]),
    JSON.stringify(restored));
}

console.log(results.join("\n"));
console.log(`${results.length - failed} passed, ${failed} failed`);
await browser.close();
process.exit(failed ? 1 : 0);
