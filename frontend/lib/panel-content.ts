/** Per-view Aito-panel content.
 *
 * Each view exports one `AitoPanelConfig`. The right-rail panel
 * renders endpoint pills, a one-line "what this page is doing"
 * description, the actual JSON body that drove the latest query,
 * and learn-more links.
 *
 * The example queries below are **draft** — they read straight
 * from the visual mock's `views` object. Once each view ships
 * its real `_predict` / `_relate` / `_recommend` / `_search`
 * implementation, the matching builder is replaced with the
 * runnable query body that was actually sent (CLAUDE.md prime
 * directive #3 — no aspirational queries in the panel).
 */

import type { AitoPanelConfig } from "./types";


const LEARN_MORE_LINKS: NonNullable<AitoPanelConfig["links"]> = [
  { label: "API Reference",  url: "https://aito.ai/docs/api/" },
  { label: "Documentation",  url: "https://aito.ai/docs/" },
  { label: "Source (GitHub)", url: "https://github.com/AitoDotAI/aito-ecommerce-demo", kind: "github" },
];


/** Shared rendering helpers — these mirror the syntax-highlight
 *  classes in `globals.css` (`.aito-query .k|.s|.n|.p`). Kept here
 *  so builders below stay readable. */
function k(s: string): string { return `<span class="k">${s}</span>`; }
function n(s: string): string { return `<span class="n">${s}</span>`; }
function s(v: string): string { return `<span class="s">${v}</span>`; }


