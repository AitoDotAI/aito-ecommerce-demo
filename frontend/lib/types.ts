/* Shared TypeScript interfaces.
 *
 * Per-view DTOs (OverviewResponse, SmartSearchResponse, etc.) land
 * here as their views are built. For the scaffold step we only need
 * the cross-demo invariants — the AitoPanel contract and the
 * `WhyExplanation` shape used by `WhyTooltip` / `PredictionBadge`. */

/** Aito side panel — content contract.
 *
 * Each view exports one `AitoPanelConfig` from `lib/panel-content.ts`.
 * The panel renders endpoint pills, the actual JSON body that the
 * page just sent to Aito, and a one-paragraph "how it works"
 * explanation plus learn-more links.
 *
 * Every query in `query` MUST be runnable against the live PetNord
 * data — no aspirational queries (CLAUDE.md prime directive).
 */
export interface AitoPanelConfig {
  /** Single endpoint badge displayed in the header (e.g. "_predict"). */
  operation: string;
  /** 3-4 small KPIs shown above the body block. */
  stats?: Array<{ label: string; value: string }>;
  /** HTML-allowed prose explaining what the page is doing with Aito. */
  description: string;
  /** HTML-allowed query block — typically a colourised JSON body. */
  query: string;
  /** Learn-more / source links. `kind` controls the leading icon. */
  links?: Array<{ label: string; url: string; kind?: "doc" | "github" | "external" }>;
  /** Aito endpoints used on this page — rendered as purple-tinted pills. */
  endpoints?: string[];
}

/** Per-pattern lift extracted from Aito `$why.factors`. */
export interface WhyLift {
  lift: number;
  proposition_str: string;
  highlights: Array<{
    field: string;
    raw_field: string;
    html: string;
  }>;
}

/** Processed explanation payload for one prediction. Computed
 *  server-side from the raw `$why` response. */
export interface WhyExplanation {
  base_p: number;
  lifts: WhyLift[];
  final_p: number;
  normalizer: number | null;
  context_fields: string[];
}

/** Flattened `$why` decomposition produced by `src/why_processor.py`.
 *  Drives the `WhyPopover` component for `_predict` results. The
 *  sibling `WhyEstimatePayload` (below) covers `_estimate` results
 *  which have a different shape. */
export interface WhyExplanationPayload {
  base_p: number;
  predicted_value: string;
  lifts: Array<{
    lift: number;
    propositions: Array<{ field: string; value: string; negate?: boolean }>;
    /** Optional per-factor highlight from Aito. Present when the
     *  factor matched on a Text-typed column; `marked_text` is the
     *  full source string with `«…»` sentinels around the matched
     *  tokens. Frontend splits on the sentinels — never raw HTML. */
    highlight?: { field: string; marked_text: string } | null;
    /** On a group, or on the Shop card's product term (src/shop_why.py): the parts it is made of. */
    joint_lift?: number;
    members?: Array<{
      lift: number;
      propositions: Array<{ field: string; value: string; negate?: boolean }>;
      highlight?: { field: string; marked_text: string } | null;
    }>;
    /** A sentence naming a term that has no conditions of its own. */
    label?: string;
    /** Names a fold-out the page can supply under this term. */
    detail?: string;
  }>;
  final_p: number | null;
}

/** Estimate-variant explanation from `src/estimate_why.py`'s
 *  `explain_estimate`: a k-NN `_estimate` (Demand, Inventory) split into
 *  a base, one contribution per field, the similar past months and any
 *  gap to Aito's estimate. In form "add" each `effect` is units added; in
 *  "multiply" a multiplier; both chain from `base` to `estimate`. Form
 *  "raw" is Aito's terms unconverted, when the split doesn't hold. A
 *  payload without `form` is a snapshot saved before this format. */
export interface WhyEstimatePayload {
  kind: "estimate";
  estimate: number | null;
  field_label: string;
  form?: "add" | "multiply" | "raw";
  base?: number | null;
  neighbours?: number;
  components: Array<{
    type: "field" | "neighbours" | "unexplained" | "raw" | string;
    label?: string;
    effect?: number;
  }>;
}

/** Either-shape why payload — services return one or the other. */
export type AnyWhyPayload = WhyExplanationPayload | WhyEstimatePayload;

