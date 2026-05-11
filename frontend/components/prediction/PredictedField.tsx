"use client";

import { useState } from "react";
import WhyTooltip from "./WhyTooltip";
import type { WhyFactor } from "@/lib/types";

interface PredictedFieldProps {
  label: string;
  value: string;
  confidence: number;
  predicted?: boolean;
  why?: WhyFactor[];
  onChange?: (value: string) => void;
  readOnly?: boolean;
}

/**
 * Form-field element with three visual states:
 *
 *   - **Empty**:     neutral border, placeholder
 *   - **Predicted**: gold tint, value filled in by Aito, ⓘ icon for `WhyTooltip`
 *   - **User**:      neutral border, value typed/picked by user
 *
 * Used by the Product Filling view. When the user edits a
 * predicted value, the badge state flips to "User" so it's
 * obvious the override is human-supplied.
 */
export default function PredictedField({
  label,
  value,
  confidence,
  predicted = true,
  why,
  onChange,
  readOnly = false,
}: PredictedFieldProps) {
  const [current, setCurrent] = useState(value);
  const [overridden, setOverridden] = useState(false);
  const isPredicted = predicted && !overridden;
  const pct = Math.round(confidence * 100);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setCurrent(v);
    setOverridden(v !== value);
    onChange?.(v);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>
          {label}
        </label>
        {isPredicted && why && why.length > 0 && <WhyTooltip factors={why} />}
      </div>
      <input
        type="text"
        className="search-input"
        style={
          isPredicted
            ? { background: "var(--cta-bg)", borderColor: "var(--cta-border)" }
            : undefined
        }
        value={current}
        onChange={handleChange}
        readOnly={readOnly}
      />
      {isPredicted && (
        <div style={{ fontSize: 11, color: "var(--cta)", fontFamily: "var(--mono)" }}>
          Predicted {pct}% confidence
        </div>
      )}
    </div>
  );
}
