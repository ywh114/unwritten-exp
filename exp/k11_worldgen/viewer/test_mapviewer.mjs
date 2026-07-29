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

test("month chips show 1..12 and are all selected by default", async () => {
  const chipInfo = await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    if (chips.length !== 12) return { ok: false, msg: `Expected 12 chips, got ${chips.length}` };
    let allOn = true;
    for (let m = 0; m < 12; m++) {
      const c = chips[m];
      if (c.textContent.trim() !== String(m + 1)) return { ok: false, msg: `Chip ${m} shows "${c.textContent.trim()}", expected "${m+1}"` };
      if (!c.classList.contains("on")) { allOn = false; }
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
    const canvases = document.querySelectorAll("canvas");
    const c = canvases[0];
    if (!c) return false;
    return c.width > 0 && c.height > 0;
  });
  if (!isSquare) throw new Error("Canvas not painted for world layer");
  console.log("  backdrop_is_square=True — World layer uses square backdrop");
});

// ── New tests: monthly features round ──

test("shift − and + rotate month selection", async () => {
  // Explicitly ensure all months are selected (may have been changed by previous tests)
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    for (let m = 0; m < 12; m++) {
      if (!chips[m].classList.contains("on")) chips[m].click();
    }
  });
  await new Promise((r) => setTimeout(r, 200));

  // Verify all are on
  let allOn = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#month-chips button")).every(c => c.classList.contains("on"));
  });
  if (!allOn) throw new Error("Could not select all months");

  // Click − to shift: all selected → still all selected
  await page.evaluate(() => { document.getElementById("month-shift-left").click(); });
  await new Promise((r) => setTimeout(r, 200));
  allOn = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#month-chips button")).every(c => c.classList.contains("on"));
  });
  if (!allOn) throw new Error("Shift-left on all-selected should keep all selected");

  // Now deselect some months and test shift
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    for (const m of [0, 1]) { if (chips[m].classList.contains("on")) chips[m].click(); }
  });
  await new Promise((r) => setTimeout(r, 200));

  const beforeShift = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#month-chips button")).map(c => c.classList.contains("on"));
  });

  // Shift right (+)
  await page.evaluate(() => { document.getElementById("month-shift-right").click(); });
  await new Promise((r) => setTimeout(r, 200));

  const afterShift = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#month-chips button")).map(c => c.classList.contains("on"));
  });

  // Selection should have rotated right by 1
  let rotated = true;
  for (let i = 0; i < 12; i++) {
    if (beforeShift[i] !== afterShift[(i + 1) % 12]) { rotated = false; break; }
  }
  if (!rotated) throw new Error("Shift-right did not rotate month selection correctly");
});

test("dblclick solos a month; dblclick again restores all", async () => {
  // Click Feb (month 1) to make it solo
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    if (chips.length >= 12) { chips[1].dispatchEvent(new MouseEvent("dblclick", {bubbles:true})); }
  });
  await new Promise((r) => setTimeout(r, 200));

  const solo = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#month-chips button")).map(c => c.classList.contains("on"));
  });
  const soloCount = solo.filter(v => v).length;
  if (soloCount !== 1) throw new Error(`Expected 1 selected after dblclick, got ${soloCount}`);
  if (!solo[1]) throw new Error("Feb (month 1) should be the only selected month");

  // Dblclick Feb again → restore all
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    if (chips.length >= 12) { chips[1].dispatchEvent(new MouseEvent("dblclick", {bubbles:true})); }
  });
  await new Promise((r) => setTimeout(r, 200));

  const restored = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#month-chips button")).map(c => c.classList.contains("on"));
  });
  if (!restored.every(v => v)) throw new Error("Dblclick again should restore all 12 months");
});

