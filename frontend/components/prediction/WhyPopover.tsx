"use client";

import React, { type CSSProperties, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import EstimateWhyBody from "@/components/prediction/EstimateWhyBody";
import { popoverStyle } from "@/lib/popover-placement";
import type { WhyEstimatePayload } from "@/lib/types";


export interface WhyProposition {
  field: string;
  value: string;
  negate?: boolean;
}

export interface WhyHighlight {
  field: string;
  marked_text: string;
}

export interface WhyLiftEntry {
  lift: number;
  propositions: WhyProposition[];
  highlight?: WhyHighlight | null;
  /** On a group only (src/why_groups.py): `lift` is the joint lift times the members',
   *  so the rows still multiply out; the parts are listed inside the card. */
  joint_lift?: number;
  members?: WhyLiftEntry[];
}

export interface WhyExplanationPayload {
  base_p: number;
  predicted_value: string;
  lifts: WhyLiftEntry[];
  final_p: number | null;
}

interface WhyPopoverProps {
  why: WhyExplanationPayload | WhyEstimatePayload;
  /** Optional one-line summary shown as the title — "Why {title}?" */
  title?: string;
}


/**
 * Rich `$why` decomposition popover — mirrors the accounting demo's
 * WhyPopover visual. Title, base-probability card, pattern-match
 * cards with highlighted tokens, multiplicative chain ending in
 * the final probability, footer explaining what lift > 1 means.
 *
 * Never simplify or drop entries from the chain (CLAUDE.md prime
 * directive — never silently transform). If a lift is < 1 it's a
 * protective factor; render it with a downward arrow but keep the
 * chain intact.
 */
export default function WhyPopover({ why, title }: WhyPopoverProps) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<CSSProperties>({});
  const btnRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (
        btnRef.current && !btnRef.current.contains(e.target as Node) &&
        tipRef.current && !tipRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  function toggle() {
    if (!open && btnRef.current) {
      // Under the button on a wide screen, right-aligned to it, and a bottom sheet on a
      // phone: the old fixed 420 px was wider than a phone (src/lib/popover-placement.ts).
      setPlacement(popoverStyle(btnRef.current.getBoundingClientRect(), 420));
    }
    setOpen(!open);
  }

  return (
    <>
      <button
        ref={btnRef}
        onClick={toggle}
        title="Show prediction reasoning"
        aria-label="Why this prediction?"
        style={{
          width: 22,
          height: 22,
          borderRadius: "50%",
          border: "none",
          background: open ? "var(--cta)" : "var(--cta-bg)",
          color: open ? "white" : "var(--cta)",
          fontSize: 12,
          fontWeight: 700,
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--mono)",
          lineHeight: 1,
          flexShrink: 0,
          padding: 0,
        }}
      >
        ?
      </button>

      {open && typeof document !== "undefined" && createPortal(
        <div
          ref={tipRef}
          style={{
            ...placement,
            zIndex: 9999,
            background: "var(--white)",
            border: "2px solid var(--cta)",
            borderRadius: 10,
            padding: "16px 18px",
            boxShadow: "0 12px 32px rgba(0,0,0,0.25)",
            color: "var(--text)",
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          {title && (
            <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 12 }}>
              Why {title}?
            </div>
          )}

          {isEstimatePayload(why)
            ? <EstimateWhyBody why={why} />
            : renderPredictBody(why)}
        </div>,
        document.body,
      )}
    </>
  );
}


function isEstimatePayload(
  why: WhyExplanationPayload | WhyEstimatePayload,
): why is WhyEstimatePayload {
  return (why as WhyEstimatePayload).kind === "estimate";
}


