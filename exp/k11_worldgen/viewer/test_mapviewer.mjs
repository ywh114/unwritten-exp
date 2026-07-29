#!/usr/bin/env node
/**
 * K11 map viewer end-to-end tests (Puppeteer).
 *
 *   node exp/k11_worldgen/viewer/test_mapviewer.mjs
 *
 * Spawns the mapserver, loads the viewer page, and runs assertions.
 * Each test prints "PASS <name>" or "FAIL <name> — <reason>" and the
 * script exits with the number of failures as the exit code.
 */

import { spawn } from "child_process";
import { createServer } from "net";
import { mkdirSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import puppeteer from "puppeteer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(__dirname, "..", "..", "..");
const PY = "uv";
const MODULE = "exp.k11_worldgen.mapserver";

// ── helpers ──

function findFreePort() {
  return new Promise((resolve, reject) => {
    const s = createServer();
    s.listen(0, "127.0.0.1", () => {
      const port = s.address().port;
      s.close(() => resolve(port));
    });
    s.on("error", reject);
  });
}

async function fetchOk(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok) return r;
    } catch (_) { /* not yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Server not ready after ${timeoutMs}ms: ${url}`);
}

// ── test runner ──

const tests = [];
let failures = 0;

function test(name, fn) {
  tests.push({ name, fn });
}

async function run() {
  for (const t of tests) {
    try {
      await t.fn();
      console.log(`PASS ${t.name}`);
    } catch (e) {
      failures++;
      console.log(`FAIL ${t.name} — ${e.message}`);
    }
  }
}

// ── global state ──

let serverProc;
let port;
let browser;
let page;

// ── tests ──

test("find free port and start mapserver", async () => {
  port = await findFreePort();
  serverProc = spawn(
    PY,
    ["run", "python", "-m", MODULE, "--port", String(port)],
    { cwd: REPO, stdio: "pipe" },
  );
  // wait for it to be ready
  await fetchOk(`http://127.0.0.1:${port}/api/worlds`);
});

test("launch puppeteer and load viewer page", async () => {
  browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
  page = await browser.newPage();

  // Collect console errors
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  await page.goto(`http://127.0.0.1:${port}/`, {
    waitUntil: "networkidle0",
    timeout: 15000,
  });

  // Store for later assertions
  page._consoleErrors = consoleErrors;
  page._pageErrors = pageErrors;
});

test("zero console errors", async () => {
  if (page._consoleErrors.length > 0) {
    throw new Error(`console errors: ${page._consoleErrors.join("; ")}`);
  }
  if (page._pageErrors.length > 0) {
    throw new Error(`page errors: ${page._pageErrors.join("; ")}`);
  }
});

test("map canvas painted (non-blank pixels)", async () => {
  // Wait a moment for first paint
  await new Promise((r) => setTimeout(r, 500));
  const hasPixels = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    if (!canvas) return false;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    if (w === 0 || h === 0) return false;
    // Sample a grid of points — canvas might have blank borders from fit
    const data = ctx.getImageData(0, 0, w, h).data;
    let nonZero = 0;
    const step = 4; // RGBA
    for (let i = 0; i < data.length; i += step * 50) {
      if (data[i] !== 0 || data[i + 1] !== 0 || data[i + 2] !== 0) {
        nonZero++;
        if (nonZero >= 5) return true;
      }
    }
    return false;
  });
  if (!hasPixels) throw new Error("Canvas has no visible pixels");
});

test("pixel tooltip appears on hover with biome name", async () => {
  // Get canvas center
  const box = await page.evaluate(() => {
    const c = document.querySelector("canvas");
    const r = c.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });

  // Move mouse to center of canvas and wait for tooltip debounce
  await page.mouse.move(box.x, box.y);
  await new Promise((r) => setTimeout(r, 600));

  const tooltipOk = await page.evaluate(() => {
    const tt = document.getElementById("tooltip");
    if (!tt || tt.style.display === "none") return false;
    const text = tt.textContent;
    // Check for known biome names
    const biomes = [
      "ocean", "boreal taiga", "temperate grassland", "tropical conifer forest",
      "desert xeric shrubland", "temperate broadleaf forest", "montane grassland",
      "mediterranean scrub", "mangrove", "rock", "ice", "lake", "tundra",
      "tropical moist forest", "tropical dry forest", "tropical grassland",
      "flooded grassland",
    ];
    for (const b of biomes) {
      if (text.toLowerCase().includes(b.toLowerCase())) return true;
    }
    return false;
  });
  if (!tooltipOk) throw new Error("Tooltip not visible or no biome name found");
});

test("area selection updates stats panel with cells count", async () => {
  // Find canvas center
  const box = await page.evaluate(() => {
    const c = document.querySelector("canvas");
    const r = c.getBoundingClientRect();
    return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
  });

  const half = 40; // selection half-size in screen pixels

  // Shift+drag to select an area
  await page.keyboard.down("Shift");
  await page.mouse.move(box.cx - half, box.cy - half);
  await page.mouse.down();
  await page.mouse.move(box.cx + half, box.cy + half);
  await new Promise((r) => setTimeout(r, 100));
  await page.mouse.up();
  await page.keyboard.up("Shift");

  // Wait for area stats fetch
  await new Promise((r) => setTimeout(r, 800));

  const areaOk = await page.evaluate(() => {
    const el = document.getElementById("area-stats");
    if (!el) return false;
    const text = el.textContent;
    // Should contain "cells" and some number
    return /cells/.test(text) && /\d+/.test(text);
  });
  if (!areaOk) throw new Error("Area stats panel not updated with cell count");
});

test("search for biome == \"ocean\" returns cells > 0 and overlay is present", async () => {
  // Type the search query
  await page.click("#search-input");
  await page.evaluate(() => {
    document.getElementById("search-input").value = "";
  });
  await page.type("#search-input", 'biome == "ocean"');
  await page.click("#search-submit");

  // Wait for results
  await new Promise((r) => setTimeout(r, 1500));

  const searchOk = await page.evaluate(() => {
    const res = document.getElementById("search-results");
    if (!res) return false;
    const text = res.textContent;
    // Check cells > 0
    if (!/\d+/.test(text)) return false;
    const m = text.match(/(\d+)\s+cells/);
    if (!m || parseInt(m[1], 10) <= 0) return false;
    return true;
  });
  if (!searchOk) throw new Error("Search did not return positive cell count");
});

test("mask overlay present in canvas after search", async () => {
  // After the ocean search, check that mask is loaded
  const maskLoaded = await page.evaluate(() => {
    // Check the internal state for maskLoaded
    // We can also test by checking canvas for semi-transparent red
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    const data = ctx.getImageData(0, 0, w, h).data;
    // Look for reddish pixels (R >> G, R >> B, alpha ~ 55% of 255)
    let redCount = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
      if (r > 180 && r > g * 1.5 && r > b * 1.5 && a > 40) {
        redCount++;
        if (redCount >= 10) return true;
      }
    }
    return false;
  });
  if (!maskLoaded) throw new Error("Search mask overlay not visible on canvas");
});

test("search for taiga then take screenshot", async () => {
  // Clear previous search and run taiga search
  await page.evaluate(() => {
    document.getElementById("search-input").value = 'biome == "boreal taiga"';
    document.getElementById("search-submit").click();
  });

  await new Promise((r) => setTimeout(r, 1500));

  const ssDir = resolve(REPO, "tmp");
  mkdirSync(ssDir, { recursive: true });
  const ssPath = resolve(ssDir, "k11_mapviewer.png");
  await page.screenshot({ path: ssPath, fullPage: false });
  console.log(`Screenshot saved: ${ssPath}`);
});

// ── main ──

async function main() {
  try {
    await run();
  } finally {
    // Cleanup
    if (page) await page.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
    if (serverProc) {
      serverProc.kill("SIGTERM");
      // Give it a moment, then force kill
      setTimeout(() => {
        try { serverProc.kill("SIGKILL"); } catch (_) {}
      }, 2000);
    }
  }

  console.log(`\n${tests.length - failures}/${tests.length} tests passed`);
  process.exit(failures);
}

main();
