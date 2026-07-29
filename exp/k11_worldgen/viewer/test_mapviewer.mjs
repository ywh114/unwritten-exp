#!/usr/bin/env node
/**
 * K11 map viewer end-to-end tests — self-contained (Puppeteer).
 *
 *   node exp/k11_worldgen/viewer/test_mapviewer.mjs
 *
 * Loads the viewer page (file://) and injects a .k11view bundle via
 * window.loadBundle().  Each test prints "PASS <name>" or "FAIL <name>"
 * and the script exits with the number of failures as the exit code.
 */

import { readFileSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import puppeteer from "puppeteer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(__dirname, "..", "..", "..");
const HTML_PATH = resolve(__dirname, "map.html");
const BUNDLE_PATH = resolve(
  REPO, "exp", "k11_worldgen", "out", "seed_00000001", "seed_00000001.k11view",
);

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

let browser;
let page;

// ── tests ──

test("launch puppeteer and load viewer page", async () => {
  browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
  page = await browser.newPage();

  // Collect console errors
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  const pageErrors = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  // Load the page from file://
  await page.goto("file://" + HTML_PATH, { waitUntil: "networkidle0", timeout: 15000 });

  page._consoleErrors = consoleErrors;
  page._pageErrors = pageErrors;
});

test("inject bundle via loadBundle", async () => {
  // Read the bundle from disk and inject via fetch from file://
  const bundleUrl = "file://" + BUNDLE_PATH;

  await page.evaluate(async (url) => {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`Failed to fetch bundle: ${r.status}`);
    const buf = await r.arrayBuffer();
    window.loadBundle(buf);
  }, bundleUrl);

  // Wait for the backdrop image to load and rendering to settle
  await new Promise((r) => setTimeout(r, 1500));
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
  const hasPixels = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    if (!canvas) return false;
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    if (w === 0 || h === 0) return false;
    const data = ctx.getImageData(0, 0, w, h).data;
    let nonZero = 0;
    for (let i = 0; i < data.length; i += 4 * 50) {
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
  const box = await page.evaluate(() => {
    const c = document.querySelector("canvas");
    const r = c.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });

  await page.mouse.move(box.x, box.y);
  await new Promise((r) => setTimeout(r, 600));

  const tooltipOk = await page.evaluate(() => {
    const tt = document.getElementById("tooltip");
    if (!tt || tt.style.display === "none") return false;
    const text = tt.textContent.toLowerCase();
    const biomes = [
      "ocean", "boreal taiga", "temperate grassland", "tropical conifer forest",
      "desert xeric shrubland", "temperate broadleaf forest", "montane grassland",
      "mediterranean scrub", "mangrove", "rock", "ice", "lake", "tundra",
      "tropical moist forest", "tropical dry forest", "tropical grassland",
      "flooded grassland",
    ];
    for (const b of biomes) {
      if (text.includes(b.toLowerCase())) return true;
    }
    return false;
  });
  if (!tooltipOk) throw new Error("Tooltip not visible or no biome name found");
});

test("area selection updates stats panel with cells count", async () => {
  const box = await page.evaluate(() => {
    const c = document.querySelector("canvas");
    const r = c.getBoundingClientRect();
    return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
  });

  const half = 40; // screen px for selection

  await page.keyboard.down("Shift");
  await page.mouse.move(box.cx - half, box.cy - half);
  await page.mouse.down();
  await page.mouse.move(box.cx + half, box.cy + half);
  await new Promise((r) => setTimeout(r, 100));
  await page.mouse.up();
  await page.keyboard.up("Shift");

  await new Promise((r) => setTimeout(r, 800));

  const areaOk = await page.evaluate(() => {
    const el = document.getElementById("area-stats");
    if (!el) return false;
    const text = el.textContent;
    return /cells/.test(text) && /\d+/.test(text);
  });
  if (!areaOk) throw new Error("Area stats panel not updated with cell count");
});

test("search for biome == \"ocean\" returns cells > 0 and overlay present", async () => {
  await page.click("#search-input");
  await page.evaluate(() => {
    const inp = document.getElementById("search-input");
    inp.value = "";
  });
  await page.type("#search-input", 'biome == "ocean"');
  await page.click("#search-submit");

  await new Promise((r) => setTimeout(r, 1500));

  const searchOk = await page.evaluate(() => {
    const res = document.getElementById("search-results");
    if (!res) return false;
    const text = res.textContent;
    const m = text.match(/(\d+)\s+cells/);
    if (!m || parseInt(m[1], 10) <= 0) return false;
    return true;
  });
  if (!searchOk) throw new Error("Search did not return positive cell count");

  // Check mask overlay rendered on canvas
  const maskLoaded = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    const data = ctx.getImageData(0, 0, w, h).data;
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

test("search elev_m>2000 biome==boreal taiga returns >1000 cells", async () => {
  // Clear and run combined search
  await page.evaluate(() => {
    document.getElementById("search-input").value =
      'elev_m > 2000 & biome == "boreal taiga"';
    document.getElementById("search-submit").click();
  });

  await new Promise((r) => setTimeout(r, 1500));

  const result = await page.evaluate(() => {
    const res = document.getElementById("search-results");
    if (!res) return { ok: false, count: 0 };
    const text = res.textContent;
    const m = text.match(/(\d+)\s+cells/);
    const count = m ? parseInt(m[1], 10) : 0;
    return { ok: count > 1000, count };
  });

  console.log(`  elev_m>2000 & boreal taiga cell count: ${result.count}`);
  if (!result.ok) {
    throw new Error(
      `Expected >1000 cells for elev_m>2000 & boreal taiga, got ${result.count}`,
    );
  }
});

test("take screenshot with taiga search overlay", async () => {
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
    if (page) await page.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
  }

  console.log(`\n${tests.length - failures}/${tests.length} tests passed`);
  process.exit(failures);
}

main();
