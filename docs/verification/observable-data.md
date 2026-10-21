# Verification — observable-only data and the Shop's intent views (ADR 0032, ADR 0033)

`./do verify` isn't wired to an adversary agent yet, so this pass was run
by an adversary agent on 2026-10-21. It used the read-only backend that was
already running (`PUBLIC_DEMO=1`, `AITO_ENV=observable`, port 8602), a fresh
static export (`next build --webpack`, because the export on disk predated
the Shop's three views), and Playwright at 1440 × 1000 and 390 × 844. About
150 API calls in all (≈ 80 direct, 100 from the pages, many of them served
from cache). Screenshots are in the session scratchpad
(`…/scratchpad/verify/shots/`) and are not committed. The pass tried to
break the feature, not to confirm it.

**Caveat on what was tested.** The backend on 8602 started at 08:36, before
`bae4951` (20:21) changed `src/shop_reasons.py`. Uvicorn runs without
`--reload`, so the Python code it serves is older than HEAD for the reason
labels. `/api/version` reports `bae4951`, but `build_info()` reads git when
a request comes in, not when the process starts, so it can't show this. A
second read-only backend from HEAD couldn't be started: the worktree has no
credentials file, and copying the running process's environment was
refused. The grid's query shape (`context.customer.pets`, month, cart words)
matches HEAD's `shop_context.py`. Only the chip labels could differ, and no
chip outside HEAD's label set was seen.

## Acceptance criteria

### ADR 0033

| Criterion | Result |
|---|---|
| No table Aito sees holds lifestyle, health focus, treat affinity or brand loyalty; a test checks the schema | Not re-tested live (`/api/schema` is 404 in public mode). No API response from the 21 views probed holds those fields. |
| The Shop's query holds only a customer id and context; a premium, health-focused cat owner's grid leans to premium wellness cat food, learned from their history | **Fail as written, superseded by the amendment.** The query holds no customer id at all (Pass on "no identity"). But it can't personalise beyond declared pets: Helena's and Maija's April grids are identical (both cat), and Janne, Olli and Saara (all dog) get the same top 3 (`desk-shop-*-2026-04.png`). The amendment dropped identity on purpose, but this criterion wasn't rewritten. |
| Every analytics view says which fields are declared and which derived | Partial. Shop analytics and Product Insights read cleanly. Churn's table header still says "Segment · region", and Purchase Analytics' panel says "Slice by … segment" (see failures). |
| A user can be Päivi (owns a cage and a bottle) and see the hideout among the first three products in the grid, with "you own a cage" or the basket among its reasons; adding the hideout brings the wheel up | **Superseded / partial.** The grid no longer shows the hideout (the kit moved to "Next for their kit", per the amendment). That view lists PetNord Hideout 17 %, Trixie Hideout 15 %, Trixie Hideout 13 %, PetNord Exercise Wheel 9 %. With the hideout in the cart, the grid's Trixie Exercise Wheel rises from 12th (28 %) to 5th (40 %). But "Next for their kit" doesn't change: it still offers the hideout already in the cart, and two more hideouts (`desk-shop-paivi-hideout-in-cart.png`). |
| Amendment: three views, one per intent; the grid drops identity and kit | Pass: "Buy again" (`_predict skus.$feature` over own orders), "Next for their kit" (`_predict product_sku` over `order_lines` with `order_id.owned_before`), "Picked for you" (`_recommend`). For all six shoppers × April 2026 and November 2025, the grid's `where` held only `context.customer.pets`, `context.month`, `just_bought`, the pets filter, and the rule `$or` (Janne). No `context.customer` id and no `context.owned` appeared, in the API or in the side panel. |

### ADR 0032 (user-visible parts)

| Criterion | Result |
|---|---|
| Budget shopper sees "On offer ×N" as one of Aito's reasons on a discounted card | **Not seen.** Offers show only as grey facts ("−21 % this month"). No "On offer" reason chip appeared on any of the ~150 cards viewed. No shopper is labelled "budget" (that's a hidden trait), so it's unclear which shopper this criterion means. |
| Launch, rival-launch, price-rise marks on a product; Shop analytics lists `product_state.on_offer` with an interval above 1 | Not tested in depth (budget). Product Insights and Price loaded with no errors or trait words. Shop analytics loaded, but its `product_state.on_offer` row wasn't checked. |

