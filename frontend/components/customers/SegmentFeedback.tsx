"use client";

import Confidence from "@/components/customers/Confidence";
import type { FeedbackEntry, FeedbackRow, ProfilesSummary } from "@/lib/customer-profiles";

/** What the segment says: how much it writes, what it writes about, and how likely it is to recommend the shop. */
export default function SegmentFeedback({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const entry = summary.feedback[selected];
  const all = summary.feedback.all;
  if (!entry) return null;
  const everyone = selected === "all";
  const scale = Math.max(30, ...entry.rows.map((r) => Math.abs(r.points ?? 0)));
  return (
    <div className="card">
      <div className="card-title">What they say</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12, margin: "6px 0 10px" }}>
        <Kpi label="Wrote reviews" value={`${Math.round((entry.reviewers / entry.customers) * 100)} %`} note={`${entry.reviews} reviews${everyone ? "" : `, all ${Math.round((all.reviewers / all.customers) * 100)} %`}`} />
        <Kpi label="Average rating" value={entry.mean_rating === null ? "–" : entry.mean_rating.toFixed(2)} note={everyone ? "stars" : `all ${all.mean_rating?.toFixed(2)}`} />
        <Kpi label="NPS" value={entry.nps === null ? "–" : `${entry.nps > 0 ? "+" : ""}${entry.nps}`}
          note={entry.nps === null ? `only ${entry.nps_respondents} answers` : `${entry.nps_respondents} answers${everyone ? "" : `, all ${all.nps !== null && all.nps > 0 ? "+" : ""}${all.nps}`}`} />
      </div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        {everyone
          ? "Of all profiled customers, how many wrote each kind of review and answered each way in the NPS survey."
          : "How many more (or fewer) points of this segment wrote each kind of review or answered each way than the other profiled customers."}{" "}
        A customer counts once. The confidence column is the difference divided by its 99.7 % margin; above 1× it is larger than chance would give.
        Simulated reviews and answers.
      </div>
      {entry.rows.length === 0 && <div className="card-sub">Too few customers in this segment to compare.</div>}
      {entry.rows.map((r) => <Row key={r.label} r={r} scale={scale} everyone={everyone} />)}
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
    <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 1.3fr) minmax(60px, 0.8fr) minmax(110px, 140px) 44px", gap: 8, alignItems: "center", fontSize: 13, margin: "3px 0" }}>
      <span>{r.label}</span>
      <span style={{ position: "relative", height: 12, background: "var(--border-light)", borderRadius: 3 }}>
        <span style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
        <span style={{ position: "absolute", top: 2, bottom: 2, borderRadius: 2, background: r.points >= 0 ? "var(--aito-teal)" : "var(--cta)",
          ...(r.points >= 0 ? { left: "50%", width } : { right: "50%", width }) }} />
      </span>
      <span className="card-sub">{r.points > 0 ? "+" : ""}{r.points} ±{r.margin_points} ({Math.round(r.share * 100)} % vs {Math.round((r.share_others ?? 0) * 100)} %)</span>
      <Confidence points={r.points} margin={r.margin_points} />
    </div>
  );
}
