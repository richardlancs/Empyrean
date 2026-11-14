// Viewport (not full-page) screenshot of the live app while an object is touched.
//   node tests/ui/bauhaus/viewport.mjs <out.png> <base> <width> <height> [--css file] [--theme high-contrast] [--any]
import fs from "node:fs";
import { loadPlaywright } from "../../agent4/pw.mjs";
const [out, base, w, h, ...rest] = process.argv.slice(2);
const opt = (n) => (rest.includes(`--${n}`) ? rest[rest.indexOf(`--${n}`) + 1] : null);
const { chromium } = await loadPlaywright();
const b = await chromium.launch();
const c = await b.newContext({ viewport: { width: Number(w), height: Number(h) } });
if (opt("theme")) await c.addInitScript((t) => localStorage.setItem("empyrean.theme", JSON.stringify(t)), opt("theme"));
const p = await c.newPage();
await p.goto(`${base}/`, { waitUntil: "domcontentloaded" });
if (opt("css")) await p.addStyleTag({ content: fs.readFileSync(opt("css"), "utf8") });
await p.waitForSelector("#touch-panel");
const end = Date.now() + 25000;
let touched = false;
while (!rest.includes("--any") && Date.now() < end) {
  if (/Touching now|Holding now/.test(await p.locator("#touch-panel").innerText().catch(() => ""))) { touched = true; break; }
  await p.waitForTimeout(120);
}
await p.waitForTimeout(rest.includes("--any") ? 2500 : 0);
await p.screenshot({ path: out });
console.log(out, "touched", touched);
await b.close();
