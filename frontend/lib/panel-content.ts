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


export function overviewPanel(): AitoPanelConfig {
  const c = (t: string) => `<code style="color:var(--aito-teal);">${t}</code>`;
  return {
    operation: "Overview",
    endpoints: ["_search", "_batch", "_aggregate", "_relate"],
    description:
      `Paged ${c("_search")} over orders and order lines, with ${c("select")}, summed in the app: ` +
      `orders and revenue per month, and units per product. Household cards are one ${c("_batch")} ` +
      `of counts and an ${c("_aggregate")} per group. The Patterns headline is the strongest pair of ` +
      `Patterns' basket ${c("_relate")}s, with its interval; Supply and Retention read those views' ` +
      `own precomputed answers. The query below is the first page of orders.`,
    query: "",
    links: LEARN_MORE_LINKS,
  };
}


export function personalisedSearchPanel(): AitoPanelConfig {
  return {
    operation: "Personalised search",
    endpoints: ["_search"],
    description:
      `One <code style="color:var(--aito-teal);">_search</code> ranks the whole ` +
      `catalogue by <code style="color:var(--aito-teal);">$multiply</code>: the ` +
      `probability this customer buys the product (` +
      `<code style="color:var(--aito-teal);">$p</code>, learned from the impressions ` +
      `funnel with the customer as context) times how well its name matches the query (` +
      `<code style="color:var(--aito-teal);">$similarity</code>). No word filter, ` +
      `so natural phrasing and misspellings still find products. The Shop's search ` +
      `is a different, two-step query: <code>src/shop_search.py</code>.`,
    query:
`${k('"search"')}: {
  ${n('"from"')}: ${s('"impressions"')},
  ${n('"get"')}: ${s('"product_sku"')},
  ${n('"where"')}: { ${n('"context.customer"')}: ${s('"CUST-00001"')} },
  ${n('"orderBy"')}: { ${n('"$multiply"')}: [
    { ${n('"$p"')}: { ${n('"$context"')}: { ${n('"purchased"')}: ${s('true')} } } },
    { ${n('"$similarity"')}: { ${n('"name"')}: ${s('"food"')} }, ${n('"theta"')}: ${s('4.0')} }
  ] },
  ${n('"limit"')}: 10
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function recommendMinimalPanel(): AitoPanelConfig {
  return {
    operation: "Query patterns",
    endpoints: ["_recommend"],
    description:
      `<code style="color:var(--aito-teal);">_recommend</code> in its minimal form: rank ` +
      `<code>product_sku</code> over <code>impressions</code> towards the goal ` +
      `<code>{purchased: true}</code>, with only the customer as context. The Shop's ` +
      `"Picked for you" sends the production form: <code>src/shop_ranking.py</code>.`,
    query:
`${k('"from"')}: ${s('"impressions"')},
${k('"where"')}: { ${n('"context.customer"')}: ${s('"CUST-00001"')} },
${k('"recommend"')}: ${s('"product_sku"')},
${k('"goal"')}: { ${n('"purchased"')}: ${n('true')} },
${k('"limit"')}: ${n('12')}`,
    links: LEARN_MORE_LINKS,
  };
}


export function businessReordersPanel(): AitoPanelConfig {
  return {
    operation: "Business reorders",
    endpoints: ["_predict", "_search", "_relate"],
    description:
      `Real data: UCI Online Retail II, a UK giftware wholesaler's invoices, in its own env. ` +
      `One <code style="color:var(--aito-teal);">_predict</code> of <code>code</code> over ` +
      `<code>lines</code>, conditioned on the buyer through the <code>invoice</code> link, drafts ` +
      `the next order. Aito learned from invoices before 1 Sep 2011 only; what the buyer ordered ` +
      `next is checked against the draft outside Aito. Labels and prices come from a ` +
      `<code style="color:var(--aito-teal);">_search</code> on <code>products</code>, and Bought ` +
      `together is a <code style="color:var(--aito-teal);">_relate</code> over each invoice's codes.`,
    query:
`${k('"predict"')}: {
  ${n('"from"')}: ${s('"lines"')},
  ${n('"where"')}: { ${n('"invoice.customer_id"')}: ${s('"12357"')} },
  ${n('"predict"')}: ${s('"code"')},
  ${n('"limit"')}: 10,
  ${n('"select"')}: [${s('"$p"')}, ${s('"$value"')}]
}`,
    links: [
      ...LEARN_MORE_LINKS,
      { label: "Online Retail II (UCI)", url: "https://doi.org/10.24432/C5CG6D", kind: "external" },
    ],
  };
}


