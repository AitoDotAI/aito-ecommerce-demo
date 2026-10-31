"use client";

import { TRAITS, TRAIT_TITLE, keyOf, type ProfilesSummary } from "@/lib/customer-profiles";

/** The segment every pane of the page shows, as a drop-down: everyone, then each variable's variations. */
export default function SegmentPicker({ summary, selected, onSelect }: {
  summary: ProfilesSummary; selected: string; onSelect: (key: string) => void;
}) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 14 }}>
      <span className="card-sub">Segment</span>
      <select value={selected} onChange={(e) => onSelect(e.target.value)}
        style={{ font: "inherit", fontWeight: 600, padding: "5px 10px", borderRadius: 6, border: "1px solid var(--border)", minWidth: 280 }}>
        <option value="all">Everyone profiled · {summary.profiled.toLocaleString("fi-FI")} customers</option>
        {TRAITS.map((trait) => (
          <optgroup key={trait} label={TRAIT_TITLE[trait]}>
            {summary.by_trait[trait].filter((s) => s.profit_per_customer_eur !== undefined).map((s) => (
              <option key={keyOf(trait, s)} value={keyOf(trait, s)}>{TRAIT_TITLE[trait]}: {s.value} · {s.customers.toLocaleString("fi-FI")}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}
