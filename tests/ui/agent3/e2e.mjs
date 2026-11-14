// Browser checks for the operations feature against the FIXTURE harness (artificial data only).
//
// Needs playwright-core and a Chromium binary; neither is a project dependency:
//   python3 -m http.server 8793 --bind 127.0.0.1        (from the repo root)
//   PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core \
//   CHROMIUM=/path/to/chrome HARNESS_URL=http://127.0.0.1:8793/tests/ui/agent3/harness.html \
//   SHOTS=/some/dir node tests/ui/agent3/e2e.mjs

import assert from "node:assert/strict";

const { chromium } = await import(process.env.PLAYWRIGHT_CORE || "playwright-core");
const BASE = process.env.HARNESS_URL || "http://127.0.0.1:8793/tests/ui/agent3/harness.html";
const SHOTS = process.env.SHOTS || "";

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
const results = [];
async function check(name, fn) {
  try {
    await fn();
    results.push(`PASS ${name}`);
  } catch (err) {
    results.push(`FAIL ${name}: ${err.message}`);
  }
}

async function open(scenario, { width = 1440, height = 1000, reducedMotion = "no-preference", contrast } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, reducedMotion, contrast });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/favicon/.test(m.location().url) && errors.push(m.text()));
  await page.goto(`${BASE}?scenario=${encodeURIComponent(scenario)}`);
  await page.waitForSelector(".operations-status");
  page.errors = errors;
  return page;
}
const action = (page, name) => page.evaluate((n) => window.__fixture.ACTIONS[n](), name);
const announcements = (page) => page.$$eval("#fixture-announcements li", (ls) => ls.map((l) => l.textContent));
const shot = async (page, name) => SHOTS && page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });

await check("real and simulated together: real stays prominent, sim compact and labelled", async () => {
  const page = await open("Real + simulated together");
  const cards = await page.$$eval(".operations-warning-card", (cs) =>
    cs.map((c) => ({ cls: c.className, text: c.textContent })),
  );
  assert.equal(cards.length, 2);
  assert.match(cards[0].cls, /operations-warning-real/);
  assert.doesNotMatch(cards[0].cls, /compact/);
  assert.match(cards[1].cls, /operations-warning-sim.*compact|compact.*operations-warning-sim/);
  assert.match(cards[1].text, /Simulated/);
  const log = await announcements(page);
  assert.ok(log.some((l) => l.startsWith("[assertive] Warning: Drop ahead")));
  assert.ok(log.some((l) => l.startsWith("[polite] Simulated warning for testing")));
  assert.ok(!log.some((l) => l.includes("[assertive] Simulated")));
  await shot(page, "real-and-simulated-1440");
  assert.deepEqual(page.errors, []);
});

await check("replayed snapshot and reconnect do not re-announce or duplicate", async () => {
  const page = await open("Real warning active");
  const before = (await announcements(page)).length;
  const rows = await page.$$eval(".operations-event", (l) => l.length);
  await action(page, "Replay same snapshot");
  await action(page, "Reconnect cycle");
  await page.waitForTimeout(1800);
  const after = await announcements(page);
  const warningAnnouncements = after.filter((l) => l.includes("Warning: Vehicle"));
  assert.equal(warningAnnouncements.length, 1);
  assert.ok(after.some((l) => l.includes("connection lost")));
  assert.ok(after.some((l) => l.includes("reconnected")));
  assert.equal(after.length, before + 2);
  assert.equal(await page.$$eval(".operations-event", (l) => l.length), rows);
});

await check("expired warning shows as previous, not active, and is not announced on load", async () => {
  const page = await open("Expired warning");
  assert.equal(await page.$$eval(".operations-warning-card", (c) => c.length), 0);
  const prev = await page.$$eval(".operations-previous-row", (r) => r.map((x) => x.textContent));
  assert.ok(prev[0].startsWith("Previous warning"));
  assert.ok(prev.some((t) => t.startsWith("Previous simulated warning") && t.includes("Simulated")));
  assert.ok(await page.isVisible("text=No recent warnings."));
  assert.equal((await announcements(page)).length, 0);
  await shot(page, "expired-1440");
});

