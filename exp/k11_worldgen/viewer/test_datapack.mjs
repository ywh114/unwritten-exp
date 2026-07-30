#!/usr/bin/env node
/**
 * K11 datapack (.k11pack) viewer tests — unified overlay format.
 *
 *   node exp/k11_worldgen/viewer/test_datapack.mjs
 *
 * Loads the viewer, injects the seed-1 .k11view bundle, then the K14 D0
 * derived.k11pack. Asserts: buttons build from pack metadata, continuous
 * and points overlays render, month_dim layers follow the month mask,
 * tooltips carry pack values, the categorical ground layer + its aux
 * mix planes load and surface in overlay/tooltip, zero console errors.
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
  for (const id of ["terr_prod", "marine_prod", "fresh_prod", "river_speed",
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
  for (const l of ["Terrestrial productivity", "Marine productivity", "Waterfalls"]) {
    if (!labels.includes(l)) throw new Error(`button "${l}" missing (have: ${labels.join(", ")})`);
  }
});

test("terrestrial productivity overlay renders on land only", async () => {
  const info = await page.evaluate(() => {
    const S = window._S;
    const pack = S.packs[0];
    pack.active.terr_prod = true;
    // render via the exposed render path
    const L = pack.layers.find((l) => l.id === "terr_prod");
    const c = (function () { return L._canvas; })();
    return null;
  });
  await page.evaluate(() => {
    const S = window._S;
    const pack = S.packs[0];
    pack.active.terr_prod = true;
  });
  // toggle via button to go through the real path
  await page.evaluate(() => {
    const S = window._S;
    S.packs[0].active.terr_prod = false;
    for (const b of document.querySelectorAll("#overlay-buttons button")) {
      if (b.textContent.trim() === "Terrestrial productivity") { b.click(); break; }
    }
  });
  await new Promise((r) => setTimeout(r, 1000));
  const px = await page.evaluate(() => {
    const S = window._S;
    const L = S.packs[0].layers.find((l) => l.id === "terr_prod");
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
  if (px.landPaint < 50) throw new Error(`terr_prod barely paints land: ${px.landPaint}`);
  if (px.oceanPaint > 0) throw new Error(`terr_prod paints ${px.oceanPaint} ocean cells (mask breach)`);
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

test("ground layer registered with 42 classes + colormap + aux mix planes", async () => {
  const info = await page.evaluate(() => {
    const S = window._S;
    const L = S.packs[0].layers.find((l) => l.id === "ground");
    if (!L) return { error: "ground layer missing" };
    return {
      kind: L.kind, label: L.label,
      nClasses: (L.classes || []).length,
      nCmap: Object.keys(L.colormap || {}).length,
      cmapMatch: (L.classes || []).every((c, i) =>
        JSON.stringify(L.colormap[String(i)]) === JSON.stringify(c.color)),
      dataLen: L.data ? L.data.length : -1,
      mixIdsLen: L.mix_ids && L.mix_ids.data ? L.mix_ids.data.length : -1,
      mixWLen: L.mix_w && L.mix_w.data ? L.mix_w.data.length : -1,
      mixShape: L.mix_ids ? L.mix_ids.shape : null,
    };
  });
  if (info.error) throw new Error(info.error);
  if (info.kind !== "categorical") throw new Error(`kind: ${info.kind}`);
  if (info.label !== "Substrate (ground)") throw new Error(`label: ${info.label}`);
  if (info.nClasses !== 42) throw new Error(`classes: ${info.nClasses}`);
  if (info.nCmap !== 42) throw new Error(`colormap entries: ${info.nCmap}`);
  if (!info.cmapMatch) throw new Error("colormap does not mirror class colors");
  if (info.dataLen !== 1024 * 1024) throw new Error(`ground data len: ${info.dataLen}`);
  if (JSON.stringify(info.mixShape) !== "[3,1024,1024]") {
    throw new Error(`mix shape: ${JSON.stringify(info.mixShape)}`);
  }
  if (info.mixIdsLen !== 3 * 1024 * 1024) throw new Error(`mix_ids len: ${info.mixIdsLen}`);
  if (info.mixWLen !== 3 * 1024 * 1024) throw new Error(`mix_w len: ${info.mixWLen}`);
});

test("Substrate (ground) overlay renders over land and ocean", async () => {
  const hasBtn = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("#overlay-buttons button"))
      .some((b) => b.textContent.trim() === "Substrate (ground)");
  });
  if (!hasBtn) throw new Error('overlay button "Substrate (ground)" missing');
  // toggle via button to go through the real path
  await page.evaluate(() => {
    window._S.packs[0].active.ground = false;
    for (const b of document.querySelectorAll("#overlay-buttons button")) {
      if (b.textContent.trim() === "Substrate (ground)") { b.click(); break; }
    }
  });
  await new Promise((r) => setTimeout(r, 1200));
  const px = await page.evaluate(() => {
    const S = window._S;
    if (!S.packs[0].active.ground) return { error: "not active after toggle" };
    const L = S.packs[0].layers.find((l) => l.id === "ground");
    if (!L._canvas) return { error: "no canvas cached" };
    const ctx = L._canvas.getContext("2d");
    const W = L._canvas.width, H = L._canvas.height;
    const data = ctx.getImageData(0, 0, W, H).data;
    const ocean = S.fields.ocean, sea = S.fields.sea;
    let landPaint = 0, oceanPaint = 0, classColors = 0;
    for (let i = 0; i < W * H; i += 97) {
      const a = data[i * 4 + 3];
      if (a > 0) {
        if (ocean[i] || sea[i]) oceanPaint++;
        else landPaint++;
        // ±1: the canvas stores premultiplied alpha, so getImageData
        // roundtrips can be off by one per channel
        const c = L.colormap[String(Math.round(L.data[i]))];
        if (c && Math.abs(data[i * 4] - c[0]) <= 1 &&
            Math.abs(data[i * 4 + 1] - c[1]) <= 1 &&
            Math.abs(data[i * 4 + 2] - c[2]) <= 1) classColors++;
      }
    }
    return { landPaint, oceanPaint, classColors };
  });
  if (px.error) throw new Error(px.error);
  if (px.landPaint < 500) throw new Error(`ground barely paints land: ${px.landPaint}`);
  if (px.oceanPaint < 500) throw new Error(`ground barely paints ocean (scope "all"): ${px.oceanPaint}`);
  if (px.classColors !== px.landPaint + px.oceanPaint) {
    throw new Error(`pixels not from colormap: ${px.classColors}/${px.landPaint + px.oceanPaint}`);
  }
});

test("tooltip shows Ground mix (3 named classes, ~100%)", async () => {
  // center the map on a cell whose top-3 mix weights are all nonzero
  const pos = await page.evaluate(() => {
    const S = window._S;
    if (!S.packs[0].active.ground) {
      for (const b of document.querySelectorAll("#overlay-buttons button")) {
        if (b.textContent.trim() === "Substrate (ground)") { b.click(); break; }
      }
    }
    const L = S.packs[0].layers.find((l) => l.id === "ground");
    const [P, Hf, Wf] = L.mix_ids.shape;
    const plane = Hf * Wf, ws = L.mix_w.data;
    let cell = -1;
    for (let i = 0; i < plane; i += 211) {
      // skip the 1px border: MouseEvent clientX floors to int, so hovering
      // an edge pixel at (cx+0.5)*scale can land at world coord -1 (out of
      // bounds → no tooltip) — a pre-existing edge effect, not data
      const bx = i % Wf, by = Math.floor(i / Wf);
      if (bx === 0 || by === 0 || bx === Wf - 1 || by === Hf - 1) continue;
      if (ws[i] > 0 && ws[plane + i] > 0 && ws[2 * plane + i] > 0) { cell = i; break; }
    }
    if (cell < 0) return { error: "no cell with 3 nonzero mix weights" };
    const cx = cell % Wf, cy = Math.floor(cell / Wf);
    const canvas = document.querySelector("canvas");
    S.scale = 0.5;
    S.ox = canvas.width / 2 - cx * S.scale;
    S.oy = canvas.height / 2 - cy * S.scale;
    render();
    const r = canvas.getBoundingClientRect();
    return { sx: r.left + S.ox + (cx + 0.5) * S.scale,
             sy: r.top + S.oy + (cy + 0.5) * S.scale,
             names: L.classes.map((c) => c.name) };
  });
  if (pos.error) throw new Error(pos.error);
  await page.mouse.move(pos.sx, pos.sy);
  await new Promise((r) => setTimeout(r, 700));
  const tt = await page.evaluate(() => {
    const g = Array.from(document.querySelectorAll("#tooltip .tt-name"))
      .find((n) => n.textContent === "Ground");
    return g ? g.parentElement.querySelector(".tt-val").textContent : null;
  });
  if (!tt) throw new Error("tooltip lacks a Ground mix line");
  const parts = tt.split(", ").map((p) => p.match(/^(.+) (\d+)%$/));
  if (parts.length !== 3 || parts.some((m) => !m)) {
    throw new Error(`mix line not 3 named classes: "${tt}"`);
  }
  for (const m of parts) {
    if (!pos.names.includes(m[1])) throw new Error(`unknown class "${m[1]}" in "${tt}"`);
  }
  const sum = parts.reduce((a, m) => a + Number(m[2]), 0);
  if (Math.abs(sum - 100) > 2) throw new Error(`mix sums to ${sum}%: "${tt}"`);

  // pack-layer convention: tooltip rows follow the active set — with
  // the overlay toggled off the Ground line disappears
  await page.evaluate(() => {
    for (const b of document.querySelectorAll("#overlay-buttons button")) {
      if (b.textContent.trim() === "Substrate (ground)") { b.click(); break; }
    }
  });
  await page.mouse.move(pos.sx + 3, pos.sy + 3);
  await new Promise((r) => setTimeout(r, 700));
  const gone = await page.evaluate(() => {
    return !Array.from(document.querySelectorAll("#tooltip .tt-name"))
      .some((n) => n.textContent === "Ground");
  });
  if (!gone) throw new Error("Ground mix line shown while layer inactive");
});

test("mask-gated tooltip: bottom temperature only over ocean", async () => {
  // bottom_temp is tooltip_only with mask "ocean" — the fill value (0)
  // must not surface over land. Find one dry-land pixel and one ocean
  // pixel, hover each, check the line's absence/presence.
  const pxs = await page.evaluate(() => {
    const S = window._S;
    const [W, H] = S.shape;
    const f = S.fields;
    // interior pixels only (4-neighbors same domain): the hover can
    // drift a pixel under clientX flooring, and a shore-adjacent cell
    // would legitimately read the other domain
    const dryAt = (i) => !f.ocean[i] && !f.sea[i] && !f.lake[i] && !f.river[i];
    const wetAt = (i) => f.ocean[i] || f.sea[i];
    let land = null, ocean = null;
    for (let i = 0; i < W * H && (!land || !ocean); i += 13) {
      const wx = i % W, wy = Math.floor(i / W);
      if (wx === 0 || wy === 0 || wx === W - 1 || wy === H - 1) continue;
      const nb = [i - 1, i + 1, i - W, i + W];
      if (!land && dryAt(i) && nb.every(dryAt)) land = { wx, wy };
      if (!ocean && wetAt(i) && nb.every(wetAt)) ocean = { wx, wy };
    }
    if (!land || !ocean) return { error: "land/ocean pixel not found" };
    return { land, ocean };
  });
  if (pxs.error) throw new Error(pxs.error);

  const hoverReadsBottomTemp = async ({ wx, wy }) => {
    // center on the world pixel, then hover it (centering first: the
    // previous hover moved the camera)
    const s = await page.evaluate(({ wx, wy }) => {
      const S = window._S;
      const canvas = document.querySelector("canvas");
      S.scale = 4;
      S.ox = canvas.width / 2 - (wx + 0.5) * S.scale;
      S.oy = canvas.height / 2 - (wy + 0.5) * S.scale;
      render();
      const r = canvas.getBoundingClientRect();
      return { sx: r.left + S.ox + (wx + 0.5) * S.scale,
               sy: r.top + S.oy + (wy + 0.5) * S.scale };
    }, { wx, wy });
    await page.mouse.move(s.sx, s.sy);
    await new Promise((r) => setTimeout(r, 700));
    return page.evaluate(() => {
      const t = document.getElementById("tooltip");
      if (t.style.display !== "block") return null;
      return Array.from(t.querySelectorAll(".tt-name"))
        .some((n) => n.textContent === "Bottom temperature");
    });
  };

  const overLand = await hoverReadsBottomTemp(pxs.land);
  if (overLand !== false) {
    throw new Error(`bottom temperature shown over land (got ${overLand})`);
  }
  const overOcean = await hoverReadsBottomTemp(pxs.ocean);
  if (overOcean !== true) {
    throw new Error(`bottom temperature missing over ocean (got ${overOcean})`);
  }
});

test("pack loader reads aux arrays; aux-less packs unchanged", async () => {
  const res = await page.evaluate(() => {
    function makePack(withAux) {
      // minimal .k11pack: one 2×2 categorical layer, aux optional
      const layer = { id: "t", label: "T", kind: "categorical",
                      field: "t_class", dtype: "u1", shape: [2, 2],
                      colormap: { "0": [10, 20, 30], "1": [40, 50, 60] } };
      const order = ["t_class"];
      const chunks = [new Uint8Array([0, 1, 1, 0])];
      if (withAux) {
        layer.mix_ids = { field: "t_ids", dtype: "u1", shape: [3, 2, 2] };
        layer.mix_w = { field: "t_w", dtype: "u1", shape: [3, 2, 2] };
        order.push("t_ids", "t_w");
        chunks.push(new Uint8Array([0, 1, 1, 0, 1, 0, 0, 1, 2, 2, 2, 2]));
        chunks.push(new Uint8Array([255, 200, 128, 64, 55, 127, 127, 191,
                                    0, 0, 0, 0]));
      }
      const header = new TextEncoder().encode(JSON.stringify(
        { format: "k11pack/1", generator: "test", layers: [layer], order }));
      const buf = new ArrayBuffer(
        8 + header.length + chunks.reduce((a, c) => a + c.length, 0));
      const u8 = new Uint8Array(buf);
      u8.set([75, 49, 49, 80], 0);                       // "K11P"
      new DataView(buf).setUint32(4, header.length, true);
      u8.set(header, 8);
      let off = 8 + header.length;
      for (const c of chunks) { u8.set(c, off); off += c.length; }
      return buf;
    }
    const plain = window.parsePack(makePack(false));
    const withAux = window.parsePack(makePack(true));
    const L = withAux.layers[0];
    return {
      plainData: Array.from(plain.layers[0].data),
      plainHasAux: "mix_ids" in plain.layers[0],
      auxData: Array.from(L.data),
      mixIds: L.mix_ids && L.mix_ids.data ? Array.from(L.mix_ids.data) : null,
      mixW: L.mix_w && L.mix_w.data ? Array.from(L.mix_w.data) : null,
    };
  });
  if (res.plainData.join(",") !== "0,1,1,0") {
    throw new Error(`aux-less main field misread: ${res.plainData}`);
  }
  if (res.plainHasAux) throw new Error("aux-less pack gained aux keys");
  if (res.auxData.join(",") !== "0,1,1,0") {
    throw new Error(`main field misread with aux present: ${res.auxData}`);
  }
  if (!res.mixIds || res.mixIds.join(",") !== "0,1,1,0,1,0,0,1,2,2,2,2") {
    throw new Error(`mix_ids bytes: ${res.mixIds}`);
  }
  if (!res.mixW || res.mixW.join(",") !== "255,200,128,64,55,127,127,191,0,0,0,0") {
    throw new Error(`mix_w bytes: ${res.mixW}`);
  }
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
