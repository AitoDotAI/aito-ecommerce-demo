"use client";

import { useState } from "react";

import { apiFetch } from "@/lib/api";
import type { CustomerProfile } from "@/lib/customer-profiles";

interface Hit { customer_id: string; name: string; profiled: boolean }

/** One customer's profile, with what each trait is counted from. A customer who did not consent has none. */
export default function CustomerLookup() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  const search = (text: string) => {
    setQuery(text);
    if (text.trim().length < 2) { setHits([]); return; }
    apiFetch<{ customers: Hit[] }>(`/api/customer-profiles/customers?q=${encodeURIComponent(text)}`)
      .then((res) => setHits(res.customers)).catch((e) => setError(String(e)));
  };
  const open = (id: string) => apiFetch<CustomerProfile>(`/api/customer-profiles/customers/${id}`)
    .then((p) => { setProfile(p); setHits([]); }).catch((e) => setError(String(e)));

  return (
    <div className="card">
      <div className="card-title">Look up a customer</div>
      <input value={query} placeholder="Name or id of a profiled customer" onChange={(e) => search(e.target.value)}
        style={{ width: "100%", padding: "6px 10px", border: "1px solid var(--border)", borderRadius: 6, font: "inherit" }} />
      {error && <div className="card-sub">{error}</div>}
      {hits.map((h) => (
        <button key={h.customer_id} className="btn btn-ghost" onClick={() => open(h.customer_id)}
          style={{ display: "block", width: "100%", textAlign: "left", marginTop: 4 }}>
          {h.name} <span className="card-sub">{h.customer_id}{h.profiled ? "" : " · not profiled"}</span>
        </button>
      ))}
      {profile && <Profile p={profile} />}
    </div>
  );
}

function Profile({ p }: { p: CustomerProfile }) {
  if (!p.profiled) {
    return (
      <div style={{ marginTop: 12 }}>
        <strong>{p.customer_id}</strong>
        <div className="card-sub">No profile: this customer did not consent to behavioural profiling.</div>
      </div>
    );
  }
  const pct = (n?: number) => (n === undefined ? "" : `${Math.round(n * 100)} %`);
  return (
    <div style={{ marginTop: 12, lineHeight: 1.7 }}>
      <strong>{p.name}</strong> <span className="card-sub">{p.customer_id} · {p.lines} lines bought</span>
      <div>Buys on offer: <strong>{p.offer}</strong> <span className="card-sub">{p.offer_share !== undefined && `${pct(p.offer_share)} of their lines were on offer`}</span></div>
      <div>Prices: <strong>{p.price}</strong> <span className="card-sub">{p.cheaper_share !== undefined && `${pct(p.cheaper_share)} of their lines were in the cheaper half of their category`}</span></div>
      <div>Ratings: <strong>{p.rating}</strong> <span className="card-sub">{p.rating_gap != null && `${p.rating_gap > 0 ? "+" : ""}${p.rating_gap} stars against their categories' average`}</span></div>
      <div>Pets they buy for: <strong>{p.pets?.length ? p.pets.join(", ") : "none seen"}</strong></div>
      <div>Diets their pet&apos;s food is made for: <strong>{p.diets?.length ? p.diets.join(", ") : "none seen"}</strong></div>
    </div>
  );
}