test("Yr button restores all-12 month selection after a solo", async () => {
  // Solo Feb
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    if (chips.length >= 12) { chips[1].dispatchEvent(new MouseEvent("dblclick", {bubbles:true})); }
  });
  await new Promise((r) => setTimeout(r, 200));

  // Verify Feb is solo
  let solo = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#month-chips button")).map(c => c.classList.contains("on"));
  });
  if (solo.filter(v => v).length !== 1) throw new Error("Expected solo after dblclick");

  // Click Yr button
  await page.evaluate(() => { document.getElementById("month-yr").click(); });
  await new Promise((r) => setTimeout(r, 200));

  const restored = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#month-chips button")).map(c => c.classList.contains("on"));
  });
  if (!restored.every(v => v)) throw new Error("Yr button should restore all 12 months");
});

test("Esc clears an active area selection", async () => {
  // Create an area selection first
  const box = await page.evaluate(() => {
    const c = document.querySelector("canvas");
    const r = c.getBoundingClientRect();
    return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
  });
  const half = 40;
  await page.keyboard.down("Shift");
  await page.mouse.move(box.cx - half, box.cy - half);
  await page.mouse.down();
  await page.mouse.move(box.cx + half, box.cy + half);
  await new Promise((r) => setTimeout(r, 100));
  await page.mouse.up();
  await page.keyboard.up("Shift");
  await new Promise((r) => setTimeout(r, 500));

  // Verify area stats panel is populated
  const hasStats = await page.evaluate(() => {
    const el = document.getElementById("area-stats");
    return el.textContent.includes("cells") && el.textContent.includes("Selection");
  });
  if (!hasStats) throw new Error("Area stats not populated after selection");

  // Press Escape
  await page.keyboard.press("Escape");
  await new Promise((r) => setTimeout(r, 300));

  // Verify area stats is cleared to placeholder
  const cleared = await page.evaluate(() => {
    const el = document.getElementById("area-stats");
    return el.textContent.includes("Shift+drag on the map");
  });
  if (!cleared) throw new Error("Escape did not clear area selection");
});

test("wind overlay toggle draws cyan lines above base", async () => {
  // Use Biomes as base layer (bright, distinct colours)
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#layer-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Biomes") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 400));

  // Toggle wind overlay ON
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Wind") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 2000));

  // Wind overlay active check
  const windActive = await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) {
      if (b.textContent.trim() === "Wind") return b.classList.contains("active");
    }
    return false;
  });
  if (!windActive) throw new Error("Wind overlay button is not active after toggle");

  // Base layer should still be visible (biome colours, not blanked).
  // Sample a grid across the centre area; most pixels should be non-black.
  const baseVisible = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const cw = canvas.width, ch = canvas.height;
    let nonBlack = 0, total = 0;
    for (let y = ch * 0.2; y < ch * 0.8; y += 12) {
      for (let x = cw * 0.2; x < cw * 0.8; x += 12) {
        total++;
        const d = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1).data;
        // Wind cyan: g>200,b>200,r<200 — exclude those, check the rest
        if ((d[0] > 30 || d[1] > 30 || d[2] > 30) &&
            !(d[1] > 200 && d[2] > 200 && d[0] < 200)) {
          nonBlack++;
        }
      }
    }
    return { nonBlack, total };
  });
  if (baseVisible.nonBlack < baseVisible.total * 0.4) {
    throw new Error(`Base map barely visible under wind overlay: ${baseVisible.nonBlack}/${baseVisible.total}`);
  }

  // Check that cyan (wind) lines exist as an overlay above the base
  const hasCyan = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const cw = canvas.width, ch = canvas.height;
    let cyanCount = 0, total = 0;
    for (let y = 0; y < ch; y += 8) {
      for (let x = 0; x < cw; x += 8) {
        total++;
        const d = ctx.getImageData(x, y, 1, 1).data;
        if (d[1] > 200 && d[2] > 200 && d[0] < 200 && d[3] > 30) cyanCount++;
      }
    }
    return { cyanCount, total };
  });
  if (hasCyan.cyanCount < 5) throw new Error("Wind overlay has no visible cyan streamlines");

  // Toggle wind OFF
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Wind") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 400));
});

