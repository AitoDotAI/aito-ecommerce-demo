"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { usePagePanel } from "@/components/shell/ShellState";
import { CLAIM as BUSINESS_REORDERS_CLAIM } from "@/components/business-reorders/ClaimBox";
import { DataMark, SYNTHETIC_DATA_SENTENCE, type EvidenceData } from "@/components/evidence/EvidenceHeader";
import type { EvalResponse } from "@/lib/types";


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
 * entry is marked Real or Synthetic data and has a one-line result. A
 * result is either worded as cleared (Business reorders), read from what
 * its page shows (Model checks), or says plainly that the page measures
 * nothing yet (Personalised search). Only entries with a page are listed.
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
      result: "An illustration, not a measurement: the same words ranked by text alone and with the shopper's " +
              "history, side by side, live for three shoppers.",
    },
    {
      href: "/evidence/model-checks/",
      title: "Model checks",
      data: "Synthetic",
      adr: "ADR 0010",
      result: <ModelChecksResult />,
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

      <div className="card" style={{ marginBottom: 16, display: "grid", gap: 8 }}>
        <div className="card-sub" style={{ lineHeight: 1.6 }}>
          <DataMark data="Real" /> A real business&apos;s records, from a public dataset. A result on real
          data is worded only as it was cleared by Aito&apos;s core team.
        </div>
        <div className="card-sub" style={{ lineHeight: 1.6 }}>
          <DataMark data="Synthetic" /> {SYNTHETIC_DATA_SENTENCE}
        </div>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
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


/** Model checks' line, read from the evaluation its page shows, so the two
 *  can't disagree after a re-run. */
function ModelChecksResult() {
  const [data, setData] = useState<EvalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<EvalResponse>("/api/evaluation").then(setData, (e) => setError(String(e)));
  }, []);

  if (error) return <>Couldn&apos;t load the evaluation: {error}</>;
  if (!data) return <>Loading the evaluation…</>;
  const thresholds = new Set(data.models.map((m) => m.threshold_pp));
  if (thresholds.size !== 1) throw new Error(`Model checks: expected one pass threshold, got ${[...thresholds].join(", ")}`);
  const errored = data.models.filter((m) => m.error !== null);
  const scored = data.models.filter((m) => m.error === null);
  const passing = scored.filter((m) => m.verdict === "pass");
  const failing = scored.filter((m) => m.verdict === "fail");
  const names = (models: typeof scored) => models.map((m) => m.label).join(", ");
  return (
    <>
      Held-out accuracy against always guessing the most common value: {passing.length} of {scored.length}{" "}
      models beat that guess by {[...thresholds][0]} points or more.
      {failing.length > 0 && <> {names(failing)} {failing.length === 1 ? "doesn't" : "don't"}, and the page shows it.</>}
      {errored.length > 0 && <> {names(errored)} couldn&apos;t be evaluated in this run.</>}
    </>
  );
}
