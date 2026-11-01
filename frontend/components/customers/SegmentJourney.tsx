"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

interface Cell { offset: number; churned: number | null; active: number | null; n_churned: number; n_active: number; points: number | null; margin: number | null; clear: boolean | null; by_definition: boolean }
interface Journey {
  too_small: boolean; customers: { churned: number; active: number }; without_control?: number; comparable?: boolean; reason?: string;
  offsets?: number[]; events?: { code: string; label: string }[]; cells?: Record<string, Cell[]>;
}

const pct = (n: number | null) => (n === null ? "–" : `${Math.round(n * 100)} %`);
const heading = (offset: number) => (offset === 0 ? "Month of the order" : offset < 0 ? `${-offset} month${offset === -1 ? "" : "s"} before` : `${offset} month${offset === 1 ? "" : "s"} after`);

// What a customer did, as a verb phrase, and the group each kind of event belongs to.
const VERB: Record<string, string> = {
  order: "ordered", visit: "visited the shop", return: "returned a line", incident: "had a late or damaged delivery",
  low_review: "wrote a 1–2 star review", detractor: "answered the NPS survey 0–6", action: "were sent an action by the shop",
};
const NOUN: Record<string, string> = { return: "returns", incident: "late or damaged deliveries", low_review: "low reviews", detractor: "detractor answers" };
const GROUPS: { title: string; codes: string[]; hint: string }[] = [
  { title: "Activity", codes: ["visit", "order"], hint: "how engaged they were" },
  { title: "Things that went wrong", codes: ["return", "incident", "low_review", "detractor"], hint: "problems and complaints" },
  { title: "What the shop did", codes: ["action"], hint: "emails, ads, discounts, vouchers, apologies" },
];

/** The offsets (months from the last order) that are a clear difference, as a short span. */
function span(offsets: number[]): string {
  const before = offsets.filter((o) => o < 0);
  const parts: string[] = [];
  if (before.length) parts.push(before.length === 1 ? `the month ${-before[0]} before their last order` : `${before.length} of the 5 months before their last order`);
  if (offsets.includes(0)) parts.push("the month of the last order");
  const after = offsets.filter((o) => o > 0);
  if (after.length) parts.push(after.length === 1 ? "the month after" : "the months after");
  return parts.join(", and in ");
}

/** What stands out, in sentences: for each kind of event, whether those who left differ clearly from those who stayed, and when. */
function standsOut(journey: Journey): { text: string; clear: boolean }[] {
  const lines: { text: string; clear: boolean }[] = [];
  for (const group of GROUPS) {
    for (const code of group.codes) {
      const cells = (journey.cells?.[code] ?? []).filter((c) => c.clear);
      const verb = VERB[code];
      if (cells.length === 0) continue;
      const lower = cells.filter((c) => (c.churned ?? 0) < (c.active ?? 0)).length;
      const more = lower === 0 ? "more often" : lower === cells.length ? "less often" : "differently";
      lines.push({ text: `Those who left ${verb} ${more} than those who stayed, clearly, in ${span(cells.map((c) => c.offset))}.`, clear: true });
    }
  }
  const anyBefore = Object.values(journey.cells ?? {}).some((row) => row.some((c) => c.offset < 0 && c.clear));
  if (journey.comparable && !anyBefore) {
    lines.push({ text: "In the months before their last order, those who left look like those who stayed in every kind of event: there is no early warning in these events.", clear: true });
  }
  const none = GROUPS[1].codes.filter((code) => (journey.cells?.[code] ?? []).every((c) => !c.clear));
  if (none.length > 0) {
    const all = none.length === GROUPS[1].codes.length;
    lines.push({ text: `No clear difference in ${none.map((c) => NOUN[c]).join(", ")}: ${all ? "problems are not what sets those who left apart" : "not what sets those who left apart"}.`, clear: false });
  }
  return lines;
}

/**
 * The journey of the segment (ADR 0059): every customer lined up on their own last order, and what share of those who left and of those who stayed had each kind of
 * event in each month around it. A summary in words first, then the grid: two bars per cell (teal: those who left, grey: those who stayed), shaded where the difference
 * is a clear pattern. The data is monthly: the order of events within a month is not known.
 */
