# ADR 0062: A dataset where demand moves: seasonal ware, trends, and launches that become hits or flops

**Status:** Proposed. The generator and the backtest are built; the switches are off in the committed fixtures. Nothing is loaded into shared Aito.
**Date:** 2026-11-02
**Deciders:** Antti ("Could we have some seasonality? … new products or trends? … new product demand may change depending on state, reviews, pricing")

## Context

[ADR 0061](0061-supply-follows-demand.md) found that Aito's forecast with the product's stars, age, season and category only ties "the same range as last month".
The generated demand is close to flat per product: a category has a season, a launch gets a fixed ×2 for three months. A simple rule models that about as well as anything.

## Decision

`data/demand_dynamics.py` adds three effects, each behind a switch (`D1`–`D3`, off in the committed fixtures, so with them off `./do generate-fixtures` writes the fixtures byte for byte),
each from an RNG stream of its own:

- **D1 seasonal ware.** 36 products (toys, accessories, treats, grooming, health) sell mostly in one season (winter, summer, or the weeks before Christmas): ×5 at the peak, ×0.35 away from it.
- **D2 trends.** 36 products rise (×1.14 a month, up to ×4) or fade (×0.86 a month, down to ×0.2) from a month of their own.
- **D3 launches.** For eight months a launch's pull is shaped by its price against its category median and its quality (the stars show it once reviews arrive): a good, fairly priced launch ramps up over four months to
  as much as ×3.6; a poor or dear one falls to ×0.4–0.6. The flat ×2 of ADR 0032 applies when D3 is off.

Only a product's pick weight in a month changes. Demand for a product comes out of its category's share of the orders, as before.

## Aito usage

None in the generator. The question this dataset is for: does Aito's `_evaluate` with product state and season beat the simple rule when demand moves? `scripts/harder_demand_backtest.py` answers it offline first
(adjustments fitted only on earlier months); the Aito run needs the dataset in an env (`./do env-new`, `env-load`: Antti's call).

## Result so far (offline, last seven months, 4,586 product-months)

The planted effects are large where they act (a rising product goes from 7 to 182 units a month against 62 without the trend), but over all products the plain three-month rate is still not beaten:
category and season, momentum, age and stars all come out as no clear difference or worse, and so do trend lines. Most products sell about three units a month, and only about a fifth of the catalogue is
affected, so the noise of small counts dominates the average. Where the drivers should matter, on products in their first three months, age and stars beat the rule by 4.3 units
(± 3.0, 49 product-months) on the new data and not clearly on the old (−1.9 ± 4.4). That is a small sample.

## Acceptance criteria

- With `D1`–`D3` off, `./do generate-fixtures` writes the committed fixtures byte for byte (checked: no diff).
- With them on, a seasonal product sells more than four times as much in its peak month as in the opposite season, a rising product ends the window above where it began, and a good launch outsells a flop (`tests/test_demand_dynamics.py`).

## Demo impact

None until a data release carries the dataset.

## Out of scope

Loading it into Aito; making it the default; named seasonal products (winter coats, advent calendars) in the catalogue, which is a catalogue change; weather.
