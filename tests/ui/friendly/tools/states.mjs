// Capture the friendly states from a LIVE app: no touch (pointing Pip), help sign open,
// welcome open, cleared (empty) history with seated Pip. Usage: node states.mjs <base> <outdir>
import { loadPlaywright } from "../../agent4/pw.mjs";
const [base, out] = process.argv.slice(2);
const { chromium } = await loadPlaywright();
const b = await chromium.launch();
const c = await b.newContext({ viewport: { width: 1440, height: 900 } });
const p = await c.newPage();
await p.goto(`${base}/`, { waitUntil: "domcontentloaded" });
await p.waitForSelector("#touch-panel");
const waitFor = async (sel, re, ms = 25000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (re.test(await p.locator(sel).innerText().catch(() => ""))) return true; await p.waitForTimeout(120); }
  return false;
};
await waitFor("#touch-panel", /Touch an object to hear its name\./);
await p.locator("#touch-panel").screenshot({ path: `${out}/state-no-touch.png` });
await p.locator("#touch-panel summary", { hasText: "How touch works" }).click();
await p.waitForTimeout(200);
await p.locator("#touch-panel").screenshot({ path: `${out}/state-help-sign.png` });
await p.locator(".app-welcome > summary").click();
await p.waitForTimeout(200);
await p.screenshot({ path: `${out}/state-welcome.png`, clip: { x: 700, y: 0, width: 740, height: 360 } });
await p.locator(".app-welcome > summary").click();
await p.getByRole("button", { name: "Clear this view" }).click();
await p.waitForTimeout(300);
await p.locator("#events-panel").screenshot({ path: `${out}/state-history-empty.png` });
console.log("ok");
await b.close();
