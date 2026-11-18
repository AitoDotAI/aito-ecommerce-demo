/** The Customers profit footnote's cost sentence, from the facts the profile summary stores. */
export interface CostFacts { kept_lines: number; lines_below_cost: number; unit_cost_share_of_list_price: number }

export function costFootnote(facts: CostFacts): string {
  const share = Math.round(facts.unit_cost_share_of_list_price * 100);
  const below = facts.lines_below_cost.toLocaleString("en-GB");
  const kept = facts.kept_lines.toLocaleString("en-GB");
  return `(about ${share} % of the list price) applied to two years of sales, and ${below} of ${kept} kept lines were sold below it.`;
}
