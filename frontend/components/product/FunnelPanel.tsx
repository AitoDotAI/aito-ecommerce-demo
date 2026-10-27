"use client";

import HelpPopover from "@/components/prediction/HelpPopover";
import type { Funnel, ProductFunnel } from "@/lib/types";
import { money, monthLabel, pct } from "./labels";

/**
 * The right of the Product view, on the Funnel tab (ADR 0050): showings narrow to clicks and clicks to
 * purchases, and a purchase buys some units. Width is events (impressions, clicks, purchases), so a step is
 * never wider than the one before it; the purchase step's height is the units a purchase buys. The money (revenue,
 * profit) is a value, not a bar. Everything on the left that can be changed moves it: the offer, the list price,
 * stars, label, pictures, description, advertising. Each step shows today's value and the value with the changes.
 * Backend: src/product_funnel.py.
 */
export default function FunnelPanel({ funnel, loading }: { funnel: ProductFunnel | null; loading: boolean }) {
  if (!funnel) return <div className="card" aria-busy="true" style={{ height: 320, background: "var(--border-light)" }} />;
  const changed = funnel.changed.length > 0;
  const top = Math.max(funnel.now.impressions, funnel.asked.impressions, 1e-9);
  const height = Math.min(48, 10 * Math.max(funnel.units_per_purchase, 1));

  const stages = [
    { id: "impressions", label: "Impressions", unit: "showings", get: (f: Funnel) => f.impressions, rows: 1 },
    { id: "clicks", label: "Clicks", unit: "clicks", get: (f: Funnel) => f.clicks, rows: 1 },
    { id: "purchases", label: "Purchases", unit: "purchases", get: (f: Funnel) => f.purchases, rows: height / 10 },
  ];

  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)", opacity: loading ? 0.6 : 1, transition: "opacity .15s" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div className="card-sub">Funnel · {monthLabel(funnel.month)} · estimates from Aito</div>
        <HelpPopover label="How is the funnel estimated?" title="How the funnel is estimated">
          <p style={{ margin: "0 0 8px" }}>
            <strong>Impressions</strong> are the {funnel.mean_showings.toFixed(1)} showings a month the product had before
            {" "}{monthLabel(funnel.month)}, times Aito&apos;s <code>showings_index</code> for its offer and advertising: the ranker
            shows an offered or advertised product more. <strong>Clicks</strong> are the impressions times Aito&apos;s chance of a click
            (<code>_predict clicked</code> on the product&apos;s properties). <strong>Purchases</strong> are the clicks times Aito&apos;s chance that a click
            goes on to a purchase (<code>_predict purchased</code> given <code>clicked</code>), so a step is never wider than the one before.
          </p>
          <p style={{ margin: "0 0 8px" }}>
            Aito learns those over the ranked showings. The product&apos;s own history sets the level: it clicks {pct(funnel.own_ctr, 0)} of
            its showings and {pct(funnel.own_conversion, 0)} of its clicks go on to a purchase, and a purchase has bought
            {" "}{funnel.units_per_purchase.toFixed(2)} units (shoppers take several, and some re-order without a showing). The
            properties you change move those chances up or down from there. The step&apos;s height is the units a purchase buys.
          </p>
          <p style={{ margin: 0, color: "var(--text-muted)" }}>
            <strong>Profit</strong> is units times (price − cost), less the month&apos;s ad spend. Ad spend is our assumption until the shop
            declares its own: {Object.entries(funnel.ad_spend_assumed).map(([level, eur]) => `${level} ${money(eur)}`).join(", ")} a month.
            This is the first month after a change; the ranker&apos;s response to a better click-through comes later.
          </p>
        </HelpPopover>
      </div>

      <div className="page-title" style={{ fontSize: 28, margin: "4px 0 2px" }}>
        {changed && <span style={{ color: "var(--text-muted)", fontSize: 18, fontWeight: 400 }}>{money(funnel.now.profit_eur)} → </span>}
        {money(funnel.asked.profit_eur)}
      </div>
      <div style={{ fontSize: 14, color: "var(--text-2)", marginBottom: 14 }}>
        profit a month{changed && <> · {delta(funnel.asked.profit_eur, funnel.now.profit_eur)} with your changes</>}
      </div>

      {stages.map((stage) => {
        const now = stage.get(funnel.now), asked = stage.get(funnel.asked);
        const rowHeight = stage.rows * 10;
        return (
          <div key={stage.id} style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
              <span style={{ fontWeight: 600 }}>{stage.label}</span>
              <span style={{ fontFamily: "var(--mono)" }}>
                {changed && <span style={{ color: "var(--text-muted)" }}>{now.toFixed(1)} → </span>}{asked.toFixed(1)}
                {changed && <span style={{ color: asked >= now ? "var(--green)" : "var(--red)" }}> {delta(asked, now)}</span>}
              </span>
            </div>
            <Bar value={asked} top={top} height={rowHeight} color="var(--cta)" />
            {changed && <Bar value={now} top={top} height={4} color="var(--border)" thin />}
            {stage.id === "clicks" && <div className="card-sub">click-through {pct(funnel.asked.ctr, 0)} of showings</div>}
            {stage.id === "purchases" && (
              <div className="card-sub">
                {pct(funnel.asked.clicks ? funnel.asked.purchases / funnel.asked.clicks : 0, 0)} of clicks · height: {funnel.units_per_purchase.toFixed(2)} units
                a purchase = <strong>{funnel.asked.units.toFixed(1)} units</strong>
                {changed && <> (was {funnel.now.units.toFixed(1)})</>}
              </div>
            )}
          </div>
        );
      })}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 10, margin: "14px 0 6px" }}>
        <Value label="Price paid" now={funnel.now.price_eur} asked={funnel.asked.price_eur} changed={changed} />
        <Value label="Revenue" now={funnel.now.revenue_eur} asked={funnel.asked.revenue_eur} changed={changed} />
        <Value label="Gross profit" now={funnel.now.gross_profit_eur} asked={funnel.asked.gross_profit_eur} changed={changed} />
        {(funnel.asked.ad_spend_eur > 0 || funnel.now.ad_spend_eur > 0) && (
          <Value label="Advertising (assumed)" now={funnel.now.ad_spend_eur} asked={funnel.asked.ad_spend_eur} changed={changed} />
        )}
        <Value label="Profit" now={funnel.now.profit_eur} asked={funnel.asked.profit_eur} changed={changed} strong />
      </div>

      <div className="card-sub" style={{ marginTop: 8 }}>
        {funnel.last_month.showings !== undefined && <>{monthLabel(funnel.month)} itself: {funnel.last_month.showings} showings, {funnel.last_month.units} sold. </>}
        Showings estimated from {funnel.showings_support} earlier months.
      </div>
      {funnel.no_data && <div role="status" className="card-sub" style={{ marginTop: 6, color: "var(--red)" }}>{funnel.no_data}</div>}
      {funnel.check_units !== null && (
        <div role="status" className="card-sub" style={{ marginTop: 6, color: funnel.check_ok ? undefined : "var(--red)" }}>
          {funnel.check_ok
            ? <>Cross-check: units by price give {funnel.check_units.toFixed(1)}, within 25 % of the funnel&apos;s {funnel.asked.units.toFixed(1)}.</>
            : <>The two routes disagree: units by price give {funnel.check_units.toFixed(1)}, the funnel {funnel.asked.units.toFixed(1)}.
                Treat the units as indicative.</>}
        </div>
      )}
    </div>
  );
}