await check("active warning expires quietly", async () => {
  const page = await open("Real warning active");
  await page.waitForTimeout(3500);
  assert.equal(await page.$$eval(".operations-warning-card", (c) => c.length), 0);
  assert.ok((await page.textContent(".operations-previous")).includes("Previous warning"));
  assert.equal((await announcements(page)).length, 1);
});

await check("simulate success routes through renderer once, despite socket echo", async () => {
  const page = await open("Quiet, all active");
  await page.click("summary:has-text('Demo tools')");
  assert.ok(await page.isVisible("text=Adds a simulated warning to this dashboard only."));
  await page.click("button:has-text('Simulate alert')");
  assert.equal(await page.getAttribute(".operations-button-demo", "aria-disabled"), "true");
  await page.waitForSelector(".operations-demo-status[data-status='success']");
  assert.ok(await page.isVisible(".operations-warning-sim"));
  await page.waitForTimeout(700); // socket echo
  const simRows = await page.$$eval(".operations-event-sim", (l) => l.length);
  assert.equal(simRows, 1);
  const count = await page.$$eval(".operations-event-sim .operations-count", (c) => c.map((x) => x.hidden));
  assert.deepEqual(count, [true]);
  const simAnn = (await announcements(page)).filter((l) => l.includes("Simulated warning for testing"));
  assert.equal(simAnn.length, 1);
  assert.equal(await page.getAttribute(".operations-button-demo", "aria-disabled"), "false");
  await shot(page, "simulate-success-1440");
});

for (const [mode, pattern] of [
  ["http", /HTTP 500/],
  ["network", /Could not reach/],
]) {
  await check(`simulate ${mode} failure is reported and the button re-enables`, async () => {
    const page = await open("Quiet, all active");
    await page.selectOption("#fixture-request", mode);
    await page.click("summary:has-text('Demo tools')");
    await page.click("button:has-text('Simulate alert')");
    await page.waitForSelector(".operations-demo-status[data-status$='_error']");
    assert.match(await page.textContent(".operations-demo-status"), pattern);
    assert.equal(await page.getAttribute(".operations-button-demo", "aria-disabled"), "false");
    assert.equal(await page.$$eval(".operations-warning-sim", (c) => c.length), 0);
    if (mode === "http") await shot(page, "simulate-http-failure-1440");
  });
}

await check("active real warning stays first while demo tools are used", async () => {
  const page = await open("Real warning active");
  await page.click("summary:has-text('Demo tools')");
  await page.click("button:has-text('Simulate alert')");
  await page.waitForSelector(".operations-demo-status[data-status='success']");
  const cls = await page.$$eval(".operations-warning-card", (cs) => cs.map((c) => c.className));
  assert.match(cls[0], /real/);
  assert.match(cls[1], /sim.*compact|compact.*sim/);
});

await check("pause freezes the list, counts new events, keeps focus, and resumes", async () => {
  const page = await open("Quiet, all active");
  const rows = await page.$$eval(".operations-event", (l) => l.length);
  await page.click("button:has-text('Pause activity view')");
  assert.equal(await page.getAttribute("button[data-focus-key='pause']", "aria-pressed"), "true");
  await page.focus("button[data-focus-key='pause']");
  await action(page, "Push touch");
  await action(page, "Push touch");
  assert.equal(await page.$$eval(".operations-event", (l) => l.length), rows);
  assert.match(await page.textContent(".operations-notice-paused"), /2 new events since pausing/);
  assert.equal(await page.evaluate(() => document.activeElement.dataset.focusKey), "pause");
  await action(page, "Burst 15 touches (one update)");
  assert.match(await page.textContent(".operations-notice-paused"), /At least 12 new events/);
  await shot(page, "paused-1440");
  await page.click(".operations-notice-paused button");
  assert.equal(await page.evaluate(() => document.activeElement.dataset.focusKey), "pause");
  assert.ok((await page.$$eval(".operations-event", (l) => l.length)) > rows);
});

