"use client";

import { Suspense } from "react";
import Link from "next/link";

import { personalisedSearchPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import EvidenceHeader from "@/components/evidence/EvidenceHeader";
import PersonalisedSearchResults from "@/components/evidence/PersonalisedSearchResults";
import SearchSideBySide from "@/components/evidence/SearchSideBySide";
import type { PersonalisedSearchFile } from "@/lib/evidence-types";
import { useEvidence } from "@/lib/use-evidence";


/**
 * Personalised search (ADR 0037 §3; ADR 0041): how much of the shopper does
 * Aito recover? The benchmark's one-line result, the live side-by-side that
 * illustrates two of its rankings, then the benchmark itself, from the
 * committed `data/evidence/personalised-search.json`. Nothing on the page
 * runs a benchmark; the side-by-side runs two live searches.
 */
function PersonalisedSearchView() {
  usePagePanel(personalisedSearchPanel(), {
    title: "Personalised search",
    description: "How much of the shopper does Aito recover? Six rankings on held-out search sessions.",
    breadcrumb: "Evidence › Personalised search",
  });
  const { data, error } = useEvidence<PersonalisedSearchFile>("personalised-search");

  return (
    <div className="fade-in">
      <EvidenceHeader title="Personalised search" data="Synthetic">
        Each generated shopper has hidden tastes: brands, a pet&apos;s size, a diet. When they search, do Aito&apos;s
        rankings put what they then bought in the top 10, against text alone, and against the generator&apos;s own
        ranking as a ceiling? The search that ships is the <Link href="/shop/">Shop&apos;s</Link>: it reads the
        household&apos;s declared pets, the month and the cart rather than the customer&apos;s history (ADR 0033).
      </EvidenceHeader>

      {error && <ErrorState title="Couldn't load the benchmark" message={error} command="./do evidence personalised-search" />}
      {data && (
        <div className="card" style={{ marginBottom: 16, borderLeft: "3px solid var(--green)" }}>
          <div className="card-title" style={{ marginBottom: 4 }}>The result, over all {data.run.sessions.toLocaleString("en")} sessions</div>
          <div style={{ fontSize: 14, lineHeight: 1.5 }}>{data.headline}</div>
          <div className="card-sub" style={{ marginTop: 6 }}>Per history slice, and the other comparisons, below the live example.</div>
        </div>
      )}

      <SearchSideBySide />

      {data && <PersonalisedSearchResults data={data} />}
      {!data && !error && <div className="card card-sub">Loading the benchmark…</div>}
    </div>
  );
}


// The live example reads its state from the URL (`useUrlState`), which the
// static export only allows under a Suspense boundary.
export default function PersonalisedSearchPage() {
  return (
    <Suspense>
      <PersonalisedSearchView />
    </Suspense>
  );
}
