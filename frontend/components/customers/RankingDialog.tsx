"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { PreferenceRanking, ProfilesSummary, SegmentView } from "@/lib/customer-profiles";
import PreferenceGraph from "@/components/customers/PreferenceGraph";

const GROUPS: [string, (id: string) => boolean][] = [
  ["Shopping", (id) => !id.includes(":")], ["Pets", (id) => id.startsWith("pet:")],
  ["Categories", (id) => id.startsWith("category:")], ["Brands", (id) => id.startsWith("brand:")],
];
// The ranking a shopping condition is a slice of; the dialog opens on it.
const RANKING_OF: Record<string, string> = { offer: "offer", price: "cheaper", rating: "rated" };

/**
 * The customers ranked by how much they prefer something (discounts, dogs, a category, a brand), and where the segment sits in that
 * ranking. It opens behind the "?" beside the segment name; the preference is chosen here, so the page itself has one control.
 */
export default function RankingDialog({ summary, view }: { summary: ProfilesSummary; view: SegmentView }) {
  const slice = view.conditions.map((c) => RANKING_OF[c.split(":")[0]]).find(Boolean);
  const [variable, setVariable] = useState(slice ?? "offer");
  const [ranked, setRanked] = useState<PreferenceRanking | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = [`var=${encodeURIComponent(variable)}`, ...view.conditions.map((c) => `c=${encodeURIComponent(c)}`)].join("&");
    apiFetch<PreferenceRanking>(`/api/customer-profiles/ranking?${query}`).then((r) => { setRanked(r); setError(null); }).catch((e) => setError(String(e)));
  }, [variable, view.key, view.conditions]);

  return (
    <div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 10 }}>
        <span className="card-sub">Preference</span>
        <select value={variable} onChange={(e) => setVariable(e.target.value)} style={{ font: "inherit", padding: "3px 8px", maxWidth: "min(100%, 380px)" }}>
          {GROUPS.map(([title, belongs]) => (
            <optgroup key={title} label={title}>
              {summary.ranking_variables.filter((v) => belongs(v.id)).map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </optgroup>
          ))}
        </select>
      </label>
      {error && <div className="card-sub">{error}</div>}
      {!ranked && !error && <div className="card-sub">Loading…</div>}
      {ranked && <PreferenceGraph ranked={ranked} selected={ranked.key ?? view.key} segmentShare={view.customers / summary.profiled} />}
      {ranked && view.conditions.length === 0 && (
        <div className="card-sub" style={{ marginTop: 6 }}>No segment is ticked, so this is the ranking of every profiled customer.</div>
      )}
    </div>
  );
}
