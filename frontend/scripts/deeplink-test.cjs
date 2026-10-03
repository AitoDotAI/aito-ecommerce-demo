/**
 * Shareable URLs: a pasted link opens a view exactly as it was shared, and
 * back/forward step through the user's choices.
 *
 * Run after `npx next build` (static export in out/):
 *   node scripts/deeplink-test.cjs
 *
 * Serves out/ locally and opens each link in a FRESH browser context (a cold
 * load, as when someone pastes it). The API is intercepted, never reached:
 * the test asserts that the page's first request carries the state from the
 * URL, which is what proves the link was read. Evaluation's state is
 * client-side only, so it gets the precomputed snapshot as its response.
 * Nothing here touches Aito.
 *
 * Opening a URL only proves links are READ. The click-through cases prove the
 * other half: using the UI updates the address bar, and the copied address
 * reopens the same state. Waits are explicit (no networkidle, no fixed sleeps).
 */

const { chromium } = require("playwright-core");
const fs = require("fs");
const http = require("http");
const path = require("path");

const OUT = path.resolve(__dirname, "../out");
const EVAL_SNAPSHOT = path.resolve(__dirname, "../../data/precomputed/v2-master/evaluation.json");
const PORT = 8611;
const BASE = `http://localhost:${PORT}`;
const TIMEOUT = 15000;