/** Legacy shape kept for backwards compatibility — older endpoints
 *  still return this. New code should prefer `WhyExplanation`. */
export interface WhyFactor {
  field: string;
  value: string;
  lift: number;
}

export interface Alternative {
  value: string;
  confidence: number;
  why?: WhyExplanation | WhyFactor[];
}

/** Health endpoint response. */
export interface HealthResponse {
  status: "ok";
  aito_connected: boolean;
  aito_url?: string | null;
}

/* ─── Evaluation (/api/evaluation) ─── */

export interface EvalModelResult {
  id: string;
  label: string;
  table: string;
  predict: string;
  features: string[];
  accuracy: number;
  base_accuracy: number;
  accuracy_gain: number;
  n: number;
  threshold_pp: number;
  verdict: "pass" | "fail";
  last_query: { endpoint: string; body: Record<string, unknown> };
  error: string | null;
}

export interface EvalResponse {
  models: EvalModelResult[];
  last_run: string;
  total_response_ms: number;
}

/* ─── Product Filling (/api/product-filling) ─── */

export interface FillingFieldOut {
  field: string;
  label: string;
  predicted_value: string | number | null;
  confidence: number;
  alternatives: Array<{ value: string; confidence: number }>;
  why_factors: Array<{ field: string; value: string; lift: number }>;
  why_explanation: WhyExplanationPayload | null;
  hidden_for_demo: boolean;
}

