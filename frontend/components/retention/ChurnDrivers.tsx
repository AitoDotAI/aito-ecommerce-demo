import type { ChurnDriverRow } from "@/lib/types";

/**
 * Which profiles churn more, across all customers (`_relate` over churned
 * customers; tenure bands from counts). The rates are observed shares,
 * not predictions: "62 % of the 635 customers with 18 months or more
 * churned, against 33 % of all".
 */
export default function ChurnDrivers({ drivers, withoutEffect }: { drivers: ChurnDriverRow[]; withoutEffect: string[] }) {
  return (
    <>
      {drivers.length === 0 && <div className="card-sub">No profile churns more or less than the average.</div>}
      {drivers.map((d) => {
        const up = d.lift >= 1;
        return (
          <div key={`${d.field}-${d.value}`} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
            padding: "8px 12px", marginBottom: 6, borderRadius: 6,
            background: up ? "var(--red-bg)" : "var(--green-bg)",
          }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13 }}>
                <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>{d.field}</span>{" "}
                {d.value.replace(/_/g, " ")}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {Math.round(d.churn_rate * 100)} % of {d.customers} customers churned, against{" "}
                {Math.round(d.churn_rate_overall * 100)} % of all
              </div>
            </div>
            <div style={{ fontWeight: 800, color: up ? "var(--red)" : "var(--green)" }}>
              {up ? "↑" : "↓"} {d.lift.toFixed(2)}×
            </div>
          </div>
        );
      })}
      {withoutEffect.length > 0 && (
        <div className="card-sub" style={{ marginTop: 8 }}>
          Also checked, no effect: {withoutEffect.map((f) => f.replace(/_/g, " ")).join(", ")}
        </div>
      )}
    </>
  );
}
