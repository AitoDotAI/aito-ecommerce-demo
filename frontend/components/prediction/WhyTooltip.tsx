"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { WhyFactor } from "@/lib/types";

interface WhyTooltipProps {
  factors: WhyFactor[];
}

/**
 * `$why` decomposition popover. Reads Aito's per-pattern lift
 * factors and shows them verbatim — multiplicative chain ending
 * in the final probability. Never simplify or summarise the
 * chain (CLAUDE.md / framework §6.3): the demo's auditability
 * story depends on showing the arithmetic.
 */
export default function WhyTooltip({ factors }: WhyTooltipProps) {
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
      setPos({ top: rect.bottom + 6, left: Math.max(8, rect.left - 120) });
    }
    setOpen(!open);
  }

  if (!factors || factors.length === 0) return null;

  return (
    <>
      <button
        ref={btnRef}
        onClick={toggle}
        title="Show prediction reasoning"
        style={{
          width: 18,
          height: 18,
          borderRadius: "50%",
          border: "1px solid var(--border)",
          background: open ? "var(--cta-bg)" : "var(--white)",
          color: open ? "var(--cta)" : "var(--text-2)",
          fontSize: 10,
          fontWeight: 700,
          cursor: "pointer",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--mono)",
          lineHeight: 1,
          flexShrink: 0,
        }}
        aria-label="Why this prediction?"
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
            background: "var(--aito-bg)",
            border: "1px solid rgba(155,105,255,0.3)",
            borderRadius: 6,
            padding: "10px 12px",
            minWidth: 240,
            maxWidth: 320,
            boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
          }}
        >
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: 0.5,
              color: "var(--aito-purple)",
              marginBottom: 8,
            }}
          >
            $why factors
          </div>
          {factors.map((f, i) => (
            <div
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "auto auto 1fr",
                gap: 8,
                fontSize: 11,
                color: "var(--aito-text)",
                marginBottom: 6,
                alignItems: "baseline",
              }}
            >
              <span style={{ fontFamily: "var(--mono)", color: "var(--aito-teal)" }}>
                {f.field}
              </span>
              <span
                style={{
                  fontFamily: "var(--mono)",
                  color: "var(--aito-teal)",
                  fontWeight: 700,
                }}
              >
                {f.lift.toFixed(1)}×
              </span>
              <span style={{ color: "var(--aito-dim)" }}>{f.value}</span>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}
