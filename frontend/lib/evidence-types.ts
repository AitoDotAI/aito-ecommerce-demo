/**
 * The committed Evidence result files (`data/evidence/*.json`, ADR 0037),
 * as `/api/evidence/<entry>` serves them. Every sentence in them was worded
 * in Python by the rules of ADR 0037 §2 (a tie when the interval spans 0);
 * the pages render those sentences and never word a result themselves.
 */
import type { EvalModelResult } from "@/lib/types";

export interface EvidenceRun {
  command: string;
  date: string;
  code_commit: string;
  aito_env?: string;
  aito_api?: string;
  aito_version?: string;
  derived_by?: string;
}

export interface Interval { mean: number; low: number | null; high: number | null }

export interface WordedDifference {
  baseline: string;
  difference: number;
  low: number;
  high: number;
  sentence: string;
}

// ── Model checks ─────────────────────────────────────────────────────

export interface ModelCheck extends EvalModelResult {
  accuracy_low: number;
  accuracy_high: number;
  comparisons: WordedDifference[];
}

export interface HeldOutAccuracy {
  label: string;
  table: string;
  predict: string;
  accuracy: number;
  accuracy_low: number;
  accuracy_high: number;
  base_accuracy: number;
  n: number;
  method: string;
  comparisons: WordedDifference[];
}

export interface ModelChecksFile {
  run: EvidenceRun;
  threshold_pp: number;
  models: ModelCheck[];
  churn: HeldOutAccuracy & { features: string[] };
  demand: HeldOutAccuracy & { naive_accuracy: number; test_month: string };
}

// ── Search relevance ─────────────────────────────────────────────────

export interface SearchArm { arm: string; ndcg10: number; p5: number; r20: number; mrr: number; zero: number }

export interface SearchComparison { arm: string; base: string; difference: number; low: number; high: number; sentence: string }

export interface SearchRelevanceFile {
  run: EvidenceRun;
  report: string;
  theta: number;
  thetas_tried: number[];
  headline: string;
  queries: number;
  strata: Record<string, number>;
  arms: SearchArm[];
  by_stratum: Array<Record<string, number | string>>;
  comparisons: SearchComparison[];
  out_of_sample: {
    splits: number;
    chosen: Record<string, number>;
    median_gain: number;
    gain_90: [number, number];
    positive_share: number;
    one_split: {
      seed: number; theta: number; queries: number;
      by_persona: Record<string, { difference: number; low: number; high: number; sentence: string }>;
    };
  };
  controls: { random_ndcg10: number; shuffled_labels_ndcg10: number };
  personas: Record<string, string>;
}

// ── Personalised search ──────────────────────────────────────────────

export interface PersonalisedSlice {
  name: string;
  label: string;
  sessions: number;
  hit10: Record<string, Interval>;
  mrr: Record<string, Interval>;
  best_aito: string;
  comparisons: Array<{ ranking: string; against: string; difference: Interval }>;
  sentences: string[];
}

export interface PersonalisedSearchFile {
  run: EvidenceRun & { sessions: number; subsample: number | null; held_out: string };
  preregistration: string;
  metric: { primary: string; secondary: string };
  rankings: string[];
  headline: string;
  slices: PersonalisedSlice[];
}
