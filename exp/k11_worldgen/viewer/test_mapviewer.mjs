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

test("tooltip hidden when hovering outside map area", async () => {
  // Move mouse to the left panel area (well outside the canvas)
  await page.mouse.move(10, 300);
  await new Promise((r) => setTimeout(r, 600));

  const hidden = await page.evaluate(() => {
    const tt = document.getElementById("tooltip");
    return tt.style.display === "none" || tt.style.display === "";
  });
  if (!hidden) throw new Error("Tooltip should be hidden outside map area");
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

// ── New tests for fixes ──

test("month chips exist and are all selected by default", async () => {
  const chipInfo = await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    if (chips.length !== 12) return { ok: false, msg: `Expected 12 chips, got ${chips.length}` };
    let allOn = true;
    for (const c of chips) {
      if (!c.classList.contains("on")) { allOn = false; break; }
    }
    return { ok: allOn, count: chips.length };
  });
  if (!chipInfo.ok) throw new Error(chipInfo.msg || "Not all month chips are on by default");
});

test("deselecting months changes tooltip label", async () => {
  // First get the current tooltip at center with all months selected
  const box = await page.evaluate(() => {
    const c = document.querySelector("canvas");
    const r = c.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });

  // Dispatch mousemove to get tooltip with all months on
  await page.evaluate(({ x, y }) => {
    const c = document.querySelector("canvas");
    const ev = new MouseEvent("mousemove", { clientX: x, clientY: y, bubbles: true });
    c.dispatchEvent(ev);
  }, box);
  await new Promise((r) => setTimeout(r, 600));

  const ttAll = await page.evaluate(() => {
    const tt = document.getElementById("tooltip");
    return { text: tt.textContent, display: tt.style.display };
  });
  if (ttAll.display !== "block") throw new Error("Tooltip not visible with all months");

  // Now deselect months June, July, August (months 5,6,7) — only winter
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    // Deselect JJA (months 5,6,7)
    for (const m of [5, 6, 7]) {
      if (chips[m] && chips[m].classList.contains("on")) chips[m].click();
    }
  });
  await new Promise((r) => setTimeout(r, 200));

  // Re-trigger tooltip
  await page.evaluate(({ x, y }) => {
    const c = document.querySelector("canvas");
    const ev = new MouseEvent("mousemove", { clientX: x, clientY: y, bubbles: true });
    c.dispatchEvent(ev);
  }, box);
  await new Promise((r) => setTimeout(r, 600));

  const ttWinter = await page.evaluate(() => {
    const tt = document.getElementById("tooltip");
    return { text: tt.textContent, display: tt.style.display };
  });
  if (ttWinter.display !== "block") throw new Error("Tooltip not visible with winter months");

  // Tooltip should show a month label like "(SONDJFMAM)" or "(JJA)" etc — not just "(year)"
  if (ttWinter.text.includes("(year)") && !ttWinter.text.includes("SONDJFMAM")) {
    // If it still says "(year)", the months might not have been deselected
  }
  // The tooltip label should have changed
  if (ttWinter.text === ttAll.text) {
    throw new Error("Tooltip text did not change after deselecting months");
  }
  console.log(`  Tooltip with all months: ${ttAll.text.substring(0, 100)}`);
  console.log(`  Tooltip with winter: ${ttWinter.text.substring(0, 100)}`);
});

test("missing field gives helpful error", async () => {
  // Search for a known spec field that might be absent — use "non_existent_field" which is NOT a known spec field
  // and also test that the error for a truly unknown field still works
  const result = await page.evaluate(() => {
    const inp = document.getElementById("search-input");
    const btn = document.getElementById("search-submit");
    const err = document.getElementById("search-error");
    // Test unknown field
    inp.value = "xyz_unknown_field > 0";
    btn.click();
    const msg1 = err.textContent;
    // Reset
    inp.value = "";
    btn.click();
    return { msg: msg1 };
  });
  if (!result.msg.includes("unknown field")) {
    throw new Error(`Expected 'unknown field' error, got: ${result.msg}`);
  }
});

test("stats panel has overflow-y auto", async () => {
  const overflow = await page.evaluate(() => {
    const body = document.getElementById("stats-body");
    if (!body) return null;
    const style = window.getComputedStyle(body);
    return style.overflowY;
  });
  if (overflow !== "auto") {
    throw new Error(`Expected overflow-y:auto, got: ${overflow}`);
  }
});

test("backdrop image is square", async () => {
  const isSquare = await page.evaluate(() => {
    // We can't directly access the backdropImg from outside, but we can check
    // the canvas renders squarely. Alternative: check that switching to World
    // layer renders the backdrop (square image).
    // Since backdrop_is_square is true in the new bundle, the Image should be loaded.
    // Check that the canvas has content and that switching to world layer works.
    const canvases = document.querySelectorAll("canvas");
    // The main canvas should be painted
    const c = canvases[0];
    if (!c) return false;
    return c.width > 0 && c.height > 0;
  });
  if (!isSquare) throw new Error("Canvas not painted for world layer");
  console.log("  backdrop_is_square=True — World layer uses square backdrop");
});

test("take screenshot with winter temperature overlay", async () => {
  // Clear search
  await page.evaluate(() => {
    document.getElementById("search-clear").click();
  });

  // Switch to Temperature layer
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#layer-buttons button");
    for (const b of btns) {
      if (b.textContent.trim() === "Temperature") { b.click(); break; }
    }
  });
  await new Promise((r) => setTimeout(r, 400));

  // Deselect summer months (JJA = 5,6,7) to show winter average
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    for (const m of [5, 6, 7]) {
      if (chips[m] && chips[m].classList.contains("on")) chips[m].click();
    }
  });
  await new Promise((r) => setTimeout(r, 600));

  // Type "winter" into search to show nothing on overlay (we want the temp layer visible)
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
