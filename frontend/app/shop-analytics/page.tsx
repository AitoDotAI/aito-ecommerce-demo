"use client";

import { Suspense, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { shopAnalyticsPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import { useUrlState } from "@/lib/use-url-state";
import type { ShopAnalyticsResponse, ShopBasketPair, ShopLiftRow, ShopSearchWordRow } from "@/lib/types";


/**
 * Shop analytics — the owner's side of ADR 0031: what goes with a click
 * and a purchase, who buys what and when, baskets, and search words.
 * Data layer: `src/shop_analytics_service.py`. The KPI and the "who/when"
 * live in the URL (`?kpi=clicked&who=grain-free`).
 */
function ShopAnalyticsView() {
  usePagePanel(shopAnalyticsPanel(), {
    title: "Shop analytics",
    description: "What goes with clicks and purchases, who buys what and when, baskets and search words.",
    breadcrumb: "Shop analytics",
  });

  const { setPanel } = useShell();
  const [kpi, setKpi] = useUrlState("kpi", "purchased");
  const [who, setWho] = useUrlState("who", "summer");
  const [data, setData] = useState<ShopAnalyticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Only the request for the state now in the URL may update the page.
    let current = true;
    setError(null);
    setData(null);
    const query = new URLSearchParams({ kpi, who });
    apiFetch<ShopAnalyticsResponse>(`/api/shop-analytics?${query}`).then((res) => {
      if (!current) return;
      setData(res);
      setPanel({ ...shopAnalyticsPanel(res.last_query.of), query: highlightQuery(res.last_query.body) });
    }, (e) => {
      if (current) setError(String(e));
    });
    return () => { current = false; };
  }, [kpi, who, setPanel]);

  const kpiNoun = kpi === "clicked" ? "clicks" : "purchases";
  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Shop analytics</div>
        <div className="page-desc">
          The patterns behind the shop, each a <code>_relate</code> lift with the counts behind it and a 95 %
          interval. A lift whose interval includes 1 is not shown.
        </div>
      </div>

      {error && (
        <ErrorState title="Couldn't load Shop analytics" message={`Aito returned an error. ${error}`} command="./do load-data" />
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 16 }}>
        <Card title={`What goes with ${kpiNoun}`}
              sub={`Over- or under-represented among ${kpiNoun}, against all impressions`}
              controls={
                <div style={{ display: "flex", gap: 6 }}>
                  {["purchased", "clicked"].map((k) => (
                    <button key={k} id={`kpi-${k}`} className={`customer-chip${kpi === k ? " selected" : ""}`}
                            onClick={() => setKpi(k)}>
                      {k === "clicked" ? "Clicks" : "Purchases"}
                    </button>
                  ))}
                </div>
              }>
          {data && <LiftList rows={data.funnel_rows} unit={kpiNoun} />}
          {data && <NoEffect fields={data.funnel_fields_without_effect} />}
        </Card>

        <Card title="Who buys what, and when" sub="Categories and dietary lines over- or under-represented in a group's order lines"
              controls={
                <select id="who-picker" className="search-input" style={{ paddingLeft: 12, width: "auto" }}
                        value={who} onChange={(e) => setWho(e.target.value)}>
                  {groupOptions(data?.who_options ?? [{ id: who, label: who, group: "" }]).map(([group, options]) => (
                    <optgroup key={group} label={group}>
                      {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </optgroup>
                  ))}
                </select>
              }>
          {data && <LiftList rows={data.who_rows} unit="order lines" />}
          {data && <NoEffect fields={data.who_fields_without_effect} />}
        </Card>

        <Card title="Baskets" sub="Category pairs in the same order more (or less) often than chance">
          {data && <BasketList pairs={data.basket_pairs} />}
          <a href="/basket-rules/" style={{ fontSize: 13 }}>Rules with confidence and support in Basket Rules →</a>
        </Card>

        <Card title="Search words" sub="Words whose searches end in a purchase more or less often than the average search">
          {data && <SearchWordList words={data.search_words} />}
        </Card>
      </div>
    </div>
  );
}


const FIELD_LABELS: Record<string, string> = {
  "product_sku.rating_band": "rating", "product_sku.category": "category", "product_sku.dietary": "dietary line",
  customer_segment: "segment", customer_lifestyle: "lifestyle", customer_diet_rule: "diet rule",
  just_bought: "in their last order", surface: "surface",
};
const fieldLabel = (field: string) => FIELD_LABELS[field] ?? field;

