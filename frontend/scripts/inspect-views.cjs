/**
 * Visual inspection: walks every sidebar view (ADR 0041's sections),
 * exercises a few controls (shopper, search, anchor, SKU picker), and
 * captures full-page screenshots into `screenshots/inspect/`.
 *
 * Run: node scripts/inspect-views.cjs
 */

const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

// INSPECT_BASE: another running copy, e.g. a backend serving the static export.
const BASE = process.env.INSPECT_BASE || "http://localhost:8500";
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

  // The site by job (ADR 0041): the Shop, the owner's views, the operator's
  // tools, Evidence and Query patterns. The old views redirect to these
  // (frontend/lib/moved-routes.ts), so they aren't walked.

  // 1. Overview: KPIs, one headline per owner view, best sellers, households
  await gotoAndSettle(page, "/", ".hbar-row");
  await shot(page, "01-overview.png", "Overview: KPIs / headlines per owner view / best sellers / households");

  // 2. Shop: Päivi's kit path (the partner demo's Flow 1), then Janne's search
  await gotoAndSettle(page, "/shop/?shopper=paivi", ".shop-card-name");
  await shot(page, "02-shop-paivi.png", "Shop: Päivi, Buy again / Next for their kit / Picked for you");

  await gotoAndSettle(page, "/shop/?shopper=janne&q=food", ".shop-card-name");
  await shot(page, "02-shop-janne-food.png", "Shop: Janne searches 'food', his household's grain-free rule");

  // 3. Product: the offer decision and the what-ifs for the Flow 2 product
  await gotoAndSettle(page, "/product/?sku=SKU-PT-0563&month=2026-04&tab=what-if", "[role=tablist]");
  await shot(page, "03-product-what-if.png", "Product: Trixie Hideout, the offer decision and what-ifs");

  // 4. Patterns: baskets as rules, filtered to one anchor
  await gotoAndSettle(page, "/patterns/?anchor=dog_dryfood", "#basket-rules");
  await shot(page, "04-patterns-baskets-dog-dryfood.png", "Patterns: baskets as rules, dog dry-food anchor");

  // 5–6. Supply and Retention
  await gotoAndSettle(page, "/supply/", ".card-title");
  await shot(page, "05-supply.png", "Supply: reorder now, overstock and its markdown");

  await gotoAndSettle(page, "/retention/", ".card-title");
  await shot(page, "06-retention.png", "Retention: at-risk customers and their win-back offer");

  // 7. Product filling: wait for a confidence chip, then a second SKU
  await gotoAndSettle(page, "/product-filling/", ".fill-conf");
  await shot(page, "07-product-filling-default.png", "Product filling: default (Hill's Sensitive)");

  const skuOptions = await page.$$eval("#sku-picker option", (opts) =>
    opts.map((o) => o.value).filter((v) => v),
  );
  if (skuOptions.length > 3) {
    const target = skuOptions[3];
    await page.selectOption("#sku-picker", target);
    await settleAfterInteraction(page, ".fill-conf");
    await shot(page, "07-product-filling-alt.png", `Product filling: alt SKU ${target}`);
  }

  // 8. Review triage
  await gotoAndSettle(page, "/review-triage/", "#rev-picker");
  await shot(page, "08-review-triage.png", "Review triage: category, sentiment, assignee");

  // 9–12. Evidence: the index, real data (UCI), and the synthetic pages
  await gotoAndSettle(page, "/evidence/", ".evidence-entry");
  await shot(page, "09-evidence-index.png", "Evidence: index, Real / Synthetic marks");

  await gotoAndSettle(page, "/evidence/business-reorders/", ".card-title");
  await shot(page, "10-evidence-business-reorders.png", "Evidence: a business buyer's next order (UCI, real data)");

  await gotoAndSettle(page, "/evidence/personalised-search/", ".card-title");
  await shot(page, "11-evidence-personalised-search.png", "Evidence: personalised search, side by side");

  await gotoAndSettle(page, "/evidence/model-checks/", ".data-table");
  await shot(page, "12-evidence-model-checks.png", "Evidence: model checks, with the honest failure");

  // 13. For developers: one minimal call per endpoint
  await gotoAndSettle(page, "/query-patterns/", ".rec-card");
  await shot(page, "13-query-patterns.png", "Query patterns: the minimal _recommend");

  // 14. Mobile breakpoint sanity (≤ 768px hides both side rails)
  await ctx.close();
  const mobileCtx = await browser.newContext({ viewport: { width: 414, height: 900 } });
  const mp = await mobileCtx.newPage();
  await mp.goto(BASE + "/", { waitUntil: "networkidle", timeout: 90_000 });
  await mp.waitForTimeout(WAIT_AFTER_NETWORK);
  await mp.screenshot({ path: path.join(OUT_DIR, "14-mobile-overview.png"), fullPage: false });
  console.log(`   mobile overview captured`);

  await browser.close();
  console.log(`Done. ${OUT_DIR}`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
