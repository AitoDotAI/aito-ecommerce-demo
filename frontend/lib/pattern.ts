/**
 * Whether a difference is a pattern in the data or could be luck, in words (ADR 0055). The statistic behind it is the difference in
 * standard errors, `z`: Yes from 3 (a chance of about 1 in 370 or less), Likely from 2 (about 1 in 20), Possibly from 1, else Unlikely.
 * A pattern is not a cause: the data shows that two things go together, never why.
 */
export type PatternLevel = "yes" | "likely" | "possibly" | "unlikely";

export const PATTERN_LABEL: Record<PatternLevel, string> = { yes: "Yes", likely: "Likely", possibly: "Possibly", unlikely: "Unlikely" };

export function patternOf(z: number | null): PatternLevel | null {
  if (z === null) return null;
  return z >= 3 ? "yes" : z >= 2 ? "likely" : z >= 1 ? "possibly" : "unlikely";
}

/** The standard errors of a difference of shares whose 99.7 % margin is `margin` (a margin is three of them). */
export function zOfShares(points: number, margin: number): number {
  return margin > 0 ? (3 * Math.abs(points)) / margin : 0;
}

/** The two-sided chance of a gap this large by luck alone, for `z` standard errors (Abramowitz and Stegun 7.1.26 for erfc). */
export function pValue(z: number): number {
  const x = Math.abs(z) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * x);
  const poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
  return Math.min(1, poly * Math.exp(-x * x));
}

/** "about 1 time in 370", for the hover. */
export function chanceInWords(z: number): string {
  const p = pValue(z);
  if (z >= 8) return "far less than 1 time in a million";
  const n = Math.max(1, Math.round(1 / p));
  return n <= 1 ? "often" : `about 1 time in ${n.toLocaleString("en-GB")}`;
}
