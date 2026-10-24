import type { ReactNode } from "react";

export type EvidenceData = "Real" | "Synthetic";

/** ADR 0037 §2: every synthetic page carries this above its first number. */
export const SYNTHETIC_DATA_SENTENCE =
  "Synthetic data with planted effects. This tests whether Aito finds the effects, " +
  "not how large they are in a real shop.";

/** The Real data / Synthetic data mark, on the index and on each page. */
export function DataMark({ data }: { data: EvidenceData }) {
  return (
    <span className={`pill ${data === "Real" ? "pill-green" : "pill-grey"}`} style={{ whiteSpace: "nowrap" }}>
      {data} data
    </span>
  );
}

/**
 * The top of an Evidence page: its title, its data mark, what it measures,
 * and, on synthetic data, the sentence that says what the page can't prove.
 */
export default function EvidenceHeader({
  title,
  data,
  children,
}: {
  title: string;
  data: EvidenceData;
  children: ReactNode;
}) {
  return (
    <div className="page-header">
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div className="page-title">{title}</div>
        <DataMark data={data} />
      </div>
      <div className="page-desc">{children}</div>
      {data === "Synthetic" && (
        <div className="tip-box" role="note" style={{ marginTop: 12, marginBottom: 0 }}>
          <span className="tip-icon" aria-hidden="true">ⓘ</span>
          <span>{SYNTHETIC_DATA_SENTENCE}</span>
        </div>
      )}
    </div>
  );
}