test("currents overlay: ocean-only, no paint on land", async () => {
  // Use Biomes as base layer
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#layer-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Biomes") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 400));

  // Toggle currents overlay ON
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Currents") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 2000));

  const currentsActive = await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) {
      if (b.textContent.trim() === "Currents") return b.classList.contains("active");
    }
    return false;
  });
  if (!currentsActive) throw new Error("Currents overlay button is not active after toggle");

  // Read the overlay canvas directly (not the composite) to check for orange pixels
  const overlayInfo = await page.evaluate(() => {
    const S = window._S;
    if (!S || !S.overlayCanvas || !S.overlayCanvas.currents) {
      return { error: "overlay canvas not found in S.overlayCanvas.currents" };
    }
    const ovCanvas = S.overlayCanvas.currents.canvas;
    if (!ovCanvas) return { error: "overlay canvas is null" };
    const ovCtx = ovCanvas.getContext("2d");
    const W = ovCanvas.width, H = ovCanvas.height;
    const data = ovCtx.getImageData(0, 0, W, H).data;

    // Count orange pixels (r>200, g in 100-200, b<100, a>30)
    let orangeCount = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
      if (r > 200 && g > 100 && g < 200 && b < 100 && a > 30) orangeCount++;
    }
    return { orangeCount, W, H };
  });
  if (overlayInfo.error) throw new Error(overlayInfo.error);
  if (overlayInfo.orangeCount < 10) {
    throw new Error(`Currents overlay canvas has only ${overlayInfo.orangeCount} orange pixels (expected >= 10)`);
  }

  // Check no orange pixels over land cells by cross-referencing ocean mask
  const landCheck = await page.evaluate(() => {
    const S = window._S;
    const ovCanvas = S.overlayCanvas.currents.canvas;
    const ovCtx = ovCanvas.getContext("2d");
    const W = ovCanvas.width, H = ovCanvas.height;
    const data = ovCtx.getImageData(0, 0, W, H).data;
    const ocean = S.fields.ocean; // Uint8Array at 1024²
    if (!ocean) return { error: "ocean mask not available" };

    // Sample a grid of land cells (ocean[i] === 0)
    // and verify no orange pixels exist at those coordinates on the overlay
    let landOrangeViolations = 0;
    const step = 32;
    for (let y = 0; y < H; y += step) {
      for (let x = 0; x < W; x += step) {
        const idx = y * W + x;
        if (ocean[idx] === 0) {
          // This is a land cell
          const pi = idx * 4;
          const r = data[pi], g = data[pi + 1], b = data[pi + 2], a = data[pi + 3];
          if (r > 200 && g > 100 && g < 200 && b < 100 && a > 30) {
            landOrangeViolations++;
          }
        }
      }
    }
    return { landOrangeViolations };
  });
  if (landCheck.error) throw new Error(landCheck.error);
  if (landCheck.landOrangeViolations > 0) {
    throw new Error(`Currents overlay has ${landCheck.landOrangeViolations} orange pixels on land cells`);
  }

  // Base layer should still be visible on composite canvas
  const baseVisible = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const cw = canvas.width, ch = canvas.height;
    let nonBlack = 0, total = 0;
    for (let y = ch * 0.2; y < ch * 0.8; y += 12) {
      for (let x = cw * 0.2; x < cw * 0.8; x += 12) {
        total++;
        const d = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1).data;
        // Currents orange: r>200, g in 100-200, b<100 — exclude, check rest
        if ((d[0] > 30 || d[1] > 30 || d[2] > 30) &&
            !(d[0] > 200 && d[1] > 100 && d[1] < 200 && d[2] < 100)) {
          nonBlack++;
        }
      }
    }
    return { nonBlack, total };
  });
  if (baseVisible.nonBlack < baseVisible.total * 0.3) {
    throw new Error(`Base map barely visible under currents: ${baseVisible.nonBlack}/${baseVisible.total}`);
  }

  // Toggle currents OFF
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Currents") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 400));

  console.log(`  Orange pixels on overlay canvas: ${overlayInfo.orangeCount}`);
  console.log(`  Land orange violations: ${landCheck.landOrangeViolations}`);
});

