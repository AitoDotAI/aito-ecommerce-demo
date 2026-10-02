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
 */

const { chromium } = require("playwright-core");
const fs = require("fs");
const http = require("http");
const path = require("path");

const OUT = path.resolve(__dirname, "../out");
const EVAL_SNAPSHOT = path.resolve(__dirname, "../../data/precomputed/v2-master/evaluation.json");
const PORT = 8611;
const BASE = `http://localhost:${PORT}`;

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
];

async function firstApiRequest(page, apiPath, respond) {
  return new Promise((resolve) => {
    page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.replace(/\/$/, "") === apiPath) resolve(url);
      await respond(route, url);
    });
  });
}

const fail503 = (route) => route.fulfill({ status: 503, body: "test: no backend" });

async function main() {
  const server = serveStatic();
  const browser = await chromium.launch({ executablePath: findChrome() });
  const failures = [];
  const check = (ok, label) => { console.log(`  ${ok ? "ok  " : "FAIL"}  ${label}`); if (!ok) failures.push(label); };

  try {
    console.log("Cold load: the first request carries the link's state");
    for (const link of LINKS) {
      const context = await browser.newContext();       // fresh: nothing cached, no history
      const page = await context.newPage();
      const seen = firstApiRequest(page, link.api, fail503);
      await page.goto(`${BASE}/${link.view}/?${link.query}`);
      const url = await Promise.race([seen, new Promise((r) => setTimeout(() => r(null), 15000))]);
      const ok = url !== null && Object.entries(link.expect).every(([k, v]) => url.searchParams.get(k) === v);
      check(ok, `${link.view}?${link.query} → ${url ? url.pathname + url.search : "no request"}`);
      await context.close();
    }

    console.log("Back/forward: a choice is a history step");
    for (const [view, chosen, other] of [["smart-search", "maija", "olli"], ["recommendations", "olli", "saara"]]) {
      const context = await browser.newContext();
      const page = await context.newPage();
      const asked = [];
      await page.route("**/api/**", (route) => {
        asked.push(new URL(route.request().url()).searchParams.get("customer"));
        return fail503(route);
      });
      await page.goto(`${BASE}/${view}/?customer=${chosen}`);
      await page.waitForTimeout(800);
      await page.locator("button.customer-chip", { hasText: new RegExp(other, "i") }).first().click();
      await page.waitForURL(new RegExp(`customer=${other}`));
      await page.goBack();
      await page.waitForURL(new RegExp(`customer=${chosen}`));
      await page.waitForTimeout(800);
      const selected = await page.locator("button.customer-chip.selected").first().innerText();
      check(asked.includes(other) && asked[asked.length - 1] === chosen && new RegExp(chosen, "i").test(selected),
            `${view}: ${chosen} → ${other} → back restores ${chosen} (requests: ${asked.join(", ")})`);
      await context.close();
    }

    console.log("Evaluation: the focused model survives a cold load and back");
    const snapshot = JSON.parse(fs.readFileSync(EVAL_SNAPSHOT, "utf8")).data;
    const serveEval = (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(snapshot) });
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.route("**/api/**", serveEval);
    await page.goto(`${BASE}/evaluation/?model=dietary_from_name`);
    const focusedRow = page.locator("tr[style*='solid']").first();
    await focusedRow.waitFor({ timeout: 15000 });
    check(/diet/i.test(await focusedRow.innerText()), "evaluation?model=dietary_from_name focuses the dietary row");
    await page.locator("tr", { hasText: /segment/i }).first().click();
    await page.waitForURL(/model=segment_from_product/);
    await page.goBack();
    await page.waitForURL(/model=dietary_from_name/);
    check(/diet/i.test(await page.locator("tr[style*='solid']").first().innerText()), "evaluation: back restores the dietary focus");
    await context.close();
  } finally {
    await browser.close();
    server.close();
  }

  console.log(failures.length ? `\n${failures.length} FAILED` : "\nAll links open as shared.");
  process.exit(failures.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
