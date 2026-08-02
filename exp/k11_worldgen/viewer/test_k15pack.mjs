#!/usr/bin/env node
/**
 * K15 delivery-pack (.k11pack) viewer tests — sim overlay layers.
 *
 *   node exp/k11_worldgen/viewer/test_k15pack.mjs
 *
 * Loads the viewer, injects the seed-1 .k11view bundle, then the K15
 * sim-delivery .k11pack (exp/k15_simdiff/out/seed_00000001/delivery.k11pack
 * — write it first via `python -m exp.k15_simdiff --seed 1 --rounds N`).
 * Asserts: the sim overlay buttons build from pack metadata, the
 * display-only density/richness layers render, the "Lineages present"
 * tooltip line lists the sids at a hovered cell, zero console errors.
 * SKIP (exit 0) when the pack has not been produced yet.
 */

import { readFileSync, existsSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import puppeteer from "puppeteer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(__dirname, "..", "..", "..");
const HTML_PATH = resolve(__dirname, "map.html");
const BUNDLE_PATH = resolve(
  REPO, "exp", "k11_worldgen", "out", "seed_00000001", "seed_00000001.k11view");
const PACK_PATH = resolve(
  REPO, "exp", "k15_simdiff", "out", "seed_00000001", "delivery.k11pack");

if (!existsSync(PACK_PATH)) {
  console.log(`SKIP k15 delivery pack missing — run: ` +
    `uv run python -m exp.k15_simdiff --seed 1 --rounds 8`);
  process.exit(0);
}

const tests = [];
let failures = 0;
function test(name, fn) { tests.push({ name, fn }); }
async function run() {
  for (const t of tests) {
    try { await t.fn(); console.log(`PASS ${t.name}`); }
    catch (e) { failures++; console.log(`FAIL ${t.name} — ${e.message}`); }
  }
}

let browser, page;

test("launch + load viewer, bundle, k15 pack", async () => {
  browser = await puppeteer.launch({ headless: true,
    args: ["--no-sandbox", "--allow-file-access-from-files"] });
  page = await browser.newPage();
  const consoleErrors = [], pageErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await page.goto("file://" + HTML_PATH, { waitUntil: "networkidle0", timeout: 15000 });
  page._consoleErrors = consoleErrors;
  page._pageErrors = pageErrors;

  await page.evaluate(async (bUrl, pUrl) => {
    const rb = await fetch(bUrl);
    window.loadBundle(await rb.arrayBuffer());
    const rp = await fetch(pUrl);
    window.loadPack(await rp.arrayBuffer());
  }, "file://" + BUNDLE_PATH, "file://" + PACK_PATH);
  await new Promise((r) => setTimeout(r, 1500));
});

test("k15 pack registered with the sim overlay layers", async () => {
  const info = await page.evaluate(() => {
    const S = window._S;
    const pack = S.packs.find((p) => p.header.generator === "k15_simdiff");
    if (!pack) return { error: "no k15 pack" };
    return {
      layers: pack.layers.map((l) => l.id),
      kinds: pack.layers.map((l) => l.kind),
      shapes: pack.layers.map((l) => JSON.stringify(l.shape)),
      generator: pack.header.generator,
    };
  });
  if (info.error) throw new Error(info.error);
  for (const id of ["sim_density", "species_richness", "lineages"]) {
    if (!info.layers.includes(id)) throw new Error(`layer ${id} missing`);
  }
  if (info.generator !== "k15_simdiff") throw new Error(`generator: ${info.generator}`);
  if (info.shapes[0] !== "[1024,1024]") throw new Error(`sim_density shape: ${info.shapes[0]}`);
});

test("overlay buttons built from the pack metadata", async () => {
  const labels = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#overlay-buttons button"))
      .map((b) => b.textContent.trim());
  });
  for (const l of ["Sim density (display)", "Species richness", "Lineages present"]) {
    if (!labels.includes(l)) throw new Error(`button "${l}" missing (have: ${labels.join(", ")})`);
  }
});

