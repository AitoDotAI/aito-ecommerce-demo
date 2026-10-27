"use client";

import HelpPopover from "@/components/prediction/HelpPopover";
import { fmtEur } from "@/lib/api";
import type { Funnel, ProductFunnel } from "@/lib/types";
import { monthLabel, pct } from "./labels";

interface Step { id: string; label: string; unit: string; get: (f: Funnel) => number; show: (v: number) => string }

const STEPS: Step[] = [
  { id: "impressions", label: "Impressions", unit: "showings", get: (f) => f.impressions, show: (v) => v.toFixed(1) },
  { id: "clicks", label: "Clicks", unit: "clicks", get: (f) => f.clicks, show: (v) => v.toFixed(1) },
  { id: "purchases", label: "Purchases", unit: "units", get: (f) => f.purchases, show: (v) => v.toFixed(1) },
  { id: "profit", label: "Profit", unit: "after ad spend", get: (f) => f.profit_eur, show: (v) => fmtEur(v, 0) },
];

/**
 * The right of the Product view, on the Funnel tab (ADR 0050): impressions → clicks → purchases → profit for
 * a month, as the product's properties say. Everything on the left that can be changed moves it: the offer, the
 * list price, stars, label, pictures, description, advertising. Each step shows today's value and the value
 * with the changes. Backend: src/product_funnel.py.
 */
export default function FunnelPanel({ funnel, loading }: { funnel: ProductFunnel | null; loading: boolean }) {
  if (!funnel) return <div className="card" aria-busy="true" style={{ height: 320, background: "var(--border-light)" }} />;
  const changed = funnel.changed.length > 0;
  const reach = Math.max(...STEPS.filter((s) => s.id !== "profit").flatMap((s) => [s.get(funnel.now), s.get(funnel.asked)]), 1e-9);
  const profitReach = Math.max(Math.abs(funnel.now.profit_eur), Math.abs(funnel.asked.profit_eur), 1e-9);

  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)", opacity: loading ? 0.6 : 1, transition: "opacity .15s" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div className="card-sub">Funnel · {monthLabel(funnel.month)} · estimates from Aito</div>
        <HelpPopover label="How is the funnel estimated?" title="How the funnel is estimated">
          <p style={{ margin: "0 0 8px" }}>
            <strong>Impressions</strong> are the {funnel.mean_showings.toFixed(1)} showings a month the product had before
            {" "}{monthLabel(funnel.month)}, times Aito&apos;s <code>showings_index</code> for its offer and advertising: the ranker
            shows an offered or advertised product more. <strong>Clicks</strong> and <strong>purchases</strong> are impressions times
            the chance a showing ends in one (<code>_predict clicked / purchased</code> on the product&apos;s properties).
            <strong> Profit</strong> is purchases times (price − cost), less the month&apos;s ad spend.
          </p>
          <p style={{ margin: "0 0 8px" }}>
            Purchases are counted from the showing, as the shop&apos;s data counts them, not as clicks times a conversion,
            and they are units: this product has sold {funnel.units_per_purchase.toFixed(2)} units for each showing that ended
            in a purchase (shoppers take several, and some re-order without a showing).
          </p>
          <p style={{ margin: 0, color: "var(--text-muted)" }}>
            Ad spend is our assumption until the shop declares its own: {Object.entries(funnel.ad_spend_assumed)
              .map(([level, eur]) => `${level} ${fmtEur(eur, 0)}`).join(", ")} a month. This is the first month after a change; the
            ranker&apos;s response to a better click-through comes later.
          </p>
        </HelpPopover>
      </div>

      <div className="page-title" style={{ fontSize: 28, margin: "4px 0 2px" }}>
        {changed && <span style={{ color: "var(--text-muted)", fontSize: 18, fontWeight: 400 }}>{fmtEur(funnel.now.profit_eur, 0)} → </span>}
        {fmtEur(funnel.asked.profit_eur, 0)}
      </div>
      <div style={{ fontSize: 14, color: "var(--text-2)", marginBottom: 14 }}>
        profit a month{changed && <> · {delta(funnel.asked.profit_eur, funnel.now.profit_eur)} with your changes</>}
      </div>

      {STEPS.map((step) => {
        const now = step.get(funnel.now), asked = step.get(funnel.asked);
        const top = step.id === "profit" ? profitReach : reach;
        return (
          <div key={step.id} style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span style={{ fontWeight: 600 }}>{step.label}</span>
              <span style={{ fontFamily: "var(--mono)" }}>
                {changed && <span style={{ color: "var(--text-muted)" }}>{step.show(now)} → </span>}{step.show(asked)}
                {changed && <span style={{ color: asked >= now ? "var(--green)" : "var(--red)" }}> {delta(asked, now)}</span>}
              </span>
            </div>
            <Bar value={asked} top={top} color={asked < 0 ? "var(--red)" : "var(--cta)"} />
            {changed && <Bar value={now} top={top} color="var(--border)" thin />}
            {step.id === "clicks" && <div className="card-sub">click-through {pct(funnel.asked.ctr, 0)} of showings</div>}
            {step.id === "purchases" && <div className="card-sub">{pct(funnel.asked.purchase_rate, 1)} of showings end in a purchase · price {fmtEur(funnel.asked.price_eur, 2)}</div>}
            {step.id === "profit" && funnel.asked.ad_spend_eur > 0 && <div className="card-sub">after {fmtEur(funnel.asked.ad_spend_eur, 0)} of advertising (assumed)</div>}
          </div>
        );
      })}

      <div className="card-sub" style={{ marginTop: 8 }}>
        {funnel.last_month.showings !== undefined && <>{monthLabel(funnel.month)} itself: {funnel.last_month.showings} showings, {funnel.last_month.units} sold. </>}
        Showings estimated from {funnel.showings_support} earlier months.
      </div>
      {funnel.check_units !== null && (
        <div role="status" className="card-sub" style={{ marginTop: 6, color: funnel.check_ok ? undefined : "var(--red)" }}>
          {funnel.check_ok
            ? <>Cross-check: units by price give {funnel.check_units.toFixed(1)}, within 25 % of the funnel&apos;s {funnel.asked.purchases.toFixed(1)}.</>
            : <>The two routes disagree: units by price give {funnel.check_units.toFixed(1)}, the funnel {funnel.asked.purchases.toFixed(1)}.
                Treat the purchases as indicative.</>}
        </div>
      )}
    </div>
  );
}

function Bar({ value, top, color, thin }: { value: number; top: number; color: string; thin?: boolean }) {
  const width = Math.min(100, (Math.abs(value) / top) * 100);
  return (
    <div style={{ height: thin ? 4 : 10, background: "var(--border-light)", borderRadius: 4, marginTop: thin ? 2 : 4 }}>
      <div style={{ width: `${width}%`, height: "100%", background: color, borderRadius: 4 }} />
    </div>
  );
}

function delta(a: number, b: number): string {
  if (!b) return "";
  return `${a >= b ? "+" : "−"}${Math.abs((a / b - 1) * 100).toFixed(0)} %`;
}