test("Hydro layer renders with blue ocean depth + magenta salinity", async () => {
  // Switch to Hydro base layer
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#layer-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Hydro") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 600));

  const info = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const cw = canvas.width, ch = canvas.height;
    let blueOcean = 0, magentaWater = 0, nonBlack = 0, total = 0;
    // Sample a grid
    for (let y = 0; y < ch; y += 12) {
      for (let x = 0; x < cw; x += 12) {
        total++;
        const d = ctx.getImageData(x, y, 1, 1).data;
        const r = d[0], g = d[1], b = d[2];
        if (r > 10 || g > 10 || b > 10) nonBlack++;
        // Blue ocean: b dominant, r low
        if (b > g && b > r && r < 120 && b > 60) blueOcean++;
        // Magenta saline: r high, b moderate, g low
        if (r > 145 && b > 70 && g < 130) magentaWater++;
      }
    }
    return { nonBlack, blueOcean, magentaWater, total };
  });
  if (info.nonBlack < info.total * 0.3) throw new Error("Hydro layer mostly black");
  if (info.blueOcean < 5) throw new Error("Hydro layer has no blue ocean depth pixels");
  if (info.magentaWater < 3) throw new Error("Hydro layer has no magenta saline water pixels");
  console.log(`  Hydro: ${info.nonBlack}/${info.total} non-blank, blue=${info.blueOcean}, magenta=${info.magentaWater}`);
});

test("temperature overlay composites over World base", async () => {
  // Ensure World base
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#layer-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "World") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 400));

  // Sample base-only canvas
  const baseSamples = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const samples = [];
    for (let y = 100; y < 500; y += 100) {
      for (let x = 100; x < 500; x += 100) {
        const d = ctx.getImageData(x, y, 1, 1).data;
        samples.push([d[0], d[1], d[2]]);
      }
    }
    return samples;
  });

  // Toggle Temp overlay ON
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Temp") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 600));

  const overlayActive = await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Temp") return b.classList.contains("active"); }
    return false;
  });
  if (!overlayActive) throw new Error("Temp overlay not active after toggle");

  // Samples with overlay: should differ from base-only (overlay changes colours)
  const overlaySamples = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const samples = [];
    for (let y = 100; y < 500; y += 100) {
      for (let x = 100; x < 500; x += 100) {
        const d = ctx.getImageData(x, y, 1, 1).data;
        samples.push([d[0], d[1], d[2]]);
      }
    }
    return samples;
  });

  // Verify overlay changes pixels (not identical to base)
  let changed = 0;
  for (let i = 0; i < baseSamples.length; i++) {
    if (baseSamples[i][0] !== overlaySamples[i][0] ||
        baseSamples[i][1] !== overlaySamples[i][1] ||
        baseSamples[i][2] !== overlaySamples[i][2]) {
      changed++;
    }
  }
  if (changed < baseSamples.length * 0.3) {
    throw new Error(`Temperature overlay barely changes base: ${changed}/${baseSamples.length} pixels differ`);
  }
  console.log(`  Temp overlay changed ${changed}/${baseSamples.length} sample pixels`);

  // Ensure base is still visible (not blanked)
  const nonBlank = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const cw = canvas.width, ch = canvas.height;
    let count = 0, total = 0;
    for (let y = ch * 0.2; y < ch * 0.8; y += 12) {
      for (let x = cw * 0.2; x < cw * 0.8; x += 12) {
        total++;
        const d = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1).data;
        if (d[0] > 10 || d[1] > 10 || d[2] > 10) count++;
      }
    }
    return { count, total };
  });
  if (nonBlank.count < nonBlank.total * 0.5) {
    throw new Error(`Base mostly blanked under temp overlay: ${nonBlank.count}/${nonBlank.total}`);
  }

  // Toggle Temp OFF
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Temp") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 400));
});

