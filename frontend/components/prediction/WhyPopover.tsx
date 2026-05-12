"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";


export interface WhyProposition {
  field: string;
  value: string;
  negate?: boolean;
}

export interface WhyLiftEntry {
  lift: number;
  propositions: WhyProposition[];
}

export interface WhyExplanationPayload {
  base_p: number;
  predicted_value: string;
  lifts: WhyLiftEntry[];
  final_p: number | null;
}


interface WhyPopoverProps {
  why: WhyExplanationPayload;
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
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
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
      const rect = btnRef.current.getBoundingClientRect();
      // Position the popover to the LEFT of the button so it stays
      // visible when the row is on the right side of the table.
      const popoverWidth = 420;
      const left = Math.max(12, rect.right - popoverWidth);
      const top = Math.min(rect.bottom + 8, window.innerHeight - 600);
      setPos({ top, left });
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
            position: "fixed",
            top: pos.top,
            left: pos.left,
            zIndex: 9999,
            background: "var(--white)",
            border: "2px solid var(--cta)",
            borderRadius: 10,
            padding: "16px 18px",
            width: 420,
            maxHeight: "min(620px, calc(100vh - 40px))",
            overflowY: "auto",
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
                fontSize: 9,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: 0.6,
                color: "var(--text-muted)",
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

          {/* Multiplicative chain */}
          {why.final_p !== null && (
            <div style={{
              textAlign: "center",
              padding: "10px 0 6px",
              fontFamily: "var(--mono)",
              fontSize: 13,
              color: "var(--text-2)",
            }}>
              {pctOf(why.base_p)}%
              {why.lifts.map((entry, i) => (
                <span key={i}> × {entry.lift.toFixed(1)}</span>
              ))}
              {" = "}
              <strong style={{ color: "var(--text)", fontSize: 14 }}>
                {pctOf(why.final_p)}%
              </strong>
            </div>
          )}

          {/* Footer */}
          <div style={{
            marginTop: 8,
            paddingTop: 10,
            borderTop: "1px solid var(--border-light)",
            fontSize: 11,
            color: "var(--text-muted)",
            lineHeight: 1.5,
          }}>
            <strong>Lift &gt; 1</strong> means this feature makes the
            prediction more likely; <strong>base P</strong> is the prior
            probability of the predicted value.
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}


function PatternMatchCard({ entry }: { entry: WhyLiftEntry }) {
  const up = entry.lift >= 1;
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
          Pattern match
        </div>
        <div style={{ fontSize: 12, color: "var(--text)" }}>
          When{" "}
          {entry.propositions.map((p, i) => (
            <span key={i}>
              {i > 0 && <span style={{ color: "var(--text-muted)" }}> and </span>}
              <code style={{ fontFamily: "var(--mono)", color: "var(--text-2)" }}>
                {p.field}
              </code>
              <span style={{ color: "var(--text-muted)" }}>
                {" "}{p.negate ? "is not " : "is "}
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
        </div>
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


function pctOf(p: number | null): string {
  if (p === null) return "?";
  return Math.round(p * 100).toString();
}
