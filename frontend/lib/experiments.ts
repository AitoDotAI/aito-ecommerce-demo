/** Types and wording for the Experiments page (ADR 0064), over `/api/experiments` (`data/evidence/experiments.json`). */

export type Kind = "offer" | "title" | "image";
export type Status = "draft" | "running" | "decided";
export type ArmVerdict = "second arm better" | "control better" | "no clear difference";
export type PersonVerdict = "choose per person" | "small gain" | "keep the plain winner";

export interface Arm {
  arm: string; is_control: boolean; price_eur: number; margin_eur: number; title: string; image: string;
  showings: number; purchases: number; rate: number; profit_per_showing: number;
}
export interface Experiment {
  experiment_id: string; product_sku: string; product: string; kind: Kind; hypothesis: string; status: Status;
  started_month: string | null; decided_month: string | null; decided_arm: string | null; allocation: number; explore_floor: number; signal: string;
  arms: [Arm, Arm]; difference: { delta: number; interval: [number, number] } | null; verdict: ArmVerdict | null;
}
/** One level of the shop's signal: how many showings of each arm, their purchase rates, and the second arm's lift. */
export type SignalLevel = { signal: string; lift: number | null } & Record<string, unknown>;
export interface PersonalChoice {
  signal: string; levels: SignalLevel[]; experiments: string[]; held_out_month: string; pairs: number;
  gain_percent: number; interval_percent: [number, number]; ceiling_gain_percent: number; share_of_gap: number | null; verdict: PersonVerdict;
  profit_per_showing: { control: number; winner: number; personal: number; oracle: number };
}
export interface ExperimentsData { months: string[]; held_out_month: string; experiments: Experiment[]; per_person: Record<Kind, PersonalChoice> }

/** The two arms of each kind, control first. */
export const ARMS: Record<Kind, [string, string]> = { offer: ["list", "offer"], title: ["plain", "benefit"], image: ["packshot", "lifestyle"] };
export const KIND_LABEL: Record<Kind, string> = { offer: "Offer", title: "Title", image: "Image" };
export const ARM_LABEL: Record<string, string> = {
  list: "List price", offer: "15 % off", plain: "Plain title", benefit: "Benefit-led title", packshot: "Pack shot", lifestyle: "Lifestyle image",
};
export const SIGNAL_TEXT: Record<string, string> = {
  offer_buyer: "how much of the shopper's earlier buying was on offer",
  wellness_share: "how much of what the shopper bought is a wellness diet",
  first_source: "where the shopper's first visit came from",
};
export const STATUS_LABEL: Record<Status, string> = { draft: "Draft", running: "Running", decided: "Decided" };
export const ARM_VERDICT_TEXT: Record<ArmVerdict, string> = {
  "second arm better": "The second arm earns more per showing; the interval is above zero.",
  "control better": "The control earns more per showing; the interval is below zero.",
  "no clear difference": "Not enough showings to tell the arms apart: the interval includes zero. Keep running.",
};
export const PERSON_VERDICT_TEXT: Record<PersonVerdict, string> = {
  "choose per person": "Worth choosing per person: the gain is at least 3 % and its interval is above zero.",
  "small gain": "A real but small gain (the interval is above zero, the gain under 3 %): not worth a second way of choosing yet.",
  "keep the plain winner": "Keep the plain winner: the gain's interval includes zero.",
};
/** A per-person choice that earns clearly less than the plain winner says so: the signal is too noisy to act on. */
export const WORSE_TEXT = "Keep the plain winner: choosing per person earned less (the interval is below zero). The signal splits shoppers into groups too small to read a difference from.";

export const eur = (value: number, decimals = 2) => `€${value.toFixed(decimals)}`;
export const signedEur = (value: number) => `${value >= 0 ? "+" : "−"}€${Math.abs(value).toFixed(2)}`;
export const percent = (value: number, decimals = 1) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(decimals)} %`;
export const rate = (value: number) => `${(100 * value).toFixed(1)} %`;

/** The arm that is clearly better, if the interval excludes zero. */
export function clearWinner(e: Experiment): string | null {
  if (e.verdict === "second arm better") return e.arms[1].arm;
  return e.verdict === "control better" ? e.arms[0].arm : null;
}
