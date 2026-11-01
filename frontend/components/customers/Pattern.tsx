"use client";

import { PATTERN_LABEL, chanceInWords, patternOf, pValue } from "@/lib/pattern";

const COLOUR = { yes: "var(--text)", likely: "var(--text)", possibly: "var(--text-muted)", unlikely: "var(--text-muted)" };

/**
 * "Pattern?": whether a difference is a pattern in the data. Yes, Likely, Possibly or Unlikely, from how many standard errors the difference is;
 * the hover says how often luck alone would give a gap this big. `detail` says what the difference is.
 */
export default function Pattern({ z, detail }: { z: number | null; detail?: string }) {
  const level = patternOf(z);
  if (level === null || z === null) return <span className="card-sub">–</span>;
  const p = pValue(z);
  return (
    <span title={`${detail ? `${detail}. ` : ""}A gap this big would come up by luck alone ${chanceInWords(z)} (p ${p < 0.001 ? "< 0.001" : `≈ ${p.toFixed(3)}`}).`}
          style={{ fontSize: 13, fontWeight: level === "yes" ? 700 : 400, color: COLOUR[level], whiteSpace: "nowrap" }}>
      {PATTERN_LABEL[level]}
    </span>
  );
}
