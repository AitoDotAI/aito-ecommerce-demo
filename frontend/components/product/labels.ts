/** Words for the Product view's values, shared by its sections. */

import { fmtEur } from "@/lib/api";

export const BAND_LABEL: Record<string, string> = {
  "none": "No discount",
  "10-15": "10–15 % off",
  "15-20": "15–20 % off",
  "20+": "20 % or more off",
};

export const monthLabel = (m: string) =>
  new Date(Number(m.slice(0, 4)), Number(m.slice(5)) - 1, 1).toLocaleString("en", { month: "long", year: "numeric" });

export const shortMonth = (m: string) =>
  new Date(Number(m.slice(0, 4)), Number(m.slice(5)) - 1, 1).toLocaleString("en", { month: "short", year: "2-digit" });

export const pct = (p: number, digits = 1) => `${(p * 100).toFixed(digits)} %`;

/** "dental-treats" → "dental treats", "small_animal" → "small animal". */
export const words = (s: string) => s.replace(/[-_]/g, " ");

/** Whole euros for a month of a big product, cents for the small ones the demo also has. */
export const money = (eur: number) => fmtEur(eur, Math.abs(eur) < 100 ? 2 : 0);
