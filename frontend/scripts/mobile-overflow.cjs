/**
 * Mobile overflow check: every view, and the states where overflow hides, at a phone width.
 *
 * Screenshots alone missed two bugs a reader hits at once: a popover wider than the screen
 * (the page's scroll width is unchanged when a fixed popover is clipped), and a breadcrumb
 * pushing the avatar past the edge. So this measures: per state it reports the page's scroll
 * width against the viewport, the elements whose right edge leaves the screen (off-canvas
 * panels excluded), and, for an open popover, whether its rectangle sits inside the screen on
 * all four sides. It exits 1 when any state overflows.
 *
 * Run after `./do dev` is up:
 *   ./do verify-mobile              # 414 px, writes screenshots/inspect-mobile/overflow/
 *   VW=360 node frontend/scripts/mobile-overflow.cjs   # another width
 *   node frontend/scripts/mobile-overflow.cjs <outdir> <state-name-substring>
 */
const { chromium } = require("playwright-core");
const fs = require("fs"), path = require("path");

// The Chromium the Nix shell provides (as inspect-mobile.cjs finds it), or $CHROME.
// Symlinks are followed: the Nix browsers directory is made of them.
function findChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!root) throw new Error("Set PLAYWRIGHT_BROWSERS_PATH (the Nix shell does) or CHROME to a Chromium binary.");
  const stack = [root];
  let limit = 30_000;
  while (stack.length && limit-- > 0) {
    const dir = stack.pop();
    let names = [];
    try { names = fs.readdirSync(dir); } catch { continue; }
    for (const name of names) {
      const p = path.join(dir, name);
      let st;
      try { st = fs.statSync(p); } catch { continue; }
      if (st.isDirectory()) stack.push(p);
      else if (name === "chrome") return p;
    }
  }
  throw new Error(`No Chromium ("chrome") found under ${root}.`);
}

const OUT = process.argv[2] || path.resolve(__dirname, "../../screenshots/inspect-mobile/overflow");
const ONLY = process.argv[3] || "";
fs.mkdirSync(OUT, { recursive: true });
const W = Number(process.env.VW || 414);

const STATES = [
  { name: "shop", url: "/shop/?shopper=paivi&demo=1" },
  { name: "shop-drawer", url: "/shop/?shopper=paivi&demo=1", open: async (p) => { await p.getByRole("button", { name: /details/i }).first().click(); } },
  { name: "overview", url: "/?demo=1" },
  { name: "patterns", url: "/patterns/" },
  { name: "product-whatif", url: "/product/?sku=SKU-PT-0563&month=2026-04&tab=what-if&demo=1" },
  { name: "product-whatif-folded-open", url: "/product/?sku=SKU-PT-0563&month=2026-04&tab=what-if", open: async (p) => { await p.locator("details summary").first().click(); } },
  { name: "product-history", url: "/product/?sku=SKU-PT-0563&month=2026-04&tab=history&demo=1" },
  { name: "product-forwhom", url: "/product/?sku=SKU-PT-0563&month=2026-04&tab=for-whom&demo=1" },
  { name: "supply", url: "/supply/?demo=1" },
  { name: "supply-row-details", url: "/supply/?demo=1", open: async (p) => { await p.getByText("Details", { exact: true }).first().click(); } },
  { name: "reviews", url: "/reviews/?demo=1" },
  { name: "retention", url: "/retention/?demo=1" },
  { name: "retention-winback", url: "/retention/?demo=1", open: async (p) => { await p.getByText(/win-back offer/i).first().click(); } },
  { name: "product-filling", url: "/product-filling/" },
  { name: "product-filling-why", url: "/product-filling/", open: async (p) => { await p.locator("button[aria-label='Why this prediction?']").first().click(); } },
  { name: "product-filling-why-parts", url: "/product-filling/", open: async (p) => {
      await p.locator("button[aria-label='Why this prediction?']").first().click();
      await p.getByText(/parts multiplied/).first().click(); } },
  { name: "review-triage", url: "/review-triage/" },
  { name: "review-triage-why", url: "/review-triage/", open: async (p) => { await p.locator("button[aria-label='Why this prediction?']").first().click(); } },
  { name: "evidence", url: "/evidence/" },
  { name: "business-reorders", url: "/evidence/business-reorders/" },
  { name: "personalised-search", url: "/evidence/personalised-search/" },
  { name: "search-relevance", url: "/evidence/search-relevance/" },
  { name: "model-checks", url: "/evidence/model-checks/" },
  { name: "query-patterns", url: "/query-patterns/" },
];

