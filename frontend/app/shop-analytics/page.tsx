"use client";

import { Suspense, useEffect } from "react";

import { highlightQuery } from "@/lib/highlight-query";
import { shopAnalyticsPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import NotFoundNotice from "@/components/shell/NotFoundNotice";
import { Card, LiftList, More, NoClearEffect, Row, Threshold, fmt, pct, useSection } from "@/components/shop-analytics/LiftParts";
import { useUrlState } from "@/lib/use-url-state";
import type { ShopBasketSection, ShopLiftSection, ShopSearchWordRow, ShopSearchWordSection } from "@/lib/types";


/**
 * Shop analytics — the owner's side of ADR 0031: what goes with a click
 * and a purchase, who buys what and when, baskets, and search words.
 * Data layer: `src/shop_analytics_service.py`, `src/basket_pairs.py`,
 * `src/search_words.py`. Each section has its own endpoint, so changing
 * the KPI re-asks only its section. The KPI and the "who/when" live in
 * the URL (`?kpi=clicked&who=grain-free`).
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
  const funnel = useSection<ShopLiftSection>(`/api/shop-analytics/funnel?kpi=${encodeURIComponent(kpi)}`);
  const group = useSection<ShopLiftSection>(`/api/shop-analytics/who?who=${encodeURIComponent(who)}`);
  const baskets = useSection<ShopBasketSection>("/api/shop-analytics/baskets");
  const words = useSection<ShopSearchWordSection>("/api/shop-analytics/search-words");

  useEffect(() => {
    if (!funnel.data) return;
    const sent = [funnel.data, group.data, baskets.data, words.data].reduce((n, s) => n + (s?.queries_sent ?? 0), 0);
    setPanel({ ...shopAnalyticsPanel(sent), query: highlightQuery(funnel.data.example_query.body) });
  }, [funnel.data, group.data, baskets.data, words.data, setPanel]);

  const error = funnel.error ?? group.error ?? baskets.error ?? words.error;
  const kpiNoun = kpi === "clicked" ? "clicks" : "purchases";
  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Shop analytics</div>
        <div className="page-desc">
          The patterns behind the shop, each a <code>_relate</code> lift with the counts behind it. A lift is shown
          when its interval clears 1 at 95 % for its whole section, with the interval widened because one
          customer&apos;s rows are not independent.
        </div>
      </div>

      {error && (
        <ErrorState title="Couldn't load Shop analytics" message={`Aito returned an error. ${error}`} command="./do load-data" />
      )}
      {funnel.badLink && <NotFoundNotice message={funnel.badLink} resetLabel="Show purchases" onReset={() => setKpi("purchased")} />}
      {group.badLink && <NotFoundNotice message={group.badLink} resetLabel="Show summer" onReset={() => setWho("summer")} />}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(380px, 100%), 1fr))", gap: 16 }}>
        <Card title={`What goes with ${kpiNoun}`} sub={`Over- or under-represented among ${kpiNoun}, against all impressions`}
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
          {funnel.data && <LiftSectionBody section={funnel.data} unit={kpiNoun} />}
        </Card>

        <Card title="Who buys what, and when" sub="Categories and dietary lines over- or under-represented in a group's order lines"
              controls={
                <select id="who-picker" className="search-input" style={{ paddingLeft: 12, width: "auto" }}
                        value={who} onChange={(e) => setWho(e.target.value)}>
                  {groupOptions(group.data?.options ?? [{ id: who, label: who, group: "" }]).map(([name, options]) => (
                    <optgroup key={name} label={name}>
                      {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </optgroup>
                  ))}
                </select>
              }>
          {group.data && <LiftSectionBody section={group.data} unit="order lines" />}
        </Card>

        <Card title="Baskets" sub="Category pairs in the same order more (or less) often than chance">
          {baskets.data && <BasketList section={baskets.data} />}
          <a href="/basket-rules/" style={{ fontSize: 13 }}>Rules with confidence and support in Basket Rules →</a>
        </Card>

        <Card title="Search words" sub="Words whose searches end in a purchase more or less often than the average search">
          {words.data && <SearchWordList section={words.data} />}
        </Card>
      </div>
    </div>
  );
}


function LiftSectionBody({ section, unit }: { section: ShopLiftSection; unit: string }) {
  return (
    <>
      <LiftList rows={section.rows} unit={unit} />
      <NoClearEffect fields={section.fields_without_clear_effect} />
      <Threshold significance={section.significance}
                 designEffect={`clustering by customer (design effect ${section.clustering.design_effect.toFixed(1)})`} />
    </>
  );
}

const TOGETHER_SHOWN = 8;
const APART_SHOWN = 4;

function BasketList({ section }: { section: ShopBasketSection }) {
  const together = section.pairs.filter((p) => p.lift > 1);
  const apart = section.pairs.filter((p) => p.lift < 1).sort((a, b) => a.lift - b.lift);
  const effects = Object.values(section.design_effects);
  const pair = (p: ShopBasketSection["pairs"][number]) => (
    <Row key={`${p.first}-${p.second}`} lift={p.lift} low={p.interval_low} high={p.interval_high}
         label={<>{p.first} + {p.second}</>}
         counts={`${fmt(p.orders_with_both)} of ${fmt(p.orders_with_first)} orders with ${p.first.toLowerCase()}`} />
  );
  return (
    <>
      <div className="card-sub" style={{ marginBottom: 8 }}>{section.pairs.length} pairs clear the bar</div>
      {together.slice(0, TOGETHER_SHOWN).map(pair)}
      <More count={together.length - TOGETHER_SHOWN} what="pairs bought together" />
      {apart.slice(0, APART_SHOWN).map(pair)}
      <More count={apart.length - APART_SHOWN} what="pairs kept apart" />
      <Threshold significance={section.significance}
                 designEffect={`clustering by customer (design effect ${Math.min(...effects).toFixed(1)}–${Math.max(...effects).toFixed(1)} by anchor)`} />
    </>
  );
}

const ABOVE_SHOWN = 8;
const BELOW_SHOWN = 5;
const NEVER_SHOWN = 4;

function SearchWordList({ section }: { section: ShopSearchWordSection }) {
  const average = section.search_purchases / section.search_impressions;
  const above = section.rows.filter((w) => w.lift > 1);
  const below = section.rows.filter((w) => w.lift < 1).sort((a, b) => a.lift - b.lift);
  const row = (w: ShopSearchWordRow) => (
    <Row key={w.word} lift={w.lift} low={w.interval_low} high={w.interval_high} label={<>“{w.word}”</>}
         counts={`${fmt(w.purchases)} purchases of ${fmt(w.impressions)} (${pct(w.purchases / w.impressions)})`} />
  );
  return (
    <>
      <div className="card-sub" style={{ marginBottom: 8 }}>
        Average search: {pct(average)} of {fmt(section.search_impressions)} impressions bought ·{" "}
        {section.rows.length} of {section.significance.tested} testable words differ ({section.words} words and phrases in all)
      </div>
      {above.slice(0, ABOVE_SHOWN).map(row)}
      <More count={above.length - ABOVE_SHOWN} what="words above average" />
      {below.length > 0 && <div className="card-sub" style={{ margin: "8px 0 4px" }}>Below average</div>}
      {below.slice(0, BELOW_SHOWN).map(row)}
      <More count={below.length - BELOW_SHOWN} what="words below average" />
      {section.never_bought.length > 0 && (
        <div className="card-sub" style={{ marginTop: 8 }}>
          Searched, never bought (no purchases to test a lift on):{" "}
          {section.never_bought.slice(0, NEVER_SHOWN)
            .map((w) => `“${w.word}” ${fmt(w.impressions)} impressions, ~${w.expected_purchases} expected`).join("; ")}
          {section.never_bought.length > NEVER_SHOWN && `; +${section.never_bought.length - NEVER_SHOWN} more`}
        </div>
      )}
      <Threshold significance={section.significance}
                 designEffect={`clustering by customer (design effect ${section.clustering.design_effect.toFixed(1)})`} />
    </>
  );
}

function groupOptions(options: ShopLiftSection["options"]) {
  const groups = new Map<string, ShopLiftSection["options"]>();
  for (const o of options) groups.set(o.group, [...(groups.get(o.group) ?? []), o]);
  return [...groups.entries()];
}


// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function ShopAnalyticsPage() {
  return (
    <Suspense>
      <ShopAnalyticsView />
    </Suspense>
  );
}
