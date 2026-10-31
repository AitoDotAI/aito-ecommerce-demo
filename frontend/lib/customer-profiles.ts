/** The Customers view's data (ADR 0053). */

export interface Segment {
  value: string; customers: number; share: number; churn_rate?: number; avg_spend_eur?: number; thin?: boolean;
}

export interface ResponseCell {
  rows: number; order_rate: number | null; thin: boolean; lift_points: number | null; margin_points: number | null; clear: boolean | null;
}

export interface ResponseRow {
  value: string; none: { rows: number; order_rate: number | null }; actions: Record<string, ResponseCell>;
}

export interface ProfilesSummary {
  release: string; simulated: boolean; stale: boolean; customers: number; profiled: number; not_profiled: number;
  by_trait: Record<"offer" | "price" | "rating" | "pets" | "diets", Segment[]>;
  response: Record<string, ResponseRow[]>;
}

export interface CustomerProfile {
  customer_id: string; name: string; profiled: boolean; lines: number; offer: string; price: string; rating: string;
  offer_share?: number; cheaper_share?: number; rating_gap?: number | null; pets: string[]; diets: string[];
}

export const TRAIT_TITLE: Record<string, string> = {
  offer: "Buys on offer", price: "Prices they pick", rating: "Ratings they pick", pets: "Pets they buy for", diets: "Diets their pet's food is made for",
};

export const FIELD_TITLE: Record<string, string> = {
  offer_buyer: "Buys on offer", recency_bucket: "Last order", email_history: "Earlier emails", tracking_consent: "Consented to tracking",
  spend_band: "Order size", open_issue: "Open issue",
};

export const ACTION_TITLE: Record<string, string> = {
  email: "Email", ad: "Ad", discount: "Discount", voucher: "Voucher", apology: "Apology",
};
