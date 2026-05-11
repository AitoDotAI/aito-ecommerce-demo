# Visual inspection — 2026-05-11

A Playwright-driven walk of every view, screenshot each, then a read-
through under three hats: tester, designer, e-commerce expert.

The Playwright script that produced the inputs:
[`frontend/scripts/inspect-views.cjs`](../../frontend/scripts/inspect-views.cjs).
Screenshots in `screenshots/inspect/` (gitignored — regenerate locally
via `cd frontend && node scripts/inspect-views.cjs` against a running
`./do dev`).

17 frames captured across the 8 views + 3 persona / anchor variations
+ one mobile breakpoint.

---

## Tester hat — what's broken

### B1. **CRITICAL · Bought Together aquarium anchor leaves stale state on screen**

Selecting the **Aquarium food** anchor leaves the page in a half-loaded
state: the dropdown reflects the new anchor, but the **anchor card
still shows "Cat wet-food"** (the previous selection), the four
cross-sell tiles are stuck on the skeleton loader, and the Aito panel's
`query` block still quotes `$match: "cat_wetfood"`.

Two possible root causes, both real:

1. **App bug** — `bought-together/page.tsx` keeps the previous
   `data` visible while `loading: true`. When the new fetch takes
   longer than a glance, the user sees the new selection in the
   dropdown alongside the *old* anchor card + Aito-panel body.

2. **Slow `_relate` cold path** — the aquarium token is rare
   (~6 % of orders), and Aito's `_relate` on the first cold call can
   take 30 s+. By the time the screenshot was taken, the fetch hadn't
   returned. (Cache subsequently warm; the live demo will only hit
   this on the first aquarium visit per cache window.)

Both contribute. The visible fix: clear `data` on anchor change so
the anchor card swaps to a loading state too, and add a visible
"this might take a moment" hint on first cold pull. Same pattern
applies to Pattern Explorer and Smart Search.

### B2. Mobile dashboard (≤ 414 px) overflows

KPI grid shows only 3 of 4 cards fully — the **€ Avg Basket** card
is half-cut off the right edge. Top Purchase Patterns and Customer
Segments columns sit side-by-side at this width when they should
stack. The `two-col` CSS rule from
`predictive-ecommerce-demo.html` collapses to a single column
under 900 px in the mock — we may have lost that breakpoint when
porting.

### B3. Bought Together latency badge stays "frozen" on warm-cache hits

The `2360 ms` badge is the time the response was first computed,
not the time the user just spent. After cache warm-up subsequent
loads still display this stale value. Reads as "every click is 2.4
seconds" when the cached path is < 50 ms.

Fix: show *server response time* (read off `X-Aito-Calls` header
via the `LatencyBadge` event bus we already have on the topbar)
rather than the `last_response_ms` value baked into the cached
DTO.

### B4. Pattern Explorer "Neutral patterns" empty state

For both probed anchors (`dog_dryfood`, `cat_wetfood`) the
neutral band is empty — every co-occurrence is either positive
(≥ 1.5×) or protective (< 0.7×). The view dutifully renders
"(none for this anchor)" but the empty section reads as
"this didn't load."

Fix: hide the section when empty, or collapse it.

### B5. Evaluation Pet-type baseline shows 0.0 %

The cell reads `0.0%`, which to a tester looks like "missing data."
Documented in ADR 0010 as a known Aito quirk (`baseAccuracy` returns
0 for some predicts) but the UI doesn't communicate that — it
just looks wrong. Hover-tooltip or a small `?` icon would close
this gap.

### B6. For You uses identical pet-type emojis for every tile

Each tile uses `🐕 / 🐈 / 🐹 / 🐦 / 🐟` as a placeholder image. In
Maija's grid (all cat) every tile renders the same `🐈` — twelve
identical emojis stacked. The visual reads "no product images
configured" rather than "predictive grid."

A neutral fallback: brand initial in a coloured square (e.g. "RC"
on yellow for Royal Canin), or a single shared `cart` emoji.

---

## Designer hat — visual / typography / spacing

### D1. Smart Search column subtitles are too code-y

Left column reads
`` `_search where name $match q` · plain token match ``, right reads
`` _recommend goal: { segment: "dog_owner", pet_size: "large" } ``
— accurate, but as a *page subtitle* this is denser than the rest
of the demo's copy. The Aito panel is the right place for the
verbatim body. The column subtitles should read as plain English:
"Standard search — token match only" vs. "Predictive — re-ranked
for this customer."

### D2. Pattern Explorer red labels on red bars — poor contrast

The protective-band rows use red bars with the lift number ("× 0.3")
also rendered in red. Reads OK on the bar but the chip itself
washes out. Either change the chip background to neutral (white /
cream) with red text, or invert (white text on red chip).

### D3. Pattern Explorer green text on green bars — slight contrast issue

Less severe than D2 but the positive-band rows show green chips on
green bars with the chip's `lift-hint up` rule using
`background: var(--green-bg)` and `color: var(--green)`. The chip
itself reads fine, but the green-on-green-on-green stack (bar fill
+ chip bg + label text) is monochromatic to the point of feeling
"flat".

### D4. Dashboard "Insight" tip-box overflows the two-column rhythm

The two-col grid above (Top Patterns | Customer Segments) is tidy.
The tip-box and Recent Orders below run full-width. Reads as a slight
break in rhythm — could be a deliberate "callout" effect, or could be
tightened. Designer preference.

### D5. Bought Together anchor-card sample SKUs render with name-wrap

Cat wet-food anchor's sample product list shows names wrapping to
two lines ("Felix Grain Free Chicken Cat Food 150g") with the price
hanging in its own visual cell. Looks bumpy. Either truncate names
or widen the card's name column.

