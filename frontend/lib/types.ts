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