export interface FillingResponse {
  product: {
    sku: string;
    name: string;
    brand: string;
    pet_type: string;
    category: string;
    weight_kg: number | null;
    dietary: string | null;
    tax_class: string | null;
    price_eur: number;
  };
  fields: FillingFieldOut[];
  candidate_skus: Array<{ sku: string; name: string }>;
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── For You (/api/for-you) ─── */

export interface ForYouTile {
  sku: string;
  name: string;
  brand: string;
  pet_type: string;
  category: string;
  price_eur: number;
  rank: number;
  /** P(purchased | this customer) from Aito's `$p`. Surfaced as a
   *  per-tile "0.91" score chip. */
  score: number;
}

export interface ForYouResponse {
  persona: {
    id: string;
    label: string;
    customer_id: string;
  };
  tiles: ForYouTile[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Smart Search (/api/smart-search) ─── */

export interface SmartSearchHit {
  sku: string;
  name: string;
  brand: string;
  pet_type: string;
  category: string;
  price_eur: number;
  rank: number;
}

export interface SmartSearchHitWithDelta extends SmartSearchHit {
  /** Rank delta vs. the baseline column. Negative = moved up.
   *  null when this product wasn't in the baseline top-N at all
   *  (combined with `new_entry: true` for the gold ★ chip). */
  delta_rank: number | null;
  new_entry: boolean;
}

export interface SmartSearchResponse {
  query: string;
  customer: {
    id: string;
    label: string;
    customer_id: string;
  };
  baseline: SmartSearchHit[];
  predictive: SmartSearchHitWithDelta[];
  // false: no product name contains a query word, so the predictive
  // column is purchase probability alone — the page says so.
  text_matched: boolean;
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Overview (/api/overview, ADR 0041) ─── */

export interface OverviewKpis {
  first_month: string;          // the last 12 months: first_month … last_month
  last_month: string;
  orders: number;
  orders_before: number;        // the 12 months before
  months_before: number;        // how many of those 12 the data holds
  revenue_eur: number;
  revenue_before_eur: number;
  avg_basket_eur: number;
  customers_ordering: number;
  customers: number;
  products: number;
}

export interface OverviewMonth {
  month: string;
  orders: number;
  revenue_eur: number;
}

export interface OverviewTopProduct {
  sku: string;
  name: string;
  pet_type: string;
  category: string;
  units: number;                // in the last 12 months
}

export interface OverviewHousehold {
  id: string;
  emoji: string;
  label: string;
  customers: number;
  share_pct: number;
  avg_basket_eur: number;
  pill_text: string | null;
  pill_tone: string | null;
}

/** One owner view's headline, a link (src/overview_headlines.py). */
export interface OverviewHeadline {
  view: string;
  href: string;
  headline: string;
  detail: string;
}

export interface OverviewResponse {
  kpis: OverviewKpis;
  monthly: OverviewMonth[];
  top_products: OverviewTopProduct[];
  households: OverviewHousehold[];
  headlines: OverviewHeadline[];
  last_query: { endpoint: string; body: Record<string, unknown> };
}

/* ─── Review triage (/api/review-triage) ─── */

export interface ReviewTriageField {
  field: string;
  label: string;
  predicted_value: string | boolean | null;
  confidence: number;
  alternatives: Array<{ value: string; confidence: number }>;
  why_factors: Array<{ field: string; value: string; lift: number }>;
  why_explanation: WhyExplanationPayload | null;
}

export interface ReviewTriageReview {
  review_id: string;
  customer_id: string;
  customer_short: string;
  product_sku: string;
  product_name: string;
  rating: number;
  text: string;
  created_at: string;
  actual_category: string;
  actual_sentiment: string;
  actual_assigned_to: string;
}

export interface ReviewTriageResponse {
  review: ReviewTriageReview;
  fields: ReviewTriageField[];
  candidate_reviews: Array<{ review_id: string; rating: number; text_short: string }>;
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Retention (/api/retention) ─── */

export interface WinbackOffer {
  sku: string;
  name: string;
  category: string;              // "small_animal/dry-food"
  price_eur: number;
  response_p: number;            // calibrated `_predict responded`
  order_value_eur: number;       // expected order if they respond
  expected_return_eur: number;   // response_p × order value − email cost
}

export interface AtRiskRow {
  customer_id: string;
  name: string;
  pets: string;                  // declared (ADR 0033), else read from their orders
  pets_declared: boolean;
  dog_size: string | null;
  region: string;
  tenure_months: number;
  last_order_month: string;
  latest_rating: number | null;
  risk: "likely" | "very likely";
  risk_p: number;                // for the $why popover; not shown as a rate
  spend_12m_eur: number;
  why_explanation: WhyExplanationPayload | null;
  offer: WinbackOffer | null;    // null: no past email sent a product for their pets
}

export interface ChurnDriverRow {
  field: string;
  value: string;
  lift: number;                // churn_rate / churn_rate_overall
  customers: number;           // customers with this profile
  churners: number;            // of whom churned
  churn_rate: number;
  churn_rate_overall: number;
}

export interface RetentionResponse {
  as_of_month: string;
  /** The last month whose three months of follow-up are in the data. */
  learned_until: string;
  decision: {
    customers: number;
    spend_12m_eur: number;
    offers: number;
    offers_expected_return_eur: number;
    email_cost_eur: number;
  };
  counts: { active: number; likely_to_leave: number; churned: number };
  at_risk: AtRiskRow[];
  drivers: ChurnDriverRow[];
  /** Profile fields related to churn whose every value stayed near lift 1. */
  driver_fields_without_effect: string[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Supply (/api/supply) ─── */

export interface PriceBand {
  list_price_eur: number;
  mean_price_eur: number;
  band_low_eur: number;
  band_high_eur: number;
  observations: number;
  outlier: boolean;
}

export interface MarkdownPoint {
  discount_pct: number;
  price_eur: number;
  monthly_units: number;
  weeks_to_clear: number | null;   // null: an estimate of 0 units never clears
}

export interface MarkdownProposal {
  action: "hold" | "markdown" | "wont_clear";
  discount_pct: number;
  price_eur: number;
  weeks_to_clear: number | null;
  units_cleared: number;
  extra_units_vs_full_price: number;
  capital_freed_eur: number;
  margin_given_up_eur: number;
  curve: MarkdownPoint[];
}

export interface SupplyReorderRow {
  sku: string;
  name: string;
  category: string;
  supplier: string;
  lead_time_days: number;
  current_stock: number;
  reorder_point: number;
  forecast_units: number | null;
  order_qty: number;
  order_cost_eur: number;
  revenue_at_risk_eur: number;
  why_explanation: AnyWhyPayload | null;
  price: PriceBand | null;
}

export interface SupplyOverstockRow {
  sku: string;
  name: string;
  category: string;
  current_stock: number;
  reorder_point: number;
  excess_units: number;
  unit_cost_eur: number;
  tied_capital_eur: number;
  price: PriceBand | null;
  markdown: MarkdownProposal;
}

export interface SupplyMoverRow {
  sku: string;
  name: string;
  category: string;
  avg_monthly_units: number;
  last_month_units: number;
  forecast_units: number;
  current_stock: number;
  why_explanation: AnyWhyPayload | null;
}

export interface SupplyPriceOutlier {
  sku: string;
  name: string;
  category: string;
  price: PriceBand;
  above_band_pct: number;
}

export interface SupplyResponse {
  forecast_month: string;
  band_counts: { critical: number; low: number; ok: number; overstock: number };
  reorder: { skus: number; units: number; order_cost_eur: number; revenue_at_risk_eur: number };
  overstock_decision: {
    skus: number;
    tied_capital_eur: number;
    scored: number;
    hold: number;
    markdown: number;
    wont_clear: number;
    markdown_units_cleared: number;
    markdown_capital_freed_eur: number;
    markdown_margin_given_up_eur: number;
  };
  reorder_queue: SupplyReorderRow[];
  overstock: SupplyOverstockRow[];
  top_movers: SupplyMoverRow[];
  price_outliers: SupplyPriceOutlier[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Price curve (/api/product/price-curve?sku=…, ADR 0029) ─── */

export interface PriceHistoricalPoint {
  month: string;
  price_eur: number;
  units_sold: number;
  revenue_eur: number;
  profit_eur: number;
}

export interface PriceCurvePoint {
  price_eur: number;
  units_sold: number;
  profit_eur: number;
  adjustment_pct: number;
}

export interface PriceCurve {
  sku: string;
  name: string;
  list_price_eur: number;
  unit_cost_eur: number;
  mean_price_eur: number;
  historical: PriceHistoricalPoint[];
  curve: PriceCurvePoint[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Price what-if (/api/product/price-what-if, ADR 0029) ─── */

export interface PriceWhatIfFactor {
  field: string;        // the `where` field, or "other" / "residual"
  label: string;        // "Price €4.68", "Sold 23 last month", ...
  effect: number;       // a multiplier (form "multiply") or units added (form "add")
}

export interface PriceWhatIf {
  sku: string;
  name: string;
  price_eur: number;
  cost_eur: number;
  units: number;
  below_zero: boolean;  // a linear estimate under 0, shown as 0 units
  revenue_eur: number;
  profit_eur: number;
  form: "multiply" | "add";   // how the factors combine onto base_units
  base_units: number;
  factors: PriceWhatIfFactor[];
  last_query: { endpoint: string; body: Record<string, unknown> };
}

/* ─── Discount what-if (part of /api/product, ADR 0032) ─── */

export interface DiscountBandEstimate {
  band: "none" | "10-15" | "15-20" | "20+";
  p_purchase: number;          // Aito's $p that the product is bought when shown
  vs_no_discount: number;      // p_purchase / p_purchase at "none"
  band_lift: number | null;    // the band's lift in $why; null when Aito leaves it out
  product_lift: number | null;
  base_p: number;              // purchase rate of all impressions
  normaliser: number;          // Aito's normalisers multiplied (exclusiveness, calibration)
  calibrated: boolean;         // $why holds a `calibration` (rowCap) factor
  shown: number;               // this product's impressions at the band
  purchased: number;
  current: boolean;            // the product's band in the month asked about
}

export interface DiscountWhatIf {
  sku: string;
  name: string;
  current_band: string;
  month: string;
  bands: DiscountBandEstimate[];
  last_query: { endpoint: string; body: Record<string, unknown> };
}

/* ─── Product (/api/product?sku=&month=, ADR 0041) ─── */

export type DiscountBand = DiscountBandEstimate["band"];

export interface ProductMonth {
  month: string;
  units_sold: number;
  price_eur: number;
  list_price_eur: number;
  discount_band: DiscountBand;
  rating_band: string;      // "unrated" | "1-2" | "3" | "4" | "5"
  age: "new" | "established";
  rival_launched: boolean;  // a rival product launched recently
  price_change: "none" | "rise";
  reviews: number;          // reviews written that month
}

export interface ProductHistory {
  funnel: Array<{ step: "impressions" | "clicked" | "added_to_cart" | "purchased"; count: number }>;
  surfaces: Array<{ surface: string; impressions: number; purchased: number }>;
  months: ProductMonth[];
  ratings: Record<string, number>;      // "1".."5"
  sentiments: Record<string, number>;   // "positive" | "neutral" | "negative"
}

export interface ProductBuyerRow {
  field: string;          // "order_id.customer_id.pets", ...
  value: string;
  lift: number;           // share among this product's lines / among all lines
  lines: number;          // this product's order lines with this profile
  lines_total: number;    // this product's order lines
}

export interface BandMargin {
  band: DiscountBand;
  price_eur: number;            // list price less the band's typical discount
  p_purchase: number;           // Aito's estimate, bought when shown
  margin_per_100_eur: number;   // 100 × p × (price − cost)
}

export interface OfferDecision {
  action: "keep" | "offer" | "change" | "end_offer";
  current_band: DiscountBand;
  best_band: DiscountBand;
  current: BandMargin;
  best: BandMargin;
  breakeven_ratio: number | null;   // sales needed at the best band vs list price
  expected_ratio: number;           // Aito's p at the best band / at no discount
  margins: BandMargin[];
}

export interface ProductCandidate {
  sku: string;
  name: string;
  brand: string;
  category: string;
  pet_type: string;
}

export interface ProductView {
  product: { sku: string; name: string; brand: string; pet_type: string; category: string;
             price_eur: number; unit_cost_eur: number };
  month: string;
  forecast_month: string;
  state: ProductMonth;
  decision: OfferDecision;
  discount: DiscountWhatIf;
  price_now: PriceWhatIf;
  price_best: PriceWhatIf | null;
  history: ProductHistory;
  buyers: ProductBuyerRow[];
  shopper: { key: string; name: string; matches: string[] } | null;
  basket_category: { token: string; label: string };
  candidates: ProductCandidate[];
  last_query: { endpoint: string; body: Record<string, unknown> };
}


/* ─── Shop (/api/shop/*, ADR 0031) ─── */

export interface ShopShopper {
  key: string;            // URL value: /shop/?shopper=paivi
  customer_id: string;
  name: string;
  emoji: string;
  story: string;
}

export interface ShopProduct {
  sku: string;
  name: string;
  brand: string;
  pet_type: string;
  category: string;
  price_eur: number;
}

export interface ShopReason {
  label: string;   // "Goes with your cart", "Sells in April", "Fits your pets"
  lift: number;    // how much it multiplies this product's odds of a purchase
}

export interface ShopItem extends ShopProduct {
  p: number;                   // P(purchased) for this shopper, now
  reasons: ShopReason[];       // Aito's: what lifts this product for this shopper
  why_explanation: WhyExplanationPayload | null;   // the `$why` chain behind p; null once re-asked (just bought)
  features: Array<{ field: string; tokens: string[] }>;  // the tokens behind "this one's features" (src/shop_features.py)
  avg_rating: number | null;   // facts, shown beside the reasons, not as reasons
  offer_pct: number | null;
  keeps_rule: boolean;
  p_if_new: number | null;     // bought last order: its P before Aito was told so
  measured_rank: number | null;          // sandbox: its rank by Aito's $p, before re-scoring
  adjustment: ScoreAdjustment | null;    // sandbox: set when its 2026-05 state re-scored it
  same_name_skus: string[];    // other SKUs of the same name this card stands for (src/same_name.py)
}

/** Why a re-scored card's score differs from Aito's $p (ADR 0043, src/shop_rescore.py). */
export interface ScoreAdjustment {
  aito_p: number;
  offer_band: string;
  offer_factor: number;        // lift(offer band) / lift(no offer), shop-wide
  rating_band: string;
  rating_band_before: string;
  rating_factor: number;       // lift(stars) / lift(April's stars), shop-wide
  score: number;               // aito_p × offer_factor × rating_factor
}

/** `/api/sandbox` (ADR 0043). */
export interface SandboxStatus {
  configured: boolean;
  can_create?: boolean;
  month?: string;
  max_live?: number;
  max_age_hours?: number;
  sandbox?: { env: string; expires_at: string; starts_from: string } | null;
}

/** A product's state row, as `product_states` holds it. */
export interface ProductStateRow {
  product_state_id: string;
  product_sku: string;
  month: string;
  price_eur: number;
  list_price_eur: number;
  discount_pct: number;
  on_offer: boolean;
  discount_band: string;
  rating_band: string;
}

/** `/api/levers/state`. */
export interface LeverStates { april: ProductStateRow; next: ProductStateRow | null; next_month: string }

/** `/api/levers/offer` and `/api/levers/review`: the row as read back. */
export interface LeverResult {
  sku: string;
  lever: "offer" | "review";
  state: ProductStateRow;
  rating_band_before: string;
  rating_band_changed: boolean;
  reviews: number;
  avg_rating: number | null;
  review: { review_id: string; rating: number; text: string } | null;
}

export interface ShopSearch {
  query: string;
  text_matched: boolean;       // false: no product name holds any query word
  items: ShopItem[];
  last_query: { endpoint: string; body: Record<string, unknown> };
}

export interface ShopGrid {
  shopper: ShopShopper;
  month: string;
  rule: string | null;          // the household's diet rule, applied as a filter
  cart: ShopProduct[];
  items: ShopItem[];
  last_order_skus: string[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  rescored: boolean;            // sandbox, 2026-05: re-scored by the levers' states (ADR 0043)
  identity: boolean;            // also conditioned on the customer themselves (an experiment)
  trust: boolean;               // ...and not narrowed to the household's pets
  recent: boolean;              // the last order's items are in the context as if in the cart
}

export interface ShopBasketPair {
  sku: string;
  name: string;
  lift: number;
  together: number;        // orders holding both
  orders_with_it: number;  // orders holding the drawer's product
  same_name_skus: string[];
}

export interface ShopProductDrawer {
  product: ShopProduct & { avg_rating: number | null; dietary: string | null; tags: string };
  offer_pct: number | null;    // this month's offer, from product_states
  alternatives: ShopItem[];    // the same kind of product, ranked for this shopper
  same_basket: ShopBasketPair[];
  your_orders: string[];   // months of this shopper's orders that held it
  last_query: { endpoint: string; body: Record<string, unknown> };
}

export interface ShopSuggestion {
  sku: string;
  name: string;
  p: number;
  same_name_skus: string[];
}

export interface ShopSuggestions {
  usual: ShopSuggestion[];
  next_for_pet: ShopSuggestion[];
  owned: Record<string, string[]>;   // kit owned per pet: {"small_animal": ["cage", …]}
  no_history: boolean;
  queries: Array<{ endpoint: string; body: Record<string, unknown> }>;
}

/* ─── Shop analytics (/api/shop-analytics/*) ─── */

/** One `_relate` lift whose interval excludes 1 (src/lift_rows.py). */
export interface ShopLiftRow {
  field: string;            // "product_sku.rating_band"; for a basket pair, the first category
  value: string;            // "1-2"; a Boolean reads "true" / "false"
  lift: number;
  interval_low: number;     // family-wise, widened for clustering by customer
  interval_high: number;
  rows_with_value: number;  // the condition's rows with the value
  condition_rows: number;   // the condition's rows, e.g. all purchases
}

export interface ShopSignificance {
  tested: number;           // lifts with ≥ 30 independent rows
  z: number;                // Bonferroni z for `tested` tests
  family_confidence: number;
}

export interface ShopClustering {
  customers: number;
  rows_per_customer: number;
  intra_customer_correlation: number;
  design_effect: number;
}

interface ShopSectionBase {
  significance: ShopSignificance;
  queries_sent: number;
  example_query: { endpoint: string; body: Record<string, unknown> };
}

export interface ShopLiftSection extends ShopSectionBase {
  selected: string;         // "purchased" / "clicked", or "summer", "dog_owner", "grain-free"
  options: Array<{ id: string; label: string; group: string }>;
  rows: ShopLiftRow[];
  fields_without_clear_effect: string[];
  clustering: ShopClustering;
}

/** A basket pair as a rule with a direction (src/basket_pairs.py). */
export interface ShopAnalyticsPair {
  first: string;            // "Dog dry-food", the anchor mined
  second: string;           // "Dog dental-treats"
  first_id: string;         // "dog_dryfood"
  second_id: string;
  lift: number;
  interval_low: number;
  interval_high: number;
  orders_with_both: number;
  orders_with_first: number;
  orders_with_second: number;
  orders: number;
  confidence: number;          // first → second
  reverse_confidence: number;  // second → first
  support: number;             // share of all orders holding both
}

export interface ShopBasketSection extends ShopSectionBase {
  pairs: ShopAnalyticsPair[];
  anchors: Array<{ id: string; label: string }>;   // the anchor filter
  design_effects: Record<string, number>;   // per anchor category
}

export interface ShopSearchWordRow {
  word: string;             // a word, or a phrase always searched together
  lift: number;             // conversion with the word / conversion of all searches
  interval_low: number;
  interval_high: number;
  purchases: number;
  impressions: number;
}

export interface ShopSearchWordSection extends ShopSectionBase {
  rows: ShopSearchWordRow[];
  never_bought: Array<{ word: string; impressions: number; expected_purchases: number }>;
  words: number;
  search_impressions: number;
  search_purchases: number;
  clustering: ShopClustering;
}


// ── Business reorders, UCI Online Retail II (ADR 0034) ──────────────

export interface UciBuyer {
  customer_id: string;
  prior_invoices: number;
  group: string;              // "1-2 earlier orders" | "regular buyer"
  next_order_date: string;
}

export interface UciDraftLine {
  code: string;
  description: string;
  probability: number;        // Aito's $p
  last_price_gbp: number;
  ordered_next: boolean;      // in the buyer's next order, which Aito never saw
}

export interface UciDraftOrder {
  customer_id: string;
  prior_invoices: number;
  lines: UciDraftLine[];
  draft_value_gbp: number;    // last prices, one of each
  next_order_date: string | null;
  next_order_size: number;
  top_suggestion_ordered: boolean;
  query: Record<string, unknown>;
}

export interface UciBoughtWith {
  code: string;
  description: string;
  lift: number;
  shared_invoices: number;
  invoices_with_code: number;
}

export interface UciBoughtTogether {
  product: { code: string; description: string; last_price_gbp: number };
  invoices_with_product: number;
  bought_with: UciBoughtWith[];
  query: Record<string, unknown>;
}


/* ─── Reviews (/api/reviews/*) ─── */

export interface ReviewsReplyEffect {
  replied_months: number;
  replied_churned: number;
  unreplied_months: number;
  unreplied_churned: number;
  risk_ratio: number;
  interval_low: number;
  interval_high: number;
  verdict: "fewer leave" | "more leave" | "a tie";
}


/* ─── Acquisition (/api/acquisition) ─── */

export interface AcquisitionRate { successes: number; total: number; low: number; high: number }

export interface AcquisitionSource {
  source: string;
  sessions: number;
  conversion: AcquisitionRate;
  labelled_customers: number;
  regular: AcquisitionRate;
  predicted_regular: number;
  source_lift: number;
  landing: { category: string; lift: number }[];
}

export interface AcquisitionSection {
  sources: AcquisitionSource[];
  regular_basket: ShopLiftRow[];
  queries_sent: number;
  example_query: { from: string; where: Record<string, unknown>; relate: string; limit: number };
}

/** `/api/ask` (ADR 0042): GET says whether Ask is on, POST answers a question with the lever tools. */
export interface AskStatus { enabled: boolean; model: string | null }
export interface AskToolCall { name: string; input: Record<string, unknown>; ms: number; error: string | null }
export interface AskAnswer { answer: string; tool_calls: AskToolCall[]; model: string; input_tokens: number; output_tokens: number }

/* ─── Product KPIs by properties (/api/product/kpi, ADR 0048) ─── */

export type KpiName = "clicked" | "purchased";

export interface KpiFactor {
  fields: string[];     // short property names; several when Aito gave one lift for a correlated group
  values: Array<string | boolean>;
  lift: number;
}

export interface KpiEstimate {
  kpi: KpiName;
  p: number;
  base_p: number;
  normaliser: number;
  factors: KpiFactor[];
  similar_shown: number;
  similar_hits: number;
  product_shown: number;
  product_hits: number;
}

/** The properties the owner can change, by the name the API takes them under. */
export interface KpiProperties {
  brand: string; category: string; pet_type: string;
  discount_band: string; rating_band: string; label: string; age: string; stock: string; rival_launched: boolean;
}

export interface ProductKpis {
  sku: string;
  month: string;
  properties: KpiProperties;
  changed: string[];
  estimates: Record<KpiName, KpiEstimate>;
  last_query: { endpoint: string; body: Record<string, unknown> };
}
