"use client";

import Link from "next/link";
import { useState } from "react";

import { ApiError, apiFetch, fmtEur } from "@/lib/api";
import { SANDBOX_MONTH, rememberLever, withSandbox } from "@/lib/sandbox";
import type { LeverResult, LeverStates, ProductStateRow } from "@/lib/types";
import { BAND_LABEL } from "./labels";

const BANDS = ["none", "10-15", "15-20", "20+"];

/** Pull a lever in the sandbox (ADR 0043): put the product on offer in May
 *  2026, or add a review. Each writes the product's May state in this
 *  sandbox, reads it back, and the page re-asks its estimates from what
 *  was read (`onPulled`). Backend: src/product_levers.py. */
export default function LeverPanel({ sku, states, sandbox, onPulled }: {
  sku: string;
  states: LeverStates;
  sandbox: string;
  onPulled: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LeverResult | null>(null);
  const [stars, setStars] = useState(5);
  const [text, setText] = useState("");
  const may = states.next;

  const pull = async (path: string, body: object, lever: "offer" | "review") => {
    setBusy(true);
    setError(null);
    try {
      const read = await apiFetch<LeverResult>(path, { method: "POST", body: JSON.stringify(body) });
      setResult(read);
      rememberLever({ sku, lever });
      if (lever === "review") setText("");
      onPulled();
    } catch (e) {
      setError(e instanceof ApiError ? e.serverMessage ?? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ borderColor: "var(--orange-border)" }}>
      <div className="card-title">Pull a lever: May 2026, in this sandbox</div>
      <div className="card-sub" style={{ marginBottom: 8 }}>
        {may ? <>May now: {describe(may)}.</> : <>No May state yet; April: {describe(states.april)}.</>}
        {" "}A lever writes the product&apos;s May state, reads it back, and the estimates below are asked again.
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Offer:</span>
        {BANDS.map((band) => (
          <button key={band} type="button" disabled={busy}
                  className={`btn${may?.discount_band === band ? "" : " btn-ghost"}`}
                  onClick={() => pull("/api/levers/offer", { sku, band }, "offer")}>
            {band === "none" ? "No offer" : BAND_LABEL[band]}
          </button>
        ))}
      </div>

      <form style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}
            onSubmit={(e) => { e.preventDefault(); pull("/api/levers/review", { sku, stars, text }, "review"); }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Review:</span>
        <select aria-label="Stars" className="search-input" style={{ width: "auto", paddingLeft: 8 }}
                value={stars} onChange={(e) => setStars(Number(e.target.value))}>
          {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{"★".repeat(n)}</option>)}
        </select>
        <input className="search-input" style={{ flex: 1, minWidth: 160, paddingLeft: 8 }} aria-label="Review text"
               placeholder="What the customer says" value={text} onChange={(e) => setText(e.target.value)} />
        <button className="btn" type="submit" disabled={busy || !text.trim()}>Add review</button>
      </form>

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
      <div className="card-sub" style={{ marginTop: 10 }}>
        Next month&apos;s units follow the price only: Aito&apos;s <code>_estimate</code> can&apos;t take the
        discount band (it lives on the linked state), so the units what-if is at the offer&apos;s price.
        {" "}<Link href={withSandbox(`/shop/?shopper=paivi&month=${SANDBOX_MONTH}`, sandbox)}>
          See the Shop react →
        </Link>
      </div>
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
