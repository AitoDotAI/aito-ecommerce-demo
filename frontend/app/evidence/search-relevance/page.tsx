"use client";

import ErrorState from "@/components/shell/ErrorState";
import EvidenceHeader from "@/components/evidence/EvidenceHeader";
import RunFacts from "@/components/evidence/RunFacts";
import { usePagePanel } from "@/components/shell/ShellState";
import type { SearchArm, SearchRelevanceFile } from "@/lib/evidence-types";
import { useEvidence } from "@/lib/use-evidence";

// The report's arm names, as the page names them.
const ARM_LABELS: Record<string, string> = {
  "before: $match": "Before: every word must match ($match)",
  "left: bm25": "Text only: BM25 over the name",
  "random (control)": "Control: a random order",
  "table order (control)": "Control: the table's order",
};

function armLabel(arm: string, personas: Record<string, string>): string {
  const right = arm.match(/^right θ[\d.]+\[(\w+)\]$/);
  if (right) return `Text × purchase probability, ${personas[right[1]] ?? right[1]}`;
  return ARM_LABELS[arm] ?? arm;
}


/**
 * Search relevance (ADR 0037; the report of ADR 0026's `./do search-eval`):
 * 60 hand-written queries, every product graded from its attributes, and
 * Smart Search's two columns scored on them. Rendered from the committed
 * `data/evidence/search-relevance.json`; the page runs nothing live.
 */
export default function SearchRelevancePage() {
  usePagePanel(null, {
    title: "Search relevance",
    description: "Does each search column find the products a query asks for? 60 judged queries.",
    breadcrumb: "Evidence › Search relevance",
  });
  const { data, error } = useEvidence<SearchRelevanceFile>("search-relevance");

  return (
    <div className="fade-in">
      <EvidenceHeader title="Search relevance" data="Synthetic">
        Does a search find what the words ask for? {data?.queries ?? 60} hand-written queries (exact names, brands,
        synonyms, paraphrases, misspellings, Finnish and Swedish), and every product in the catalogue graded
        against each from its attributes, never by a search system. The labels ignore who is searching, so this
        page can&apos;t see personalisation: <a href="/evidence/personalised-search/">Personalised search</a> measures that.
      </EvidenceHeader>

      {error && <ErrorState title="Couldn't load the search evaluation" message={error} command="./do evidence search-relevance" />}
      {!data && !error && <div className="card card-sub">Loading the search evaluation…</div>}

      {data && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-title" style={{ marginBottom: 8 }}>Did each column improve?</div>
            <ul className="verdict-list">
              {data.comparisons.map((c) => <li key={c.arm}>{c.sentence}</li>)}
            </ul>
            <div className="card-sub" style={{ marginTop: 10, lineHeight: 1.5 }}>
              nDCG@10 differences, paired query by query, with 95 % bootstrap intervals. The right column&apos;s text
              weight θ = {data.theta} was chosen on these same queries, so its lead over BM25 is in-sample; the
              out-of-sample check is below.
            </div>
          </div>

          <ArmsTable arms={data.arms} personas={data.personas} />
          <OutOfSample data={data} />
          <StrataTable data={data} />

          <RunFacts
            run={data.run}
            n={`${data.queries} queries (${Object.entries(data.strata).map(([s, k]) => `${k} ${s}`).join(", ")}), ` +
               `each against the whole catalogue`}
            method={<>
              Each arm ranks the catalogue for each query; nDCG@10 rewards relevant products near the top against
              the best ordering of all relevant products. Controls: a random order scores{" "}
              {data.controls.random_ndcg10.toFixed(3)}, and the best arm against shuffled labels{" "}
              {data.controls.shuffled_labels_ndcg10.toFixed(3)}; both are near chance, as they must be for the
              metric to mean anything.
            </>}
            sources={[
              { label: "src/search_eval/run.py", path: "src/search_eval/run.py" },
              { label: "the full report", path: data.report },
              { label: "judged queries", path: "data/search_eval/queries.json" },
              { label: "ADR 0026", path: "docs/adr/0026-three-way-smart-search.md" },
              { label: "ADR 0037", path: "docs/adr/0037-an-evidence-section.md" },
            ]}
          />
        </>
      )}
    </div>
  );
}


function ArmsTable({ arms, personas }: { arms: SearchArm[]; personas: Record<string, string> }) {
  const num = (v: number) => v.toFixed(3);
  return (
    <div className="card" style={{ overflowX: "auto", marginBottom: 16 }}>
      <div className="card-title" style={{ marginBottom: 8 }}>Each arm, over all queries</div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Arm</th>
            <th style={{ textAlign: "right" }}>nDCG@10</th>
            <th style={{ textAlign: "right" }}>P@5</th>
            <th style={{ textAlign: "right" }}>Recall@20</th>
            <th style={{ textAlign: "right" }}>MRR</th>
            <th style={{ textAlign: "right" }}>No result</th>
          </tr>
        </thead>
        <tbody>
          {arms.map((a) => (
            <tr key={a.arm} style={a.arm.includes("control") ? { color: "var(--text-muted)" } : undefined}>
              <td>{armLabel(a.arm, personas)}</td>
              {[a.ndcg10, a.p5, a.r20, a.mrr].map((v, i) => (
                <td key={i} style={{ textAlign: "right", fontFamily: "var(--mono)" }}>{num(v)}</td>
              ))}
              <td style={{ textAlign: "right", fontFamily: "var(--mono)" }}>{(a.zero * 100).toFixed(0)} %</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function OutOfSample({ data }: { data: SearchRelevanceFile }) {
  const o = data.out_of_sample;
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-title" style={{ marginBottom: 8 }}>The text weight, chosen out of sample</div>
      <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--text-2)" }}>
        θ chosen on half the queries and scored on the other half, over {o.splits} stratified splits: the right
        column&apos;s gain over BM25 had a median of {o.median_gain >= 0 ? "+" : ""}{o.median_gain.toFixed(3)} nDCG@10,
        90 % of splits in [{o.gain_90[0].toFixed(3)}, {o.gain_90[1].toFixed(3)}], positive in{" "}
        {(o.positive_share * 100).toFixed(0)} % of splits. The splits overlap, so they show stability, not
        independent evidence. One split (seed {o.one_split.seed}, θ = {o.one_split.theta}), on its{" "}
        {o.one_split.queries} held-out queries:
      </div>
      <ul className="verdict-list" style={{ marginTop: 8 }}>
        {Object.entries(o.one_split.by_persona).map(([p, c]) => <li key={p}>{c.sentence}</li>)}
      </ul>
    </div>
  );
}


function StrataTable({ data }: { data: SearchRelevanceFile }) {
  const arms = data.arms.slice(0, 5).map((a) => a.arm);
  return (
    <div className="card" style={{ overflowX: "auto" }}>
      <div className="card-title" style={{ marginBottom: 8 }}>nDCG@10 by kind of query</div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Kind (queries)</th>
            {arms.map((a) => <th key={a} style={{ textAlign: "right" }}>{armLabel(a, data.personas)}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.by_stratum.map((row) => (
            <tr key={String(row.stratum)}>
              <td>{String(row.stratum)} ({data.strata[String(row.stratum)]})</td>
              {arms.map((a) => (
                <td key={a} style={{ textAlign: "right", fontFamily: "var(--mono)" }}>{Number(row[a]).toFixed(3)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="card-sub" style={{ marginTop: 8 }}>
        Point estimates on {Math.min(...Object.values(data.strata))}–{Math.max(...Object.values(data.strata))} queries
        per kind: too few to read a kind on its own, so no interval is given and no kind is compared.
      </div>
    </div>
  );
}