/** A money value for the month, with today's beside it when something is changed. */
function Value({ label, now, asked, changed, strong }: { label: string; now: number; asked: number; changed: boolean; strong?: boolean }) {
  return (
    <div>
      <div className="card-sub">{label}</div>
      <div style={{ fontFamily: "var(--mono)", fontSize: strong ? 16 : 14, fontWeight: strong ? 700 : 500, whiteSpace: "nowrap",
                    color: asked < 0 ? "var(--red)" : undefined }}>
        {money(asked)}
      </div>
      {changed && Math.abs(asked - now) > 0.005 && <div className="card-sub" style={{ whiteSpace: "nowrap" }}>was {money(now)}</div>}
    </div>
  );
}

function Bar({ value, top, height, color, thin }: { value: number; top: number; height: number; color: string; thin?: boolean }) {
  const width = Math.min(100, (Math.abs(value) / top) * 100);
  return (
    <div style={{ height, background: "var(--border-light)", borderRadius: 4, marginTop: thin ? 2 : 4 }}>
      <div style={{ width: `${width}%`, height: "100%", background: color, borderRadius: 4 }} />
    </div>
  );
}

function delta(a: number, b: number): string {
  if (!b) return "";
  return `${a >= b ? "+" : "−"}${Math.abs((a / b - 1) * 100).toFixed(0)} %`;
}