function renderPredictBody(why: WhyExplanationPayload): React.ReactNode {
  // The lifts are marginal per-pattern factors; Aito's posterior is NOT
  // their naive product. Aito normalises overlapping evidence, so with
  // weak evidence the product does land on the model's probability, but
  // with strong evidence it overshoots — measured: 35% × 1.5 × 2.9 × 1.7
  // × 1.8 = 434% for a class whose actual $p is 98%. Printing "= 98%"
  // there is an arithmetically false equation (the "0% × 0.7 = 58%"
  // demo-effect class the accounting demo hit).
  //
  // Rather than soften the equals sign, surface the normalising constant
  // as its own term so the chain genuinely reconciles and stays checkable
  // by eye. This mirrors the grocery demo (aito-demo InvoicingPage),
  // which shows the same term for the same reason.
  // Derive it from the ROUNDED figures actually on screen, not the raw
  // ones — otherwise multiplying what the reader sees still misses the
  // stated result, which defeats the point of showing the term at all.
  const shownBase = Math.round(why.base_p * 100) / 100;
  const shownLifts = why.lifts.map((e) => Number(e.lift.toFixed(1)));
  const chainProduct = shownLifts.reduce((acc, l) => acc * l, shownBase);
  const normalizer =
    why.final_p !== null && chainProduct > 0 ? why.final_p / chainProduct : 1;
  const showNormalizer = Math.abs(normalizer - 1) > 0.1;
  return (
    <>
      {/* Base probability card */}
      <div style={{
        background: "var(--bg)",
        padding: "10px 12px",
        borderRadius: 6,
        marginBottom: 10,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}>
        <div>
          <div style={{
            fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            letterSpacing: 0.6, color: "var(--text-muted)",
          }}>
            Base probability
          </div>
          <div style={{ fontSize: 11, color: "var(--text-2)", marginTop: 2 }}>
            Prior rate of <strong>{why.predicted_value}</strong>
          </div>
        </div>
        <div style={{ fontWeight: 800, fontSize: 18 }}>
          {pctOf(why.base_p)}%
        </div>
      </div>

      {/* Pattern match cards */}
      {why.lifts.map((entry, i) => (
        <PatternMatchCard key={i} entry={entry} />
      ))}

      {/* Evidence chain. The normalising constant is shown as its own
          term whenever it moves the result, so the equation reconciles
          (see above). */}
      {why.final_p !== null && (
        <>
          <div style={{
            textAlign: "center", padding: "10px 0 6px",
            fontFamily: "var(--mono)", fontSize: 13,
            color: "var(--text-2)",
          }}>
            {pctOf(why.base_p)}%
            {why.lifts.map((entry, i) => (
              <span key={i}> × {entry.lift.toFixed(1)}</span>
            ))}
            {showNormalizer && (
              <span style={{ color: "var(--green)" }}>
                {" × "}{normalizer.toFixed(2)}
              </span>
            )}
            {" = "}
            <strong style={{ color: "var(--text)", fontSize: 14 }}>
              {pctOf(why.final_p)}%
            </strong>
          </div>
          {showNormalizer && (
            <div style={{
              textAlign: "center", fontSize: 10.5,
              color: "var(--text-muted)", marginTop: -2, marginBottom: 2,
              lineHeight: 1.45,
            }}>
              <strong>× {normalizer.toFixed(2)}</strong>{" "}
              is Aito&apos;s
              normalising constant — evidence that overlaps is not counted
              twice, so the result is not the raw product of the lifts.
            </div>
          )}
        </>
      )}

      {/* Footer */}
      <div style={{
        marginTop: 8, paddingTop: 10,
        borderTop: "1px solid var(--border-light)",
        fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5,
      }}>
        <strong>Lift &gt; 1</strong> means this feature makes the
        prediction more likely; <strong>base P</strong> is the prior
        probability of the predicted value.
      </div>
    </>
  );
}


function PatternMatchCard({ entry }: { entry: WhyLiftEntry }) {
  const up = entry.lift >= 1;
  // Use the highlighted-sentence rendering only when the source field
  // has *surrounding text* — i.e., it's a Text-typed column where the
  // marked tokens are embedded in a longer string. Numeric / String /
  // Boolean columns produce highlights like `«3»` with nothing
  // outside the sentinels; for those the structured "When X is Y"
  // rendering reads better.
  // And only when something in it is actually marked: Aito often returns the plain sentence
  // for a one-word match, and printing it unmarked makes every card look like a copy of the
  // same row. Then the card states the proposition itself ("name has the word Turkey").
  const isTextMatch = Boolean(entry.highlight && _hasSurroundingText(entry.highlight.marked_text));
  const highlight = isTextMatch && entry.highlight && /[«‹]/.test(entry.highlight.marked_text)
    ? entry.highlight
    : null;
  const members = entry.members ?? [];
  return (
    <div style={{
      background: up ? "rgba(245,166,35,0.10)" : "rgba(82,183,136,0.08)",
      borderLeft: `3px solid ${up ? "var(--cta)" : "var(--green)"}`,
      padding: "8px 12px",
      borderRadius: 4,
      marginBottom: 8,
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      gap: 10,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 9,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.6,
          color: "var(--text-muted)",
          marginBottom: 4,
        }}>
          Pattern match{highlight && (
            <>
              {" · "}<code style={{ fontFamily: "var(--mono)", textTransform: "none" }}>
                {highlight.field}
              </code>
            </>
          )}
        </div>
        {highlight ? (
          // Highlighted-sentence rendering — Text-column matches surface
          // the full source string with the matched tokens emphasised.
          // Sentinel-split is safe; no innerHTML.
          <div style={{
            fontSize: 12.5,
            color: "var(--text)",
            fontStyle: "italic",
            lineHeight: 1.55,
          }}>
            {renderMarkedText(highlight.marked_text, up)}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: "var(--text)" }}>
            <Conditions entry={entry} up={up} />
          </div>
        )}
        {members.length > 0 && <Parts entry={entry} members={members} />}
      </div>
      <div style={{
        fontFamily: "var(--mono)",
        fontWeight: 700,
        fontSize: 14,
        color: up ? "var(--cta)" : "var(--green)",
        flexShrink: 0,
      }}>
        {up ? "↑" : "↓"} {entry.lift.toFixed(1)}×
      </div>
    </div>
  );
}


