#!/usr/bin/env node
/**
 * Copies monaco-editor/min/vs into public/monaco-vs so the editor can be
 * served from the Next.js origin instead of a public CDN. Runs automatically
 * after npm install and can be re-run manually via `npm run copy:monaco`.
 */
import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "..", "node_modules", "monaco-editor", "min", "vs");
const dest = resolve(here, "..", "public", "monaco-vs");

if (!existsSync(src)) {
  console.warn(
    `[copy-monaco] Skipped: ${src} does not exist yet. Re-run after npm install.`,
  );
  process.exit(0);
}

if (existsSync(dest)) {
  rmSync(dest, { recursive: true, force: true });
}

cpSync(src, dest, { recursive: true });
console.log(`[copy-monaco] Copied Monaco editor into ${dest}`);
