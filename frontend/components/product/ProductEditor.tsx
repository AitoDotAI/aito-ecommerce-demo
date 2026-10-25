"use client";

import Link from "next/link";
import { useState } from "react";

import HelpPopover from "@/components/prediction/HelpPopover";
import { ApiError, apiFetch, fmtEur } from "@/lib/api";
import { SANDBOX_MONTH, rememberLever, withSandbox } from "@/lib/sandbox";
import type { LeverResult, LeverStates, ProductStateRow, ProductView } from "@/lib/types";
import { BAND_LABEL, monthLabel, words } from "./labels";

const BANDS = ["none", "10-15", "15-20", "20+"];

/** The product's properties, on the left of the Product view (ADR 0041, the "edit the product" form):
 *  what it is (read-only), and what the owner can change: the offer and a review. In a sandbox
 *  (ADR 0043) a change writes next month's state, reads it back, and the page asks its estimates
 *  again (`onPulled`). Outside one, the offer is a preview: the numbers on the right show the chosen
 *  band, nothing is saved. Backend: src/product_levers.py. */
export default function ProductEditor({ view, sandbox, states, previewBand, onPreview, onPulled }: {
  view: ProductView;
  sandbox: string | null;
  states: LeverStates | null;
  previewBand: string | null;
  onPreview: (band: string | null) => void;
  onPulled: () => void;
}) {
  const { product: p, state: s, decision } = view;
  const live = !!sandbox && !!states;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LeverResult | null>(null);
  const [stars, setStars] = useState(5);
  const [text, setText] = useState("");
  const selected = live ? decision.current_band : (previewBand ?? decision.current_band);
  const priceOf = (band: string) => decision.margins.find((m) => m.band === band)?.price_eur ?? p.price_eur;

  const pull = async (path: string, body: object, lever: "offer" | "review") => {
    setBusy(true);
    setError(null);
    try {
      const read = await apiFetch<LeverResult>(path, { method: "POST", body: JSON.stringify(body) });
      setResult(read);
      rememberLever({ sku: p.sku, lever });
      if (lever === "review") setText("");
      onPulled();
    } catch (e) {
      setError(e instanceof ApiError ? e.serverMessage ?? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const chooseBand = (band: string) =>
    live ? pull("/api/levers/offer", { sku: p.sku, band }, "offer") : onPreview(band === decision.current_band ? null : band);

  return (
    <div className="card" style={{ borderColor: live ? "var(--orange-border)" : undefined }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div className="card-title" style={{ margin: 0 }}>The product · {monthLabel(view.month)}</div>
        <HelpPopover label="What can I change here?" title="What can I change here?">
          <p style={{ margin: "0 0 8px" }}>
            <strong>The offer</strong> and <strong>a review</strong> are the two things the shop data shows moving
            purchases, so they are what you can change. {live
              ? "In this sandbox a change writes next month's state, reads it back from the database, and the numbers on the right are asked again."
              : "Outside a sandbox the offer is a preview: the numbers on the right show the band you pick, and nothing is saved. Open a sandbox to write it."}
          </p>
          <p style={{ margin: "0 0 8px" }}>
            The name, brand, category and list price are read-only here. Changing them is the catalogue manager&apos;s
            job (ADR 0046, not built).
          </p>
          <p style={{ margin: 0, color: "var(--text-muted)" }}>
            An existing product&apos;s own history dominates its estimates, so editing its properties would move them
            little. A new product with no history is where its properties matter most.
          </p>
        </HelpPopover>
      </div>

      <div style={{ margin: "10px 0", fontSize: 13, display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px" }}>
        <span className="card-sub">Name</span><strong>{p.name}</strong>
        <span className="card-sub">Brand</span><span>{p.brand}</span>
        <span className="card-sub">Pet</span><span>{words(p.pet_type)}</span>
        <span className="card-sub">Category</span><span>{words(p.category)}</span>
        <span className="card-sub">List price</span><span>{fmtEur(p.price_eur, 2)}</span>
        <span className="card-sub">Cost</span><span>{fmtEur(p.unit_cost_eur, 2)}</span>
        <span className="card-sub">Stars</span>
        <span>{starsLabel(s.rating_band)} · {s.reviews} review{s.reviews === 1 ? "" : "s"}</span>
        <span className="card-sub">This month</span>
        <span>{[`sold ${s.units_sold}`, s.age, ...(s.rival_launched ? ["a rival launched recently"] : []),
                ...(s.price_change === "rise" ? ["after a price rise"] : [])].join(" · ")}</span>
      </div>

      <div style={{ fontSize: 13, fontWeight: 600, margin: "12px 0 6px" }}>Offer{!live && <span className="card-sub" style={{ fontWeight: 400 }}> · preview</span>}</div>
      <div role="group" aria-label="Offer" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {BANDS.map((band) => (
          <button key={band} type="button" disabled={busy} aria-pressed={selected === band}
                  className={`btn${selected === band ? "" : " btn-ghost"}`}
                  title={band === decision.current_band ? "Its offer this month" : undefined}
                  onClick={() => chooseBand(band)}>
            {band === "none" ? "No offer" : BAND_LABEL[band]}
          </button>
        ))}
      </div>
      <div className="card-sub" style={{ marginTop: 6 }}>
        Price {fmtEur(priceOf(selected), 2)}: list less the band&apos;s typical discount
        {selected !== decision.current_band && !live && <> · now {BAND_LABEL[decision.current_band].toLowerCase()}, {fmtEur(priceOf(decision.current_band), 2)}</>}.
      </div>

      {live && (
        <>
          <form style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 14 }}
                onSubmit={(e) => { e.preventDefault(); pull("/api/levers/review", { sku: p.sku, stars, text }, "review"); }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Review:</span>
            <select aria-label="Stars" className="search-input" style={{ width: "auto", paddingLeft: 8 }}
                    value={stars} onChange={(e) => setStars(Number(e.target.value))}>
              {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{"★".repeat(n)}</option>)}
            </select>
            <input className="search-input" style={{ flex: 1, minWidth: 140, paddingLeft: 8 }} aria-label="Review text"
                   placeholder="What the customer says" value={text} onChange={(e) => setText(e.target.value)} />
            <button className="btn" type="submit" disabled={busy || !text.trim()}>Add review</button>
          </form>
          <div className="card-sub" style={{ marginTop: 10 }}>
            {states?.next ? <>May now: {describe(states.next)}.</> : <>No May state yet; April: {describe(states!.april)}.</>}
          </div>
        </>
      )}
      {error && <div style={{ color: "var(--red)", fontSize: 13, marginTop: 8 }}>{error}</div>}
      {result && (
        <div style={{ fontSize: 13, marginTop: 10 }}>
          <strong>Read back from the sandbox:</strong> May 2026, {describe(result.state)}.
          {result.lever === "review" && (result.rating_band_changed
            ? <> Its star band changed: {starsLabel(result.rating_band_before)} → {starsLabel(result.state.rating_band)}
                {" "}({result.reviews} reviews, average {result.avg_rating?.toFixed(2)}).</>
            : <> No change in its star band: still {starsLabel(result.state.rating_band)}
                {" "}({result.reviews} reviews, average {result.avg_rating?.toFixed(2)}).</>)}
        </div>
      )}
      {live && sandbox && (
        <div className="card-sub" style={{ marginTop: 10 }}>
          <Link href={withSandbox(`/shop/?shopper=paivi&month=${SANDBOX_MONTH}`, sandbox)}>See the Shop react →</Link>
        </div>
      )}
    </div>
  );
}

function describe(s: ProductStateRow): string {
  const offer = s.discount_band === "none" ? "at list price" : `${BAND_LABEL[s.discount_band]}`;
  return `${offer}, ${fmtEur(s.price_eur, 2)}, ${starsLabel(s.rating_band)}`;
}

function starsLabel(band: string): string {
  return band === "unrated" ? "no stars yet" : `${band} stars`;
}
