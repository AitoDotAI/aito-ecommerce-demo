import type { ChurnTellRow } from "@/lib/types";

/** A lift within this distance of 1 is "no effect" (the same band the profile drivers use). */
const NEUTRAL = 0.15;

/**
 * What a customer went through in the last three months, against whether they
 * stopped ordering after: an NPS answer as a detractor, a 1–2 star review, a
 * returned item, a late or damaged delivery. Among customers who had just
 * ordered, with the tell against without. Observed shares, not a cause.
 */
export default function ChurnTells({ tells }: { tells: ChurnTellRow[] }) {
  return (
    <>
      {tells.map((t) => {
        const neutral = Math.abs(t.lift - 1) < NEUTRAL;
        const up = t.lift >= 1;
        return (
          <div key={t.tell} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
            padding: "8px 12px", marginBottom: 6, borderRadius: 6,
            background: neutral ? "var(--border-light)" : up ? "var(--red-bg)" : "var(--green-bg)",
          }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{t.label}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {Math.round(t.churn_rate * 100)} % of {t.customer_months.toLocaleString()} customer-months stopped within
                3 months, against {Math.round(t.churn_rate_without * 100)} % without it
                {t.at_risk_listed > 0 && <> · {t.at_risk_listed} of the listed</>}
              </div>
            </div>
            <div style={{ fontWeight: 800, color: neutral ? "var(--text-muted)" : up ? "var(--red)" : "var(--green)", whiteSpace: "nowrap" }}>
              {neutral ? "no effect" : <>{up ? "↑" : "↓"} {t.lift.toFixed(2)}×</>}
            </div>
          </div>
        );
      })}
    </>
  );
}