export default function SegmentJourney({ conditions }: { conditions: string[] }) {
  const [journey, setJourney] = useState<Journey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const query = conditions.map((c) => `c=${encodeURIComponent(c)}`).join("&");

  useEffect(() => {
    apiFetch<Journey>(`/api/customer-profiles/journey${query ? `?${query}` : ""}`).then((j) => { setJourney(j); setError(null); }).catch((e) => setError(String(e)));
  }, [query]);

  if (error) return <div className="card card-sub">{error}</div>;
  if (!journey) return <div className="card" style={{ height: 160, background: "var(--border-light)" }} />;
  if (journey.too_small || !journey.cells || !journey.offsets || !journey.events) return <div className="card card-sub">Too few customers in this segment to compare.</div>;
  const cells = journey.cells;
  const summary = standsOut(journey);
  return (
    <div className="card">
      <div className="card-title">What happened before customers left</div>
      <div className="card-sub" style={{ lineHeight: 1.55, marginBottom: 8 }}>
        <strong>Left</strong> is the shop&apos;s rule: no order in the last three months of the data. Nobody can tell the day someone decided to leave, only that three months passed with
        no order. {journey.customers.churned.toLocaleString("en-GB")} customers in this segment have left. Each is lined up on their <strong>last order</strong> (the month of the order is the middle column).
        {" "}{journey.customers.active.toLocaleString("en-GB")} customers <strong>stayed</strong>. For them there is no last order to line up on that means the same, so each is lined up on an
        ordinary order of theirs, picked at random among those followed by at least three months of data: a control, an order after which they kept ordering.
        {journey.without_control ? ` ${journey.without_control.toLocaleString("en-GB")} who stayed are left out because all their orders are within the last three months.` : ""}{" "}
        Each cell is the share of customers who had that kind of event that month, counting only months the customer existed.
      </div>

      <div style={{ background: "var(--border-light)", borderRadius: 6, padding: "8px 12px", marginBottom: 10 }}>
        <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>What stands out</div>
        {journey.comparable ? (
          summary.length === 0 ? <div style={{ fontSize: 13 }}>Nothing differs clearly between those who left and those who stayed.</div>
            : summary.map((s, i) => <div key={i} style={{ fontSize: 13, lineHeight: 1.5, color: s.clear ? "var(--text)" : "var(--text-muted)" }}>• {s.text}</div>)
        ) : <div style={{ fontSize: 13 }}>Not compared: {journey.reason}.</div>}
      </div>

      <div style={{ display: "flex", gap: 14, alignItems: "center", fontSize: 12, margin: "0 0 6px" }} className="card-sub">
        <span><span style={{ display: "inline-block", width: 18, height: 8, background: "var(--aito-teal)", borderRadius: 2, marginRight: 5 }} />left</span>
        <span><span style={{ display: "inline-block", width: 18, height: 8, background: "var(--text-muted)", opacity: 0.55, borderRadius: 2, marginRight: 5 }} />stayed</span>
        <span><span style={{ display: "inline-block", width: 18, height: 12, background: "rgba(0, 168, 150, 0.2)", border: "1px solid var(--border)", borderRadius: 2, marginRight: 5 }} />a clear difference (not luck)</span>
        <span>Hover a cell for the numbers.</span>
      </div>
      <div className="scroll-x">
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr className="card-sub" style={{ fontSize: 12 }}>
              <th style={{ textAlign: "left", fontWeight: 500 }}>Share of customers who…</th>
              {journey.offsets.map((o) => <th key={o} style={{ fontWeight: o === 0 ? 700 : 500, padding: "2px 6px", minWidth: 62 }}>{heading(o)}</th>)}
            </tr>
          </thead>
          <tbody>
            {GROUPS.map((group) => (
              [
                <tr key={`g-${group.title}`}>
                  <td colSpan={journey.offsets!.length + 1} style={{ fontWeight: 700, fontSize: 12, paddingTop: 10 }}>
                    {group.title} <span className="card-sub" style={{ fontWeight: 400 }}>· {group.hint}</span>
                  </td>
                </tr>,
                ...group.codes.map((code) => {
                  const event = journey.events!.find((e) => e.code === code)!;
                  const top = Math.max(0.0001, ...cells[code].flatMap((c) => [c.churned ?? 0, c.active ?? 0]));
                  return (
                    <tr key={code} style={{ borderTop: "1px solid var(--border-light)", textAlign: "center" }}>
                      <td style={{ textAlign: "left", padding: "4px 8px 4px 0" }}>{event.label.replace(/^The shop sent/, "Were sent")}</td>
                      {cells[code].map((cell) => (
                        <td key={cell.offset} style={{ padding: "3px 6px", background: cell.clear ? "rgba(0, 168, 150, 0.2)" : undefined, textAlign: "left", opacity: cell.by_definition ? 0.45 : 1 }}
                            title={cell.by_definition ? "Not compared: those who left have no order after their last one, so nothing that follows an order can follow it either." : cell.points === null ? "Not compared" : `${cell.n_churned} left: ${pct(cell.churned)}; ${cell.n_active} stayed: ${pct(cell.active)}. ${cell.points > 0 ? "+" : ""}${cell.points} points; ${cell.clear ? "a clear difference" : "within what luck gives"}.`}>
                          {[{ share: cell.churned, colour: "var(--aito-teal)", opacity: 1 }, { share: cell.active, colour: "var(--text-muted)", opacity: 0.55 }].map((bar, i) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, margin: "1px 0" }}>
                              <span style={{ display: "block", height: 6, borderRadius: 2, background: bar.colour, opacity: bar.opacity, width: `${Math.max(1, ((bar.share ?? 0) / top) * 36)}px` }} />
                              <span style={{ fontSize: 11 }} className="card-sub">{pct(bar.share)}</span>
                            </div>
                          ))}
                        </td>
                      ))}
                    </tr>
                  );
                }),
              ]
            ))}
          </tbody>
        </table>
      </div>
      <div className="card-sub" style={{ marginTop: 8, lineHeight: 1.5 }}>
        The data is monthly, so the order of events within a month is not known. Faded cells are not compared: after their last order, those who left have no orders, returns, deliveries or reviews, by definition.
        This shows what came before leaving, not what caused it.
      </div>
    </div>
  );
}
