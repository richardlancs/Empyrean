// Design-iteration screenshots of the LIVE app at a comparable moment (an object
// being touched). Optional --css injects an exploration stylesheet into this
// browser only; nothing is shipped or changed on the server.
//   node tests/ui/bauhaus/shoot.mjs <out.png> [--base URL] [--width 1440] [--css file] [--full] [--theme high-contrast]
import fs from "node:fs";
import { loadPlaywright } from "../agent4/pw.mjs";

const args = process.argv.slice(2);
const out = args[0];
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : fallback;
};
const base = opt("base", "http://localhost:8002");
const width = Number(opt("width", "1440"));
const css = opt("css", null);
const theme = opt("theme", null);
const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width, height: 1000 } });
if (theme) {
  await context.addInitScript((t) => localStorage.setItem("empyrean.theme", JSON.stringify(t)), theme);
}
const page = await context.newPage();
await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
if (css) await page.addStyleTag({ content: fs.readFileSync(css, "utf8") });
await page.waitForSelector("#touch-panel", { timeout: 10000 });
const deadline = Date.now() + 25000;
let touched = false;
while (Date.now() < deadline) {
  const t = await page.locator("#touch-panel").innerText().catch(() => "");
  if (/Touching now|Holding now/.test(t)) { touched = true; break; }
  await page.waitForTimeout(120);
}
await page.screenshot({ path: out, fullPage: args.includes("--full") });
console.log(`${out} touched=${touched}`);
await browser.close();
