// ============================================================================
// K13 Tree Viewer — Puppeteer test suite
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

  // Find a species for tooltip test
  const brownBear = treeData.nodes.find(n =>
    n.rank === "species" && n.label === "brown bear"
  );
  const bearPath = brownBear ? brownBear.path : treeData.nodes.find(n =>
    n.rank === "species" && n.flags && n.flags.includes("pinned")
  ).path;

  console.log(`Tree: ${treeData.nodes.length} nodes, orders+above: ${expectedInitialCount}`);
  console.log(`Beetle order: ${beetlePath} (${beetleSubtreeSize} descendants, expect ${expectedExpandedCount} when expanded)`);

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
  // Wait for render
  await new Promise(r => setTimeout(r, 600));

  // ========================================================================
  // Test overlay: file-picker must be hidden after programmatic loadTree
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
  // Test a: DOM node count == visible count == expected
  // ========================================================================
  const domCount = await page.evaluate(() =>
    document.querySelectorAll("#svg-group .tree-node").length
  );
  const visibleCount = await page.evaluate(() => window.getVisibleNodeCount());

  assert(
    domCount === expectedInitialCount,
    `a1: DOM node count ${domCount} == expected ${expectedInitialCount}`
  );
  assert(
    visibleCount === expectedInitialCount,
    `a2: getVisibleNodeCount() ${visibleCount} == expected ${expectedInitialCount}`
  );
  assert(
    domCount === visibleCount,
    `a3: DOM count ${domCount} == getVisibleNodeCount() ${visibleCount}`
  );

  // ========================================================================
  // Test b: Click order node → subtree appears
  // ========================================================================
  const clicked = await page.evaluate(path => {
    const els = document.querySelectorAll(".tree-node");
    for (const el of els) {
      if (el.getAttribute("data-path") === path) {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return true;
      }
    }
    return false;
  }, beetlePath);
  assert(clicked, `b1: clicked beetle order node`);
  await new Promise(r => setTimeout(r, 400));

  const countAfterExpand = await page.evaluate(() => window.getVisibleNodeCount());
  assert(
    countAfterExpand === expectedExpandedCount,
    `b2: visible count after expand ${countAfterExpand} == expected ${expectedExpandedCount}`
  );

  // ========================================================================
  // Test c: Double-click → subtree hidden
  // ========================================================================
  await page.evaluate(path => {
    const els = document.querySelectorAll(".tree-node");
    for (const el of els) {
      if (el.getAttribute("data-path") === path) {
        el.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
        return true;
      }
    }
    return false;
  }, beetlePath);
  await new Promise(r => setTimeout(r, 400));

  const countAfterCollapse = await page.evaluate(() => window.getVisibleNodeCount());
  assert(
    countAfterCollapse === expectedInitialCount,
    `c1: visible count after dblclick collapse ${countAfterCollapse} == expected ${expectedInitialCount}`
  );

  // ========================================================================
  // Test d: Arrow-key navigation 5x → selection moves, count UNCHANGED
  // ========================================================================
  // Select first phylum node (which has a sibling to navigate to)
  const phylum1 = treeData.nodes.find(n => n.rank === "phylum");
  if (phylum1) {
    await page.evaluate(path => {
      const els = document.querySelectorAll(".tree-node");
      for (const el of els) {
        if (el.getAttribute("data-path") === path) {
          el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
          return true;
        }
      }
      return false;
    }, phylum1.path);
    await new Promise(r => setTimeout(r, 200));
  }

  const selBefore = await page.evaluate(() => window.getSelectedPath());
  const countBeforeArrows = await page.evaluate(() => window.getVisibleNodeCount());
  assert(!!selBefore, "d1: node selected before arrow nav");

  const navMoves = [];
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("ArrowDown");
    await new Promise(r => setTimeout(r, 80));
    const sel = await page.evaluate(() => window.getSelectedPath());
    navMoves.push(sel);
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
  await new Promise(r => setTimeout(r, 500));
  const countAfterReset = await page.evaluate(() => window.getVisibleNodeCount());
  assert(
    countAfterReset === expectedInitialCount,
    `e1: visible count after reset ${countAfterReset} == expected ${expectedInitialCount}`
  );

  // ========================================================================
  // Test f: Unselected label boxes — single-row, no overflow
  // ========================================================================
  const labelOverflow = await page.evaluate(() => {
    const nodes = document.querySelectorAll(".tree-node:not(.selected) .label-box");
    const issues = [];
    for (const lb of nodes) {
      const textEl = lb.querySelector("text");
      if (!textEl) continue;
      // SVG text — use getBBox if available
      let textH = 0;
      try {
        const bbox = textEl.getBBox();
        textH = bbox.height;
      } catch (e) {
        // getBBox unavailable in some contexts, try getBoundingClientRect
        const rect = textEl.getBoundingClientRect();
        textH = rect.height;
      }
      const rectEl = lb.querySelector("rect");
      let boxH = 17;
      if (rectEl) boxH = parseFloat(rectEl.getAttribute("height")) || 17;

      // Text height should be ≤ box height + 2px tolerance
      if (textH > boxH + 2) {
        issues.push({
          path: lb.closest(".tree-node").getAttribute("data-path"),
          textH, boxH
        });
      }
    }
    return issues;
  });
  assert(
    labelOverflow.length === 0,
    `f1: all ${await page.evaluate(() => document.querySelectorAll(".tree-node:not(.selected) .label-box").length)} unselected labels single-row (${labelOverflow.length} overflow: ${JSON.stringify(labelOverflow.slice(0, 5))})`
  );

  // ========================================================================
  // Test g: Tooltip — hover species → tooltip has border, bg, z-index above nodes, alpha order
  // ========================================================================
  // First expand to make the species visible
  await page.evaluate(path => {
    const els = document.querySelectorAll(".tree-node");
    for (const el of els) {
      if (el.getAttribute("data-path") === path) {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return true;
      }
    }
    return false;
  }, bearPath.split(".").slice(0, 5).join(".")); // expand genus level ancestor
  await new Promise(r => setTimeout(r, 400));
  // Expand more if needed
  await page.evaluate(path => {
    // Expand family if visible and collapsed
    const fam = path.split(".").slice(0, 4).join(".");
    const els = document.querySelectorAll(".tree-node");
    for (const el of els) {
      if (el.getAttribute("data-path") === fam) {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return true;
      }
    }
    return false;
  }, bearPath);
  await new Promise(r => setTimeout(r, 400));
  await page.evaluate(path => {
    // Expand genus if visible
    const gen = path.split(".").slice(0, 5).join(".");
    const els = document.querySelectorAll(".tree-node");
    for (const el of els) {
      if (el.getAttribute("data-path") === gen) {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return true;
      }
    }
    return false;
  }, bearPath);
  await new Promise(r => setTimeout(r, 400));

  // Now hover the species to trigger tooltip
  const tooltipResult = await page.evaluate(path => {
    // Use mousemove on the node to trigger tooltip
    const els = document.querySelectorAll(".tree-node");
    let found = null;
    for (const el of els) {
      if (el.getAttribute("data-path") === path) {
        found = el;
        break;
      }
    }
    if (!found) return { error: "species node not found in DOM" };

    const rect = found.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    found.dispatchEvent(new MouseEvent("mousemove", {
      bubbles: true,
      clientX: cx,
      clientY: cy
    }));
    // Wait a frame for tooltip to render
    return { cx, cy };
  }, bearPath);
  await new Promise(r => setTimeout(r, 300));

  const tt = await page.evaluate(() => {
    const tt = document.getElementById("tooltip");
    const style = window.getComputedStyle(tt);
    const isVisible = style.display !== "none" && tt.innerHTML.trim().length > 0;

    // Collect axis keys from tooltip HTML and check alpha order
    const rows = tt.querySelectorAll(".tt-row");
    const axisKeys = [];
    let inAxes = false;
    for (const row of rows) {
      const k = row.querySelector(".tt-k");
      if (k) {
        const text = k.textContent.trim();
        if (text === "Axes" || inAxes) {
          // Skip section title
          if (inAxes && text !== "path" && text !== "rank" && text !== "parent" && text !== "label" &&
              text !== "folk name" && text !== "binomial" && text !== "g" && text !== "Axes" &&
              text !== "Generics" && text !== "Flags") {
            axisKeys.push(text);
          }
        }
      }
    }

    let alphaOk = true;
    for (let i = 1; i < axisKeys.length; i++) {
      if (axisKeys[i] < axisKeys[i - 1]) {
        alphaOk = false;
        break;
      }
    }

    // Get z-index of tooltip
    const ttZI = parseInt(style.zIndex) || 0;

    // Get max z-index of all tree nodes
    let maxNodeZI = 0;
    const nodes = document.querySelectorAll(".tree-node");
    nodes.forEach(n => {
      const ns = window.getComputedStyle(n);
      const zi = parseInt(ns.zIndex) || 0;
      if (zi > maxNodeZI) maxNodeZI = zi;
    });

    return {
      isVisible,
      bg: style.backgroundColor,
      border: style.border,
      ttZIndex: ttZI,
      maxNodeZIndex: maxNodeZI,
      axisKeys,
      alphaOk,
      rowCount: rows.length
    };
  });

  assert(
    tt.isVisible,
    `g1: tooltip is visible (display=${tt.isVisible}, rows=${tt.rowCount})`
  );
  assert(
    tt.bg !== "rgba(0, 0, 0, 0)" && tt.bg !== "transparent",
    `g2: tooltip has non-transparent background (${tt.bg})`
  );
  assert(
    tt.border && tt.border !== "0px none rgb(0, 0, 0)" && !tt.border.includes("0px"),
    `g3: tooltip has visible border (${tt.border})`
  );
  assert(
    tt.ttZIndex > tt.maxNodeZIndex,
    `g4: tooltip z-index ${tt.ttZIndex} > max node z-index ${tt.maxNodeZIndex}`
  );
  assert(
    tt.alphaOk,
    `g5: tooltip axis keys in alphabetical order (${tt.axisKeys.slice(0, 8).join(", ")}...)`
  );

  // ========================================================================
  // Test h: Drag simulation → no text selection
  // ========================================================================
  // Reset first to get clean state
  await page.evaluate(() => {
    document.getElementById("btn-reset").click();
  });
  await new Promise(r => setTimeout(r, 400));

  // Simulate drag on canvas (not on a node)
  const canvasWrap = await page.$("#canvas-wrap");
  const wrapBox = await canvasWrap.boundingBox();
  const startX = wrapBox.x + 50;
  const startY = wrapBox.y + 50;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 100, startY + 10, { steps: 5 });
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

  // ========================================================================
  // Test i: Zero console errors
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
  await new Promise(r => setTimeout(r, 500));
  fs.mkdirSync(path.dirname(SCREENSHOT_INIT), { recursive: true });
  await page.screenshot({ path: SCREENSHOT_INIT, fullPage: false });
  console.log(`Screenshot saved: ${SCREENSHOT_INIT}`);

  // Expand beetle order for expanded screenshot
  await page.evaluate(path => {
    const els = document.querySelectorAll(".tree-node");
    for (const el of els) {
      if (el.getAttribute("data-path") === path) {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return true;
      }
    }
    return false;
  }, beetlePath);
  await new Promise(r => setTimeout(r, 500));
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