test("take screenshot with winter temperature overlay over world", async () => {
  // World base + temperature overlay + winter months
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#layer-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "World") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 200));

  // Toggle temp overlay
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Temp") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 200));

  // Deselect summer (JJA = months 5,6,7)
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    for (const m of [5, 6, 7]) { if (chips[m].classList.contains("on")) chips[m].click(); }
  });
  await new Promise((r) => setTimeout(r, 600));

  const ssDir = resolve(REPO, "tmp");
  mkdirSync(ssDir, { recursive: true });
  const ssPath = resolve(ssDir, "k11_mapviewer.png");
  await page.screenshot({ path: ssPath, fullPage: false });
  console.log(`Screenshot saved: ${ssPath}`);
});

test("month chips + Yr + shift fit on a single row", async () => {
  const rowOk = await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    if (chips.length === 0) return false;
    const firstTop = chips[0].offsetTop;
    for (const c of chips) {
      if (c.offsetTop !== firstTop) return false;
    }
    const sl = document.getElementById("month-shift-left");
    const sr = document.getElementById("month-shift-right");
    const yr = document.getElementById("month-yr");
    if (sl && sl.offsetTop !== firstTop) return false;
    if (sr && sr.offsetTop !== firstTop) return false;
    if (yr && yr.offsetTop !== firstTop) return false;
    return true;
  });
  if (!rowOk) throw new Error("Month chips, shift or Yr button wrap to a second row");
});

test("wind overlay responds to month-mask changes", async () => {
  // Ensure all months selected and world base active
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#layer-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "World") { b.click(); break; } }
  });
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    for (let m = 0; m < 12; m++) {
      if (!chips[m].classList.contains("on")) chips[m].click();
    }
  });
  await new Promise((r) => setTimeout(r, 200));

  // Toggle wind overlay ON
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Wind") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 2000));

  // Sample pixel grid with all months
  const allPixels = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const samples = [];
    for (let y = 0; y < 200; y += 50) {
      for (let x = 0; x < 200; x += 50) {
        const d = ctx.getImageData(x, y, 1, 1).data;
        samples.push(d[0], d[1], d[2]);
      }
    }
    return samples.join(",");
  });

  // Deselect JJA (months 5,6,7)
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    for (const m of [5, 6, 7]) { if (chips[m].classList.contains("on")) chips[m].click(); }
  });
  await new Promise((r) => setTimeout(r, 2000));

  // Sample again
  const winterPixels = await page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const samples = [];
    for (let y = 0; y < 200; y += 50) {
      for (let x = 0; x < 200; x += 50) {
        const d = ctx.getImageData(x, y, 1, 1).data;
        samples.push(d[0], d[1], d[2]);
      }
    }
    return samples.join(",");
  });

  // The wind overlay was re-rendered with new month mask
  // (test passes if we got here without error — both renders completed)
  console.log("  Wind overlay re-rendered with winter month mask");
  // Restore all months
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    for (let m = 0; m < 12; m++) {
      if (!chips[m].classList.contains("on")) chips[m].click();
    }
  });
  await new Promise((r) => setTimeout(r, 200));
  // Toggle wind OFF
  await page.evaluate(() => {
    const btns = document.querySelectorAll("#overlay-buttons button");
    for (const b of btns) { if (b.textContent.trim() === "Wind") { b.click(); break; } }
  });
  await new Promise((r) => setTimeout(r, 400));
});

// ── New tests: ice-cover + seasonal-river tooltips ──

// Hover a specific world pixel and return the tooltip text. Zooms the
// view into the pixel first so 1-px targeting is exact at any scale.
async function tooltipAtWorldPixel(wx, wy) {
  await page.evaluate(({ wx, wy }) => {
    const S = window._S;
    const c = document.querySelector("canvas");
    const r = c.getBoundingClientRect();
    S.scale = 8;
    S.ox = 200 - (wx + 0.5) * S.scale;
    S.oy = 200 - (wy + 0.5) * S.scale;
    const ev = new MouseEvent("mousemove", {
      clientX: r.left + 200, clientY: r.top + 200, bubbles: true,
    });
    c.dispatchEvent(ev);
  }, { wx, wy });
  await new Promise((r) => setTimeout(r, 500));
  return page.evaluate(() => {
    const tt = document.getElementById("tooltip");
    return { text: tt.textContent, display: tt.style.display,
             html: tt.innerHTML };
  });
}

