import { KIND_LABEL, PERSON_VERDICT_TEXT, SIGNAL_TEXT, WORSE_TEXT, eur, percent, rate, type Kind, type PersonalChoice as Choice } from "@/lib/experiments";

/** Whether choosing the arm per person beats choosing one arm for everybody, for one kind of experiment, with the signal it reads. */
export default function PersonalChoice({ kind, result, arms }: { kind: Kind; result: Choice; arms: [string, string] }) {
  const [low, high] = result.interval_percent;
  const verdictColour = result.verdict === "choose per person" ? "var(--aito-teal)" : result.verdict === "small gain" ? "var(--text)" : "var(--text-muted)";
  return (
    <div className="card">
      <div className="card-title" style={{ margin: 0 }}>Choosing per person: {KIND_LABEL[kind].toLowerCase()} experiments</div>
      <div className="card-sub" style={{ margin: "4px 0 8px", lineHeight: 1.5 }}>
        Aito chooses the arm for each shopper from {SIGNAL_TEXT[result.signal]}, crossed with the arm shown, and the choice is weighed by what each arm earns per sale.
        The levels below show why that signal helps: how much better the second arm sells at each.
      </div>
      <div className="scroll-x">
        <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
          <thead>
            <tr className="card-sub" style={{ fontSize: 11.5, textAlign: "left" }}>
              <th>Signal</th><th>Showings</th><th>Rate, first arm</th><th>Rate, second arm</th><th title="Purchase rate on the second arm divided by the first's">Second arm lift</th>
            </tr>
          </thead>
          <tbody>
            {result.levels.map((level) => {
              const [a, b] = arms.map((arm) => level[arm] as { showings: number; rate: number | null });
              return (
                <tr key={level.signal} style={{ borderTop: "1px solid var(--border-light)" }}>
                  <td style={{ padding: "3px 6px 3px 0" }}>{level.signal}</td><td>{(a.showings + b.showings).toLocaleString("en-GB")}</td>
                  <td>{a.rate === null ? "–" : rate(a.rate)}</td><td>{b.rate === null ? "–" : rate(b.rate)}</td>
                  <td style={{ fontWeight: 600 }}>{level.lift === null ? "–" : `×${level.lift.toFixed(2)}`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 12, fontSize: 13, lineHeight: 1.6 }}>
        On the {result.held_out_month} showings, which Aito had not learned from ({result.pairs.toLocaleString("en-GB")} shoppers and products), choosing per person earned{" "}
        <strong>{eur(result.profit_per_showing.personal, 3)}</strong> per showing against <strong>{eur(result.profit_per_showing.winner, 3)}</strong> for the plain winner:{" "}
        <strong>{percent(result.gain_percent)}</strong> <span className="card-sub">(95 % interval {percent(low)} to {percent(high)})</span>.
        With a perfect signal the gain would be {percent(result.ceiling_gain_percent)}{result.share_of_gap !== null && <>; this signal gets {Math.round(100 * result.share_of_gap)} % of it</>}.
      </div>
      <div style={{ marginTop: 8, fontSize: 13, fontWeight: 600, color: verdictColour }}>{result.verdict === "keep the plain winner" && high < 0 ? WORSE_TEXT : PERSON_VERDICT_TEXT[result.verdict]}</div>
      <div className="card-sub" style={{ marginTop: 6, lineHeight: 1.5 }}>
        Scored against the generator&apos;s true purchase chances for each shopper, which a real shop does not have: it would hold a group of shoppers out and
        compare. The generator plants a reaction that differs between shoppers (an offer sells {`×2.6`} to high discount sensitivity and {`×1.05`} to low; a benefit-led
        title is lifted by a high health focus and put off by a low one); the shop sees only the signal above.
      </div>
    </div>
  );
}