await check("clear affects this view only; new activity appears; restore works", async () => {
  const page = await open("Repeated warnings");
  await page.click("button:has-text('Clear this view')");
  assert.equal(await page.$$eval(".operations-event", (l) => l.length), 0);
  assert.match(await page.textContent(".operations-history"), /Saved history and other viewers are not affected/);
  assert.equal(await page.getAttribute("button[data-focus-key='clear']", "aria-disabled"), "true");
  // The warning panel is unaffected by clearing.
  assert.equal(await page.$$eval(".operations-warning-real", (c) => c.length), 1);
  await action(page, "Push touch");
  assert.equal(await page.$$eval(".operations-event", (l) => l.length), 1);
  await page.click("button:has-text('Show cleared activity')");
  assert.ok((await page.$$eval(".operations-event", (l) => l.length)) > 1);
});

await check("repeats are grouped with a count and every occurrence time", async () => {
  const page = await open("Repeated warnings");
  const first = page.locator(".operations-event").first();
  assert.match(await first.textContent(), /× 4/);
  await first.locator("summary:has-text('Show all 4 times')").click();
  assert.equal(await first.locator(".operations-occurrence-list li").count(), 4);
  await shot(page, "repeated-1440");
});

await check("filters show selected state and empty messages", async () => {
  const page = await open("Quiet, all active");
  await page.click(".operations-filter:has-text('Warning')");
  assert.equal(await page.getAttribute(".operations-filter:has-text('Warning')", "aria-pressed"), "true");
  assert.equal(await page.getAttribute(".operations-filter:has-text('All')", "aria-pressed"), "false");
  assert.ok(await page.isVisible("text=No warnings in recent activity."));
  await page.click(".operations-filter:has-text('Touch')");
  assert.equal(await page.$$eval(".operations-event-touch", (l) => l.length), 2);
});

await check("exact time is available on focus and click", async () => {
  const page = await open("Quiet, all active");
  const time = page.locator(".operations-event .operations-time").first();
  assert.equal(await time.locator(".operations-time-exact").isVisible(), false);
  await time.locator("button").focus();
  assert.equal(await time.locator(".operations-time-exact").isVisible(), true);
  await time.locator("button").click();
  assert.equal(await time.locator("button").getAttribute("aria-expanded"), "true");
  assert.match(await time.locator("button").getAttribute("aria-label"), /^At /);
});

await check("connection and module status are separate; unknown telemetry is unknown", async () => {
  const page = await open("Unknown telemetry (old server)");
  assert.match(await page.textContent(".operations-connection"), /Dashboard connected/);
  const statuses = await page.$$eval(".operations-chip-status", (s) => s.map((x) => x.textContent));
  assert.deepEqual(statuses, ["Unknown", "Unknown", "Unknown", "Unknown", "Unknown"]);
  await page.selectOption("#fixture-connection", "reconnecting");
  assert.match(await page.textContent(".operations-connection"), /disconnected, reconnecting/);
});

await check("partial failure is visible, idle naming is not 'failed'", async () => {
  const page = await open("Partial module failure");
  const chips = await page.$$eval(".operations-chip", (cs) => cs.map((c) => [c.dataset.tone, c.textContent]));
  assert.deepEqual(chips.map((c) => c[0]), ["caution", "ok", "caution", "error", "unknown"]);
  assert.match(chips[0][1], /No recent frames/);
  await page.click("summary:has-text('Status details')");
  assert.match(await page.textContent(".operations-status-list"), /database host unreachable/);
  await shot(page, "partial-failure-1440");
  const quiet = await open("Quiet, all active");
  const naming = await quiet.$$eval(".operations-chip", (cs) => cs[2].textContent);
  assert.match(naming, /Naming.*Active/);
});