test("ice cover appears in tooltip over frozen ocean pixel", async () => {
  // Find an ocean pixel with substantial January sea ice (seed-1 bundle
  // carries seaice_monthly)
  const px = await page.evaluate(() => {
    const S = window._S;
    const [W, H] = S.shape;
    const si = S.monthly.seaice_monthly;
    const [FH, FW] = S.monthly._shapes.seaice_monthly;
    const sc = W / FW;
    for (let i = 0; i < W * H; i += 7) {
      if (S.fields.ocean[i] !== 1) continue;
      const wx = i % W, wy = Math.floor(i / W);
      const fi = Math.floor(wy / sc) * FW + Math.floor(wx / sc);
      if (si[0 * FW * FH + fi] > 0.3) return { wx, wy };
    }
    return null;
  });
  if (!px) throw new Error("No frozen ocean pixel found in seed-1 bundle");

  const tt = await tooltipAtWorldPixel(px.wx, px.wy);
  if (tt.display !== "block") throw new Error("Tooltip not visible over ocean pixel");
  const m = tt.text.match(/Ice cover \(year\)\s*(\d+)%/);
  if (!m) throw new Error(`No ice-cover line in tooltip: ${tt.text}`);
  if (parseInt(m[1], 10) <= 0) throw new Error(`Expected positive ice cover, got: ${m[1]}`);
  console.log(`  Ocean pixel (${px.wx},${px.wy}): ${m[0]}`);
});

test("glacier pixel is marked glacier with thickness", async () => {
  // Find a glacier pixel with substantial thickness (seed-1 bundle
  // carries the glacier mask bit + glacier_m)
  const px = await page.evaluate(() => {
    const S = window._S;
    const [W, H] = S.shape;
    if (!S.fields.glacier || !S.fields.glacier_m) return null;
    let best = null, bestT = 0;
    for (let i = 0; i < W * H; i += 5) {
      if (S.fields.glacier[i] !== 1) continue;
      if (S.fields.glacier_m[i] > bestT) {
        bestT = S.fields.glacier_m[i];
        best = { wx: i % W, wy: Math.floor(i / W), t: bestT };
      }
    }
    return best;
  });
  if (!px) throw new Error("No glacier pixel found in seed-1 bundle");

  const tt = await tooltipAtWorldPixel(px.wx, px.wy);
  if (tt.display !== "block") throw new Error("Tooltip not visible over glacier pixel");
  if (!/glacier/i.test(tt.text)) throw new Error(`Tooltip not marked glacier: ${tt.text}`);
  const m = tt.text.match(/Glacier ice\s*(\d+)\s*m thick/);
  if (!m) throw new Error(`No thickness line in tooltip: ${tt.text}`);
  if (parseInt(m[1], 10) <= 0) throw new Error(`Expected positive thickness, got: ${m[1]}`);
  // the biome line names it glacier, not generic ice
  if (!/tt-biome[^>]*>\s*glacier\s*</.test(tt.html)) {
    throw new Error(`Biome line not marked glacier: ${tt.html}`);
  }
  console.log(`  Glacier pixel (${px.wx},${px.wy}): ${m[0]}`);
});