(async () => {
  const browser = await chromium.launch({ executablePath: findChrome() });
  const ctx = await browser.newContext({ viewport: { width: W, height: 900 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, colorScheme: "light" });
  await ctx.addInitScript(() => { try { localStorage.setItem("ecom.aitoCollapsed", "true"); } catch {} });
  const page = await ctx.newPage();
  const rows = [];
  for (const s of STATES) {
    if (ONLY && !s.name.includes(ONLY)) continue;
    let note = "";
    try {
      await page.goto((process.env.BASE || "http://localhost:8500") + s.url, { waitUntil: "networkidle", timeout: 240000 });
      await page.waitForTimeout(2500);
      if (s.open) {
        try { await s.open(page); await page.waitForTimeout(1500); }
        catch (e) { note = "could not open state: " + e.message.split("\n")[0].slice(0, 70); }
      }
      const m = await page.evaluate((vw) => {
        const de = document.documentElement;
        const scrolls = (el) => { for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if ((o === "auto" || o === "scroll") && a.scrollWidth > a.clientWidth + 1) return true; } return false; };
        const bad = [];
        for (const el of document.querySelectorAll("body *")) {
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) continue;
          if (el.closest(".aito-panel, .sidebar, nav")) continue;
          if (r.right > vw + 1 && !scrolls(el)) bad.push({ tag: el.tagName.toLowerCase(), cls: (el.className && el.className.toString().slice(0, 40)) || "", text: (el.innerText || "").trim().slice(0, 40).replace(/\s+/g, " "), right: Math.round(r.right), width: Math.round(r.width) });
        }
        bad.sort((a, b) => b.right - a.right);
        const vh = window.innerHeight;
        const pops = [...document.querySelectorAll("body > div")].filter((d) => getComputedStyle(d).position === "fixed" && getComputedStyle(d).zIndex === "9999")
          .map((d) => { const r = d.getBoundingClientRect(); return { left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top), bottom: Math.round(r.bottom), w: Math.round(r.width) }; });
        const popBad = pops.filter((r) => r.left < 0 || r.right > vw + 1 || r.top < 0 || r.bottom > vh + 1);
        return { scrollWidth: de.scrollWidth, bodyScroll: document.body.scrollWidth, bad: bad.slice(0, 4), count: bad.length, pops, popBad: popBad.length };
      }, W);
      const over = m.scrollWidth > W + 1 || m.popBad > 0;
      rows.push({ name: s.name, over, ...m, note });
      await page.screenshot({ path: path.join(OUT, `${s.name}.png`), fullPage: true });
    } catch (e) {
      rows.push({ name: s.name, over: null, note: "ERROR " + e.message.split("\n")[0].slice(0, 90) });
    }
  }
  await browser.close();
  for (const r of rows) {
    const flag = r.over === null ? "ERR " : r.over ? "OVER" : "ok  ";
    const detail = r.bad && r.bad.length ? " | " + r.bad.map((b) => `${b.tag}.${b.cls.split(" ")[0]} right=${b.right} w=${b.width} "${b.text}"`).join(" ; ") : "";
    console.log(`${flag} ${r.name.padEnd(28)} scrollW=${r.scrollWidth ?? "-"} offenders=${r.count ?? "-"}${r.pops && r.pops.length ? " popover=" + JSON.stringify(r.pops[0]) + (r.popBad ? " OUT-OF-SCREEN" : " in-screen") : ""}${r.note ? " (" + r.note + ")" : ""}${detail}`);
  }
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(rows, null, 1));
  const failed = rows.filter((r) => r.over !== false);
  console.log(failed.length ? `\n${failed.length} of ${rows.length} states overflow or failed.` : `\nAll ${rows.length} states fit ${W} px.`);
  process.exit(failed.length ? 1 : 0);
})();
