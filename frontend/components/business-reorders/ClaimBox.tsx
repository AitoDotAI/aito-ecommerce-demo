/**
 * The benchmark's result, worded exactly as cleared (ADR 0034, "The claim,
 * as cleared"), with the dataset's citation and licence. Don't reword it:
 * "the whole order was right" or "beats every baseline" are not cleared.
 * The Evidence index quotes `CLAIM` as this entry's result.
 */
export const CLAIM =
  "For buyers with 1–2 earlier orders, Aito's top suggestion was in their next orders 31 % of the " +
  "time, against 15 % for the strongest of five classical baselines.";

export default function ClaimBox() {
  return (
    <div className="card" style={{ borderLeft: "4px solid var(--aito-teal)" }}>
      <div className="card-title">The benchmark</div>
      <p style={{ fontSize: 15, lineHeight: 1.5, margin: "6px 0 10px", color: "var(--text)" }}>{CLAIM}</p>
      <div className="card-sub" style={{ lineHeight: 1.5 }}>
        Data: Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository.{" "}
        <a href="https://doi.org/10.24432/C5CG6D" target="_blank" rel="noreferrer">https://doi.org/10.24432/C5CG6D</a>.
        Licence CC BY 4.0. Aito learned from invoices before 1 Sep 2011; each buyer&apos;s next order after
        that is the test.
      </div>
    </div>
  );
}
