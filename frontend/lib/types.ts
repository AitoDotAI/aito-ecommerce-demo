/* Shared TypeScript interfaces.
 *
 * Per-view DTOs (DashboardResponse, SmartSearchResponse, etc.) land
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
  }>;
  final_p: number | null;
}

/** Estimate-variant explanation from `src/why_processor.py`'s
 *  `process_estimate_why`. K-NN / regression-coefficient
 *  decomposition for `_estimate` queries (Demand / Inventory /
 *  Price). Each component's `value` is on the log scale Aito uses
 *  internally — the popover converts to %-lift for display. */
export interface WhyEstimatePayload {
  kind: "estimate";
  estimate: number | null;
  field_label: string;
  components: Array<{
    name: string;
    value: number;
    type: "regression" | "residual" | "mean" | string;
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

/* ─── Purchase Analytics (/api/purchase-analytics) ─── */

export interface AnalyticsMonthly {
  month: string;
  orders: number;
  revenue_eur: number;
}

export interface AnalyticsTopProduct {
  sku: string;
  name: string;
  pet_type: string;
  category: string;
  line_count: number;
}

export interface AnalyticsSegment {
  segment: string;
  label: string;
  customers: number;
  orders: number;
  revenue_eur: number;
  avg_basket_eur: number;
}

export interface AnalyticsCategoryMixEntry {
  pet_type: string;
  category: string;
  count: number;
  share_pct: number;
}

export interface AnalyticsCategoryMixRow {
  segment: string;
  label: string;
  top_categories: AnalyticsCategoryMixEntry[];
}

export interface AnalyticsResponse {
  monthly: AnalyticsMonthly[];
  top_products: AnalyticsTopProduct[];
  segments: AnalyticsSegment[];
  category_mix_by_segment: AnalyticsCategoryMixRow[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Pattern Explorer (/api/pattern-explorer) ─── */

export interface PatternEntry {
  label: string;
  token: string;
  lift: number;
  support: { f: number; f_on_condition: number };
  p_given: number;
  p_overall: number;
  band: "positive" | "neutral" | "protective";
}

export interface PatternResponse {
  anchor: { id: string; pet_type: string; category: string; display: string };
  patterns: PatternEntry[];
  available_anchors: Array<{ id: string; display: string }>;
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
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

/* ─── Bought Together (/api/bought-together) ─── */

export interface BoughtTogetherSkuSample {
  sku: string;
  name: string;
  brand: string;
  price_eur: number;
}

export interface BoughtTogetherCrossSell {
  label: string;
  token: string;
  lift: number;
  support: {
    f: number;
    f_on_condition: number;
  };
  sample_skus: BoughtTogetherSkuSample[];
}

export interface BoughtTogetherAnchor {
  id: string;
  pet_type: string;
  category: string;
  display: string;
  sample_skus: BoughtTogetherSkuSample[];
}

export interface BoughtTogetherResponse {
  anchor: BoughtTogetherAnchor;
  cross_sells: BoughtTogetherCrossSell[];
  available_anchors: Array<{ id: string; display: string }>;
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
  /** P(segment | product) from Aito's `$p`. Surfaced as a per-tile
   *  "0.91" score chip. */
  score: number;
}

export interface ForYouResponse {
  persona: {
    id: string;
    label: string;
    segment: string;
    pet_size: string | null;
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
    segment: string;
    pet_size: string | null;
  };
  baseline: SmartSearchHit[];
  predictive: SmartSearchHitWithDelta[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Dashboard (/api/dashboard) ─── */

export interface DashboardKpi {
  value: number;
  delta_label: string | null;
}

export interface DashboardPattern {
  label: string;
  lift: number;
  bar_pct: number;
}

export interface DashboardSegment {
  id: string;
  emoji: string;
  label: string;
  share_pct: number;
  avg_basket_eur: number;
  note: string;
  pill_text: string;
  pill_tone: "orange" | "blue" | "grey" | "purple" | "green" | "red" | "amber";
}

export interface DashboardInsight {
  headline: string;
  body: string;
}

export interface DashboardRecentOrder {
  order_id: string;
  customer_short: string;
  month: string;
  line_summary: string;
  total_eur: number;
}

export interface DashboardResponse {
  kpis: {
    products:       DashboardKpi;
    orders_12mo:    DashboardKpi;
    customers:      DashboardKpi;
    avg_basket_eur: DashboardKpi;
  };
  top_patterns: DashboardPattern[];
  segments: DashboardSegment[];
  insight: DashboardInsight;
  recent_orders: DashboardRecentOrder[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Feedback (/api/feedback) ─── */

export interface FeedbackPredictedField {
  field: string;
  label: string;
  predicted_value: string | boolean | null;
  confidence: number;
  alternatives: Array<{ value: string; confidence: number }>;
  why_factors: Array<{ field: string; value: string; lift: number }>;
  why_explanation: WhyExplanationPayload | null;
}

export interface FeedbackReviewSummary {
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
  actual_churn_within_90d: boolean;
}

export interface FeedbackResponse {
  review: FeedbackReviewSummary;
  fields: FeedbackPredictedField[];
  candidate_reviews: Array<{ review_id: string; rating: number; text_short: string }>;
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Churn (/api/churn) ─── */

export interface ChurnKpi {
  label: string;
  value: number;
  sub: string;
}

export interface ChurnAtRiskCustomer {
  customer_id: string;
  customer_short: string;
  segment: string;
  pet_size: string | null;
  region: string;
  tenure_months: number;
  visits: number;
  purchases: number;
  spent_eur: number;
  latest_rating: number | null;
  latest_sentiment: string | null;
  risk_score: number;
  confidence_band: "high" | "medium" | "low";
  why_explanation: WhyExplanationPayload | null;
}

export interface ChurnDriverRow {
  field: string;
  value: string;
  lift: number;
  support_f: number;
  p_churn: number;
  p_overall: number;
}

export interface ChurnEvalSummary {
  accuracy: number;
  base_accuracy: number;
  accuracy_gain_pp: number;
  n: number;
}

export interface ChurnResponse {
  kpis: ChurnKpi[];
  at_risk: ChurnAtRiskCustomer[];
  drivers: ChurnDriverRow[];
  evaluation: ChurnEvalSummary;
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Demand Forecast (/api/demand) ─── */

export interface DemandTopMover {
  sku: string;
  name: string;
  pet_type: string;
  category: string;
  avg_monthly_units: number;
  last_month_units: number;
  forecast_units: number;
  forecast_p: number;
  why_explanation: AnyWhyPayload | null;
}

export interface DemandSeasonRow {
  season: string;
  pet_type: string;
  category: string;
  lift: number;
  f_on_condition: number;
  p_on_condition: number;
  p_overall: number;
}

export interface DemandEvalSummary {
  accuracy: number;
  base_accuracy: number;
  accuracy_gain_pp: number;
  n: number;
}

export interface DemandResponse {
  forecast_month: string;
  top_movers: DemandTopMover[];
  seasonality: DemandSeasonRow[];
  evaluation: DemandEvalSummary;
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Inventory Intelligence (/api/inventory) ─── */

export interface InventoryKpi {
  label: string;
  value: number;
  sub: string;
}

export interface InventoryReorderRow {
  sku: string;
  name: string;
  pet_type: string;
  category: string;
  current_stock: number;
  reorder_point: number;
  days_of_supply: number;
  avg_monthly_units: number;
  forecast_units: number;
  suggested_reorder_qty: number;
  unit_cost_eur: number;
  revenue_at_risk_eur: number;
  supplier: string;
  lead_time_days: number;
  why_explanation: AnyWhyPayload | null;
}

export interface InventoryOverstockRow {
  sku: string;
  name: string;
  pet_type: string;
  category: string;
  current_stock: number;
  reorder_point: number;
  months_of_supply: number;
  tied_capital_eur: number;
  unit_cost_eur: number;
}

export interface InventoryResponse {
  kpis: InventoryKpi[];
  reorder_queue: InventoryReorderRow[];
  overstock: InventoryOverstockRow[];
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}

/* ─── Price Intelligence (/api/price) ─── */

export interface PriceFairBandRow {
  sku: string;
  name: string;
  pet_type: string;
  category: string;
  list_price_eur: number;
  mean_price_eur: number;
  min_price_eur: number;
  max_price_eur: number;
  std_dev_eur: number;
  observation_count: number;
  outlier: boolean;
  band_lower_eur: number;
  band_upper_eur: number;
}

export interface PriceSweetSpotRow {
  discount_band: "list" | "mild" | "promo";
  category: string;
  lift: number;
  f_on_condition: number;
  p_on_condition: number;
  p_overall: number;
}

export interface PriceResponse {
  fair_bands: PriceFairBandRow[];
  sweet_spots: PriceSweetSpotRow[];
  summary: {
    total_skus: number;
    observations: number;
    outlier_skus: number;
    promo_share_pct: number;
  };
  last_query: { endpoint: string; body: Record<string, unknown> };
  last_response_ms: number;
}
