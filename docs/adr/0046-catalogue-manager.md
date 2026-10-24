# ADR 0046: Catalogue manager — import, fill, edit, and see the estimates

**Status:** Accepted (2026-10-24, Antti: "a product management view, where you can edit
product naming, pricing and properties and see the KPIs live real time … an import button
which will import items in different format (from vendor) and fill then the metadata")
**Date:** 2026-10-24
**Deciders:** Antti

## Context

A merchant's catalogue work is:
- importing a vendor's new items, in the vendor's own format;
- completing their metadata;
- pricing them;
- later, editing items as offers and assortments change.

Today the parts exist apart:
- **Product filling** (ADR 0009): `_predict` fills five fields from a product's name.
- **Product** (ADR 0041): one product's estimates and what-ifs.
- **Sandbox branches** (ADR 0043): writes in a per-session env, never in master.

Nothing connects "this is a new item" to "this is what it will do".

New items are Aito's cold-start strength. With no history, the estimate comes from the
item's attributes and from products like it. An existing product's own history dominates
its estimate, so editing its name or a property moves the estimate little. The view must
say which kind of edit can move what.

## Decision

A view **Catalogue** (Operate › Catalogue), sandbox-only for its writes. It absorbs
Product filling.

1. **Import.**
   - Upload a vendor file (CSV or JSON, or paste rows).
   - Map the vendor's columns to ours (name, brand, price, cost, pack size, EAN …). The
     mapping is suggested by column-name similarity and confirmed by the user; it's
     remembered per vendor.
   - Unmapped or empty fields stay empty: they're filled in step 2, not guessed by the
     importer.
   - Rows that fail validation are listed and counted, never dropped silently.
2. **Fill.**
   - For each imported item, `_predict` fills the missing fields (pet type, category,
     dietary, tags, size class) from the name and the mapped fields, with `$p` and
     `$why`.
   - Fields under the confidence rule (`$p` < 0.6) are marked "check" rather than filled.
     The user accepts, edits or rejects each.
3. **Estimate.** Before any sale, per item, at the price and offer the user sets:
   - the chance a showing ends in a purchase: `_predict purchased` on impressions with
     the item's attributes (no `product_sku`, since it has no history);
   - expected units next month: `_estimate units_sold` with its attributes and price
     index (ADR 0045);
   - the three most similar existing products and how they sell (`_match` or `_search`
     by attributes), so the estimate has visible neighbours.
4. **Edit, live.**
   - Name, price, cost, properties and offer band, for new and existing items.
   - Each edit writes the item to the session's sandbox branch, reads it back and
     re-asks the estimates; the change is shown as before → after, with `$why`.
   - **What an edit can move is stated beside each field:**
     - for an existing product, "its own history dominates: a property change moves
       this little";
     - for a new one, "estimated from its attributes and products like it".
5. **Publish** is out of scope. The sandbox branch is the result; a real shop would
   export it to its PIM or shop platform.

## Aito usage, probed before use

| Query | Question |
|---|---|
| `_predict purchased` on impressions with `product_sku.*` attribute conditions and no SKU | Does a new item's estimate come from the attributes, with `$why` naming them? |
| `_estimate units_sold` from attributes plus `price_index` | Does it answer for an unseen product? |
| `_match` / `_search` for similar products | Which form gives sensible neighbours? |
| `_predict` fill with several known fields in `where` | Does it improve over the name alone? |

## Evidence

**Catalogue estimates, checked:** take products launched in the data (ADR 0032's
launches), hide their history, estimate them as new from their attributes, then compare
with their first three months. Pre-registered; the error goes with its interval.

## Acceptance criteria

- [ ] A user can import a vendor CSV with different column names, confirm the mapping,
      and see each row filled or marked "check", with `$why`. Invalid rows are listed.
- [ ] Each new item shows its estimates and three similar products before any sale.
- [ ] Editing price or offer updates the estimates live, with read-back.
- [ ] Editing an existing product's property shows the note that its history dominates.
- [ ] Writes happen only in a sandbox branch (ADR 0043's fence).
- [ ] The cold-start estimate's error is an Evidence entry with its interval.

## Out of scope

- Publishing to a shop platform or PIM.
- Images.
- Vendor feeds over APIs (file upload only).

## Consequences

**Good:**
- The demo shows Aito where it's strongest, new items with no history, in a merchant's
  everyday task.
- Product filling gets a real job in a workflow instead of a standalone page.

**Bad:**
- A second write path in the sandbox (items, not just state rows).
- Column mapping is real UI work. It's kept simple: suggestions plus confirmation.