export function dashboardPanel(): AitoPanelConfig {
  return {
    operation: "Dashboard",
    endpoints: ["_search", "_relate"],
    description:
      `KPIs from live <code style="color:var(--aito-teal);">_search limit=0</code> ` +
      `counts. Top patterns come from live ` +
      `<code style="color:var(--aito-teal);">_relate</code> over ` +
      `<code>orders.line_categories</code> — the same query body that powers ` +
      `Bought Together. Drill into any pattern there for the full lift band.`,
    query:
`${k('"relate"')}: {
  ${n('"from"')}: ${s('"orders"')},
  ${n('"where"')}: {
    ${n('"line_categories"')}: { ${n('"$match"')}: ${s('"dog_dryfood"')} }
  },
  ${n('"relate"')}: ${s('"line_categories"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function smartSearchPanel(): AitoPanelConfig {
  return {
    operation: "Smart Search",
    endpoints: ["_search"],
    description:
      `Re-ranks search results by combining free-text token matching ` +
      `(<code style="color:var(--aito-teal);">$match</code> on the ` +
      `<code style="color:var(--aito-teal);">name</code> Text column) with ` +
      `customer-context biasing. Customers see products they're likely to ` +
      `buy, not just products whose names contain the query.`,
    query:
`${k('"search"')}: {
  ${n('"from"')}: ${s('"products"')},
  ${n('"where"')}: {
    ${n('"name"')}: { ${n('"$match"')}: ${s('"food"')} }
  },
  ${n('"limit"')}: 10
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function recommendationsPanel(): AitoPanelConfig {
  return {
    operation: "For You",
    endpoints: ["_recommend"],
    description:
      `Personalised product recommendations per customer. Aito ranks all ` +
      `products by P(this customer would buy it, given their history). ` +
      `Switching the customer in the pill bar above flips the entire grid ` +
      `in &lt; 300 ms — same query body, different ` +
      `<code style="color:var(--aito-teal);">where</code> context.`,
    query:
`${k('"recommend"')}: {
  ${n('"from"')}: ${s('"order_lines"')},
  ${n('"where"')}: {
    ${n('"orders.customer_id"')}: ${s('"CUST-00001"')}
  },
  ${n('"recommend"')}: ${s('"product_sku"')},
  ${n('"goal"')}: { ${n('"returned"')}: false }
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function boughtTogetherPanel(): AitoPanelConfig {
  return {
    operation: "Bought Together",
    endpoints: ["_relate"],
    description:
      `Co-purchase lift: how much more likely product B is bought ` +
      `alongside product A compared to its baseline. For dog dry-food, ` +
      `dental treats run at <strong style="color:var(--aito-teal);">≈ 2.7×</strong> ` +
      `their normal rate.`,
    query:
`${k('"relate"')}: {
  ${n('"from"')}: ${s('"order_lines"')},
  ${n('"where"')}: {
    ${n('"category"')}: ${s('"dry-food"')},
    ${n('"pet_type"')}: ${s('"dog"')}
  },
  ${n('"relate"')}: ${s('"category"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function purchaseAnalyticsPanel(): AitoPanelConfig {
  return {
    operation: "Purchase Analytics",
    endpoints: ["_search", "_relate"],
    description:
      `Aggregate analytics powered by <code style="color:var(--aito-teal);">_search</code> ` +
      `and <code style="color:var(--aito-teal);">_relate</code>. Slice by month, ` +
      `category, segment, region — no pre-built dashboards, just queries.`,
    query:
`${k('"search"')}: {
  ${n('"from"')}: ${s('"orders"')},
  ${n('"where"')}: {
    ${n('"month"')}: ${s('"2026-04"')}
  },
  ${n('"limit"')}: 0
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function patternExplorerPanel(): AitoPanelConfig {
  return {
    operation: "Pattern Explorer",
    endpoints: ["_relate"],
    description:
      `Ad-hoc discovery queries. Pick a field + value and Aito returns ` +
      `which other fields correlate unusually. Returns lift, support count, ` +
      `and relative strength — read the table sorted by lift descending.`,
    query:
`${k('"relate"')}: {
  ${n('"from"')}: ${s('"customers"')},
  ${n('"where"')}: {
    ${n('"pet_size"')}: ${s('"large"')}
  },
  ${n('"relate"')}: ${s('"segment"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function productFillingPanel(): AitoPanelConfig {
  return {
    operation: "Product Filling",
    endpoints: ["_predict"],
    description:
      `Predicts missing product attributes from the product's name plus ` +
      `the populated catalog. One <code style="color:var(--aito-teal);">_predict</code> ` +
      `call per missing field resolves <code style="color:var(--aito-teal);">weight_kg</code>, ` +
      `<code style="color:var(--aito-teal);">dietary</code>, and ` +
      `<code style="color:var(--aito-teal);">tax_class</code> in one round-trip.`,
    query:
`${k('"predict"')}: {
  ${n('"from"')}: ${s('"products"')},
  ${n('"where"')}: {
    ${n('"name"')}: ${s('"Acana Large Breed Adult"')},
    ${n('"pet_type"')}: ${s('"dog"')},
    ${n('"brand"')}: ${s('"Acana"')}
  },
  ${n('"predict"')}: ${s('"dietary"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function feedbackPanel(): AitoPanelConfig {
  return {
    operation: "Feedback",
    endpoints: ["_predict"],
    description:
      `Four parallel <code style="color:var(--aito-teal);">_predict</code> calls ` +
      `condition on both <code style="color:var(--aito-teal);">text</code> + ` +
      `<code style="color:var(--aito-teal);">rating</code> and return ` +
      `<strong>category</strong>, <strong>sentiment</strong>, ` +
      `<strong>assigned_to</strong>, and <strong>P(churn within 90 d)</strong> ` +
      `in one round-trip. The popover surfaces each feature's lift contribution.`,
    query:
`${k('"predict"')}: {
  ${n('"from"')}: ${s('"reviews"')},
  ${n('"where"')}: {
    ${n('"text"')}: ${s('"Package arrived late. The seal was broken."')},
    ${n('"rating"')}: 2
  },
  ${n('"predict"')}: ${s('"churn_within_90d"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function churnPanel(): AitoPanelConfig {
  return {
    operation: "Churn",
    endpoints: ["_predict", "_relate", "_evaluate"],
    description:
      `Time-series prediction over the <code style="color:var(--aito-teal);">customer_months</code> ` +
      `panel — one row per customer per month with visits, purchases, ` +
      `spend, latest review snapshot. <code style="color:var(--aito-teal);">_predict ` +
      `churned_in_3_months</code> ranks active customers by risk. Drivers via ` +
      `parallel <code style="color:var(--aito-teal);">_relate</code>. Accuracy via ` +
      `<code style="color:var(--aito-teal);">_evaluate</code>.`,
    query:
`${k('"predict"')}: {
  ${n('"from"')}: ${s('"customer_months"')},
  ${n('"where"')}: {
    ${n('"segment"')}: ${s('"small_animal_owner"')},
    ${n('"region"')}: ${s('"oulu"')},
    ${n('"visits"')}: 4,
    ${n('"purchases"')}: 0,
    ${n('"spent_eur"')}: 0,
    ${n('"latest_rating"')}: 2,
    ${n('"latest_category"')}: ${s('"shipping"')}
  },
  ${n('"predict"')}: ${s('"churned_in_3_months"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function demandPanel(): AitoPanelConfig {
  return {
    operation: "Demand Forecast",
    endpoints: ["_predict", "_relate", "_evaluate"],
    description:
      `Per-SKU <code style="color:var(--aito-teal);">_predict units_sold</code> ` +
      `from the <code style="color:var(--aito-teal);">monthly_sales</code> panel ` +
      `(SKU × month aggregates with denormalised pet_type / category / brand / ` +
      `season). Seasonality via parallel <code style="color:var(--aito-teal);">_relate</code> ` +
      `over (season, category). Honest accuracy via <code style="color:var(--aito-teal);">_evaluate</code>.`,
    query:
`${k('"predict"')}: {
  ${n('"from"')}: ${s('"monthly_sales"')},
  ${n('"where"')}: {
    ${n('"product_sku"')}: ${s('"SKU-PT-0001"')},
    ${n('"month"')}: ${s('"2026-05"')},
    ${n('"pet_type"')}: ${s('"dog"')},
    ${n('"category"')}: ${s('"dry-food"')},
    ${n('"season"')}: ${s('"spring"')}
  },
  ${n('"predict"')}: ${s('"units_sold"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function inventoryPanel(): AitoPanelConfig {
  return {
    operation: "Inventory",
    endpoints: ["_predict", "_search"],
    description:
      `Stock + lead-time arithmetic for every SKU, with Aito's ` +
      `<code style="color:var(--aito-teal);">_predict units_sold</code> ` +
      `surfacing next-month demand for the critical SKUs. Reorder workflow ` +
      `sorts by <strong>revenue at risk</strong> (forecast shortfall × retail) ` +
      `— the cash a stockout would cost.`,
    query:
`${k('"predict"')}: {
  ${n('"from"')}: ${s('"monthly_sales"')},
  ${n('"where"')}: {
    ${n('"product_sku"')}: ${s('"SKU-PT-0042"')},
    ${n('"month"')}: ${s('"2026-05"')},
    ${n('"category"')}: ${s('"dry-food"')},
    ${n('"season"')}: ${s('"spring"')}
  },
  ${n('"predict"')}: ${s('"units_sold"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function pricePanel(): AitoPanelConfig {
  return {
    operation: "Price",
    endpoints: ["_relate", "_search"],
    description:
      `Per-SKU fair-band stats from <code style="color:var(--aito-teal);">price_history</code> ` +
      `(mean ± 1.5σ over 12-17 observations) plus a sweet-spot ` +
      `<code style="color:var(--aito-teal);">_relate</code> over discount band ` +
      `↔ category — "promo-priced toys sell 2.4× more units than list-priced toys".`,
    query:
`${k('"relate"')}: {
  ${n('"from"')}: ${s('"price_history"')},
  ${n('"where"')}: {
    ${n('"discount_pct"')}: { ${n('"$gt"')}: 15.0 }
  },
  ${n('"relate"')}: ${s('"product_sku.category"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function evaluationPanel(): AitoPanelConfig {
  return {
    operation: "Evaluation",
    endpoints: ["_evaluate"],
    description:
      `Aito's <code style="color:var(--aito-teal);">_evaluate</code> holds out ` +
      `a test set, runs predictions, and reports accuracy + baseline accuracy ` +
      `+ per-case results. Honest failure cases (the return-risk model below) ` +
      `live here — Aito tells you when it doesn't know.`,
    query:
`${k('"evaluate"')}: {
  ${n('"from"')}: ${s('"order_lines"')},
  ${n('"where"')}: {
    ${n('"category"')}: { ${n('"$get"')}: ${s('"category"')} }
  },
  ${n('"predict"')}: ${s('"returned"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}
