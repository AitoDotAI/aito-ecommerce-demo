"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import type { ShopperProfile as Profile } from "@/lib/types";
import { monthLabel, words } from "@/components/product/labels";

/** What the shop knows about the shopper, as of the month: what they declared, their last basket and their
 *  purchase history. It is the evidence behind "Picked for you", shown in a "?" popover. Read, not predicted
 *  (src/shop_profile.py). */
export default function ShopperProfile({ shopper, month }: { shopper: string; month: string }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    setProfile(null);
    setError(null);
    apiFetch<Profile>(`/api/shop/profile?shopper=${shopper}&month=${month}`)
      .then((p) => { if (current) setProfile(p); }, (e) => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [shopper, month]);

  if (error) return <div style={{ color: "var(--red)" }}>Couldn&apos;t load the profile: {error}</div>;
  if (!profile) return <div style={{ height: 80, background: "var(--border-light)", borderRadius: 4 }} />;
  const chips = [
    `${words(profile.pets)} ${profile.pets_declared ? "(declared)" : "(read from their orders)"}`,
    ...(profile.diet ? [`diet: ${profile.diet}`] : []),
    ...Object.entries(profile.facts).map(([k, v]) =>
      typeof v === "boolean" ? (v ? words(k) : `not ${words(k)}`) : `${words(k)}: ${v}`),
  ];
  return (
    <div>
      <div style={{ color: "var(--text-2)", marginBottom: 8 }}>{profile.story}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
        {chips.map((c) => <span key={c} className="pdp-fact">{c}</span>)}
      </div>

      <div style={{ fontWeight: 600 }}>Last basket {profile.last_basket && <span className="card-sub">· {monthLabel(profile.last_basket.month)}</span>}</div>
      {profile.last_basket
        ? <ul style={{ margin: "4px 0 10px", paddingLeft: 18 }}>{profile.last_basket.items.map((n, i) => <li key={i}>{n}</li>)}</ul>
        : <div className="card-sub" style={{ margin: "4px 0 10px" }}>No order before {monthLabel(month)}: a cold start.</div>}

      <div style={{ fontWeight: 600 }}>
        Purchase history <span className="card-sub">· {profile.orders_total} order{profile.orders_total === 1 ? "" : "s"}, {fmtEur(profile.spent_eur, 2)}</span>
      </div>
      {profile.history.map((o) => (
        <div key={o.month + o.items.join()} style={{ padding: "4px 0", borderTop: "1px solid var(--border-light)" }}>
          <span className="card-sub">{monthLabel(o.month)}{o.total_eur !== null && <> · {fmtEur(o.total_eur, 2)}</>}</span>
          <div style={{ fontSize: 12 }}>{o.items.join(" · ")}</div>
        </div>
      ))}
      {profile.orders_total > profile.history.length && (
        <div className="card-sub" style={{ marginTop: 4 }}>+ {profile.orders_total - profile.history.length} earlier orders</div>
      )}
    </div>
  );
}