function findChrome() {
  const roots = [process.env.PLAYWRIGHT_BROWSERS_PATH, path.join(process.env.HOME, ".cache/ms-playwright")]
    .filter((r) => r && fs.existsSync(r));
  for (const root of roots) {
    for (const dir of fs.readdirSync(root).filter((d) => d.startsWith("chromium-")).sort().reverse()) {
      for (const sub of ["chrome-linux/chrome", "chrome-linux64/chrome"]) {
        const p = path.join(root, dir, sub);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  throw new Error("chromium not found: set PLAYWRIGHT_BROWSERS_PATH");
}

function serveStatic() {
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
                  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2" };
  return http.createServer((req, res) => {
    const urlPath = decodeURIComponent(new URL(req.url, BASE).pathname);
    let file = path.join(OUT, urlPath);
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (!fs.existsSync(file)) { res.writeHead(404); return res.end("not found"); }
    res.writeHead(200, { "content-type": types[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  }).listen(PORT);
}

// Each view: a link with state, and what the page's first API request must carry.
const LINKS = [
  { view: "smart-search", query: "customer=maija&q=dog+food", api: "/api/smart-search", expect: { customer: "maija", q: "dog food" } },
  { view: "recommendations", query: "customer=olli", api: "/api/for-you", expect: { customer: "olli" } },
  { view: "bought-together", query: "anchor=cat_wetfood", api: "/api/bought-together", expect: { anchor: "cat_wetfood" } },
  { view: "pattern-explorer", query: "anchor=cat_wetfood", api: "/api/pattern-explorer", expect: { anchor: "cat_wetfood" } },
  { view: "product-filling", query: "sku=SKU-PT-0042", api: "/api/product-filling", expect: { sku: "SKU-PT-0042" } },
  { view: "feedback", query: "review=REV-00042", api: "/api/feedback", expect: { review: "REV-00042" } },
  { view: "product-insights", query: "sku=SKU-PT-0042", api: "/api/product-insights", expect: { sku: "SKU-PT-0042" } },
];

// Views whose picker is filled from the API response: pick an option by
// clicking, the address bar must follow, and the copied address must reopen it.
const PICKERS = [
  { view: "bought-together", select: "#anchor-picker", key: "anchor", api: "/api/bought-together" },
  { view: "pattern-explorer", select: "#anchor-picker", key: "anchor", api: "/api/pattern-explorer" },
  { view: "product-filling", select: "#sku-picker", key: "sku", api: "/api/product-filling" },
  { view: "feedback", select: "#rev-picker", key: "review", api: "/api/feedback" },
  { view: "product-insights", select: "#sku-picker", key: "sku", api: "/api/product-insights" },
];

// Two options per picker, so there is something to pick. The selected entity
// echoes the request, as the real backend does.
const OPTIONS = { anchor: ["dog_dryfood", "cat_wetfood"], sku: ["SKU-PT-0001", "SKU-PT-0042"], review: ["REV-00001", "REV-00042"] };
const STUB_QUERY = { endpoint: "_relate", body: {} };

function stubResponse(apiPath, params) {
  const anchor = params.get("anchor") ?? OPTIONS.anchor[0];
  const anchors = OPTIONS.anchor.map((id) => ({ id, display: `Anchor ${id}` }));
  switch (apiPath) {
    case "/api/bought-together":
      return { anchor: { id: anchor, pet_type: "dog", category: "dry-food", display: `Anchor ${anchor}`, sample_skus: [] },
               cross_sells: [], available_anchors: anchors, last_query: STUB_QUERY, last_response_ms: 1 };
    case "/api/pattern-explorer":
      return { anchor: { id: anchor, pet_type: "dog", category: "dry-food", display: `Anchor ${anchor}` },
               patterns: [], available_anchors: anchors, last_query: STUB_QUERY, last_response_ms: 1 };
    case "/api/product-filling": {
      const sku = params.get("sku") ?? OPTIONS.sku[0];
      return { product: { sku, name: `Product ${sku}`, brand: "PetNord", pet_type: "dog", category: "dry-food",
                          weight_kg: null, dietary: null, tax_class: null, price_eur: 10 },
               fields: [], candidate_skus: OPTIONS.sku.map((s) => ({ sku: s, name: `Product ${s}` })),
               last_query: STUB_QUERY, last_response_ms: 1 };
    }
    case "/api/feedback": {
      const review = params.get("review") ?? OPTIONS.review[0];
      return { review: { review_id: review, customer_id: "CUST-00001", customer_short: "Maija", product_sku: "SKU-PT-0001",
                         product_name: "Product", rating: 4, text: `Review ${review}`, created_at: "2026-01-01",
                         actual_category: "quality", actual_sentiment: "positive", actual_assigned_to: "Anna",
                         actual_churn_within_90d: false },
               fields: [], candidate_reviews: OPTIONS.review.map((r) => ({ review_id: r, rating: 4, text_short: `Review ${r}` })),
               last_query: STUB_QUERY, last_response_ms: 1 };
    }
    case "/api/product-insights": {
      const sku = params.get("sku") ?? OPTIONS.sku[0];
      return { product: { sku, name: `Product ${sku}`, brand: "PetNord", pet_type: "dog", category: "treats", price_eur: 3 },
               funnel: [{ step: "impressions", count: 10 }, { step: "clicked", count: 5 },
                        { step: "added_to_cart", count: 3 }, { step: "purchased", count: 2 }],
               surfaces: [], buyers: [], monthly: [], ratings: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 },
               sentiments: { positive: 0, neutral: 0, negative: 0 },
               candidate_products: OPTIONS.sku.map((s) => ({ sku: s, name: `Product ${s}`, category: "treats", pet_type: "dog" })),
               bought_together_anchor: null, last_query: STUB_QUERY };
    }
    case "/api/evaluation":
      return JSON.parse(fs.readFileSync(EVAL_SNAPSHOT, "utf8")).data;
    default:
      return null;   // Smart Search and For You show their controls without data.
  }
}

const apiPathOf = (url) => url.pathname.replace(/\/$/, "");

// Opens `url` cold, the way a pasted link arrives: a fresh context with no
// cache and no history. Every API request is answered from stubs and recorded.
async function openFresh(browser, url) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const requests = [];
  await page.route("**/api/**", (route) => {
    const requested = new URL(route.request().url());
    requests.push(requested);
    const body = stubResponse(apiPathOf(requested), requested.searchParams);
    return body === null
      ? route.fulfill({ status: 503, body: "test: no backend" })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto(url);
  return { context, page, requests };
}

// The first request to `apiPath`, once one arrives. Polls rather than waiting
// for networkidle, which never settles on pages that poll.
async function firstRequest(requests, apiPath) {
  const deadline = Date.now() + TIMEOUT;
  while (Date.now() < deadline) {
    const found = requests.find((u) => apiPathOf(u) === apiPath);
    if (found) return found;
    await new Promise((r) => setTimeout(r, 100));
  }
  return null;
}

async function main() {
  const server = serveStatic();
  const browser = await chromium.launch({ executablePath: findChrome() });
  const failures = [];
  const check = (ok, label) => { console.log(`  ${ok ? "ok  " : "FAIL"}  ${label}`); if (!ok) failures.push(label); };
  const appears = (locator) => locator.waitFor({ timeout: TIMEOUT }).then(() => true, () => false);
  const urlMatches = (page, re) => page.waitForURL(re, { timeout: TIMEOUT }).then(() => true, () => false);
  const carries = (url, expect) => url !== null && Object.entries(expect).every(([k, v]) => url.searchParams.get(k) === v);

  try {
    console.log("Cold load: the first request carries the link's state");
    for (const link of LINKS) {
      const { context, requests } = await openFresh(browser, `${BASE}/${link.view}/?${link.query}`);
      const first = await firstRequest(requests, link.api);
      check(carries(first, link.expect), `${link.view}?${link.query} → ${first ? first.pathname + first.search : "no request"}`);
      await context.close();
    }

    console.log("Click-through: the address bar follows the UI, and the copied URL reopens the same state");
    for (const picker of PICKERS) {
      const chosen = OPTIONS[picker.key][1];
      const visit = await openFresh(browser, `${BASE}/${picker.view}/`);
      const select = visit.page.locator(picker.select);
      await select.locator(`option[value='${chosen}']`).waitFor({ state: "attached", timeout: TIMEOUT });
      await select.selectOption(chosen);
      const followed = await urlMatches(visit.page, new RegExp(`[?&]${picker.key}=${chosen}`));
      const copied = visit.page.url();
      await visit.context.close();
      check(followed, `${picker.view}: picking ${chosen} puts it in the address bar (${copied})`);

      const reopened = await openFresh(browser, copied);
      const first = await firstRequest(reopened.requests, picker.api);
      const selected = await appears(reopened.page.locator(`${picker.select}:has(option[value='${chosen}']:checked)`));
      check(carries(first, { [picker.key]: chosen }) && selected,
            `${picker.view}: the copied URL reopens ${chosen} (requested and selected)`);
      await reopened.context.close();
    }

    {
      const visit = await openFresh(browser, `${BASE}/smart-search/`);
      await visit.page.locator("button.customer-chip", { hasText: /maija/i }).first().click();
      await visit.page.locator("form.search-wrap input").fill("cat litter");
      await visit.page.locator("form.search-wrap button[type=submit]").click();
      const followed = await urlMatches(visit.page, /customer=maija/) && await urlMatches(visit.page, /q=cat(\+|%20)litter/);
      const copied = visit.page.url();
      await visit.context.close();
      check(followed, `smart-search: a persona click and a search put both in the address bar (${copied})`);

      const reopened = await openFresh(browser, copied);
      const first = await firstRequest(reopened.requests, "/api/smart-search");
      const chip = await appears(reopened.page.locator("button.customer-chip.selected", { hasText: /maija/i }));
      const query = await reopened.page.locator("form.search-wrap input").inputValue();
      check(carries(first, { customer: "maija", q: "cat litter" }) && chip && query === "cat litter",
            `smart-search: the copied URL reopens Maija searching "cat litter" (input shows "${query}")`);
      await reopened.context.close();
    }

    {
      const visit = await openFresh(browser, `${BASE}/recommendations/`);
      await visit.page.locator("button.customer-chip", { hasText: /olli/i }).first().click();
      const followed = await urlMatches(visit.page, /customer=olli/);
      const copied = visit.page.url();
      await visit.context.close();
      check(followed, `recommendations: a persona click puts it in the address bar (${copied})`);

      const reopened = await openFresh(browser, copied);
      const first = await firstRequest(reopened.requests, "/api/for-you");
      const chip = await appears(reopened.page.locator("button.customer-chip.selected", { hasText: /olli/i }));
      check(carries(first, { customer: "olli" }) && chip, "recommendations: the copied URL reopens Olli");
      await reopened.context.close();
    }

    {
      const visit = await openFresh(browser, `${BASE}/evaluation/`);
      await visit.page.locator("tr", { hasText: /segment/i }).first().click();
      const followed = await urlMatches(visit.page, /model=segment_from_product/);
      const copied = visit.page.url();
      await visit.context.close();
      check(followed, `evaluation: a row click puts the model in the address bar (${copied})`);

      const reopened = await openFresh(browser, copied);
      const focused = await appears(reopened.page.locator("tr[style*='solid']", { hasText: /segment/i }).first());
      check(focused, "evaluation: the copied URL reopens with the segment row focused");
      await reopened.context.close();
    }

    console.log("Back/forward: a choice is a history step");
    for (const [view, chosen, other] of [["smart-search", "maija", "olli"], ["recommendations", "olli", "saara"]]) {
      const { context, page, requests } = await openFresh(browser, `${BASE}/${view}/?customer=${chosen}`);
      const isSelected = (name) => appears(page.locator("button.customer-chip.selected", { hasText: new RegExp(name, "i") }));
      await isSelected(chosen);
      await page.locator("button.customer-chip", { hasText: new RegExp(other, "i") }).first().click();
      const forward = await urlMatches(page, new RegExp(`customer=${other}`)) && await isSelected(other);
      await page.goBack();
      const back = await urlMatches(page, new RegExp(`customer=${chosen}`)) && await isSelected(chosen);
      const asked = requests.map((u) => u.searchParams.get("customer"));
      check(forward && back && asked.includes(other) && asked[asked.length - 1] === chosen,
            `${view}: ${chosen} → ${other} → back restores ${chosen} (requests: ${asked.join(", ")})`);
      await context.close();
    }

    {
      const { context, page } = await openFresh(browser, `${BASE}/evaluation/?model=dietary_from_name`);
      const focusedDietary = page.locator("tr[style*='solid']", { hasText: /diet/i }).first();
      check(await appears(focusedDietary), "evaluation?model=dietary_from_name focuses the dietary row");
      await page.locator("tr", { hasText: /segment/i }).first().click();
      const forward = await urlMatches(page, /model=segment_from_product/);
      await page.goBack();
      const back = await urlMatches(page, /model=dietary_from_name/) && await appears(focusedDietary);
      check(forward && back, "evaluation: segment → back restores the dietary focus");
      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  console.log(failures.length ? `\n${failures.length} FAILED` : "\nAll links open as shared.");
  process.exit(failures.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