export function shopPanel(): AitoPanelConfig {
  return {
    operation: "Shop",
    endpoints: ["_recommend", "_predict", "_batch", "_relate", "_search"],
    description:
      `Be a shopper. One view per intent: "Buy again" and "Next for their kit" are ` +
      `<code style="color:var(--aito-teal);">_predict</code> over orders; "Picked for you" is one ` +
      `<code style="color:var(--aito-teal);">_recommend</code> with the household's declared pets, ` +
      `the month and the cart as context. The declared pets and diet are filters, not ` +
      `predictions. Anything from their last order is re-asked in one ` +
      `<code style="color:var(--aito-teal);">_batch</code> as "just bought", and falls. ` +
      `Each card's reasons are the lifts in its <code style="color:var(--aito-teal);">$why</code>. ` +
      `A search ranks the products its words name the same way. The query below is the one behind what is shown.`,
    query: "",
    links: LEARN_MORE_LINKS,
  };
}


export function productPanel(): AitoPanelConfig {
  const c = (t: string) => `<code style="color:var(--aito-teal);">${t}</code>`;
  return {
    operation: "Product",
    endpoints: ["_predict", "_estimate", "_relate", "_batch", "_search"],
    description:
      `One product, live. The discount what-if is ${c("_predict purchased")} on impressions with ` +
      `${c("product_state.discount_band")} set to each band; the price what-if and curve are ` +
      `${c("_estimate units_sold")} with the regression model at a chosen price. History is ` +
      `counts and rows in one ${c("_batch")}; for whom is ${c("_relate")} over the product's order ` +
      `lines, per declared customer field. The query below is the one behind what is shown.`,
    query: "",
    links: LEARN_MORE_LINKS,
  };
}


export function shopAnalyticsPanel(queriesSent?: number): AitoPanelConfig {
  const c = (t: string) => `<code style="color:var(--aito-teal);">${t}</code>`;
  return {
    operation: "Patterns",
    endpoints: ["_relate", "_search"],
    description:
      `Each section is ${c("_relate")}, sent in parallel: which values are over- or ` +
      `under-represented among purchases (or clicks), in a group's order lines, in baskets with a ` +
      `category (whose ${c("fs")} counts also give each rule's confidence both ways and its support), ` +
      `and in searches that convert. Two more ${c("_relate")}s on the customer column ` +
      `measure how clustered the rows are, which widens every interval. A lift is shown when its ` +
      `interval excludes 1 at 95 % for the whole section (Bonferroni) and it rests on 30 or more ` +
      `independent rows. ${c("_search")} checks which search words are always searched together. ` +
      `The query below is one of the ${queriesSent ?? "…"} sent.`,
    query: "",
    links: LEARN_MORE_LINKS,
  };
}


export function reviewsPanel(queriesSent?: number): AitoPanelConfig {
  const c = (t: string) => `<code style="color:var(--aito-teal);">${t}</code>`;
  return {
    operation: "Reviews",
    endpoints: ["_relate", "_search"],
    description:
      `Each section is ${c("_relate")}: which stars, review and reply facts are over- or under-represented ` +
      `among clicks, purchases, NPS detractors and churned customer-months. ${c("_relate")} cannot follow an ` +
      `order to its lines, so an NPS answer carries its order's first product as it was that month. ` +
      `The reply comparison counts customer-months with ${c("_search")}. A lift is shown when its interval ` +
      `excludes 1 for the whole section. The query below is one of the ${queriesSent ?? "…"} sent.`,
    query: "",
    links: LEARN_MORE_LINKS,
  };
}


