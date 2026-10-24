"use client";

import type { ReactNode } from "react";
import Link from "next/link";

import { usePagePanel } from "@/components/shell/ShellState";
import { CLAIM as BUSINESS_REORDERS_CLAIM } from "@/components/business-reorders/ClaimBox";
import { DataMark, SYNTHETIC_DATA_SENTENCE, type EvidenceData } from "@/components/evidence/EvidenceHeader";
import type { ModelChecksFile, PersonalisedSearchFile, SearchRelevanceFile } from "@/lib/evidence-types";
import { useEvidence, type EvidenceEntry } from "@/lib/use-evidence";


interface Entry {
  href: string;
  title: string;
  data: EvidenceData;
  adr: string;
  result: ReactNode;
}


/**
 * The Evidence index (ADR 0037): "how well does it work, against what?",
 * kept apart from the 360° views, which carry no accuracy numbers. Each
 * entry is marked Real or Synthetic data and has a one-line result: worded
 * as cleared (Business reorders), or read from the committed result file
 * its page renders (`data/evidence/*.json`), so the two can't disagree.
 * Only entries with a page are listed.
 */
export default function EvidenceIndexPage() {
  usePagePanel(null, {
    title: "Evidence",
    description: "How well it works, against what baseline, on which data.",
    breadcrumb: "Evidence",
  });

  const entries: Entry[] = [
    {
      href: "/evidence/business-reorders/",
      title: "A business buyer's next order",
      data: "Real",
      adr: "ADR 0034",
      result: BUSINESS_REORDERS_CLAIM,
    },
    {
      href: "/evidence/personalised-search/",
      title: "Personalised search",
      data: "Synthetic",
      adr: "ADR 0037",
      result: <FileLine<PersonalisedSearchFile> entry="personalised-search"
                        line={(f) => <>Held out, {f.run.sessions.toLocaleString("en")} search sessions, hit@10: {f.headline}</>} />,
    },
    {
      href: "/evidence/search-relevance/",
      title: "Search relevance",
      data: "Synthetic",
      adr: "ADR 0026",
      result: <FileLine<SearchRelevanceFile> entry="search-relevance"
                        line={(f) => <>On {f.queries} judged queries: {f.headline}</>} />,
    },
    {
      href: "/evidence/model-checks/",
      title: "Model checks",
      data: "Synthetic",
      adr: "ADR 0010",
      result: <FileLine<ModelChecksFile> entry="model-checks" line={modelChecksLine} />,
    },
  ];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Evidence</div>
        <div className="page-desc">
          How well does it work, and against what? The shop and the owner&apos;s views show how Aito answers a
          shop&apos;s questions; the numbers that say how well live here. Each entry says which data it rests on.
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16, display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 8 }}>
        <div className="card-sub" style={{ lineHeight: 1.6 }}>
          <DataMark data="Real" /> A real business&apos;s records, from a public dataset. A result on real
          data is worded only as it was cleared by Aito&apos;s core team.
        </div>
        <div className="card-sub" style={{ lineHeight: 1.6 }}>
          <DataMark data="Synthetic" /> {SYNTHETIC_DATA_SENTENCE}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 12 }}>
        {entries.map((e) => (
          <Link key={e.href} href={e.href} className="card evidence-entry">
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
              <span className="card-title" style={{ margin: 0, fontSize: 15 }}>{e.title}</span>
              <DataMark data={e.data} />
              <span className="card-sub" style={{ marginLeft: "auto" }}>{e.adr} →</span>
            </div>
            <div style={{ fontSize: 14, lineHeight: 1.5, color: "var(--text-2)" }}>{e.result}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}


/** An entry's line, read from the committed result file its page renders. */
function FileLine<T>({ entry, line }: { entry: EvidenceEntry; line: (file: T) => ReactNode }) {
  const { data, error } = useEvidence<T>(entry);
  if (error) return <>Couldn&apos;t load the result: {error}</>;
  if (!data) return <>Loading the result…</>;
  return <>{line(data)}</>;
}


function modelChecksLine(f: ModelChecksFile): ReactNode {
  const passing = f.models.filter((m) => m.verdict === "pass");
  const failing = f.models.filter((m) => m.verdict === "fail");
  const naive = f.demand.comparisons.find((c) => c.baseline.startsWith("naive"));
  if (!naive) throw new Error("Model checks: the demand result has no comparison with the naive forecast");
  return (
    <>
      Held out, against always guessing the most common value: {passing.length} of {f.models.length} catalogue
      models beat it by {f.threshold_pp} points or more
      {failing.length > 0 && <>; {failing.map((m) => m.label).join(", ")} {failing.length === 1 ? "doesn't" : "don't"}, and the page shows it</>}.
      {" "}Churn: {f.churn.comparisons[0].sentence} Demand: {naive.sentence}
    </>
  );
}