test("sim density overlay renders (display-only layer)", async () => {
  await page.evaluate(() => {
    const S = window._S;
    const pack = S.packs.find((p) => p.header.generator === "k15_simdiff");
    pack.active.sim_density = false;
    for (const b of document.querySelectorAll("#overlay-buttons button")) {
      if (b.textContent.trim() === "Sim density (display)") { b.click(); break; }
    }
  });
  await new Promise((r) => setTimeout(r, 1000));
  const px = await page.evaluate(() => {
    const S = window._S;
    const pack = S.packs.find((p) => p.header.generator === "k15_simdiff");
    if (!pack.active.sim_density) return { error: "not active after toggle" };
    const L = pack.layers.find((l) => l.id === "sim_density");
    if (!L._canvas) return { error: "no canvas cached" };
    const ctx = L._canvas.getContext("2d");
    const W = L._canvas.width, H = L._canvas.height;
    const data = ctx.getImageData(0, 0, W, H).data;
    let painted = 0;
    for (let i = 0; i < W * H; i += 97) {
      if (data[i * 4 + 3] > 0) painted++;
    }
    return { painted };
  });
  if (px.error) throw new Error(px.error);
  if (px.painted < 50) throw new Error(`sim_density barely paints: ${px.painted}`);
});

test("lineages tooltip lists the sids at a hovered cell", async () => {
  // tooltip rows follow the active set — activate the layer first
  await page.evaluate(() => {
    for (const b of document.querySelectorAll("#overlay-buttons button")) {
      if (b.textContent.trim() === "Lineages present") { b.click(); break; }
    }
  });
  await new Promise((r) => setTimeout(r, 600));
  const pos = await page.evaluate(() => {
    const S = window._S;
    const pack = S.packs.find((p) => p.header.generator === "k15_simdiff");
    const L = pack.layers.find((l) => l.id === "lineages");
    // a cell whose lineage list is non-empty (skip the world edge)
    const [Hf, Wf] = L.shape;
    let cell = -1, firstSid = null;
    for (let i = 0; i < Hf * Wf; i++) {
      const bx = i % Wf, by = Math.floor(i / Wf);
      if (bx === 0 || by === 0 || bx === Wf - 1 || by === Hf - 1) continue;
      const entries = (L.lists[Math.round(L.data[i])] || []);
      if (entries.length) { cell = i; firstSid = entries[0]; break; }
    }
    if (cell < 0) return { error: "no cell with lineages" };
    const cx = cell % Wf, cy = Math.floor(cell / Wf);
    const canvas = document.querySelector("canvas");
    S.scale = 0.5;
    S.ox = canvas.width / 2 - (cx * 4 + 2) * S.scale;
    S.oy = canvas.height / 2 - (cy * 4 + 2) * S.scale;
    render();
    const r = canvas.getBoundingClientRect();
    return { sx: r.left + S.ox + (cx * 4 + 2) * S.scale,
             sy: r.top + S.oy + (cy * 4 + 2) * S.scale,
             firstSid };
  });
  if (pos.error) throw new Error(pos.error);
  await page.mouse.move(pos.sx, pos.sy);
  await new Promise((r) => setTimeout(r, 700));
  const tt = await page.evaluate(() => {
    const t = document.getElementById("tooltip");
    return { display: t.style.display, text: t.textContent };
  });
  if (tt.display !== "block") throw new Error("tooltip not visible at occupied cell");
  if (!tt.text.includes("Lineages present")) {
    throw new Error(`tooltip lacks Lineages line: ${tt.text.slice(0, 160)}`);
  }
  if (!tt.text.includes(pos.firstSid)) {
    throw new Error(`tooltip lacks sid ${pos.firstSid}: ${tt.text.slice(0, 200)}`);
  }
});

test("zero console errors", async () => {
  if (page._consoleErrors.length) throw new Error(page._consoleErrors.join("; "));
  if (page._pageErrors.length) throw new Error(page._pageErrors.join("; "));
});

test("screenshot with sim overlays", async () => {
  const ssDir = resolve(REPO, "tmp");
  mkdirSync(ssDir, { recursive: true });
  const ssPath = resolve(ssDir, "k15_sim_overlay.png");
  await page.screenshot({ path: ssPath });
  console.log(`  screenshot: ${ssPath}`);
});

async function main() {
  try { await run(); }
  finally {
    if (page) await page.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
  }
  console.log(`\n${tests.length - failures}/${tests.length} tests passed`);
  process.exit(failures);
}

main();
