import RunFacts from "@/components/evidence/RunFacts";
import FinePrint from "@/components/shell/FinePrint";
import type { Interval, PersonalisedSearchFile, PersonalisedSlice } from "@/lib/evidence-types";
import { pctInterval } from "@/lib/use-evidence";

// What each ranking is, in a line (docs/verification/personalised-search-prereg.md has the exact queries).
const WHAT: Record<string, string> = {
  "BM25": "Aito's $similarity over the name, the products holding a query word",
  "BM25, reference": "a plain Okapi BM25 in Python (k1 1.2, b 0.75), to show the left column is one",
  "Aito, the Shop's search": "the shipped search: the words' products, ranked by the household's $p × the text lift",
  "Aito, with the shopper's history": "Smart Search's one query: $p for this customer's id × $similarity",
  "Household only": "the Shop search's $p alone, without the text lift",
  "Generator's ranking": "the ceiling estimate: the generator's own weight for this shopper",
};

const COMPARISONS = [
  "The Shop's search against BM25",
  "The shopper's history against the Shop's search",
  "The generator's ranking against the best Aito ranking",
];


/**
 * The personalised-search benchmark (ADR 0037 §3), from the committed
 * `data/evidence/personalised-search.json`: hit@10 for six rankings per
 * history slice, with intervals, and the three pre-registered comparisons
 * as the result file worded them (a tie when the interval spans 0).
 */
export default function PersonalisedSearchResults({ data }: { data: PersonalisedSearchFile }) {
  const slices = data.slices;
  return (
    <>
      <div className="card" style={{ overflowX: "auto", marginBottom: 16 }}>
        <div className="card-title" style={{ marginBottom: 4 }}>hit@10 by the shopper&apos;s orders before the session</div>
        <div className="card-sub" style={{ marginBottom: 10 }}>
          Share of sessions with a product the shopper bought in the top 10, with its 95 % interval.
          Each Aito ranking read the data with that session left out.
        </div>
        <ScoreTable slices={slices} rankings={data.rankings} pick={(s) => s.hit10} />
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title" style={{ marginBottom: 8 }}>The three comparisons, fixed before the run</div>
        {COMPARISONS.map((title, i) => (
          <div key={title} style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{title}</div>
            <ul className="verdict-list">
              {slices.map((s) => <li key={s.name}>{s.sentences[i]}</li>)}
            </ul>
          </div>
        ))}
        <div className="card-sub" style={{ lineHeight: 1.5 }}>
          Differences in hit@10, paired session by session.
          <FinePrint>
            {" "}The Shop&apos;s search reads the household&apos;s declared pets, not the shopper&apos;s history, so it
            isn&apos;t expected to rise with history; the history form is. The generator&apos;s ranking is an
            estimate of the ceiling, not a bound: purchases were drawn from what was shown, through the purchase
            funnel, not from its weight.
          </FinePrint>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto", marginBottom: 16 }}>
        <div className="card-title" style={{ marginBottom: 4 }}>MRR (secondary)</div>
        <div className="card-sub" style={{ marginBottom: 10 }}>
          The mean of 1 / the rank of the first product bought, 0 beyond rank 100.
        </div>
        <ScoreTable slices={slices} rankings={data.rankings} pick={(s) => s.mrr} digits={3} />
      </div>

      <RunFacts
        run={data.run}
        n={`${data.run.sessions.toLocaleString("en")} search sessions with a purchase, the three personas left out` +
           (data.run.subsample ? ` (a pre-registered random subsample of ${data.run.subsample})` : "")}
        method={<>
          The generator&apos;s search sessions: a shopper, the words they typed, and what they bought. The words were
          drawn from a product the shopper is drawn to, so the purchases are labels a shop would observe, not
          judgements. Each ranking orders the catalogue for the session&apos;s words; Aito reads everything except
          that session (a nested <code>from</code>). The design, every query and the known limits were fixed in the
          pre-registration before the run.
        </>}
        sources={[
          { label: "the pre-registration", path: data.preregistration },
          { label: "src/personalised_search/", path: "src/personalised_search/run.py" },
          { label: "src/shop_search.py", path: "src/shop_search.py" },
          { label: "ADR 0037 §3", path: "docs/adr/0037-an-evidence-section.md" },
        ]}
      />
    </>
  );
}


function ScoreTable({ slices, rankings, pick, digits }: {
  slices: PersonalisedSlice[];
  rankings: string[];
  pick: (s: PersonalisedSlice) => Record<string, Interval>;
  digits?: number;
}) {
  // The estimate, and its 95 % interval on a second line, so five slices fit side by side.
  const show = (v: Interval) => (
    <>
      <div>{digits ? v.mean.toFixed(digits) : `${(v.mean * 100).toFixed(1)} %`}</div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400 }}>
        {digits ? `[${v.low?.toFixed(digits)}, ${v.high?.toFixed(digits)}]` : pctInterval(v.low, v.high)}
      </div>
    </>
  );
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Ranking</th>
          {slices.map((s) => (
            <th key={s.name} style={{ textAlign: "right", whiteSpace: "nowrap" }}>
              {s.name === "all" ? "All" : s.name.replace("-", "–")}
              <div style={{ fontWeight: 400, fontSize: 11 }}>{s.sessions.toLocaleString("en")} sessions</div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rankings.map((r) => (
          <tr key={r}>
            <td style={{ minWidth: 220 }}>
              <div style={{ fontWeight: 600 }}>{r}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{WHAT[r]}</div>
            </td>
            {slices.map((s) => (
              <td key={s.name} style={{ textAlign: "right", fontFamily: "var(--mono)", whiteSpace: "nowrap",
                                        fontWeight: r === s.best_aito ? 700 : 400 }}>
                {show(pick(s)[r])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
