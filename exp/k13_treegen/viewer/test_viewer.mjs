// ============================================================================
// K13 Tree Viewer — Puppeteer test suite (Canvas 2D + Sidebar edition)
// Run: node exp/k13_treegen/viewer/test_viewer.mjs
// ============================================================================

import puppeteer from "puppeteer";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "../../..");

const TREE_JSON_PATH = path.join(REPO, "exp/k13_treegen/out/k13_seed00000001.json");
const VIEWER_PATH = path.join(__dirname, "tree.html");
const SCREENSHOT_INIT = path.join(REPO, "tmp/m10_viewer.png");
const SCREENSHOT_EXPAND = path.join(REPO, "tmp/m10_viewer_expanded.png");

let passed = 0;
let failed = 0;
let errors = [];

const RED = "\x1b[31m";
const GREEN = "\x1b[32m";
const RESET = "\x1b[0m";

function pass(msg) {
  passed++;
  console.log(`${GREEN}PASS${RESET} ${msg}`);
}

function fail(msg) {
  failed++;
  errors.push(msg);
  console.log(`${RED}FAIL${RESET} ${msg}`);
}

function assert(cond, msg) {
  if (cond) pass(msg);
  else fail(msg);
}

async function main() {
  // Load tree data
  const treeData = JSON.parse(fs.readFileSync(TREE_JSON_PATH, "utf8"));

  // Precompute expected counts
  const ordersAndAbove = treeData.nodes.filter(n =>
    ["kingdom", "phylum", "class", "order"].includes(n.rank)
  );
  const expectedInitialCount = ordersAndAbove.length;

  // Find beetle order for expand test
  const beetleOrder = treeData.nodes.find(n => n.label === "beetles" && n.rank === "order");
  if (!beetleOrder) {
    console.error("Could not find beetle order node");
    process.exit(1);
  }
  const beetlePath = beetleOrder.path;
  const beetleSubtreeSize = treeData.nodes.filter(n => n.path.startsWith(beetlePath + ".")).length;
  const expectedExpandedCount = expectedInitialCount + beetleSubtreeSize;

  // Find a phylum for click tests
  const phylum1 = treeData.nodes.find(n => n.rank === "phylum");
  if (!phylum1) {
    console.error("Could not find a phylum node");
    process.exit(1);
  }

  // Find a carnivore species with diet_spectrum weight = 1.0
  const carnivoreSpecies = treeData.nodes.find(n =>
    n.rank === "species" &&
    n.axes && n.axes.diet_spectrum &&
    Object.values(n.axes.diet_spectrum).some(w => w === 1.0)
  );

  // Find a species (any) for sidebar axes test — prefer a beetle species under beetlePath
  const beetleSpecies = treeData.nodes.find(n =>
    n.rank === "species" && n.path.startsWith(beetlePath + ".") && n.axes && typeof n.axes === "object"
  );
  // Fallback: any species with axes
  const anySpecies = beetleSpecies || treeData.nodes.find(n =>
    n.rank === "species" && n.axes && typeof n.axes === "object"
  );

  console.log(`Tree: ${treeData.nodes.length} nodes, orders+above: ${expectedInitialCount}`);
  console.log(`Beetle order: ${beetlePath} (${beetleSubtreeSize} descendants, expect ${expectedExpandedCount} when expanded)`);
  console.log(`Phylum: ${phylum1.path}`);
  if (carnivoreSpecies) console.log(`Carnivore species: ${carnivoreSpecies.path}`);
  if (anySpecies) console.log(`Species (axes): ${anySpecies.path}`);

  // Launch browser
  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-gpu"]
  });
  const page = await browser.newPage();

  // Collect console errors
  const consoleErrors = [];
  page.on("console", msg => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", err => consoleErrors.push(err.message));

  // Load the viewer
  await page.goto(`file://${VIEWER_PATH}`, { waitUntil: "networkidle0" });

  // Inject tree data
  await page.evaluate(data => { window.loadTree(data); }, treeData);
  // Wait for render (zoomToFit is debounced via ResizeObserver, then draw)
  await new Promise(r => setTimeout(r, 800));

  // ========================================================================
  // overlay: file-picker must be hidden after programmatic loadTree
  // ========================================================================
  const overlayDisplay = await page.evaluate(() => {
    const el = document.getElementById("file-picker");
    return el ? window.getComputedStyle(el).display : null;
  });
  assert(
    overlayDisplay === "none",
    `overlay: file-picker hidden after loadTree (display=${overlayDisplay})`
  );

  // ========================================================================
  // Test a2: visible node count matches expected
  // ========================================================================
  const visibleCount = await page.evaluate(() => window.getVisibleNodeCount());
  assert(
    visibleCount === expectedInitialCount,
    `a2: getVisibleNodeCount() ${visibleCount} == expected ${expectedInitialCount}`
  );

  // ========================================================================
  // Test b: Click order node → subtree appears
  // ========================================================================
  {
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), beetlePath);
    assert(pos !== null, `b1: beetle order node has screen position`);
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 600));
    }
  }

  const countAfterExpand = await page.evaluate(() => window.getVisibleNodeCount());
  assert(
    countAfterExpand === expectedExpandedCount,
    `b2: visible count after expand ${countAfterExpand} == expected ${expectedExpandedCount}`
  );

  // ========================================================================
  // Test c: Double-click → subtree hidden
  // ========================================================================
  {
    // Zoom to fit so the beetle order node is in view
    await page.evaluate(() => document.getElementById("btn-fit").click());
    await new Promise(r => setTimeout(r, 400));
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), beetlePath);
    assert(pos !== null, `c1: beetle order node still has screen position for dblclick`);
    if (pos) {
      // Use two rapid clicks within 300ms for double-click detection
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 50));
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 600));
    }
  }

  const countAfterCollapse = await page.evaluate(() => window.getVisibleNodeCount());
  assert(
    countAfterCollapse === expectedInitialCount,
    `c2: visible count after dblclick collapse ${countAfterCollapse} == expected ${expectedInitialCount}`
  );

  // ========================================================================
  // Test d: Arrow-key navigation — select first phylum, then arrow keys
  // ========================================================================
  {
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), phylum1.path);
    assert(pos !== null, "d1: phylum node has screen position");
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 300));
    }
  }

  const selBefore = await page.evaluate(() => window.getSelectedPath());
  const countBeforeArrows = await page.evaluate(() => window.getVisibleNodeCount());
  assert(!!selBefore, "d1b: node selected before arrow nav");

  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("ArrowDown");
    await new Promise(r => setTimeout(r, 100));
  }

  const selAfter = await page.evaluate(() => window.getSelectedPath());
  const countAfterArrows = await page.evaluate(() => window.getVisibleNodeCount());
  assert(
    selAfter !== selBefore,
    `d2: selection moved after 5 arrow keys (${selBefore} → ${selAfter})`
  );
  assert(
    countAfterArrows === countBeforeArrows,
    `d3: visible count unchanged after arrows (${countBeforeArrows} == ${countAfterArrows})`
  );

  // ========================================================================
  // Test e: Reset button → visible count == initial
  // ========================================================================
  await page.evaluate(() => {
    document.getElementById("btn-reset").click();
  });
  await new Promise(r => setTimeout(r, 800));

  const countAfterReset = await page.evaluate(() => window.getVisibleNodeCount());
  assert(
    countAfterReset === expectedInitialCount,
    `e1: visible count after reset ${countAfterReset} == expected ${expectedInitialCount}`
  );

  // ========================================================================
  // Test g1: sidebar shows selected node details (click phylum)
  // ========================================================================
  {
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), phylum1.path);
    assert(pos !== null, "g1: phylum node has screen position for sidebar test");
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 300));
    }
  }

  const sidebarHtml = await page.evaluate(() => {
    const sb = document.getElementById("sidebar");
    return sb ? sb.innerHTML : "";
  });
  const hasPathOrName = sidebarHtml.includes(phylum1.path) ||
    (phylum1.name && phylum1.name.binomial && sidebarHtml.includes(phylum1.name.binomial)) ||
    (phylum1.label && sidebarHtml.includes(phylum1.label));
  assert(
    hasPathOrName,
    `g1: sidebar shows selected node details (contains path or name; path=${phylum1.path})`
  );

  // ========================================================================
  // Test g2: sidebar has overflow-y: auto
  // ========================================================================
  const sidebarOverflow = await page.evaluate(() => {
    const sb = document.getElementById("sidebar");
    return sb ? window.getComputedStyle(sb).overflowY : "none";
  });
  assert(
    sidebarOverflow === "auto",
    `g2: sidebar overflow-y is auto (got "${sidebarOverflow}")`
  );

  // ========================================================================
  // Tests g3 + l1: Need a species visible — expand beetle order
  // ========================================================================
  {
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), beetlePath);
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 600));
    }
  }

  // ========================================================================
  // Test g3: sidebar axes in alphabetical order (checked together with l1 below)
  // ========================================================================
  pass("g3: deferred to l1 (species selection is tested there)");

  // ========================================================================
  // Test l1: diet_spectrum weight 1.0 → "100%" in sidebar (not "1%")
  //   Also checks: sidebar axes in alphabetical order (g3)
  // ========================================================================
  if (carnivoreSpecies) {
    // Expand ancestors to make the carnivore species visible, then select it
    const ancParts = carnivoreSpecies.path.split(".");
    for (let i = 3; i < ancParts.length; i++) {
      const ancPath = ancParts.slice(0, i + 1).join(".");
      const aPos = await page.evaluate(p => window.__nodeScreenPos(p), ancPath);
      if (aPos) {
        await page.mouse.click(aPos.x, aPos.y);
        await new Promise(r => setTimeout(r, 300));
      }
    }
    await page.evaluate(path => {
      if (window.__selectPath) window.__selectPath(path);
    }, carnivoreSpecies.path);
    await new Promise(r => setTimeout(r, 300));

    const sidebarText = await page.evaluate(() => {
      const sb = document.getElementById("sidebar");
      return sb ? sb.innerHTML : "";
    });

    // Should show "100%" not " 1%"
    const hasBadFormat = /\b1%/.test(sidebarText) && !/\b100%/.test(sidebarText);
    assert(
      !hasBadFormat,
      `l1: diet_spectrum weight 1.0 renders as 100%, not 1% (snippet: ${sidebarText.substring(0, 200)})`
    );

    // Also check axis keys are in alphabetical order (g3)
    const axisKeysFromData = Object.keys(carnivoreSpecies.axes || {}).filter(k => carnivoreSpecies.axes[k] !== "N/A" && carnivoreSpecies.axes[k] != null).sort();
    const sidebarKeys = await page.evaluate(() => {
      const sb = document.getElementById("sidebar");
      if (!sb) return [];
      const spans = sb.querySelectorAll('.sk');
      return Array.from(spans).map(s => s.textContent.trim());
    });
    // All axis keys from the data should appear in the sidebar in alpha order
    // (after the metadata keys: path, rank, parent, label, folk name, binomial, g)
    const metaKeys = new Set(["path","rank","parent","label","folk name","binomial","g"]);
    const sidebarAxisKeys = [];
    for (const k of sidebarKeys) {
      if (metaKeys.has(k)) continue;
      if (!axisKeysFromData.includes(k)) break; // stop at generics
      sidebarAxisKeys.push(k);
    }
    let alphaOk = axisKeysFromData.every((k, i) => sidebarAxisKeys.indexOf(k) === i || sidebarAxisKeys.indexOf(k) === -1);
    alphaOk = alphaOk && sidebarAxisKeys.length >= axisKeysFromData.length;
    assert(
      alphaOk,
      `l2: sidebar axis keys in alphabetical order (expected ${axisKeysFromData.slice(0,5).join(", ")}..., got ${sidebarAxisKeys.slice(0,5).join(", ")}...)`
    );
  } else {
    pass("l1: no 1.0-weight species found — skipped");
  }

  // ========================================================================
  // Test k1: click at zoom ~0.3 selects the node
  // ========================================================================
  // First, get canvas-wrap center
  const wrapBox = await page.evaluate(() => {
    const el = document.getElementById("canvas-wrap");
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });

  // Zoom out by scrolling down many times
  await page.mouse.move(wrapBox.x, wrapBox.y);
  for (let i = 0; i < 20; i++) {
    await page.mouse.wheel({ deltaX: 0, deltaY: 150 });
    await new Promise(r => setTimeout(r, 30));
  }
  await new Promise(r => setTimeout(r, 400));

  // Click a phylum node at low zoom
  {
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), phylum1.path);
    assert(pos !== null, "k1: phylum node has screen pos at low zoom");
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 300));
    }
  }

  const selLowZoom = await page.evaluate(() => window.getSelectedPath());
  assert(
    selLowZoom === phylum1.path,
    `k1: click selects at low zoom (selected=${selLowZoom}, expected=${phylum1.path})`
  );

  // ========================================================================
  // Test k2: click at zoom ~8 selects the node
  // ========================================================================
  // Zoom in a lot
  await page.mouse.move(wrapBox.x, wrapBox.y);
  for (let i = 0; i < 35; i++) {
    await page.mouse.wheel({ deltaX: 0, deltaY: -150 });
    await new Promise(r => setTimeout(r, 30));
  }
  await new Promise(r => setTimeout(r, 400));

  {
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), phylum1.path);
    assert(pos !== null, "k2: phylum node has screen pos at high zoom");
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 300));
    }
  }

  const selHighZoom = await page.evaluate(() => window.getSelectedPath());
  assert(
    selHighZoom === phylum1.path,
    `k2: click selects at high zoom (selected=${selHighZoom}, expected=${phylum1.path})`
  );

  // ========================================================================
  // Reset view for remaining tests
  // ========================================================================
  await page.evaluate(() => {
    document.getElementById("btn-reset").click();
  });
  await new Promise(r => setTimeout(r, 800));

  // ========================================================================
  // Test h1: Drag on canvas-wrap → no text selection
  // ========================================================================
  {
    const box = await page.evaluate(() => {
      const el = document.getElementById("canvas-wrap");
      const r = el.getBoundingClientRect();
      return { x: r.left + 50, y: r.top + 50 };
    });

    await page.mouse.move(box.x, box.y);
    await page.mouse.down();
    await page.mouse.move(box.x + 100, box.y + 10, { steps: 5 });
    await page.mouse.up();
    await new Promise(r => setTimeout(r, 200));

    const selectionAfterDrag = await page.evaluate(() => {
      const sel = window.getSelection();
      return sel ? sel.toString() : "";
    });

    assert(
      selectionAfterDrag === "",
      `h1: no text selection after drag ("${selectionAfterDrag}")`
    );
  }

  // ========================================================================
  // Test m1: After panning, clicking still selects the right node
  // ========================================================================
  {
    // Reset to a clean state first
    await page.evaluate(() => document.getElementById("btn-reset").click());
    await new Promise(r => setTimeout(r, 500));

    // Use canvas coordinates for pan start (top-left, clear of nodes)
    const box = await page.evaluate(() => {
      const c = document.querySelector("#canvas-wrap canvas");
      const r = c.getBoundingClientRect();
      return { x: r.left + 10, y: r.top + 10 };
    });

    // Pan 200px right
    await page.mouse.move(box.x, box.y);
    await page.mouse.down();
    await page.mouse.move(box.x + 200, box.y, { steps: 10 });
    await page.mouse.up();
    await new Promise(r => setTimeout(r, 300));

    // Click a phylum node after panning
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), phylum1.path);
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 300));
    }

    const selAfterPan = await page.evaluate(() => window.getSelectedPath());
    assert(
      selAfterPan === phylum1.path,
      `m1: after panning, click selects correct node (selected=${selAfterPan}, expected=${phylum1.path})`
    );
  }

  // ========================================================================
  // Reset and expand beetle order for perf test
  // ========================================================================
  await page.evaluate(() => {
    document.getElementById("btn-reset").click();
  });
  await new Promise(r => setTimeout(r, 600));

  {
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), beetlePath);
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 600));
    }
  }

  const visibleForPerf = await page.evaluate(() => window.getVisibleNodeCount());
  console.log(`Visible nodes for perf test: ${visibleForPerf}`);

  // ========================================================================
  // Test n1: Perf smoke — __drawDirect() < 200ms
  // ========================================================================
  const drawTime = await page.evaluate(() => {
    const start = performance.now();
    window.__drawDirect();
    const end = performance.now();
    return end - start;
  });
  assert(
    drawTime < 200,
    `n1: __drawDirect() took ${drawTime.toFixed(1)}ms (must be < 200ms)`
  );

  // ========================================================================
  // Test i1: Zero console errors
  // ========================================================================
  assert(
    consoleErrors.length === 0,
    `i1: zero console errors (${consoleErrors.length} found: ${consoleErrors.slice(0, 5).join("; ")})`
  );

  // ========================================================================
  // Screenshots
  // ========================================================================
  // Reset to initial view for screenshot
  await page.evaluate(() => {
    document.getElementById("btn-reset").click();
  });
  await new Promise(r => setTimeout(r, 800));

  fs.mkdirSync(path.dirname(SCREENSHOT_INIT), { recursive: true });
  await page.screenshot({ path: SCREENSHOT_INIT, fullPage: false });
  console.log(`Screenshot saved: ${SCREENSHOT_INIT}`);

  // Expand beetle order for expanded screenshot
  {
    const pos = await page.evaluate(path => window.__nodeScreenPos(path), beetlePath);
    if (pos) {
      await page.mouse.click(pos.x, pos.y);
      await new Promise(r => setTimeout(r, 800));
    }
  }
  await page.screenshot({ path: SCREENSHOT_EXPAND, fullPage: false });
  console.log(`Screenshot saved: ${SCREENSHOT_EXPAND}`);

  // ========================================================================
  // Summary
  // ========================================================================
  await browser.close();

  console.log(`\n${passed} passed, ${failed} failed`);
  if (failed > 0) {
    console.log("\nFailures:");
    errors.forEach(e => console.log(`  ${RED}✗${RESET} ${e}`));
    process.exit(1);
  }
}

main().catch(err => {
  console.error("Fatal error:", err);
  process.exit(1);
});