await check("no live regions inside feature roots (timer ticks stay quiet)", async () => {
  const page = await open("Real warning active");
  const live = await page.$$eval(
    "#health-panel [aria-live], #warning-panel [aria-live], #events-panel [aria-live], #demo-panel [aria-live], #health-panel [role=status], #warning-panel [role=status], #events-panel [role=status], #demo-panel [role=status], #warning-panel [role=alert]",
    (l) => l.length,
  );
  assert.equal(live, 0);
});

await check("keyboard: every control reachable and focus is visible", async () => {
  const page = await open("Repeated warnings");
  await page.click("summary:has-text('Demo tools')");
  const seen = new Set();
  for (let i = 0; i < 60; i += 1) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => {
      const a = document.activeElement;
      if (!a || !a.closest("#health-panel, #warning-panel, #events-panel, #demo-panel")) return null;
      const cs = getComputedStyle(a);
      return { text: (a.textContent || "").trim().slice(0, 40), outline: cs.outlineStyle, width: cs.outlineWidth };
    });
    if (info) {
      assert.equal(info.outline, "solid", `no focus outline on ${info.text}`);
      seen.add(info.text);
    }
  }
  for (const label of ["All", "Touch", "Warning", "Pause activity view", "Clear this view", "Simulate alert", "Status details"]) {
    assert.ok([...seen].some((t) => t.startsWith(label) || t.includes(label)), `not reachable: ${label}`);
  }
});

await check("44px minimum target size for primary controls", async () => {
  const page = await open("Quiet, all active");
  await page.click("summary:has-text('Demo tools')");
  const small = await page.$$eval(".operations-button, .operations-filter, .operations-disclosure-summary", (bs) =>
    bs.filter((b) => b.offsetParent && b.getBoundingClientRect().height < 44 && !b.closest(".operations-event")).map((b) => b.textContent),
  );
  assert.deepEqual(small, []);
});

for (const [width, height] of [
  [360, 800],
  [720, 900], // 1440 at 200% zoom
  [768, 1000],
  [1440, 1000],
]) {
  await check(`no horizontal overflow at ${width}px with long names`, async () => {
    const page = await open("Overflowing history, long names", { width, height });
    await page.click("summary:has-text('Status details')");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(overflow <= 0, `overflow ${overflow}px`);
    await shot(page, `long-names-${width}`);
  });
}

await check("contrast of key text pairs is at least 4.5:1 (normal and high contrast)", async () => {
  for (const contrast of ["no-preference", "more"]) {
    const page = await open("Real + simulated together", { contrast });
    await page.click("summary:has-text('Demo tools')");
    const low = await page.evaluate(() => {
      const rgb = (s) => s.match(/[\d.]+/g).slice(0, 4).map(Number);
      const lum = ([r, g, b]) => {
        const f = (c) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
      };
      const bgOf = (el) => {
        for (let n = el; n; n = n.parentElement) {
          const c = rgb(getComputedStyle(n).backgroundColor);
          if (c.length < 4 || c[3] > 0) return c;
        }
        return [255, 255, 255];
      };
      const bad = [];
      const roots = document.querySelectorAll("#health-panel, #warning-panel, #events-panel, #demo-panel");
      for (const root of roots) {
        for (const el of root.querySelectorAll("*")) {
          if (!el.offsetParent || ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
          const a = lum(rgb(getComputedStyle(el).color));
          const b = lum(bgOf(el));
          const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          if (ratio < 4.5) bad.push(`${el.className || el.tagName}: ${ratio.toFixed(2)}`);
        }
      }
      return bad;
    });
    assert.deepEqual(low, [], `${contrast}: ${low.join(", ")}`);
    await shot(page, `contrast-${contrast}`);
  }
});

await check("cleanup removes the feature and stops updates", async () => {
  const page = await open("Quiet, all active");
  await page.evaluate(() => window.__cleanup());
  await action(page, "Push real warning");
  assert.equal(await page.$$eval("#warning-panel *", (l) => l.length), 0);
  assert.deepEqual(page.errors, []);
});

await browser.close();
console.log(results.join("\n"));
const failed = results.filter((r) => r.startsWith("FAIL")).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
