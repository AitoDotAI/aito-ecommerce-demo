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
  id: string; title: string; as_of_month: string; stale: boolean; routine: string; tally: Record<Outcome, Tally & StockTally>;
}

/** What a stock run's outcome groups would order and protect (ADR 0057); the win-back's groups hold expected euros instead. */
export interface StockTally { order_cost_eur?: number; revenue_at_risk_eur?: number }

export interface StockSettings { min_recent_units: number; order_limit_eur: number; urgent_share: number }

export interface StockStep {
  kind: "reorder" | "overstock"; sku: string; name: string; category: string; outcome: Outcome; reason: string; current_stock: number;
  supplier?: string; lead_time_days?: number; reorder_point?: number; recent_units?: number; order_qty?: number; order_cost_eur?: number; revenue_at_risk_eur?: number;
  excess_units?: number; tied_capital_eur?: number;
  markdown?: { action: string; discount_pct: number; price_eur: number; weeks_to_clear: number; units_cleared: number; capital_freed_eur: number; margin_given_up_eur: number };
}

export interface StockRun {
  id: string; routine: "stock"; title: string; release: string; as_of_month: string; source: string; stale: boolean; stale_reason: string | null;
  steps: StockStep[]; tally: Record<Outcome, { steps: number; order_cost_eur: number; revenue_at_risk_eur: number }>;
  settings: { in_force: StockSettings; recommended: StockSettings };
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
  stock_settings: { in_force: StockSettings; recommended: StockSettings };
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
  routine: "winback"; id: string; title: string; release: string; as_of_month: string; source: string; stale: boolean; stale_reason: string | null;
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

/** The query string that makes the server judge a stock run under `settings`; empty when they are the recommended ones. */
export function stockQuery(settings: StockSettings, recommended: StockSettings): string {
  if (JSON.stringify(settings) === JSON.stringify(recommended)) return "";
  return `?${new URLSearchParams({ min_recent_units: String(settings.min_recent_units), order_limit_eur: String(settings.order_limit_eur), urgent_share: String(settings.urgent_share) })}`;
}

interface BrowserState { settings?: GateSettings; stock?: StockSettings; decisions?: Record<string, "approved" | "rejected"> }

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