export function acquisitionPanel(queriesSent?: number): AitoPanelConfig {
  const c = (t: string) => `<code style="color:var(--aito-teal);">${t}</code>`;
  return {
    operation: "Acquisition",
    endpoints: ["_search", "_predict", "_relate"],
    description:
      `Per source: ${c("_search")} counts give the sessions that end in a first order and the customers who ` +
      `became regular; ${c("_predict became_regular")} from the first source alone gives the expected stay with the ` +
      `source's lift in ${c("$why")}; ${c("_relate")} on the context gives where its visitors land, and on customers ` +
      `which first-basket words go with becoming regular. Rates carry a 95 % Wilson interval. ` +
      `The query below is one of the ${queriesSent ?? "…"} sent.`,
    query: "",
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


export function reviewTriagePanel(): AitoPanelConfig {
  return {
    operation: "Review triage",
    endpoints: ["_predict"],
    description:
      `Three parallel <code style="color:var(--aito-teal);">_predict</code> calls ` +
      `condition on both <code style="color:var(--aito-teal);">text</code> + ` +
      `<code style="color:var(--aito-teal);">rating</code> and return ` +
      `<strong>category</strong>, <strong>sentiment</strong> and ` +
      `<strong>assigned_to</strong> in one round-trip. The popover surfaces each ` +
      `feature's lift contribution.`,
    query:
`${k('"predict"')}: {
  ${n('"from"')}: ${s('"reviews"')},
  ${n('"where"')}: {
    ${n('"text"')}: ${s('"Package arrived late. The seal was broken."')},
    ${n('"rating"')}: 2
  },
  ${n('"predict"')}: ${s('"assigned_to"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function retentionPanel(): AitoPanelConfig {
  return {
    operation: "Retention",
    endpoints: ["_predict", "_relate", "_recommend", "_estimate", "_batch"],
    description:
      `Each active customer's latest order is scored with ` +
      `<code style="color:var(--aito-teal);">_predict churned_in_3_months</code>, ` +
      `batched. A nested <code style="color:var(--aito-teal);">from</code> sets what ` +
      `Aito learns from: months in which a customer ordered, up to the last month ` +
      `whose next three months are in the data. Drivers come from ` +
      `<code style="color:var(--aito-teal);">_relate</code> over churned customers; ` +
      `the offer from <code style="color:var(--aito-teal);">_recommend</code> over past ` +
      `win-back emails, a calibrated <code style="color:var(--aito-teal);">_predict responded</code> ` +
      `and an <code style="color:var(--aito-teal);">_estimate</code> of the order.`,
    query:
`${k('"predict"')}: {
  ${n('"from"')}: {
    ${n('"from"')}: ${s('"customer_months"')},
    ${n('"where"')}: {
      ${n('"month"')}: { ${n('"$lte"')}: ${s('"2026-01"')} },
      ${n('"purchases"')}: { ${n('"$gte"')}: 1 }
    }
  },
  ${n('"where"')}: {
    ${n('"pets"')}: ${s('"small_animal"')},
    ${n('"visits"')}: 4,
    ${n('"purchases"')}: 1
  },
  ${n('"predict"')}: ${s('"churned_in_3_months"')}
}`,
    links: LEARN_MORE_LINKS,
  };
}


export function supplyPanel(): AitoPanelConfig {
  return {
    operation: "Supply",
    endpoints: ["_estimate", "_search"],
    description:
      `Aito's <code style="color:var(--aito-teal);">_estimate units_sold</code> forecasts ` +
      `next month for every SKU the view lists, once per SKU. The reorder quantity, the ` +
      `revenue at risk and the tied capital are arithmetic on it. For the largest overstock, ` +
      `the same <code style="color:var(--aito-teal);">_estimate</code> with ` +
      `<code style="color:var(--aito-teal);">model: "regression"</code> at five prices ` +
      `finds the shallowest markdown that clears the excess. Price bands come from one ` +
      `<code style="color:var(--aito-teal);">_search</code> of realised prices.`,
    query:
`${k('"estimate"')}: {
  ${n('"from"')}: ${s('"monthly_sales"')},
  ${n('"where"')}: {
    ${n('"product_sku"')}: ${s('"SKU-PT-0206"')},
    ${n('"units_last_month"')}: 30,
    ${n('"category"')}: ${s('"accessories"')},
    ${n('"season"')}: ${s('"spring"')}
  },
  ${n('"estimate"')}: ${s('"units_sold"')}
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


export function shopkeeperPanel(): AitoPanelConfig {
  return {
    operation: "Shopkeeper",
    endpoints: ["_predict", "_estimate"],
    description:
      `The agent reads the same ranked actions Retention shows: a ` +
      `<code style="color:var(--aito-teal);">_predict purchased_30d</code> per customer and candidate action. ` +
      `The gate then judges each on three things the step shows: the lift over no action, how many past rows match ` +
      `the customer's exact situation, and the kind of action. The thresholds are the store's.`,
    query: `${k('"note"')}: ${s('"The agent adds no query of its own: see Retention for the _predict body."')}`,
    links: LEARN_MORE_LINKS,
  };
}