function valueLabel(row: ShopLiftRow): string {
  if (row.field === "just_bought") return row.value === "true" ? "yes" : "no";
  if (row.field === "product_sku.rating_band") return row.value === "unrated" ? "unrated" : `${row.value.replace("-", "–")} stars`;
  return row.value.replace(/[_-]/g, " ");
}

function LiftList({ rows, unit }: { rows: ShopLiftRow[]; unit: string }) {
  if (rows.length === 0) return <div className="card-sub">No lift with an interval clear of 1.</div>;
  return (
    <>
      {rows.map((r) => (
        <Row key={`${r.field}-${r.value}`} lift={r.lift} low={r.interval_low} high={r.interval_high}
             label={<><span style={{ color: "var(--text-muted)" }}>{fieldLabel(r.field)}</span> = {valueLabel(r)}</>}
             counts={`${fmt(r.rows_with_value)} of ${fmt(r.condition_rows)} ${unit}`} />
      ))}
    </>
  );
}

// Strongest first on both sides: the pairs bought together, then the ones kept apart.
function BasketList({ pairs }: { pairs: ShopBasketPair[] }) {
  const together = pairs.filter((p) => p.lift > 1).slice(0, 8);
  const apart = pairs.filter((p) => p.lift < 1).sort((a, b) => a.lift - b.lift).slice(0, 4);
  return (
    <>
      {[...together, ...apart].map((p) => (
        <Row key={`${p.first}-${p.second}`} lift={p.lift} low={p.interval_low} high={p.interval_high}
             label={<>{p.first} + {p.second}</>}
             counts={`${fmt(p.orders_with_both)} of ${fmt(p.orders_with_first)} orders with ${p.first.toLowerCase()}`} />
      ))}
    </>
  );
}

function SearchWordList({ words }: { words: ShopAnalyticsResponse["search_words"] }) {
  const average = words.search_purchases / words.search_impressions;
  const above = words.rows.filter((w) => w.lift > 1).slice(0, 8);
  const below = words.rows.filter((w) => w.lift < 1).sort((a, b) => a.lift - b.lift).slice(0, 5);
  const row = (w: ShopSearchWordRow) => (
    <Row key={w.word} lift={w.lift} low={w.interval_low} high={w.interval_high} label={<>“{w.word}”</>}
         counts={`${fmt(w.purchases)} purchases of ${fmt(w.impressions)} (${pct(w.purchases / w.impressions)})`} />
  );
  return (
    <>
      <div className="card-sub" style={{ marginBottom: 8 }}>
        Average search: {pct(average)} of {fmt(words.search_impressions)} impressions bought ·{" "}
        {words.rows.length} of {words.words_checked} words differ
      </div>
      {above.map(row)}
      {below.length > 0 && <div className="card-sub" style={{ margin: "8px 0 4px" }}>Below average</div>}
      {below.map(row)}
    </>
  );
}

function NoEffect({ fields }: { fields: string[] }) {
  if (fields.length === 0) return null;
  return (
    <div className="card-sub" style={{ marginTop: 8 }}>
      Also checked, no effect: {fields.map(fieldLabel).join(", ")}
    </div>
  );
}

function Row({ label, lift, low, high, counts }: {
  label: React.ReactNode; lift: number; low: number; high: number; counts: string;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "5px 0", fontSize: 13 }}>
      <span>
        {label}
        <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {counts}</span>
      </span>
      <span style={{ whiteSpace: "nowrap" }}>
        <strong style={{ color: lift > 1 ? "var(--green)" : "var(--red)" }}>{lift.toFixed(2)}×</strong>
        <span style={{ color: "var(--text-muted)", fontSize: 11 }}> {low.toFixed(2)}–{high.toFixed(2)}</span>
      </span>
    </div>
  );
}

function Card({ title, sub, controls, children }: {
  title: string; sub: string; controls?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <div className="page-title" style={{ fontSize: 16, margin: "0 0 4px" }}>{title}</div>
        {controls}
      </div>
      <div className="card-sub" style={{ marginBottom: 12 }}>{sub} · lift, then its 95 % interval</div>
      {children}
    </div>
  );
}

function groupOptions(options: ShopAnalyticsResponse["who_options"]) {
  const groups = new Map<string, ShopAnalyticsResponse["who_options"]>();
  for (const o of options) groups.set(o.group, [...(groups.get(o.group) ?? []), o]);
  return [...groups.entries()];
}

const fmt = (n: number) => n.toLocaleString("en-US");
const pct = (share: number) => `${(share * 100).toFixed(1)} %`;


// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function ShopAnalyticsPage() {
  return (
    <Suspense>
      <ShopAnalyticsView />
    </Suspense>
  );
}
