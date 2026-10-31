/** The Customers view's data (ADR 0053). */

export interface Segment {
  key?: string; value: string; customers: number; share: number; churn_rate?: number; avg_spend_eur?: number; thin?: boolean;
  revenue_eur?: number; revenue_12m_eur?: number; revenue_share?: number;
  profit_eur?: number; profit_12m_eur?: number; profit_per_customer_eur?: number; margin?: number; profit_share?: number;
}

export interface ResponseCell {
  rows: number; order_rate: number | null; thin: boolean; lift_points: number | null; margin_points: number | null; clear: boolean | null;
  profit_eur: number | null; profit_lift_eur: number | null; profit_margin_eur: number | null; profit_clear: boolean | null;
}

export interface ResponseEntry {
  none: { rows: number; order_rate: number | null; profit_eur: number | null }; actions: Record<string, ResponseCell>;
}

export interface ProfilesSummary {
  release: string; simulated: boolean; stale: boolean; scope: "release" | "release-not-sandbox"; customers: number; profiled: number; not_profiled: number;
  profiled_revenue_eur: number; profiled_profit_eur: number; gross_margin: number;
  profit_distribution: { customers: number; median_eur: number; top_tenth_share: number; losing_money: number }; relations: Relation[]; preferences: Record<string, PreferenceGroup>;
  by_trait: Record<"offer" | "price" | "rating" | "pets" | "diets", Segment[]>;
  response: Record<string, ResponseEntry>;
}

export interface CustomerProfile {
  customer_id: string; name?: string; profiled: boolean; lines?: number; offer: string; price: string; rating: string;
  profit_eur?: number; offer_share?: number; cheaper_share?: number; rating_gap?: number | null; pets?: string[]; diets?: string[];
}

export const TRAIT_TITLE: Record<string, string> = {
  offer: "Buys on offer", price: "Prices they pick", rating: "Ratings they pick", pets: "Pets they buy for", diets: "Diets their pet's food is made for",
};

/** The trait groups in the order the list shows them. */
export const TRAITS = ["offer", "price", "rating", "pets", "diets"] as const;

export const ACTION_TITLE: Record<string, string> = {
  email: "Email", ad: "Ad", discount: "Discount", voucher: "Voucher", apology: "Apology",
};

export interface TraitRef { trait: string; value: string }

export interface Relation {
  if: TraitRef; then: TraitRef; customers_with: number; share_with: number; share_without: number;
  points: number; margin_points: number; clear: boolean;
}

export interface PreferenceRow {
  item: string; name?: string; buyers: number; share: number; share_others: number; points: number; margin_points: number; clear: boolean;
}

export interface PreferenceGroup {
  pet: string; customers: number; others: number;
  categories: PreferenceRow[]; brands: PreferenceRow[]; products: PreferenceRow[];
}
