// Agent 1 browser checks for the foundation, against the fixture preview server.
//
//   node tests/ui/agent1/browser/foundation-check.mjs
//
// Needs Playwright (global install is fine) and the repo's Python venv
// (PYTHON=/path/to/python to override). Starts two preview servers itself,
// prints one line per check, writes screenshots to tests/ui/agent1/screenshots/,
// and exits non-zero if any check fails. Stub features stand in for Agents 2 and 3,
// so this verifies the foundation only, not the integrated features.

import { execSync, spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../../../..");
const SHOTS = path.resolve(HERE, "../screenshots");
const PYTHON = process.env.PYTHON ?? path.resolve(ROOT, "../Empyrean/.venv/bin/python");
const PORT = 8771;
const BROKEN_PORT = 8772;
const BASE = `http://127.0.0.1:${PORT}`;

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch {
    const globalRoot = execSync("npm root -g").toString().trim();
    return createRequire(path.join(globalRoot, "noop.js"))("playwright");
  }
}

function startServer(port, extra = []) {
  const proc = spawn(PYTHON, [path.join(ROOT, "tests/ui/agent1/agent1_preview_server.py"), "--port", String(port), ...extra], {
    cwd: ROOT,
    stdio: "ignore",
  });
  return proc;
}

async function waitFor(url, ms = 15000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error(`server at ${url} did not start`);
}

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
}

const scenario = (name) => fetch(`${BASE}/preview/scenario/${name}`, { method: "POST" });

