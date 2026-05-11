"use client";

import { useEffect, useRef, useState } from "react";
import { confClass } from "@/lib/api";
import type { Alternative } from "@/lib/types";

interface PredictionBadgeProps {
  value: string;
  confidence: number;
  predicted?: boolean;
  alternatives?: Alternative[];
  onSelect?: (value: string) => void;
}

/**
 * Single predicted value with a confidence chip. Tap to see
 * alternatives (when present). Predicted values carry a 🤖
 * prefix so the user always knows what came from the model.
 */
export default function PredictionBadge({
  value,
  confidence,
  predicted = true,
  alternatives,
  onSelect,
}: PredictionBadgeProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const tier = confClass(confidence).replace("conf-", "");
  const className = `pred-badge ${tier}`;

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <span
        className={className}
        style={{ cursor: alternatives?.length ? "pointer" : "default" }}
        onClick={() => alternatives?.length && setOpen(!open)}
      >
        {predicted && <span aria-hidden="true">🤖</span>}
        {value}
      </span>

      {open && alternatives && alternatives.length > 0 && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: 4,
            background: "var(--white)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            boxShadow: "0 4px 12px rgba(0,0,0,0.12)",
            zIndex: 200,
            minWidth: 180,
            padding: "4px 0",
          }}
        >
          {alternatives.map((alt) => (
            <div
              key={alt.value}
              onClick={() => {
                onSelect?.(alt.value);
                setOpen(false);
              }}
              style={{
                padding: "6px 12px",
                fontSize: 12,
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
              }}
            >
              <span>{alt.value}</span>
              <span
                className="conf-val"
                style={{
                  color:
                    alt.confidence >= 0.8
                      ? "var(--green)"
                      : alt.confidence >= 0.5
                      ? "var(--cta)"
                      : "var(--red)",
                }}
              >
                {Math.round(alt.confidence * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
