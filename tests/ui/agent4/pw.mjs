// Load Playwright from a local or global install (not a project dependency).
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import path from "node:path";

export async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch {
    const root = execSync("npm root -g").toString().trim();
    return createRequire(path.join(root, "noop.js"))("playwright");
  }
}