async function main() {
  mkdirSync(SHOTS, { recursive: true });
  const servers = [startServer(PORT), startServer(BROKEN_PORT, ["--missing-features"])];
  const { chromium } = await loadPlaywright();
  const browser = await chromium.launch();
  try {
    await waitFor(`${BASE}/api/state`);
    await waitFor(`http://127.0.0.1:${BROKEN_PORT}/api/state`);

    // ---------- Layout at target widths ----------
    for (const [label, width, height] of [["360", 360, 780], ["768", 768, 1024], ["1440", 1440, 900], ["zoom200-1280", 640, 400]]) {
      const context = await browser.newContext({ viewport: { width, height } });
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
      for (const name of ["touch", "long-names"]) {
        await scenario(name);
        await page.goto(BASE);
        await page.waitForSelector(".experience-touch__name");
        await page.waitForTimeout(300);
        const m = await page.evaluate(() => {
          const r = (id) => document.getElementById(id).getBoundingClientRect();
          return {
            scrollW: document.documentElement.scrollWidth,
            innerW: window.innerWidth,
            touch: r("touch-panel"),
            camera: r("camera-panel"),
            warning: r("warning-panel"),
            health: r("health-panel"),
            objects: r("objects-panel"),
            clipped: [...document.querySelectorAll(".experience-touch__name, .experience-object__name")].some(
              (el) => el.scrollWidth > el.clientWidth + 1,
            ),
          };
        });
        check(`${label}px ${name}: no horizontal page scroll`, m.scrollW <= m.innerW, `${m.scrollW} <= ${m.innerW}`);
        check(`${label}px ${name}: names wrap, not clipped`, !m.clipped);
        check(`${label}px ${name}: health, then warning, above the touch`, m.health.top < m.warning.top && m.warning.top < m.touch.top);
        if (width >= 1024) {
          check(`${label}px: camera left of a 360-420px info column`, m.camera.left < m.touch.left && m.touch.width >= 359 && m.touch.width <= 421, `info ${Math.round(m.touch.width)}px`);
        } else {
          check(`${label}px ${name}: touch before camera before objects`, m.touch.top < m.camera.top && m.camera.top < m.objects.top);
        }
        if (name === "touch") await page.screenshot({ path: path.join(SHOTS, `touch-${label}.png`), fullPage: true });
      }
      check(`${label}px: no console or page errors`, errors.length === 0, errors.join(" | "));
      await context.close();
    }

    // ---------- Keyboard, focus, targets ----------
    {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      await scenario("touch");
      await page.goto(BASE);
      await page.waitForSelector(".experience-touch__name");
      await page.keyboard.press("Tab");
      const skip = await page.evaluate(() => {
        const el = document.activeElement;
        const r = el.getBoundingClientRect();
        return { cls: el.className, visible: r.top >= 0 && r.bottom <= innerHeight, text: el.textContent };
      });
      check("first Tab reaches a visible skip link", skip.cls === "skip-link" && skip.visible, skip.text);
      await page.keyboard.press("Enter");
      check("skip link moves focus to main", await page.evaluate(() => document.activeElement.id === "main"));
      await page.keyboard.press("Tab");
      const ring = await page.evaluate(() => {
        const s = getComputedStyle(document.activeElement);
        return { tag: document.activeElement.tagName, style: s.outlineStyle, width: parseFloat(s.outlineWidth), color: s.outlineColor };
      });
      check("focused control shows a 3px+ focus ring", ring.style === "solid" && ring.width >= 3, `${ring.tag} ${ring.width}px ${ring.color}`);
      const small = await page.evaluate(() =>
        [...document.querySelectorAll("button, input, select, .skip-link")]
          .filter((el) => el.offsetParent !== null)
          .map((el) => [el.textContent.trim() || el.id, el.getBoundingClientRect()])
          .filter(([, r]) => r.height < 44 || r.width < 44)
          .map(([n, r]) => `${n} ${Math.round(r.width)}x${Math.round(r.height)}`),
      );
      check("every visible control is at least 44x44px", small.length === 0, small.join(", "));
      const landmarks = await page.evaluate(() => ({
        banner: !!document.querySelector("header.app-header"),
        main: !!document.querySelector("main#main"),
        footer: !!document.querySelector("footer"),
        h1: document.querySelectorAll("h1").length,
        mountsInOrder: [...document.querySelectorAll("main section[id$='-panel']")].map((s) => s.id).join(","),
        buttonsTyped: [...document.querySelectorAll("button")].every((b) => b.hasAttribute("type")),
      }));
      check("landmarks: banner, main, footer, one h1", landmarks.banner && landmarks.main && landmarks.footer && landmarks.h1 === 1);
      check(
        "mount DOM order is the semantic order",
        landmarks.mountsInOrder === "health-panel,warning-panel,touch-panel,camera-panel,objects-panel,find-panel,events-panel,demo-panel",
      );
      check("every button has an explicit type", landmarks.buttonsTyped);
      const sizes = await page.evaluate(() => ({
        body: parseFloat(getComputedStyle(document.body).fontSize),
        brand: parseFloat(getComputedStyle(document.querySelector(".app-brand__name")).fontSize),
        name: parseFloat(getComputedStyle(document.querySelector(".experience-touch__name")).fontSize),
        chip: Math.min(...[...document.querySelectorAll(".ui-chip")].map((c) => parseFloat(getComputedStyle(c).fontSize))),
      }));
      check("body text 17-18px", sizes.body >= 17 && sizes.body <= 18, `${sizes.body}px`);
      check("object name larger than the brand", sizes.name > sizes.brand * 1.4, `${sizes.name}px vs ${sizes.brand}px`);
      check("badges at least 13px", sizes.chip >= 13, `${sizes.chip}px`);
      await context.close();
    }

    // ---------- Theme: toggle, persistence, no flash, storage failure ----------
    {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      await scenario("touch");
      await page.goto(BASE);
      await page.click("[data-shell-control=contrast]");
      const after = await page.evaluate(() => ({
        theme: document.documentElement.dataset.theme,
        saved: localStorage.getItem("empyrean.theme"),
        pressed: document.querySelector("[data-shell-control=contrast]").getAttribute("aria-pressed"),
      }));
      check("contrast toggle switches theme and saves it", after.theme === "high-contrast" && after.saved === '"high-contrast"' && after.pressed === "true");
      await page.screenshot({ path: path.join(SHOTS, "touch-1440-high-contrast.png") });
      // Block app.js entirely: the saved theme must still be applied by the head script.
      await page.route("**/static/app.js", (route) => route.abort());
      await page.goto(BASE);
      check("saved theme applies before app.js runs (no flash)", (await page.evaluate(() => document.documentElement.dataset.theme)) === "high-contrast");
      await page.unroute("**/static/app.js");
      await context.close();

      const blocked = await browser.newContext({ viewport: { width: 768, height: 900 } });
      await blocked.addInitScript(() => {
        Object.defineProperty(window, "localStorage", { get() { throw new DOMException("blocked", "SecurityError"); } });
      });
      const p2 = await blocked.newPage();
      const errs = [];
      const warns = [];
      p2.on("pageerror", (e) => errs.push(e.message));
      p2.on("console", (m) => (m.type() === "warning" ? warns : m.type() === "error" ? errs : []).push(m.text()));
      await p2.goto(BASE);
      await p2.waitForSelector(".experience-touch__name");
      await p2.click("[data-shell-control=contrast]");
      const theme = await p2.evaluate(() => document.documentElement.dataset.theme);
      check("blocked storage: page works, toggle works for this visit", errs.length === 0 && theme === "high-contrast", errs.join(" | "));
      check("blocked storage: one clear warning", warns.filter((w) => w.includes("preferences cannot be saved")).length === 1);
      await blocked.close();

      const prefers = await browser.newContext({ viewport: { width: 768, height: 900 }, contrast: "more" });
      const p3 = await prefers.newPage();
      await p3.goto(BASE);
      check("OS 'more contrast' selects high contrast by default", (await p3.evaluate(() => document.documentElement.dataset.theme)) === "high-contrast");
      await prefers.close();
    }

    // ---------- Reduced motion ----------
    {
      const context = await browser.newContext({ reducedMotion: "reduce" });
      const page = await context.newPage();
      await page.goto(BASE);
      const t = await page.evaluate(() => {
        const b = document.querySelector(".ui-button");
        return parseFloat(getComputedStyle(b).transitionDuration);
      });
      check("reduced motion removes transitions", t <= 0.001, `${t}s`);
      await context.close();
    }

    // ---------- Warnings: emphasis hook ----------
    {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      await page.goto(BASE);
      const emphasis = async (name) => {
        await scenario(name);
        await page.waitForTimeout(700);
        return page.evaluate(() => {
          const w = document.getElementById("warning-panel");
          return { emphasis: w.dataset.emphasis ?? "", position: getComputedStyle(w).position, camera: getComputedStyle(document.getElementById("camera-panel")).position };
        });
      };
      const active = await emphasis("hazard-active");
      check("active real warning pins the warning slot", active.emphasis === "urgent" && active.position === "sticky");
      await page.screenshot({ path: path.join(SHOTS, "hazard-active-1440.png") });
      await page.evaluate(() => window.scrollTo(0, 600));
      const pinnedTop = await page.evaluate(() => document.getElementById("warning-panel").getBoundingClientRect().top);
      check("pinned warning stays in view after scrolling", pinnedTop >= -1 && pinnedTop < 20, `top ${pinnedTop}`);
      await scenario("long-names");
      await page.waitForTimeout(700);
      let overlap = false;
      for (let y = 0; y <= 3000; y += 150) {
        overlap ||= await page.evaluate((y) => {
          window.scrollTo(0, y);
          const cam = document.getElementById("camera-panel").getBoundingClientRect();
          const ev = document.getElementById("events-panel").getBoundingClientRect();
          return cam.bottom > ev.top + 1 && cam.left < ev.right;
        }, y);
      }
      check("camera never covers the activity panel while scrolling", !overlap);
      await page.evaluate(() => window.scrollTo(0, 0));
      const both = await emphasis("real-and-simulated");
      check("real warning keeps priority over a later simulation", both.emphasis === "urgent");
      const sim = await emphasis("simulated");
      check("simulated warning is not pinned", sim.emphasis === "simulated" && sim.position !== "sticky");
      const expired = await emphasis("hazard-expired");
      check("expired warning releases the slot", expired.emphasis === "" && expired.position !== "sticky");
      await context.close();
    }

    // ---------- Announcements: events only, never ticks ----------
    {
      const context = await browser.newContext();
      const page = await context.newPage();
      await scenario("held");
      await page.goto(BASE);
      await page.waitForSelector(".experience-touch__name");
      await page.evaluate(() => {
        window.__writes = [];
        for (const r of document.querySelectorAll("[data-announcer]")) {
          new MutationObserver(() => r.textContent && window.__writes.push([r.dataset.announcer, r.textContent])).observe(r, { childList: true, characterData: true, subtree: true });
        }
      });
      await page.waitForTimeout(3500); // three or more 1 s snapshots, steady state
      const steady = await page.evaluate(() => window.__writes.length);
      check("steady snapshots and timers announce nothing", steady === 0, `${steady} writes`);
      await scenario("retouch");
      await page.waitForTimeout(3000);
      let writes = await page.evaluate(() => window.__writes.splice(0));
      const touches = writes.filter(([p, t]) => p === "polite" && t.includes("Touching"));
      check("a new touch is announced once, politely, across repeated snapshots", touches.length === 1 && writes.length === 1, JSON.stringify(writes));
      await scenario("hazard-active");
      await page.waitForTimeout(3000);
      writes = await page.evaluate(() => window.__writes);
      const hazard = writes.filter(([p, t]) => p === "assertive" && t.includes("Warning"));
      check("a new real warning is announced once, assertively", hazard.length === 1, JSON.stringify(writes));
      const firstPolite = writes.findIndex(([p]) => p === "polite");
      check("a warning is read before any polite message of the same moment", writes[0]?.[0] === "assertive" && (firstPolite === -1 || firstPolite > 0), JSON.stringify(writes));
      await context.close();
    }

    // ---------- Reconnect ----------
    {
      const context = await browser.newContext();
      const page = await context.newPage();
      await scenario("touch");
      await page.goto(BASE);
      await page.waitForFunction(() => window.empyreanDashboard?.store.getSnapshot().connection === "connected");
      await fetch(`${BASE}/preview/drop?seconds=2`, { method: "POST" });
      await page.waitForFunction(() => window.empyreanDashboard.store.getSnapshot().connection === "reconnecting", null, { timeout: 5000 });
      await page.waitForFunction(() => document.querySelector("[data-announcer=polite]").textContent.includes("connection lost"), null, { timeout: 3000 }).catch(() => {});
      const lost = await page.evaluate(() => document.querySelector("[data-announcer=polite]").textContent);
      check("connection loss is shown in the store and announced", lost.includes("connection lost"), lost);
      await page.waitForFunction(() => window.empyreanDashboard.store.getSnapshot().connection === "connected", null, { timeout: 15000 });
      await page.waitForTimeout(300);
      const restored = await page.evaluate(() => document.querySelector("[data-announcer=polite]").textContent);
      check("reconnects by itself and announces it", restored.includes("restored"), restored);
      await context.close();
    }

    // ---------- Cleanup ----------
    {
      const context = await browser.newContext();
      const page = await context.newPage();
      await page.goto(BASE);
      await page.waitForSelector(".experience-touch__name");
      const after = await page.evaluate(() => {
        const app = window.empyreanDashboard;
        const before = app.store.listenerCount();
        app.destroy();
        return { before, after: app.store.listenerCount(), regions: document.querySelectorAll("[data-announcer]").length, emphasis: document.getElementById("warning-panel") };
      });
      check("destroy releases every subscription and live region", after.before > 0 && after.after === 0 && after.regions === 0, `${after.before} -> ${after.after}`);
      await context.close();
    }

    // ---------- Feature load failure ----------
    {
      const context = await browser.newContext({ viewport: { width: 768, height: 1024 } });
      const page = await context.newPage();
      const errors = [];
      page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
      await page.goto(`http://127.0.0.1:${BROKEN_PORT}/`);
      await page.waitForSelector(".ui-feature-error");
      const shown = await page.evaluate(() => [...document.querySelectorAll(".ui-feature-error__title")].map((e) => e.textContent));
      check("missing features show an understandable error in all 8 mounts", shown.length === 8, shown[0]);
      check("load failures are logged, not swallowed", errors.length >= 2, `${errors.length} console errors`);
      check("shell still works without features", await page.isVisible("[data-shell-control=contrast]"));
      await page.screenshot({ path: path.join(SHOTS, "features-missing-768.png"), fullPage: true });
      await context.close();
    }

    // ---------- Inventory ----------
    {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      await page.goto(`${BASE}/preview/inventory`);
      await page.waitForSelector(".swatch");
      await page.screenshot({ path: path.join(SHOTS, "inventory-1440.png"), fullPage: true });
      check("visual inventory renders", (await page.locator(".swatch").count()) >= 16);
      await context.close();
    }
  } finally {
    await browser.close();
    for (const s of servers) s.kill();
  }
  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(2);
});
