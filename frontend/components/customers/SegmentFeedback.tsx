"use client";

import { useState } from "react";

import Pattern from "@/components/customers/Pattern";
import SegmentFeedbackPatterns, { PATTERN_SECTIONS, type FeedbackFilter } from "@/components/customers/SegmentFeedbackPatterns";
import { zOfShares } from "@/lib/pattern";
import type { FeedbackRow, SegmentView } from "@/lib/customer-profiles";

const VIEWS = [["rules", "Patterns"], ["themes", "Themes"], ["cause", "Products × themes"], ["products", "Products"], ["lines", "Product lines"], ["shares", "Reviews and answers"]] as const;
const SECTION_OF = { rules: PATTERN_SECTIONS[0][0], themes: PATTERN_SECTIONS[1][0], cause: PATTERN_SECTIONS[2][0], products: PATTERN_SECTIONS[3][0], lines: PATTERN_SECTIONS[4][0] };

/** What the segment says: the figures, then one view at a time: what stands out among poor feedback (rules, themes, products, product lines), or the share of each kind of review and answer. */
export default function SegmentFeedback({ view, selected, onSelect }: { view: SegmentView; selected: FeedbackFilter | null; onSelect: (filter: FeedbackFilter | null) => void }) {
  if (!view.feedback) return null;
  const { selected: entry, all } = view.feedback;
  const [which, setWhich] = useState<(typeof VIEWS)[number][0]>("rules");
  const everyone = view.conditions.length === 0;
  const scale = Math.max(30, ...entry.rows.map((r) => Math.abs(r.points ?? 0)));
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <div className="card-title" style={{ margin: 0 }}>What they say: reviews about products, and the NPS survey after an order</div>
        <span style={{ display: "inline-flex", gap: 4, flexWrap: "wrap" }}>
          {VIEWS.map(([id, label]) => (
            <button key={id} aria-pressed={which === id} onClick={() => setWhich(id)} style={{
              cursor: "pointer", borderRadius: 12, padding: "2px 10px", font: "inherit", fontSize: 12, color: "var(--text)",
              border: `1px solid ${which === id ? "var(--aito-teal)" : "var(--border)"}`, background: which === id ? "rgba(0, 168, 150, 0.15)" : "transparent" }}>{label}</button>
          ))}
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12, margin: "6px 0 10px" }}>
        <Kpi label="Wrote reviews" value={`${Math.round((entry.reviewers / entry.customers) * 100)} %`} note={`${entry.reviews} reviews${everyone ? "" : `, all ${Math.round((all.reviewers / all.customers) * 100)} %`}`} />
        <Kpi label="Average rating" value={entry.mean_rating === null ? "–" : entry.mean_rating.toFixed(2)} note={everyone ? "stars" : `all ${all.mean_rating?.toFixed(2)}`} />
        <Kpi label="NPS" value={entry.nps === null ? "–" : `${entry.nps > 0 ? "+" : ""}${entry.nps}`}
          note={entry.nps === null ? `only ${entry.nps_respondents} answers` : `${entry.nps_respondents} answers${everyone ? "" : `, all ${all.nps !== null && all.nps > 0 ? "+" : ""}${all.nps}`}`} />
      </div>
      {which !== "shares" && <SegmentFeedbackPatterns section={SECTION_OF[which]} conditions={view.conditions} selected={selected} onSelect={onSelect} />}
      {which === "shares" && (
        <>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        {everyone
          ? "Of all profiled customers, how many wrote each kind of review and answered each way in the NPS survey."
          : "How many more (or fewer) points of this segment wrote each kind of review or answered each way than the other profiled customers."}{" "}
        A customer counts once. "Pattern?" says whether the difference is a pattern in the data or could be luck; hover for the chance.
        Simulated reviews and answers.
      </div>
      {entry.rows.length === 0 && <div className="card-sub">Too few customers in this segment to compare.</div>}
      {!everyone && entry.rows.length > 0 && (
        <div className="card-sub" style={{ display: "grid", gridTemplateColumns: "minmax(120px, 1.3fr) minmax(60px, 0.8fr) minmax(110px, 140px) 64px", gap: 8, fontSize: 12, margin: "6px 0 2px" }}>
          <span>Review or answer</span><span>Fewer ← → more than the rest</span><span>Points (this segment vs the rest)</span><span>Pattern?</span>
        </div>
      )}
      {entry.rows.map((r) => <Row key={r.label} r={r} scale={scale} everyone={everyone} />)}
        </>
      )}
    </div>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div>
      <div className="card-sub">{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
      <div className="card-sub">{note}</div>
    </div>
  );
}

function Row({ r, scale, everyone }: { r: FeedbackRow; scale: number; everyone: boolean }) {
  if (everyone || r.points === null || r.margin_points === null) {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 1.3fr) minmax(60px, 1fr) 60px", gap: 8, alignItems: "center", fontSize: 13, margin: "3px 0" }}>
        <span>{r.label}</span>
        <span style={{ height: 8, background: "var(--border-light)", borderRadius: 3 }}>
          <span style={{ display: "block", height: 8, width: `${r.share * 100}%`, background: "var(--aito-teal)", borderRadius: 3 }} />
        </span>
        <span className="card-sub">{Math.round(r.share * 100)} %</span>
      </div>
    );
  }
  const width = `${(Math.abs(r.points) / scale) * 50}%`;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 1.3fr) minmax(60px, 0.8fr) minmax(110px, 140px) 64px", gap: 8, alignItems: "center", fontSize: 13, margin: "3px 0" }}>
      <span>{r.label}</span>
      <span style={{ position: "relative", height: 12, background: "var(--border-light)", borderRadius: 3 }}>
        <span style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
        <span style={{ position: "absolute", top: 2, bottom: 2, borderRadius: 2, background: r.points >= 0 ? "var(--aito-teal)" : "var(--cta)",
          ...(r.points >= 0 ? { left: "50%", width } : { right: "50%", width }) }} />
      </span>
      <span className="card-sub">{r.points > 0 ? "+" : ""}{r.points} ±{r.margin_points} ({Math.round(r.share * 100)} % vs {Math.round((r.share_others ?? 0) * 100)} %)</span>
      <Pattern z={zOfShares(r.points, r.margin_points)} detail={`${r.points > 0 ? "+" : ""}${r.points} points`} />
    </div>
  );
}
