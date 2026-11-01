# ADR 0055: Customers as generic analytics: a time range, more narrowing tabs, and the raw rows

**Status:** Proposed (2026-11-01, Antti's requests; plan accepted: "Makes sense")
**Slice 1 built (the time range):** a period of months is picked on the trend (drag, or the last 3, 6 or 12 months) and the page sets the selected customers in it against the period just before it and as long (Antti, 2026-11-01: a week against the week before, a month against the month before), beside everyone's change (`src/customer_period.py`, `?start=&end=` on the segment route, `from` and `to` in the page URL). The tabs under it still describe the whole history; narrowing them to the period is not built. Months only, since the data has no dates.
**Slice 2 built (the raw data widget):** full width under both panes, tabs Sales by product, Orders and Feedback (reviews and NPS answers), paged, for the selected customers and only the months of the chosen period (`src/customer_rows.py`, `data/customer_profiles/rows.json`, `/api/customer-profiles/rows`). A row never names a customer; a selection under the minimum size shows no rows. The category and location tabs are not built.
**Slice 3 built (the left-side tabs):** the tree has tabs Behaviour (as before), Products (a category or a brand the customer bought, any pet) and Where (the region); a condition of any tab is a condition of the same selection and combines with the period and the raw rows. The facts gain `region`, `categories` and `brands` per customer. Narrowing the detail tabs to the period is not built.
**Slice 4 built (reviews and NPS told apart):** the raw data widget has separate tabs Reviews (stars, product, topic, text) and NPS answers (score, group), and the tree a Feedback tab: customers who wrote a review about a topic (praise, question, quality, shipping, fit) or answered the survey as a promoter, passive or detractor. A review is about a product; an NPS answer is about an order.
**Date:** 2026-11-01
**Deciders:** Antti

## Context

The Customers view (ADR 0053) selects a segment from traits and describes it. Three extensions were asked for:

1. Select a time period in the trend graph, so the analysis narrows to it. The recent period is analysed like a segment and set against the rest, to spot a trend.
2. More narrowing tabs on the left, for product categories and locations, turning the view into a generic analytics view.
3. A data widget at the bottom with tabs (sales by product, individual feedback, ...) showing the raw rows of the selection.

## What the data allows

Orders carry a month, not a date (`orders.json`: `month`), and so do customer-months. Last 7 and 30 days cannot be
analysed from this data. Months and 6 months can. Regions and postcode areas exist on customers; categories on order lines.

## Decision

- **Time range.** The trend graph takes a range of months (drag, or the presets "last 3 months", "last 6 months", "last 12 months"). The range is a second selection beside the traits: the page analyses the selected customers *in that range* and sets them against the same customers outside it (the "recent against before" idea of ADR 0053, with a chosen range). The range is in the URL. Days need dated orders: a fixtures change, its own ADR.
- **Narrowing tabs.** The left side gets tabs: **Behaviour** (the current tree), **Products** (category, brand, pet type) and **Where** (region). A condition from any tab is a condition of the same selection; counts are made from the per-customer facts as now (more facts per customer: the categories bought and region).
- **Raw data.** A widget below the details with tabs: **Sales by product**, **Orders**, **Feedback** (the individual answers and reviews), each listing the rows of the selection, paged, without names or contact details.
- **Privacy** is unchanged: profiled and consenting customers only; groups under the minimum size answer with their size.

## Aito usage

None new: counts come from the stored facts (ADR 0053). Raw rows come from the stored fixtures.

## Acceptance criteria

- [ ] A user can pick a range in the trend; the header, figures and tabs describe the selected customers in that range, and the page says what it is set against.
- [ ] Categories, brands and regions can be ticked like the traits, and combine with them and with the range.
- [ ] The raw-data widget shows sales by product, orders and individual feedback for the selection, and a selection under the minimum size shows no rows.
- [ ] No names, emails or contact details appear in any widget.

## Out of scope

Days or weeks (needs dated fixtures); editing data; export of the rows.
