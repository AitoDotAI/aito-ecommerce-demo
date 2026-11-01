"use client";

import Pattern from "@/components/customers/Pattern";
import { zOfShares } from "@/lib/pattern";
import { kpiSpec } from "@/lib/customer-kpis";
import { TRAIT_TITLE, type KpiId, type SegmentView } from "@/lib/customer-profiles";

/**
 * How the selected segment relates to the other segments: of its customers, how many more (or fewer) points are in each other segment
 * than of the customers outside it. Beside each, what the chosen figure would be for the customers in both, and a button to tick it.
 */
export default function SegmentOthers({ view, kpi, onTick }: { view: SegmentView; kpi: KpiId; onTick: (condition: string) => void }) {
  if (view.conditions.length === 0) {
    return <div className="card card-sub">Tick a segment to see how it relates to the others.</div>;
  }
  const spec = kpiSpec(kpi);
  const rows = [...(view.relations ?? [])].sort((a, b) => Number(b.clear) - Number(a.clear) || Math.abs(b.points) - Math.abs(a.points));
  const scale = Math.max(30, ...rows.map((r) => Math.abs(r.points)));
  return (
    <div className="card">
      <div className="card-title">Other segments</div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        How many more (or fewer) points of this segment are in each other segment than of the customers outside it. "Pattern?" says whether that is a pattern
        in the data (Yes, Likely, Possibly) or Unlikely to be more than luck; hover for the chance. A pattern is not a cause. The last column is {spec.label.toLowerCase()} for
        the customers in both. Diets are left out: a diet belongs to a kind of pet, so it would only show the catalogue.
      </div>
      {rows.length === 0 && <div className="card-sub">Too few customers outside this segment to compare.</div>}
      {rows.length > 0 && (
        <div className="card-sub" style={{ display: "grid", gridTemplateColumns: "minmax(120px, 1.2fr) minmax(60px, 0.8fr) minmax(110px, 140px) 44px minmax(70px, 100px) auto", gap: 8, fontSize: 12, margin: "6px 0 2px" }}>
          <span>Other segment</span><span>More or fewer than outside</span><span>Points (in this segment vs outside)</span><span>Pattern?</span>
          <span>{spec.label} of both</span><span />
        </div>
      )}
      {rows.map((r) => {
        const condition = `${r.then.trait}:${r.then.value}`;
        const both = view.options[condition];
        const figure = both ? both[kpi] : null;
        const width = `${(Math.abs(r.points) / scale) * 50}%`;
        return (
          <div key={condition} style={{ display: "grid", gridTemplateColumns: "minmax(120px, 1.2fr) minmax(60px, 0.8fr) minmax(110px, 140px) 44px minmax(70px, 100px) auto", gap: 8,
            alignItems: "center", fontSize: 13, margin: "3px 0" }}>
            <span><span className="card-sub">{TRAIT_TITLE[r.then.trait]} · </span>{r.then.value}</span>
            <span style={{ position: "relative", height: 12, background: "var(--border-light)", borderRadius: 3 }}>
              <span style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
              <span style={{ position: "absolute", top: 2, bottom: 2, borderRadius: 2, background: r.points >= 0 ? "var(--aito-teal)" : "var(--cta)",
                ...(r.points >= 0 ? { left: "50%", width } : { right: "50%", width }) }} />
            </span>
            <span className="card-sub">{r.points > 0 ? "+" : ""}{r.points} ±{r.margin_points} ({Math.round(r.share_with * 100)} % vs {Math.round(r.share_without * 100)} %)</span>
            <Pattern z={zOfShares(r.points, r.margin_points)} detail={`${r.points > 0 ? "+" : ""}${r.points} points`} />
            <span title={both ? `${both.customers.toLocaleString("en-GB")} customers in both` : undefined}>{figure === null || figure === undefined ? "–" : spec.format(figure)}</span>
            <button className="btn btn-ghost" style={{ padding: "1px 8px", fontSize: 12 }} disabled={!both || both.customers === 0} onClick={() => onTick(condition)}>Tick</button>
          </div>
        );
      })}
    </div>
  );
}
