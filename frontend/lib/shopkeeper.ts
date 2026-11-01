/** The Shopkeeper view's data (ADR 0052) and the settings a shopkeeper keeps in the browser. */

export type Outcome = "act" | "suggest" | "never_auto" | "quiet";

export interface GateSettings {
  act_lift: number;
  suggest_lift: number;
  min_rows: number;
  never_auto: string[];
}

export interface SettingsView {
  in_force: GateSettings;
  recommended: GateSettings;
  lifts_in_runs: { min: number; median: number; max: number } | null;
}

export interface Tally { steps: number; expected_net_eur: number }

export interface BoardItem {
  id: string;
  kind: "evidence" | "approval" | "root_cause";
  owner: "agent" | "shopkeeper";
  status: string;
  raised_by: string;
  title: string;
  detail: string;
  evidence: string[];
}

export interface Routine {
  id: string; name: string; schedule: string; built: boolean; does: string; latest_run: string | null;
  kind: "rule" | "agent"; why: string;
}

export interface RunSummary {
  id: string; title: string; as_of_month: string; stale: boolean; tally: Record<Outcome, Tally>;
}

/** A stored conversation with Ask the store, as the list shows it (ADR 0054). */
export interface ConversationSummary {
  id: string; asked_at: string; question: string; model: string; tool_calls: number; tokens: number; release: string;
}

export interface ConversationToolCall { name: string; input: Record<string, unknown>; ms: number; error: string | null; result: unknown }

export interface Conversation extends Omit<ConversationSummary, "tool_calls" | "tokens"> {
  answer: string; input_tokens: number; output_tokens: number; tool_calls: ConversationToolCall[];
}

export interface ShopkeeperOverview {
  simulated: boolean; release: string; settings: SettingsView;
  board: BoardItem[]; routines: Routine[]; runs: RunSummary[]; conversations: ConversationSummary[];
}

export interface RunStep {
  customer_id: string; name: string; risk: string; spend_12m_eur: number; tells: string[];
  context: Record<string, string>; order_value_eur: number;
  best: { action: string; label: string; purchase_p: number; purchase_lift_p: number; net_vs_none_eur: number; cost_eur: number };
  none_purchase_p: number; rows: number; rows_no_action: number;
  alternatives: { label: string; purchase_p: number; purchase_lift_p: number; net_vs_none_eur: number }[];
  outcome: Outcome; reason: string;
}

export interface Run {
  id: string; title: string; release: string; as_of_month: string; source: string; stale: boolean; stale_reason: string | null;
  steps: RunStep[]; tally: Record<Outcome, Tally>; settings: SettingsView;
}

export const OUTCOME_LABEL: Record<Outcome, string> = {
  act: "Acted", suggest: "Suggested", never_auto: "Needs a person", quiet: "Stayed quiet",
};

export const OUTCOME_HELP: Record<Outcome, string> = {
  act: "Confident and enough evidence: the agent does it.",
  suggest: "Between the bars: queued for approval.",
  never_auto: "A kind the store always sends through a person.",
  quiet: "No evidence, or no gain: nothing is proposed.",
};

/** The query string that makes the server judge under `settings`; empty when they are the recommended ones. */
export function settingsQuery(settings: GateSettings, recommended: GateSettings): string {
  if (JSON.stringify(settings) === JSON.stringify(recommended)) return "";
  const q = new URLSearchParams({
    act_lift: String(settings.act_lift), suggest_lift: String(settings.suggest_lift),
    min_rows: String(settings.min_rows), never_auto: settings.never_auto.join(","),
  });
  return `?${q}`;
}

const STORAGE_KEY = "shopkeeper-browser-state";

interface BrowserState { settings?: GateSettings; decisions?: Record<string, "approved" | "rejected"> }

export function readBrowserState(): BrowserState {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}") as BrowserState;
  } catch {
    return {};  // private window or blocked storage: the view works without it
  }
}

export function writeBrowserState(state: BrowserState): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // not stored; the choice lasts until the page is closed
  }
}