/** "When name has the word Turkey and brand is Hill's": an entry's conditions as chips. */
function Conditions({ entry, up }: { entry: WhyLiftEntry; up: boolean }) {
  // Only the free-text column (the highlight's field) matches on a word; a plain-value
  // column such as `brand` matches the whole value.
  const textField = entry.highlight && _hasSurroundingText(entry.highlight.marked_text)
    ? entry.highlight.field
    : null;
  return (
    <>
      When{" "}
      {entry.propositions.map((p, i) => (
        <span key={i}>
          {i > 0 && <span style={{ color: "var(--text-muted)" }}> and </span>}
          <code style={{ fontFamily: "var(--mono)", color: "var(--text-2)" }}>
            {p.field}
          </code>
          <span style={{ color: "var(--text-muted)" }}>
            {" "}{p.field === textField
              ? (p.negate ? "does not have the word " : "has the word ")
              : (p.negate ? "is not " : "is ")}
          </span>
          <span style={{
            background: up ? "rgba(245,166,35,0.30)" : "rgba(82,183,136,0.22)",
            padding: "1px 5px",
            borderRadius: 3,
            fontWeight: 600,
          }}>
            {p.value}
          </span>
        </span>
      ))}
    </>
  );
}


/**
 * A group's parts, folded inside its card: the joint lift of all its conditions, then the
 * small lift each condition keeps on its own. Their product is the card's lift. Native
 * <details>, so it opens by tap or key as well as click; the title shows the same on hover.
 */
function Parts({ entry, members }: { entry: WhyLiftEntry; members: WhyLiftEntry[] }) {
  const part = (m: WhyLiftEntry) => m.propositions.map((p) => `${p.field} ${p.negate ? "not " : ""}${p.value}`).join(" and ");
  const joint = entry.joint_lift ?? 1;
  const hover = [`together ×${joint.toFixed(2)}`, ...members.map((m) => `${part(m)} ×${m.lift.toFixed(2)}`)].join("\n");
  return (
    <details style={{ marginTop: 6, fontSize: 11.5 }}>
      <summary title={hover} style={{ cursor: "pointer", color: "var(--text-muted)" }}>
        {members.length + 1} parts multiplied: ×{joint.toFixed(2)} together
        {members.map((m) => ` × ${m.lift.toFixed(2)}`).join("")}
      </summary>
      <div style={{ marginTop: 4, display: "grid", gap: 3 }}>
        <PartLine label={<span>All of them together</span>} lift={joint} />
        {members.map((m, i) => (
          <PartLine key={i} lift={m.lift} label={<Conditions entry={m} up={m.lift >= 1} />} />
        ))}
      </div>
    </details>
  );
}


function PartLine({ label, lift }: { label: React.ReactNode; lift: number }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, color: "var(--text-2)" }}>
      <span style={{ minWidth: 0 }}>{label}</span>
      <span style={{ fontFamily: "var(--mono)", flexShrink: 0 }}>×{lift.toFixed(2)}</span>
    </div>
  );
}


/**
 * Split Aito's highlight string on the sentinel marks and render
 * the full sentence with the matched spans wrapped in `<mark>`.
 *
 *  - «word» → positive-evidence span  (was `posPreTag` / `posPostTag`)
 *  - ‹word› → negative-evidence span  (was `negPreTag` / `negPostTag`)
 *
 * No innerHTML; we parse the sentinels into React fragments so the
 * source string is treated as text + the marks as structural spans.
 * That's the project's safety convention (CLAUDE.md prime
 * directive #2 — never silently inject).
 */
function renderMarkedText(text: string, positive: boolean): React.ReactNode {
  // Match either «...» or ‹...› spans; capture them so .split keeps them.
  const parts = text.split(/(«[^»]*»|‹[^›]*›)/);
  return parts.map((part, i) => {
    if (part.startsWith("«") && part.endsWith("»")) {
      return (
        <mark key={i} style={{
          background: positive
            ? "rgba(245,166,35,0.45)"
            : "rgba(245,166,35,0.30)",
          color: "inherit",
          padding: "0 2px",
          borderRadius: 2,
          fontWeight: 700,
          fontStyle: "normal",
        }}>{part.slice(1, -1)}</mark>
      );
    }
    if (part.startsWith("‹") && part.endsWith("›")) {
      return (
        <mark key={i} style={{
          background: "rgba(231,76,60,0.18)",
          color: "var(--red)",
          padding: "0 2px",
          borderRadius: 2,
          fontWeight: 700,
          fontStyle: "normal",
        }}>{part.slice(1, -1)}</mark>
      );
    }
    return <span key={i}>{part}</span>;
  });
}


function _hasSurroundingText(s: string): boolean {
  // Strip the marked spans; what's left is the surrounding sentence.
  // For Int/String/Boolean highlights this is empty — fall back to
  // the "When X is Y" structured rendering. For Text highlights
  // ("Package arrived late. The seal was broken.") this is non-empty
  // — render the full sentence with marks.
  const stripped = s
    .replace(/«[^»]*»/g, "")
    .replace(/‹[^›]*›/g, "")
    .trim();
  return stripped.length > 0;
}


function pctOf(p: number | null): string {
  if (p === null) return "?";
  return Math.round(p * 100).toString();
}
