"use client";

import Link from "next/link";
import { useEffect } from "react";

import { highlightQuery } from "@/lib/highlight-query";
import { reviewsPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import { Card, LiftList, NoClearEffect, Threshold, fmt, useSection } from "@/components/shop-analytics/LiftParts";
import type { ReviewsReplyEffect, ShopLiftRow, ShopLiftSection } from "@/lib/types";


/**
 * Reviews (ADR 0039): what a product's stars and a customer's reviews go with,
 * each a `_relate` lift with its interval (Patterns' machinery). A bad
 * experience is hidden; the shop sees it through stars, reviews and NPS answers,
 * so each section reads those. Data layer: `src/reviews_service.py`.
 */
export default function ReviewsPage() {
  usePagePanel(reviewsPanel(), {
    title: "Reviews",
    description: "What a product's stars and a customer's reviews go with: clicks, purchases, NPS and churn.",
    breadcrumb: "Reviews",
  });
  const { setPanel } = useShell();
  const clicked = useSection<ShopLiftSection>("/api/reviews?section=clicked");
  const purchased = useSection<ShopLiftSection>("/api/reviews?section=purchased");
  const nps = useSection<ShopLiftSection>("/api/reviews?section=nps");
  const churn = useSection<ShopLiftSection>("/api/reviews?section=churn");
  const reply = useSection<ReviewsReplyEffect>("/api/reviews/reply-effect");

  useEffect(() => {
    if (!purchased.data) return;
    const sent = [clicked.data, purchased.data, nps.data, churn.data].reduce((n, s) => n + (s?.queries_sent ?? 0), 0);
    setPanel({ ...reviewsPanel(sent), query: highlightQuery(purchased.data.example_query.body) });
  }, [clicked.data, purchased.data, nps.data, churn.data, setPanel]);

  const error = clicked.error ?? purchased.error ?? nps.error ?? churn.error ?? reply.error;
  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Reviews</div>
        <div className="page-desc">
          A bad experience with a product is hidden from the shop. It shows in stars, in reviews and in NPS answers,
          and those move what customers do next. Each row is a <code>_relate</code> lift with the counts behind it,
          shown when its interval clears 1 for the whole section.
        </div>
      </div>

      {error && <ErrorState title="Couldn't load Reviews" message={`Aito returned an error. ${error}`} command="./do load-data" />}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(380px, 100%), 1fr))", gap: 16 }}>
        <Card title="Stars and clicks" sub="Over- or under-represented among clicks, by the stars the product had when it was shown">
          {clicked.data && <Lead text={starsLead(clicked.data, "clicks")} />}
          {clicked.data && <Body section={clicked.data} unit="clicks" />}
        </Card>
        <Card title="Stars and purchases" sub="The same for purchases">
          {purchased.data && <Lead text={starsLead(purchased.data, "purchases")} />}
          {purchased.data && <Body section={purchased.data} unit="purchases" />}
        </Card>
        <Card title="NPS detractors" sub="Over- or under-represented among detractors (0–6) of surveyed orders">
          {nps.data && <Lead text={npsLead(nps.data)} />}
          {nps.data && <Body section={nps.data} unit="detractors" />}
        </Card>
        <Card title="Churn after reviews" sub="Over- or under-represented among customer-months followed by churn within 3 months">
          {churn.data && <Lead text={churnLead(churn.data)} />}
          {churn.data && <Body section={churn.data} unit="churned customer-months" />}
          {reply.data && <ReplyEffect effect={reply.data} />}
        </Card>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="page-title" style={{ fontSize: 16, margin: "0 0 4px" }}>Demand and price</div>
        <div className="card-sub">
          Not read from the stars shop-wide: a 5-star product sells fewer units than a 4-star one, because a product
          earns its stars by selling. The comparison that isolates them is one product over its own months, in{" "}
          <Link href="/product/?tab=history">Product › History</Link>, and what a price change does at its real stars
          is the <Link href="/product/?tab=what-if">Product › What-if</Link>.
        </div>
      </div>
    </div>
  );
}


function Body({ section, unit }: { section: ShopLiftSection; unit: string }) {
  return (
    <>
      <LiftList rows={section.rows} unit={unit} />
      <NoClearEffect fields={section.fields_without_clear_effect} />
      <Threshold significance={section.significance}
                 designEffect={`clustering by customer (design effect ${section.clustering.design_effect.toFixed(1)})`} />
    </>
  );
}

function Lead({ text }: { text: string | null }) {
  if (!text) return null;
  return <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.45, margin: "0 0 12px" }}>{text}</div>;
}

const row = (s: ShopLiftSection, field: string, value: string): ShopLiftRow | undefined =>
  s.rows.find((r) => r.field === field && r.value === value);
const times = (lift: number) => `×${lift.toFixed(2)}`;

function starsLead(s: ShopLiftSection, noun: string): string | null {
  const low = row(s, "product_state.rating_band", "1-2");
  const high = row(s, "product_state.rating_band", "5");
  if (!low && !high) return null;
  const parts = [low && `at 1–2 stars ${noun} are ${times(low.lift)}`, high && `at 5 stars ${times(high.lift)}`];
  return `Stars move ${noun}: ${parts.filter(Boolean).join(", ")} of the average. Fix or pull what earns 1–2 stars.`;
}

function npsLead(s: ShopLiftSection): string | null {
  const wrote = row(s, "wrote_negative_review", "true");
  const stars = s.rows.find((r) => r.field === "product_state.rating_band");
  if (!wrote) return "No review or star signal clears the bar among NPS detractors.";
  return `Customers who wrote a 1–2 star review are ${times(wrote.lift)} as common among detractors` +
    (stars ? "" : ", but the stars of the order's product don't separate them") +
    ". A negative review is how the shop sees a bad experience; most detractors never write one.";
}

function churnLead(s: ShopLiftSection): string {
  return s.rows.length === 0
    ? "Having written a negative review, being replied to, or the latest NPS answer don't clearly separate who leaves within 3 months."
    : "Reviews and replies separate who leaves:";
}

function ReplyEffect({ effect }: { effect: ReviewsReplyEffect }) {
  const rate = (churned: number, months: number) => `${((churned / months) * 100).toFixed(1)} %`;
  const verdict = effect.verdict === "a tie"
    ? "a tie: the interval spans 1, so the data doesn't say whether replying helps"
    : effect.verdict === "fewer leave" ? "fewer leave when the shop replies" : "more leave when the shop replies";
  return (
    <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>Replying to a negative review: {verdict}</div>
      <div className="card-sub" style={{ marginTop: 4 }}>
        Churn within 3 months: {rate(effect.replied_churned, effect.replied_months)} replied
        ({fmt(effect.replied_churned)} of {fmt(effect.replied_months)} customer-months) against{" "}
        {rate(effect.unreplied_churned, effect.unreplied_months)} not replied
        ({fmt(effect.unreplied_churned)} of {fmt(effect.unreplied_months)}): replied ÷ not replied{" "}
        {times(effect.risk_ratio)}, interval {effect.interval_low.toFixed(2)}–{effect.interval_high.toFixed(2)},
        widened because one customer has several months.
      </div>
    </div>
  );
}
