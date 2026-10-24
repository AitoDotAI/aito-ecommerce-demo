/**
 * Mobile screenshot harness — walks every sidebar view at a phone
 * viewport (414 × 900, iPhone-Pro-Max-ish) and captures full-page
 * screenshots into `screenshots/inspect-mobile/`.
 *
 * Layered on top of `inspect-views.cjs` (which is desktop). Use
 * this script to spot mobile-only regressions: horizontal scroll,
 * cramped KPI strips, overflowing tables, two-column layouts that
 * don't collapse, header / topbar issues.
 *
 * Run from project root after `./do dev` is up:
 *   ./do verify-mobile
 *   # or directly:
 *   node frontend/scripts/inspect-mobile.cjs
 *
 * Output dir is gitignored — these are diagnostic artefacts, not
 * curated demo collateral.
 */

const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const BASE = "http://localhost:8500";
const OUT_DIR = path.resolve(__dirname, "../../screenshots/inspect-mobile");
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

// 414 × 900 — iPhone 14 Pro Max width, slightly taller height so
// fullPage captures of mid-length pages don't need many composites.
// Devicescalefactor 2 so screenshots match Retina pixel density;
// fonts will look right on the reviewer's screen.
const MOBILE = {
  viewport: { width: 414, height: 900 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
  userAgent:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) " +
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 " +
    "Mobile/15E148 Safari/604.1",
};
const WAIT_AFTER_NETWORK = 1500;

// One screenshot per route. `selector` is an optional content
// selector to wait for before snapping (lets us avoid skeleton-
// loader screenshots). When omitted we just trust networkidle +
// the delay.
const VIEWS = [
  { route: "/shop/",                         file: "01-shop.png",                selector: null },
  { route: "/",                              file: "02-overview.png",            selector: ".hbar-row" },
  { route: "/patterns/",                     file: "03-patterns.png",            selector: null },
  { route: "/product-insights/",             file: "04-product.png",             selector: null },
  { route: "/inventory/",                    file: "05-supply.png",              selector: null },
  { route: "/churn/",                        file: "06-retention.png",           selector: null },
  { route: "/product-filling/",              file: "07-product-filling.png",     selector: ".fill-conf" },
  { route: "/feedback/",                     file: "08-review-triage.png",       selector: null },
  { route: "/evidence/",                     file: "09-evidence.png",            selector: ".evidence-entry" },
  { route: "/evidence/business-reorders/",   file: "10-business-reorders.png",   selector: null },
  { route: "/evidence/personalised-search/", file: "11-personalised-search.png", selector: ".pill-orange, .pill-blue" },
  { route: "/evidence/model-checks/",        file: "12-model-checks.png",        selector: ".eval-row-pass, .eval-row-fail" },
  { route: "/query-patterns/",               file: "13-query-patterns.png",      selector: ".rec-card" },
];

async function shot(page, file, label) {
  const out = path.join(OUT_DIR, file);
  await page.screenshot({ path: out, fullPage: true });
  const stat = fs.statSync(out);
  console.log(`  ${(stat.size / 1024).toFixed(0).padStart(4, " ")} KB  ${file}   ${label}`);
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

(async () => {
  const exe = findChrome();
  if (!exe) {
    console.error("Could not locate chromium under PLAYWRIGHT_BROWSERS_PATH or /nix/store.");
    process.exit(1);
  }
  console.log(`Using ${exe}`);
  console.log(`Mobile viewport: ${MOBILE.viewport.width} × ${MOBILE.viewport.height}, ` +
              `DPR ${MOBILE.deviceScaleFactor}`);
  const browser = await chromium.launch({ executablePath: exe, headless: true });
  const ctx = await browser.newContext(MOBILE);
  const page = await ctx.newPage();

  for (const v of VIEWS) {
    try {
      await gotoAndSettle(page, v.route, v.selector);
      await shot(page, v.file, v.route);
    } catch (err) {
      console.error(`  FAIL ${v.route}: ${err.message}`);
    }
  }

  await browser.close();
  console.log(`Done. ${OUT_DIR}`);
  console.log(`\nReview tips when scanning the output:`);
  console.log(`  - Horizontal scroll → table or .kpi-grid not stacking`);
  console.log(`  - Sidebar visible → should auto-hide ≤ 768 px`);
  console.log(`  - Touch targets < 40 px → tap targets too small`);
  console.log(`  - KPI numbers wrapping into 3+ lines → too dense`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