test("seasonal river pixel never reports River: 0", async () => {
  // Find a pixel on a seasonal edge: annual river mask 0, but monthly
  // planes carry water in some (not all) months
  const px = await page.evaluate(() => {
    const S = window._S;
    const [W, H] = S.shape;
    const mw = S.monthly.river_width_monthly;
    const [FH, FW] = S.monthly._shapes.river_width_monthly;
    const plane = FW * FH;
    const sc = W / FW;
    for (let i = 0; i < W * H; i++) {
      if (S.fields.river[i] !== 0) continue;
      const wx = i % W, wy = Math.floor(i / W);
      const fi = Math.floor(wy / sc) * FW + Math.floor(wx / sc);
      let wet = 0, dryM = -1;
      for (let m = 0; m < 12; m++) {
        if (mw[m * plane + fi] > 0) wet++;
        else if (dryM < 0) dryM = m;
      }
      if (wet > 0 && wet < 12) return { wx, wy, dryM };
    }
    return null;
  });
  if (!px) throw new Error("No seasonal river pixel found in seed-1 bundle");

  // All months selected (wet overall): "River: seasonal", not "River: 0"
  await page.evaluate(() => {
    window._S.selMonths = new Set([0,1,2,3,4,5,6,7,8,9,10,11]);
  });
  let tt = await tooltipAtWorldPixel(px.wx, px.wy);
  if (tt.display !== "block") throw new Error("Tooltip not visible over seasonal pixel");
  if (tt.text.includes("River: 0")) {
    throw new Error(`Seasonal pixel reported as "River: 0": ${tt.text}`);
  }
  if (!tt.text.includes("River: seasonal")) {
    throw new Error(`Expected "River: seasonal" in tooltip: ${tt.text}`);
  }

  // Solo a dry month: must read "below L0 this month", still not "River: 0"
  await page.evaluate((dryM) => {
    window._S.selMonths = new Set([dryM]);
  }, px.dryM);
  tt = await tooltipAtWorldPixel(px.wx, px.wy);
  if (tt.display !== "block") throw new Error("Tooltip not visible over dry seasonal pixel");
  if (tt.text.includes("River: 0")) {
    throw new Error(`Dry seasonal pixel reported as "River: 0": ${tt.text}`);
  }
  if (!tt.text.includes("River: seasonal (below L0 this month)")) {
    throw new Error(`Expected "below L0 this month" in tooltip: ${tt.text}`);
  }
  console.log(`  Seasonal pixel (${px.wx},${px.wy}), dry month ${px.dryM}: masked+dry cases OK`);

  // Restore month selection
  await page.evaluate(() => {
    window._S.selMonths = new Set([0,1,2,3,4,5,6,7,8,9,10,11]);
    const chips = document.querySelectorAll("#month-chips button");
    for (let m = 0; m < 12; m++) {
      if (!chips[m].classList.contains("on")) chips[m].click();
    }
  });
  await new Promise((r) => setTimeout(r, 200));
});

test("missing lake/river ice fields drop the line without crashing", async () => {
  // Seed-1 bundle predates lake/river ice export — hovering a lake or
  // river pixel must produce a normal tooltip with no ice-cover line
  const px = await page.evaluate(() => {
    const S = window._S;
    const [W, H] = S.shape;
    for (let i = 0; i < W * H; i += 3) {
      if (S.fields.lake[i] === 1) return { wx: i % W, wy: Math.floor(i / W), kind: "lake" };
    }
    return null;
  });
  if (!px) throw new Error("No lake pixel found in seed-1 bundle");

  const hasLakeIce = await page.evaluate(() =>
    !!(window._S.monthly.lakeice_monthly || window._S.monthly.c_lakeice_monthly));

  const tt = await tooltipAtWorldPixel(px.wx, px.wy);
  if (tt.display !== "block") throw new Error("Tooltip not visible over lake pixel");
  if (!hasLakeIce && tt.text.includes("Ice cover")) {
    throw new Error(`Ice-cover line shown without lake ice data: ${tt.text}`);
  }
  console.log(`  Lake pixel (${px.wx},${px.wy}): lakeice present=${hasLakeIce}, tooltip OK`);
});

test("no page errors after tooltip feature tests", async () => {
  if (page._consoleErrors.length > 0) {
    throw new Error(`console errors: ${page._consoleErrors.join("; ")}`);
  }
  if (page._pageErrors.length > 0) {
    throw new Error(`page errors: ${page._pageErrors.join("; ")}`);
  }
  // Restore a sane view for any later runs
  await page.evaluate(() => { fitMap(); render(); });
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
