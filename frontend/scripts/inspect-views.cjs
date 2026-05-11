/**
 * Visual inspection — walks every view, exercises interactive
 * controls (persona pills, anchor pickers, SKU dropdown), and
 * captures full-page screenshots into `screenshots/inspect/`.
 *
 * Run: node scripts/inspect-views.cjs
 */

const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const BASE = "http://localhost:8500";
const OUT_DIR = path.resolve(__dirname, "../../screenshots/inspect");
fs.mkdirSync(OUT_DIR, { recursive: true });

// Find the chromium executable Nix put on disk.
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
const WAIT_AFTER_NETWORK = 1200;

async function shot(page, file, label) {
  const out = path.join(OUT_DIR, file);
  await page.screenshot({ path: out, fullPage: true });
  const stat = fs.statSync(out);
  console.log(`  ${(stat.size / 1024).toFixed(0)} KB  ${file}   ${label}`);
}

async function gotoAndSettle(page, url, contentSelector) {
  await page.goto(BASE + url, { waitUntil: "networkidle", timeout: 90_000 });
  if (contentSelector) {
    await page.waitForSelector(contentSelector, { timeout: 90_000 });
  }
  await page.waitForTimeout(WAIT_AFTER_NETWORK);
}

/** Wait for a fetch triggered by interaction (pill click / select option)
 *  to actually land — `networkidle` returns immediately if the React
 *  effect hasn't fired yet. Combines a fixed delay (let useEffect fire)
 *  with networkidle (wait for the fetch to complete) + an optional
 *  content selector (wait for the new DOM to settle). */
async function settleAfterInteraction(page, contentSelector) {
  await page.waitForTimeout(300);
  await page.waitForLoadState("networkidle", { timeout: 90_000 });
  if (contentSelector) {
    await page.waitForSelector(contentSelector, { timeout: 90_000 });
  }
  await page.waitForTimeout(WAIT_AFTER_NETWORK);
}

(async () => {
  const exe = findChrome();
  if (!exe) {
    console.error("ERROR: chromium not found");
    process.exit(1);
  }
  console.log(`chromium: ${exe}`);

  const browser = await chromium.launch({
    executablePath: exe,
    headless: true,
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  });
  const ctx = await browser.newContext({ viewport: VIEWPORT });
  const page = await ctx.newPage();

  // 1. Dashboard — wait for top-pattern bars to render
  await gotoAndSettle(page, "/", ".lift-row");
  await shot(page, "01-dashboard.png", "Dashboard — KPIs / top patterns / segments / orders");

  // 2. Smart Search — Saara default. Wait for at least one predictive row.
  await gotoAndSettle(page, "/smart-search/", ".pill-orange, .pill-blue");
  await shot(page, "02-smart-search-saara-default.png", "Smart Search — Saara (large breed dog)");

  await page.locator(".customer-chip", { hasText: "Maija" }).click();
  await settleAfterInteraction(page, ".pill-blue");
  await shot(page, "02-smart-search-maija.png", "Smart Search — Maija (cat owner) — flipped");

  await page.locator(".customer-chip", { hasText: "Olli" }).click();
  await settleAfterInteraction(page);
  await shot(page, "02-smart-search-olli.png", "Smart Search — Olli (multi-pet small dog)");

  // 3. For You — wait for a rec-card to appear
  await gotoAndSettle(page, "/recommendations/", ".rec-card");
  await shot(page, "03-for-you-maija.png", "For You — Maija default");

  await page.locator(".customer-chip", { hasText: "Saara" }).click();
  await settleAfterInteraction(page, ".rec-card");
  await shot(page, "03-for-you-saara.png", "For You — Saara (large breed dog)");

  await page.locator(".customer-chip", { hasText: "Olli" }).click();
  await settleAfterInteraction(page, ".rec-card");
  await shot(page, "03-for-you-olli.png", "For You — Olli (multi-pet small dog)");

  // 4. Bought Together — wait for cross-sell tiles (rec-card)
  await gotoAndSettle(page, "/bought-together/", ".rec-card");
  await shot(page, "04-bought-together-dog-dryfood.png", "Bought Together — dog dry-food anchor");

  await page.selectOption("#anchor-picker", "cat_wetfood");
  await settleAfterInteraction(page, ".rec-card");
  await shot(page, "04-bought-together-cat-wetfood.png", "Bought Together — cat wet-food anchor");

  // Aquarium has a single cross-sell and is the cold-cache stress test.
  // Wait until either the rec-card lands OR the "no patterns" empty
  // state renders — whichever comes first.
  await page.selectOption("#anchor-picker", "aquarium_aquarium");
  await page.waitForTimeout(300);
  await page.waitForLoadState("networkidle", { timeout: 90_000 });
  await page.waitForFunction(
    () => document.querySelectorAll(".rec-card").length > 0
       || !!document.querySelector("[data-empty-state]"),
    null,
    { timeout: 90_000 },
  );
  await page.waitForTimeout(WAIT_AFTER_NETWORK);
  await shot(page, "04-bought-together-aquarium.png", "Bought Together — aquarium anchor (niche)");

  // 5. Purchase Analytics — wait for the hbar rows
  await gotoAndSettle(page, "/purchase-analytics/", ".hbar-row");
  await shot(page, "05-purchase-analytics.png", "Purchase Analytics");

  // 6. Pattern Explorer — wait for at least one .lift-hint to appear
  await gotoAndSettle(page, "/pattern-explorer/", ".lift-hint");
  await shot(page, "06-pattern-explorer-dog-dryfood.png", "Pattern Explorer — dog dry-food anchor (full lift band)");

  await page.selectOption("#anchor-picker", "cat_wetfood");
  await settleAfterInteraction(page, ".lift-hint");
  await shot(page, "06-pattern-explorer-cat-wetfood.png", "Pattern Explorer — cat wet-food anchor");

  // 7. Product Filling — wait for confidence chip
  await gotoAndSettle(page, "/product-filling/", ".fill-conf");
  await shot(page, "07-product-filling-default.png", "Product Filling — default (Hill's Sensitive)");

  const skuOptions = await page.$$eval("#sku-picker option", (opts) =>
    opts.map((o) => o.value).filter((v) => v),
  );
  if (skuOptions.length > 3) {
    const target = skuOptions[3];
    await page.selectOption("#sku-picker", target);
    await settleAfterInteraction(page, ".fill-conf");
    await shot(page, "07-product-filling-alt.png", `Product Filling — alt SKU ${target}`);
  }

  // 8. Evaluation — wait for at least one .eval-row-pass row
  await gotoAndSettle(page, "/evaluation/", ".eval-row-pass, .eval-row-fail");
  await shot(page, "08-evaluation.png", "Evaluation — 3 pass, 1 honest-failure");

  // 9. Mobile breakpoint sanity (≤ 768px hides both side rails)
  await ctx.close();
  const mobileCtx = await browser.newContext({ viewport: { width: 414, height: 900 } });
  const mp = await mobileCtx.newPage();
  await mp.goto(BASE + "/", { waitUntil: "networkidle", timeout: 90_000 });
  await mp.waitForTimeout(WAIT_AFTER_NETWORK);
  await mp.screenshot({ path: path.join(OUT_DIR, "09-mobile-dashboard.png"), fullPage: false });
  console.log(`   mobile dashboard captured`);

  await browser.close();
  console.log(`Done. ${OUT_DIR}`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