### D6. Aito panel "Endpoints" pills wrap when ≥ 4 endpoints active

Dashboard, Bought Together, and Evaluation all show 4 endpoint pills,
wrapping to 2 rows. Acceptable but uneven density across views. A
fixed two-row layout would feel more deliberate.

### D7. Sidebar nav "Live" badge on For You + "98 %" badge on Product Filling

Mock-faithful and reads cleanly. The yellow `--cta`-on-dark-forest
combination is the right level of attention-grab.

### D8. Aito panel's `aito..ai` wordmark with teal `..` is on-brand

The locked panel design is consistent across views — the same
`#0c0f41` indigo and `#12B5AD` teal accents. Visual identity locks
in immediately.

### D9. Brand "🐾 PetNord" wordmark

Reads as a real Nordic pet retailer. The paw emoji on the yellow
square is friendly. The "Powered by aito.ai" subtitle is small but
present — appropriate.

### D10. Evaluation table — focused row outline

The active (failing) row is outlined in yellow `--cta`. Strong
visual anchor. Pass rows use a subtle green wash; FAIL row uses a
slightly stronger red wash. Differentiation is clear.

---

## E-commerce expert hat — sales narrative + credibility

### E1. Dashboard reads as trustworthy

Real numbers (658 / 10,156 / 3,000 / €75) feel like an actual mid-
size shop. The Top Purchase Patterns lift bars don't look manufactured —
the 2.7× dog-food→dental-treats lift is high but not absurd, and the
Aquarium niche pattern at 8.4× reads as "look, niche segments have
their own physics, Aito surfaces both."

### E2. Smart Search rank-flip is the sharpest moment

Switching personas re-ranks the right column completely — every
predictive entry on Maija is cat-food; switching to Saara replaces
every row with large-breed dog food. The Aito panel's `goal` field
changing live makes the change *quantifiable*. A CTO can't unsee
this.

### E3. For You — three crisply different shoppers

Maija (cat consumables — litter / dry-food / wet-food), Olli (small-
dog accessories / grooming / health), Saara (large-breed kibble +
dog health). The flip is dramatic. **Olli's grid skewing dog-heavy
after the goal-override is the right call** — without it, Maija and
Olli looked too similar.

### E4. Bought Together — 2.7× lands

The headline 2.7× with "2,953 of 3,137 baskets" is much sharper than a
naked percentage. Sales conversations can quote the absolute basket
count alongside the lift. Cat wet-food anchor shows 2.0–2.1×
cross-sells; consistent with the Pattern Explorer view.

### E5. Pattern Explorer — the "protective band" is a bonus moment

The red protective-pattern rows ("dog dry-food → cat wet-food × 0.27",
"dog dry-food → aquarium 0.03") tell the story "Aito knows what
customers don't cross-buy." This is **not** in TASK.md's five demo
moments but is a strong sales talking point. Worth promoting:
"the same query that powers Bought Together also surfaces the
*anti*-recommendations — these are the SKUs you wouldn't want to
co-merchandise next to dog food."

Suggest: add a beat to `docs/demo-script.md` for this on
Pattern Explorer.

### E6. Product Filling — five fields with confidence chips

Strong. The 🔒 stored chip on the two already-populated fields is a
nice honesty signal. Demonstrates "Aito will not just predict
missing fields — it'll also tell you when its prediction matches
your stored data, building confidence." The 95–98 % numbers feel
high but the explanation (token match on `Sensitive` / `2kg`) makes
them earned.

### E7. Evaluation — the failure case lands

The FAIL row visibly tints red, the tip-box explains why
accuracy_gain = 0 % is the *value*. This is the strongest piece of
trust-building copy in the demo. **Keep the focus highlight on the
FAIL row by default** — the demo-script already does this.

### E8. Brand chrome reads as a real product

Sidebar sections (`OVERVIEW / ASSIST CUSTOMERS / ANALYZE / AUTOMATE`)
read as a real SaaS nav — not a marketing-mock. The aito.ai · 11,970
orders · 16 ms avg sidebar footer adds quiet credibility.

### E9. EU hosted · No PII stored — easy-to-cite

The Aito panel's Data section names both. For a Nordic CTO audience,
this is a load-bearing detail.

### E10. Demo-script holds across the inspection

Every beat from `docs/demo-script.md` survives the visual read. The
narration matches the moments captured. The two-minute target is
realistic.

---

## Punch list

### Blocking for first public demo
- **B1** — Bought Together stale-state when switching anchors with a
  cold cache. Fix: clear `data` on anchor change so the anchor card
  also enters the loading state, and add a "first call may take a
  moment" hint.

### Should fix before going live
- **B2** — mobile dashboard overflow (KPI grid + two-col stacking).
- **B3** — Bought Together latency badge stale on warm-cache hits.
- **D1** — Smart Search column subtitles too code-y.
- **D2** — Pattern Explorer red label / red bar contrast.

### Nice to have
- **B4** — collapse empty Neutral band in Pattern Explorer.
- **B5** — Pet-type baseAccuracy=0 cell: show "—" + tooltip.
- **B6** — replace pet-type emoji placeholders in For You tiles.
- **D3** — Pattern Explorer green-on-green-on-green tone.
- **D4** — Dashboard tip-box vs two-col rhythm.
- **D5** — Bought Together anchor-card SKU name wrap.
- **D6** — endpoint-pill wrap density.
- **E5** — add a Pattern Explorer "protective band" beat to demo-script.

### Bonus opportunities surfaced by the inspection
- Promote Pattern Explorer's protective-pattern story into the
  demo-script as a 6th beat for advanced viewers.
- The honesty narrative of Product Filling's "🔒 stored" chip
  could appear in the README's how-it-works section: "Aito shows
  you what it can't help you with as clearly as what it can."
