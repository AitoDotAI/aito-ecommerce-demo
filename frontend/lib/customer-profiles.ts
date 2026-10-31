/** The Customers view's data (ADR 0053). */

export interface Segment {
  key?: string; value: string; customers: number; share: number; churn_rate?: number; avg_spend_eur?: number; thin?: boolean;
  revenue_eur?: number; revenue_share?: number;
  profit_eur?: number; profit_12m_eur?: number; profit_per_customer_eur?: number; profit_per_customer_ci?: [number, number] | null;
  margin?: number; profit_share?: number;
}

export interface ResponseCell {
  rows: number; order_rate: number | null; thin: boolean; lift_points: number | null; margin_points: number | null; clear: boolean | null;
  profit_eur: number | null; profit_lift_eur: number | null; profit_margin_eur: number | null; profit_clear: boolean | null;
}

export interface ResponseEntry {
  none: { rows: number; order_rate: number | null; profit_eur: number | null }; actions: Record<string, ResponseCell>;
}

export interface FeedbackRow {
  label: string; base: number; share: number; share_others: number | null; points: number | null; margin_points: number | null; clear: boolean | null;
}

export interface FeedbackEntry {
  customers: number; reviewers: number; reviews: number; mean_rating: number | null; nps_respondents: number; nps: number | null; rows: FeedbackRow[];
}

export interface FunnelCounts { impressions: number; clicks: number; carts: number; purchases: number }

export interface RankedQuintile { customers: number; lift: number; mean_share: number; segment_share: Record<string, number> }

export interface PreferenceRanking {
  label: string; customers: number; mean_share: number; curve: number[]; quintiles: RankedQuintile[];
  top_over_average: number; top_over_bottom: number | null;
}

export interface ProfilesSummary {
  release: string; simulated: boolean; stale: boolean; scope: "release" | "release-not-sandbox"; customers: number; profiled: number; not_profiled: number;
  profiled_revenue_eur: number; profiled_profit_eur: number; gross_margin: number; margin_cut: number;
  profit_distribution: { customers: number; median_eur: number; top_tenth_share: number; losing_money: number };
  overall: Segment; definitions: Record<string, string>;
  by_trait: Record<"offer" | "price" | "rating" | "margin" | "status" | "pets" | "diets", Segment[]>;
}

/** Everything the view says about the customers who meet every ticked condition (GET /api/customer-profiles/segment). */
export interface Trend {
  months: string[]; customers: number[]; orders: number[]; revenue_eur: number[]; profit_per_customer_eur: number[]; nps: (number | null)[]; churn_rate: (number | null)[];
  recent_vs_before: Record<KpiId, number | null>;
}

/** What the tree shows beside a condition: the figures the segment would have if it were ticked. */
export interface TreeFigures { customers: number; orders: number; revenue_eur: number; profit_per_customer_eur: number | null; nps: number | null; churn_rate: number | null }

export type KpiId = "customers" | "orders" | "revenue_eur" | "profit_per_customer_eur" | "nps" | "churn_rate";

export interface FeedbackPair { selected: FeedbackEntry; all: FeedbackEntry }

export interface SegmentView {
  key: string; conditions: string[]; customers: number; options: Record<string, TreeFigures>; stale: boolean; scope: "release" | "release-not-sandbox";
  too_small: boolean; min_customers?: number;
  segment?: Segment; funnel?: { selected: FunnelCounts; all: FunnelCounts };
  ranking?: Record<string, PreferenceRanking>;
  relations?: SelectionRelation[]; preferences?: Record<string, PreferenceGroup>;
  acquisition?: Record<"source" | "landing" | "landing_category", AcquisitionRow[]>;
  response?: ResponseEntry | null; feedback?: FeedbackPair; trend?: { selected: Trend; all: Trend };
}

export interface SelectionRelation {
  then: TraitRef; customers_with: number; share_with: number; share_without: number; points: number; margin_points: number; clear: boolean;
}

export interface CustomerProfile {
  customer_id: string; name?: string; profiled: boolean; lines?: number; offer: string; price: string; rating: string;
  profit_eur?: number; offer_share?: number; cheaper_share?: number; rating_gap?: number | null; pets?: string[]; diets?: string[];
}

export const TRAIT_TITLE: Record<string, string> = {
  all: "Everyone", offer: "Buys on offer", price: "Prices they pick", rating: "Ratings they pick", margin: "Margin of their baskets", status: "Customer status",
  pets: "Pets they buy for", diets: "Diets their pet's food is made for",
};

/** The topic tree: the groups in order, and the variables in each. */
export const TREE: { title: string; traits: (keyof ProfilesSummary["by_trait"])[] }[] = [
  { title: "How they shop", traits: ["offer", "price", "rating"] },
  { title: "Value to the shop", traits: ["margin", "status"] },
  { title: "Their pets", traits: ["pets", "diets"] },
];

/** A customer has one value of each of these; pets and diets can be ticked more than once. */
export const SINGLE_VALUED = ["offer", "price", "rating", "margin", "status"];

export const ACTION_TITLE: Record<string, string> = {
  email: "Email", ad: "Ad", discount: "Discount", voucher: "Voucher", apology: "Apology",
};

export interface TraitRef { trait: string; value: string }

export interface PreferenceRow {
  item: string; name?: string; buyers: number; share: number; share_others: number; points: number; margin_points: number; clear: boolean;
}

export interface PreferenceGroup {
  pet: string; customers: number; others: number;
  categories: PreferenceRow[]; brands: PreferenceRow[]; products: PreferenceRow[];
}

/** The ticked conditions as they sit in the URL ("offer:mostly,pets:dog"), and back. */
export function parseConditions(param: string): string[] {
  return param ? param.split(",").filter(Boolean) : [];
}

/** Tick or untick a condition. Ticking another value of a single-valued trait replaces the one before. */
export function toggle(conditions: string[], condition: string): string[] {
  if (conditions.includes(condition)) return conditions.filter((c) => c !== condition);
  const trait = condition.split(":")[0];
  return [...(SINGLE_VALUED.includes(trait) ? conditions.filter((c) => c.split(":")[0] !== trait) : conditions), condition];
}

export function describe(condition: string): string {
  const [trait, ...rest] = condition.split(":");
  return `${TRAIT_TITLE[trait]}: ${rest.join(":")}`;
}

export function definitionOf(summary: ProfilesSummary, condition: string): string {
  const trait = condition.split(":")[0];
  return summary.definitions[condition] ?? summary.definitions[`_${trait}`] ?? "";
}

export interface AcquisitionRow {
  value: string; customers: number; share: number; share_others?: number; points?: number; margin_points?: number; clear?: boolean;
  profit_per_customer_eur: number | null; profit_per_customer_ci: [number, number] | null; profit_per_customer_all_eur: number | null;
}

/** The words the acquisition dimensions go by in the view. */
export const ACQUISITION_TITLE: Record<string, string> = { source: "Channel", landing: "Landing page", landing_category: "Landing category" };
