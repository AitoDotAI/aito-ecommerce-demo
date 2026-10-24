"use client";

import Link from "next/link";

import { useSandboxEnv, withSandbox } from "@/lib/sandbox";
import type { ProductBuyerRow, ProductView } from "@/lib/types";
import { words } from "./labels";

const FIELD_LABEL: Record<string, string> = {
  "order_id.customer_id.pets": "Declared pets",
  "order_id.customer_id.dog_size": "Dog size",
  "order_id.customer_id.diet": "Diet kept to",
  "order_id.customer_id.region": "Region",
};

// The same bars as src/product_buyers.py: fewer than 10 lines, or within
// 0.15 of 1 (at two decimals), is not a difference worth naming.
const MIN_LINES = 10;
const NO_DIFFERENCE = 0.15;
const isClear = (b: ProductBuyerRow) =>
  b.lines >= MIN_LINES && Math.round(Math.abs(b.lift - 1) * 100) / 100 > NO_DIFFERENCE;

/**
 * Product › For whom: which declared households buy it more, or less, than
 * households do on average (`_relate` over its order lines). A lift has no
 * interval here, so the counts sit beside it and thin lifts are grey.
 */
export default function ProductBuyers({ view }: { view: ProductView }) {
  const sandbox = useSandboxEnv();
  const clear = view.buyers.filter(isClear);
  const byField = Object.keys(FIELD_LABEL).map((f) => [f, view.buyers.filter((b) => b.field === f)] as const);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 16 }}>
      <div className="card">
        <div className="page-title" style={{ fontSize: 16, margin: "0 0 6px" }}>
          {clear.length
            ? `Bought most by: ${clear.filter((b) => b.lift > 1).map(describe).join(", ") || "no group clearly more than others"}`
            : "No household group buys it clearly more or less than others"}
        </div>
        <div className="card-sub">
          {`From its ${view.buyers[0]?.lines_total ?? 0} order lines. `}A lift is this group&apos;s share of the
          product&apos;s lines over its share of all lines. These are ratios without an interval: a lift on
          fewer than {MIN_LINES} lines, or within {NO_DIFFERENCE} of 1, is grey. Order lines include purchases
          with no tracked impression.
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 10, fontSize: 13 }}>
          {view.shopper && (
            <Link href={withSandbox(`/shop/?shopper=${view.shopper.key}&month=${view.month}`, sandbox)}>
              See it as {view.shopper.name} ({view.shopper.matches.map(words).join(", ")}) in the Shop →
            </Link>
          )}
          <Link href="/patterns/">What goes with {view.basket_category.label.toLowerCase()}, in Patterns →</Link>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
        {byField.map(([field, rows]) => (
          <div className="card" key={field}>
            <div className="page-title" style={{ fontSize: 15, margin: "0 0 8px" }}>{FIELD_LABEL[field]}</div>
            {rows.length === 0 && <div className="card-sub">No buyer declared one.</div>}
            {rows.map((b) => (
              <div key={b.value} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 13 }}>
                <span>
                  {words(b.value)}
                  <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {b.lines} of {b.lines_total} lines</span>
                </span>
                <strong style={{ color: isClear(b) ? "var(--text)" : "var(--text-muted)", fontWeight: isClear(b) ? 700 : 400 }}>
                  {b.lift.toFixed(2)}×
                </strong>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function describe(b: ProductBuyerRow): string {
  const value = words(b.value);
  const what = b.field.endsWith("dog_size") ? `${value} dogs` : b.field.endsWith("region") ? `households in ${value}` : `${value} households`;
  return `${what} (${b.lift.toFixed(2)}×)`;
}
