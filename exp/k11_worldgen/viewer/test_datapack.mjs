#!/usr/bin/env node
/**
 * K11 datapack (.k11pack) viewer tests — unified overlay format.
 *
 *   node exp/k11_worldgen/viewer/test_datapack.mjs
 *
 * Loads the viewer, injects the seed-1 .k11view bundle, then the K14 D0
 * derived.k11pack. Asserts: buttons build from pack metadata, continuous
 * and points overlays render, month_dim layers follow the month mask,
 * tooltips carry pack values, zero console errors.
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
  REPO, "exp", "k14_flora", "out", "seed_00000001", "derived.k11pack");

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

test("launch + load viewer, bundle, pack", async () => {
  if (!existsSync(PACK_PATH)) {
    throw new Error(`pack missing — run: uv run python -m exp.k14_flora.world.derived --seed 1`);
  }
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

test("pack registered with all layers", async () => {
  const info = await page.evaluate(() => {
    const S = window._S;
    return {
      packs: S.packs.length,
      layers: S.packs[0].layers.map((l) => l.id),
      generator: S.packs[0].header.generator,
    };
  });
  if (info.packs !== 1) throw new Error(`expected 1 pack, got ${info.packs}`);
  for (const id of ["fertility", "marine_prod", "fresh_prod", "river_speed",
                    "vents", "grow_season", "waterfalls", "vents_pts",
                    "springs"]) {
    if (!info.layers.includes(id)) throw new Error(`layer ${id} missing`);
  }
  if (info.generator !== "k14_flora") throw new Error(`generator: ${info.generator}`);
});

test("overlay buttons built from pack metadata", async () => {
  const labels = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#overlay-buttons button"))
      .map((b) => b.textContent.trim());
  });
  for (const l of ["Soil fertility", "Marine productivity", "Waterfalls"]) {
    if (!labels.includes(l)) throw new Error(`button "${l}" missing (have: ${labels.join(", ")})`);
  }
});

test("fertility overlay renders on land only", async () => {
  const info = await page.evaluate(() => {
    const S = window._S;
    const pack = S.packs[0];
    pack.active.fertility = true;
    // render via the exposed render path
    const L = pack.layers.find((l) => l.id === "fertility");
    const c = (function () { return L._canvas; })();
    return null;
  });
  await page.evaluate(() => {
    const S = window._S;
    const pack = S.packs[0];
    pack.active.fertility = true;
  });
  // toggle via button to go through the real path
  await page.evaluate(() => {
    const S = window._S;
    S.packs[0].active.fertility = false;
    for (const b of document.querySelectorAll("#overlay-buttons button")) {
      if (b.textContent.trim() === "Soil fertility") { b.click(); break; }
    }
  });
  await new Promise((r) => setTimeout(r, 1000));
  const px = await page.evaluate(() => {
    const S = window._S;
    const L = S.packs[0].layers.find((l) => l.id === "fertility");
    if (!L._canvas) return { error: "no canvas cached" };
    const ctx = L._canvas.getContext("2d");
    const W = L._canvas.width, H = L._canvas.height;
    const data = ctx.getImageData(0, 0, W, H).data;
    const ocean = S.fields.ocean, sea = S.fields.sea;
    let landPaint = 0, oceanPaint = 0;
    for (let i = 0; i < W * H; i += 97) {
      const a = data[i * 4 + 3];
      if (a > 0) {
        if (ocean[i] || sea[i]) oceanPaint++;
        else landPaint++;
      }
    }
    return { landPaint, oceanPaint };
  });
  if (px.error) throw new Error(px.error);
  if (px.landPaint < 50) throw new Error(`fertility barely paints land: ${px.landPaint}`);
  if (px.oceanPaint > 0) throw new Error(`fertility paints ${px.oceanPaint} ocean cells (mask breach)`);
});

test("marine productivity overlay follows month mask", async () => {
  await page.evaluate(() => {
    for (const b of document.querySelectorAll("#overlay-buttons button")) {
      if (b.textContent.trim() === "Marine productivity") { b.click(); break; }
    }
  });
  await new Promise((r) => setTimeout(r, 1500));
  const annual = await page.evaluate(() => {
    const S = window._S;
    const L = S.packs[0].layers.find((l) => l.id === "marine_prod");
    if (!L._canvas) return null;
    const ctx = L._canvas.getContext("2d");
    return ctx.getImageData(0, 0, L._canvas.width, L._canvas.height).data
      .filter((_, i) => i % 401 === 3).join(",");
  });
  if (!annual) throw new Error("marine_prod canvas not rendered");
  // solo January
  await page.evaluate(() => {
    const chips = document.querySelectorAll("#month-chips button");
    chips[0].dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 1500));
  const jan = await page.evaluate(() => {
    const S = window._S;
    const L = S.packs[0].layers.find((l) => l.id === "marine_prod");
    const ctx = L._canvas.getContext("2d");
    return ctx.getImageData(0, 0, L._canvas.width, L._canvas.height).data
      .filter((_, i) => i % 401 === 3).join(",");
  });
  if (annual === jan) throw new Error("marine overlay identical after month-mask change");
  // restore year
  await page.evaluate(() => { document.getElementById("month-yr").click(); });
});

test("waterfalls points draw markers", async () => {
  await page.evaluate(() => {
    for (const b of document.querySelectorAll("#overlay-buttons button")) {
      if (b.textContent.trim() === "Waterfalls") { b.click(); break; }
    }
  });
  await new Promise((r) => setTimeout(r, 800));
  const info = await page.evaluate(() => {
    const S = window._S;
    const L = S.packs[0].layers.find((l) => l.id === "waterfalls");
    return { n: L.points.length, active: S.packs[0].active.waterfalls,
             sample: L.points[0] };
  });
  if (!info.active) throw new Error("waterfalls layer not active");
  if (info.n < 50) throw new Error(`only ${info.n} waterfall points`);
  if (typeof info.sample.drop_m !== "number") throw new Error("point lacks drop_m");
});

test("tooltip carries pack values and point attrs", async () => {
  // center the map on the first waterfall so it is on-canvas
  const pos = await page.evaluate(() => {
    const S = window._S;
    const L = S.packs[0].layers.find((l) => l.id === "waterfalls");
    const p = L.points[0];
    const canvas = document.querySelector("canvas");
    S.scale = 0.5;
    S.ox = canvas.width / 2 - p.x * S.scale;
    S.oy = canvas.height / 2 - p.y * S.scale;
    render();
    const r = canvas.getBoundingClientRect();
    return { sx: r.left + S.ox + p.x * S.scale,
             sy: r.top + S.oy + p.y * S.scale };
  });
  await page.mouse.move(pos.sx, pos.sy);
  await new Promise((r) => setTimeout(r, 700));
  const tt = await page.evaluate(() => {
    const t = document.getElementById("tooltip");
    return { display: t.style.display, text: t.textContent };
  });
  if (tt.display !== "block") throw new Error("tooltip not visible at waterfall");
  if (!tt.text.includes("drop_m")) throw new Error(`tooltip lacks point attrs: ${tt.text.slice(0, 120)}`);
});

test("zero console errors", async () => {
  if (page._consoleErrors.length) throw new Error(page._consoleErrors.join("; "));
  if (page._pageErrors.length) throw new Error(page._pageErrors.join("; "));
});

test("screenshot with pack overlays", async () => {
  const ssDir = resolve(REPO, "tmp");
  mkdirSync(ssDir, { recursive: true });
  const ssPath = resolve(ssDir, "k11_datapack.png");
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
