/**
 * Screenshot the three new revenue-action views (Markdown, Cart
 * Completion, Win-back) for visual verification. Mirrors the
 * shape of `inspect-views.cjs` but scoped to the new pages.
 *
 * Run from project root after `./do dev` is up:
 *   node frontend/scripts/inspect-revenue-actions.cjs
 */

const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const BASE = "http://localhost:8500";
const OUT_DIR = path.resolve(__dirname, "../../screenshots/inspect");
fs.mkdirSync(OUT_DIR, { recursive: true });

function findChrome() {
  const candidates = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    "/nix/store",
  ].filter(Boolean);
  for (const root of candidates) {
    if (!fs.existsSync(root)) continue;
    const stack = [root];
    let limit = 30_000;
    while (stack.length && limit-- > 0) {
      const dir = stack.pop();
      let entries = [];
      try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
      catch { continue; }
      for (const e of entries) {
        const p = path.join(dir, e.name);
        if (e.isDirectory()) {
          if (
            e.name.startsWith("chromium-") ||
            e.name.endsWith("playwright-browsers") ||
            e.name.endsWith("chrome-linux") ||
            p.includes("playwright")
          ) stack.push(p);
        } else if (e.name === "chrome" && (e.isFile() || e.isSymbolicLink())) {
          return p;
        }
      }
    }
  }
  return null;
}

const VIEWPORT = { width: 1600, height: 1200 };
const WAIT_AFTER_NETWORK = 1500;

async function shot(page, file, label) {
  const out = path.join(OUT_DIR, file);
  await page.screenshot({ path: out, fullPage: true });
  const stat = fs.statSync(out);
  console.log(`  ${(stat.size / 1024).toFixed(0)} KB  ${file}   ${label}`);
}

async function gotoAndSettle(page, url, contentSelector) {
  await page.goto(BASE + url, { waitUntil: "networkidle", timeout: 120_000 });
  if (contentSelector) {
    try {
      await page.waitForSelector(contentSelector, { timeout: 60_000 });
    } catch {
      console.warn(`  WARN: selector "${contentSelector}" never appeared on ${url}`);
    }
  }
  await page.waitForTimeout(WAIT_AFTER_NETWORK);
}

async function settleAfterInteraction(page, contentSelector) {
  await page.waitForTimeout(300);
  await page.waitForLoadState("networkidle", { timeout: 90_000 });
  if (contentSelector) {
    try { await page.waitForSelector(contentSelector, { timeout: 60_000 }); }
    catch { /* noop — capture the empty state */ }
  }
  await page.waitForTimeout(WAIT_AFTER_NETWORK);
}

(async () => {
  const exe = findChrome();
  if (!exe) {
    console.error("Could not locate chromium under PLAYWRIGHT_BROWSERS_PATH or /nix/store.");
    process.exit(1);
  }
  console.log(`Using ${exe}`);
  const browser = await chromium.launch({ executablePath: exe, headless: true });
  const ctx = await browser.newContext({ viewport: VIEWPORT });
  const page = await ctx.newPage();

  // Markdown — wait for at least one proposal row
  await gotoAndSettle(page, "/markdown/", ".recent-table tbody tr");
  await shot(page, "14-markdown-default.png", "Markdown — overstock SKUs + proposed discount");

  // Expand the first row to see the curve table.
  const firstRow = page.locator(".recent-table tbody tr").first();
  if (await firstRow.count()) {
    await firstRow.click();
    await page.waitForTimeout(700);
    await shot(page, "14b-markdown-expanded.png", "Markdown — expanded curve for top-row SKU");
  }

  // Cart Completion — pick each scenario in turn.
  await gotoAndSettle(page, "/cart-completion/", ".customer-chip");
  await shot(page, "15-cart-completion-default.png", "Cart Completion — first scenario default");

  const chips = ["Cat essentials", "Aquarium starter", "Dog accessory + toy"];
  for (const label of chips) {
    const chip = page.locator(".customer-chip", { hasText: label });
    if (await chip.count()) {
      await chip.click();
      await settleAfterInteraction(page);
      const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
      await shot(page, `15-cart-completion-${slug}.png`, `Cart Completion — ${label}`);
    }
  }

  // Win-back — list + expand one row.
  await gotoAndSettle(page, "/winback/", ".recent-table tbody tr");
  await shot(page, "16-winback-default.png", "Win-back — top churned customers");

  const wbRow = page.locator(".recent-table tbody tr").first();
  if (await wbRow.count()) {
    await wbRow.click();
    await page.waitForTimeout(700);
    await shot(page, "16b-winback-expanded.png", "Win-back — top-3 product suggestions per customer");
  }

  await browser.close();
  console.log(`Done. ${OUT_DIR}`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