## Edge cases tried

| Case | Result |
|---|---|
| Unknown shopper (grid, suggestions, page) | 404 "No shopper 'nobody'; known: …". The page shows its not-found notice. |
| Month `2026-13`, `april`, `26-4`, missing shopper | 422 (pattern or missing) |
| Month `2030-01` and `2019-01` (outside the data) | **200, same grid for both.** An unseen `context.month` is silently ignored (see failures). |
| Unknown SKU in the cart / duplicate SKU | 404 "No product SKU-NOPE in the catalogue" / 400 "The cart lists a product twice". The page shows the error in a card (`desk-bad-*.png`). |
| Search "", "   " | 400 "Search needs at least one word". The empty form submit does nothing. |
| Search "zzqxv", 500 × "a", `{"$or":{}}` | 200, `text_matched: false`, 0.15 s. The page says so. |
| Search "hideout" (Päivi) | 3 hideouts, "Fits your pets" ×2.2–2.6 |
| Search "food" (Janne, grain-free) | 12 results, all grain-free dog food (`keeps_rule: true`) |
| Search "dental" (Päivi, guinea pig) | 12 dog products, some with **"Fits your pets ×2.4"** (failure 1) |
| Fill my usual basket (Maija) | Adds the 4 of 8 items at ≥ 15 %. None of them reappears in the grid. |
| Add a grid card, then remove a cart item | The card leaves the grid. The cart goes from 5 to 4. URL state stays consistent. |
| Päivi, November 2025 (before the guinea pig) | "No orders before November 2025: nothing to buy again or to add to a kit yet." The grid is still small-animal. |
| Probabilities | All of `p` in [0, 1]. No "%" above 100, and no NaN, undefined or Infinity text on any page. |
| Product drawer (hideout, Janne's treat, unknown SKU) | 200 / 200 / 404. Alternatives are the same kind of product. |
| Phone 390 px | Shop, search, and the drawer have no horizontal overflow. Shop analytics overflows by 6 px, Churn by 5 px. |
| Page errors | None. The only console errors are the 4xx responses above, which were intended. |
| Evaluation | Three models (pet type from name, dietary from attributes, return risk). No segment model. |

## Failures found

1. **"Fits your pets" on another pet's products in Shop search (medium).**
   Repro: `/shop/?shopper=paivi&q=dental`. Päivi declares only
   `small_animal`, but the results are all dog products, and two PetNord
   Dental Spray cards carry "Fits your pets ×2.4" and "×1.4"
   (`desk-search-paivi-dental.png`). The grid filters on declared pets;
   search doesn't, yet it labels the `$why` lift of
   `context.customer.pets` as fitting her pets. A reader would take the
   chip literally.

2. **The kit view ignores the cart (low–medium).** Repro: as Päivi, press
   "+" on PetNord Hideout. The cart holds it, but "Next for their kit"
   still lists it, plus two more hideouts, and the wheel stays 4th at 9 %.
   The same happens in "Buy again" after "Fill my usual basket": the items
   in the cart stay listed with "+". This is the "cart item reappearing"
   pattern, in the suggestion views rather than the grid.

3. **Hidden-trait words in UI copy (low, but named as a failure for this
   ADR).**
   - Churn table header: "Segment · region" (the column shows declared
     pets).
   - Purchase Analytics panel: "Slice by month, category, segment, region".
   - Dashboard: "growing segment" and "live-rank the pattern's customer
     segments".
   - Static panel queries that show before live data loads: Churn's
     `"segment": "small_animal_owner"`, and Pattern Explorer's `_relate`
     from `customers` over `pet_size` → `segment`
     (`frontend/lib/panel-content.ts`).
   - Saara's shopper story: "A large dog, premium and brand-loyal."
     *Ambiguous:* ADR 0033's demo impact uses this line on purpose ("Aito
     never sees that Saara is premium…"). But nothing on the page says
     this is the narrator's knowledge rather than data.

4. **Story contradicts declared data: Olli (low).** His story says "A small
   dog and a cat", but his declared `pets` is `dog` (the cat's weight of
   0.15 is below `main_pets`' threshold). "Picked for you" therefore never
   shows him a cat product.

5. **Dashboard pills contradict their numbers (low).** "Aquarium
   households … High AOV" has the lowest average basket (€63.05).
   Small-animal has the highest (€119.48) but is pilled "Growing". "Dog
   households … Highest LTV" has the second-lowest basket. The pills are
   static copy that was not revisited when the groups became declared pets.

6. **Out-of-data months are accepted silently (low).** `month=2030-01` and
   `2019-01` return 200 with the same grid. Aito ignores an unseen
   `context.month` value, and nothing tells the user.

7. **Pre-existing, outside this ADR's diff:** `/api/for-you?customer=nobody`
   and `/api/smart-search?customer=nobody` return 200 for Maija and Saara
   (`PERSONAS.get(...) or PERSONAS[DEFAULT_PERSONA]`, since 2026-05). This
   silent fallback breaks CLAUDE.md prime directive 2.

## Ambiguous, not counted as failures

- With anything in the cart, no card showed "Goes with your cart", even
  though the cart visibly re-ranked the grid (the wheel went from 12th to
  5th). Most "Fits your pets" chips also disappeared. The parser may be
  right, with the lifts nested under the product's own lift. But it was run
  with the pre-`bae4951` code (see caveat), so this wasn't diagnosed
  further.
- Päivi's guinea-pig household is offered rabbit and hamster food:
  `small_animal` is the declared granularity.
- Janne's grid, and the other dog grids, hold only treats and accessories,
  no food, in April 2026. In November 2025 Janne is offered two harness
  SKUs while owning a harness. The grid no longer knows the kit, by
  design.
- The Shop's intro still says suggestions follow "who they are". The grid
  uses declared pets, not identity.

## Fixes, and the re-check (2026-10-21, backend restarted at HEAD)

| Finding | Fix | Re-check (live, env `observable`) |
|---|---|---|
| 1. "Fits your pets" on dog products in Päivi's "dental" search | The chip shows only on the household's own pets' products (`src/shop_ranking.py`); search still shows other pets' products | The six top results are dog products; their only chip is "Sells in April" |
| 2. Kit and usual-basket views ignore the cart | A kit item in the cart counts as owned; nothing in the cart is suggested again (`src/shop_suggestions.py`) | Hideout SKU-PT-0558 in the cart: owned reads cage, hideout, water bottle; the wheel is first (23 %), no hideout listed |
| 3. "segment" in UI copy | Churn "Pets · region"; Churn, Pattern Explorer and Purchase Analytics panels show the queries the code sends; Saara's story states what she reorders | Copy grep clean |
| 4. Olli's story | "Declares a small dog; reorders Acana Sensitive dog food", as his row declares | — |
| 5. Dashboard pills | Computed from the card's numbers; notes with no data behind them removed | Offline test `tests/test_overview_household_pills.py`; the dashboard snapshot refreshes at precompute |
| 6. Month outside the data | 400 "The shop's data runs from 2024-05 to 2026-04" | `month=2030-01` → 400 |
| 7. Unknown customer on For You / Smart Search | 404 naming the personas, instead of a default persona | `customer=nobody` → 404 on both |
| Phone overflow | Grid columns shrink; tables scroll inside their cards | Every page measured at 390 px |

The two acceptance criteria overtaken by the amendment are replaced in ADR
0033 ("Acceptance criteria, as amended"). The kit criterion now passes
("Next for their kit": hideout first; with it in the cart, the wheel). The
grid criteria pass by construction (`tests/test_shop_grid.py`). Tests: 325
offline, and the live checks on `observable`, pass.
Not re-checked in the browser after the fixes: the layout at 390 px was
measured by the fixing agent, not by a fresh adversary pass.
