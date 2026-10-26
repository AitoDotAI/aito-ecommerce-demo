"use client";

import HelpPopover from "@/components/prediction/HelpPopover";
import type { KpiFactor, KpiName, ProductKpis } from "@/lib/types";
import { BAND_LABEL, pct, words } from "./labels";

const COPY: Record<KpiName, { title: string; unit: string; done: string }> = {
  clicked: { title: "Clicks", unit: "click it", done: "clicked it" },
  purchased: { title: "Purchases", unit: "buy it", done: "bought it" },
};
const FIELD: Record<string, string> = {
  brand: "Brand", category: "Category", pet_type: "Pet", discount_band: "Offer", rating_band: "Stars",
  label: "Shop label", age: "Age", stock: "Stock", rival_launched: "Rival launched",
};
/** Lifts this close to 1 say nothing; they are folded into one line, as on the Shop's cards. */
const NEAR_ONE = 0.03;

/**
 * The right of the Product view, on the Clicks and Purchases tabs: the chance that a shopper shown a
 * product with these properties does it, and which of the properties it comes from. The properties
 * are the product's in the month, with whatever the owner has changed on the left; `baseline` is the
 * same without the changes, so the effect of an edit reads as a before and an after.
 * Backend: src/product_kpi.py, a `_predict` on impressions with the properties in the `where`.
 */
export default function KpiPanel({ kpi, current, baseline, loading }: {
  kpi: KpiName;
  current: ProductKpis;
  baseline: ProductKpis | null;
  loading: boolean;
}) {
  const e = current.estimates[kpi];
  const before = baseline?.estimates[kpi];
  const changed = current.changed.length > 0 && before !== undefined;
  const ranked = [...e.factors].sort((a, b) => Math.abs(Math.log(b.lift)) - Math.abs(Math.log(a.lift)));
  const strong = ranked.filter((f) => Math.abs(f.lift - 1) >= NEAR_ONE);
  const folded = ranked.length - strong.length;
  const reach = Math.max(1.5, ...strong.map((f) => Math.max(f.lift, 1 / f.lift)));

  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)", opacity: loading ? 0.6 : 1, transition: "opacity .15s" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div className="card-sub">{COPY[kpi].title} · by the product&apos;s properties · estimate from Aito</div>
        <HelpPopover label={`What is ${COPY[kpi].title.toLowerCase()} here?`} title={`${COPY[kpi].title}, by properties`}>
          <p style={{ margin: "0 0 8px" }}>
            Out of 100 times a product with <strong>these properties</strong> is shown to a shopper, this many end in {kpi === "clicked" ? "a click" : "a purchase"}.
            Aito reads it from the shop&apos;s logged showings (<code>_predict {kpi}</code>), with the brand, category, pet and this month&apos;s state
            (offer, stars, label, stock, rival) as evidence, and not the product itself.
          </p>
          <p style={{ margin: "0 0 8px" }}>
            Each row below is one property&apos;s lift: how many times more (or less) likely it makes {kpi === "clicked" ? "a click" : "a purchase"}
            than the average showing. They multiply with the base rate to give the number on top.
          </p>
          <p style={{ margin: 0, color: "var(--text-muted)" }}>
            Because the product itself is left out, this is what the <em>properties</em> are worth. The product&apos;s own record, shown
            below, can differ: that gap is what its name, price or luck add. Edit a property on the left and the numbers move.
          </p>
        </HelpPopover>
      </div>

      <div className="page-title" style={{ fontSize: 30, margin: "4px 0 2px" }}>
        {changed && <span style={{ color: "var(--text-muted)", fontSize: 18, fontWeight: 400 }}>{pct(before.p, 0)} → </span>}
        {pct(e.p, 0)}
      </div>
      <div style={{ fontSize: 14, color: "var(--text-2)", marginBottom: 14 }}>
        of shoppers shown a product like this {COPY[kpi].unit}
        {changed && <> · {e.p >= before.p ? "+" : "−"}{Math.abs((e.p / before.p - 1) * 100).toFixed(0)} % with your changes</>}
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", marginBottom: 14 }}>
        <Fact label="All showings" value={pct(e.base_p, 0)} sub="the average over the shop" />
        <Fact label="This product, so far"
              value={e.product_shown ? pct(e.product_hits / e.product_shown, 0) : "–"}
              sub={`${e.product_hits} of ${e.product_shown} showings`} />
      </div>

      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>What it comes from</div>
      {strong.map((f) => <FactorRow key={f.fields.join("+")} factor={f} reach={reach} edited={f.fields.some((n) => current.changed.includes(n))} />)}
      {folded > 0 && (
        <div className="card-sub" style={{ marginTop: 6 }}>
          + {folded} more {folded === 1 ? "property" : "properties"} within ×{(1 - NEAR_ONE).toFixed(2)}–×{(1 + NEAR_ONE).toFixed(2)}: no effect to speak of.
        </div>
      )}
      <div className="card-sub" style={{ marginTop: 10 }}>
        Estimates, and for ranking. {e.similar_shown > 0
          ? <>Products with exactly these properties were shown {e.similar_shown} times: {pct(e.similar_hits / e.similar_shown, 0)} {COPY[kpi].done}.</>
          : <>No product has exactly these properties, so there is nothing to compare with.</>}
      </div>
    </div>
  );
}

function Fact({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-val" style={{ fontSize: 18 }}>{value}</div>
      <div className="card-sub">{sub}</div>
    </div>
  );
}

/** One property's lift as a bar from the middle (×1): to the right it raises the chance, to the left it lowers it. */
function FactorRow({ factor, reach, edited }: { factor: KpiFactor; reach: number; edited: boolean }) {
  const logLift = Math.log(factor.lift), span = Math.log(reach);
  const half = Math.min(50, (Math.abs(logLift) / span) * 50);
  const up = factor.lift >= 1;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(110px, 1.2fr) 2fr 52px", alignItems: "center", gap: 8, fontSize: 13, padding: "3px 0" }}>
      <span style={{ fontWeight: edited ? 600 : 400 }}>
        {edited && <span title="You changed this" style={{ color: "var(--cta)" }}>● </span>}
        {factor.fields.map((n, i) => `${FIELD[n] ?? n}: ${valueLabel(n, factor.values[i])}`).join(" · ")}
      </span>
      <div style={{ position: "relative", height: 8, background: "var(--border-light)", borderRadius: 4 }}>
        <div style={{ position: "absolute", top: 0, bottom: 0, left: up ? "50%" : `${50 - half}%`, width: `${half}%`,
                      background: up ? "var(--accent)" : "var(--red)", borderRadius: 4 }} />
        <div style={{ position: "absolute", top: -2, bottom: -2, left: "50%", width: 1, background: "var(--text-muted)" }} />
      </div>
      <span style={{ fontFamily: "var(--mono)", textAlign: "right", color: up ? "var(--green)" : "var(--red)" }}>×{factor.lift.toFixed(2)}</span>
    </div>
  );
}

function valueLabel(field: string, value: string | boolean): string {
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (field === "discount_band") return BAND_LABEL[value]?.toLowerCase() ?? value;
  if (field === "rating_band") return value === "unrated" ? "no stars yet" : `${value} stars`;
  return words(value);
}
