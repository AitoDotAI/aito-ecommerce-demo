"use client";

import { KPIS, figureOf, figuresOf, kpiSpec } from "@/lib/customer-kpis";
import { TREE, TRAIT_TITLE, describe, type KpiId, type ProfilesSummary, type SegmentView } from "@/lib/customer-profiles";

/**
 * The topic tree that selects the segment: tick any number of conditions and the page describes the customers who meet all of
 * them. Above it, the figure to compare by: every condition shows what that figure would be for the segment if it were ticked,
 * as a number and a bar, so a dead end or a standout shows before it is picked. Nothing ticked is every profiled customer.
 */
export default function SegmentTree({ summary, view, conditions, kpi, onKpi, onToggle, onClear }: {
  summary: ProfilesSummary; view: SegmentView | null; conditions: string[]; kpi: KpiId; onKpi: (kpi: KpiId) => void;
  onToggle: (condition: string) => void; onClear: () => void;
}) {
  const spec = kpiSpec(kpi);
  const own = view ? figuresOf(view) : null;
  const figures = view?.options ?? {};
  const largest = Math.max(1e-9, ...Object.values(figures).map((f) => Math.abs(figureOf(kpi, f) ?? 0)));
  return (
    <nav aria-label="Segment" className="segment-nav" style={{ position: "sticky", top: 8, display: "grid", gap: 12 }}>
      <div className="card segment-compare">
        <div className="card-title" style={{ margin: "0 0 6px" }}>Compare by</div>
        <a href="#segment-conditions" className="segment-jump">Change the segment ↓</a>
        <div role="tablist" aria-label="Figure to compare by" style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 6 }}>
          {KPIS.map((k) => {
            const value = own ? figureOf(k.id, own) : null;
            return (
              <button key={k.id} role="tab" aria-selected={kpi === k.id} onClick={() => onKpi(k.id)} style={{
                textAlign: "left", cursor: "pointer", font: "inherit", color: "var(--text)", borderRadius: 6, padding: "6px 8px", minWidth: 0,
                border: `1px solid ${kpi === k.id ? "var(--aito-teal)" : "var(--border)"}`, background: kpi === k.id ? "rgba(0, 168, 150, 0.12)" : "transparent" }}>
                <div className="card-sub" style={{ fontSize: 11, lineHeight: 1.2 }}>{k.label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{value === null ? "–" : k.format(value)}</div>
              </button>
            );
          })}
        </div>
      </div>
      <div className="card segment-conditions" id="segment-conditions">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
          <div className="card-title" style={{ margin: 0 }}>Segment</div>
          {conditions.length > 0 && <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={onClear}>Clear</button>}
        </div>
        <div className="card-sub" style={{ margin: "4px 0 8px", lineHeight: 1.45 }}>
          {conditions.length === 0
            ? `All ${summary.profiled.toLocaleString("en-GB")} profiled customers. Tick conditions to narrow down; each shows ${spec.label.toLowerCase()} for the segment it would give.`
            : `${(view?.customers ?? 0).toLocaleString("en-GB")} customers meet ${conditions.length === 1 ? "this condition" : `all ${conditions.length} conditions`}.`}
        </div>
        {TREE.map((group) => (
          <div key={group.title} style={{ marginTop: 10 }}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{group.title}</div>
            {group.traits.map((trait) => (
              <div key={trait} style={{ margin: "6px 0 0 8px" }}>
                <div className="card-sub" style={{ fontSize: 12 }}>{TRAIT_TITLE[trait]}</div>
                {summary.by_trait[trait].filter((s) => s.profit_per_customer_eur !== undefined).map((s) => {
                  const condition = `${trait}:${s.value}`;
                  const on = conditions.includes(condition);
                  const row = figures[condition];
                  const empty = row !== undefined && row.customers === 0 && !on;
                  const value = row ? figureOf(kpi, row) : null;
                  return (
                    <label key={condition} title={describe(condition)} style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", alignItems: "center", gap: 6,
                      fontSize: 13, padding: "2px 0", cursor: empty ? "not-allowed" : "pointer", opacity: empty ? 0.45 : 1 }}>
                      <input type="checkbox" checked={on} disabled={empty} onChange={() => onToggle(condition)} />
                      <span style={{ minWidth: 0 }}>
                        {s.value}
                        <span style={{ display: "block", height: 4, marginTop: 2, borderRadius: 2, background: "var(--border-light)" }}>
                          <span style={{ display: "block", height: 4, borderRadius: 2, width: `${value === null ? 0 : (Math.abs(value) / largest) * 100}%`,
                            background: value !== null && value < 0 ? "var(--cta)" : "var(--aito-teal)" }} />
                        </span>
                      </span>
                      <span className="card-sub" title={row ? `${row.customers.toLocaleString("en-GB")} customers` : undefined}>
                        {value === null ? "–" : spec.format(value)}
                      </span>
                    </label>
                  );
                })}
              </div>
            ))}
          </div>
        ))}
      </div>
    </nav>
  );
}
