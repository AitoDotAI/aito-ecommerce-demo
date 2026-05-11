"use client";

interface LiftHintProps {
  value: number;
}

/**
 * Inline "× 3.1" lift annotation, colour-coded by band:
 *
 *   ≥ 1.5×   green (positive co-occurrence)
 *   0.7–1.5× grey  (neutral)
 *   < 0.7×   red   (protective / negative)
 *
 * Used in `_relate` result tables (Pattern Explorer, Bought
 * Together) and anywhere a single lift value needs to render
 * inline next to a label.
 */
export default function LiftHint({ value }: LiftHintProps) {
  let tier: "up" | "neutral" | "down" = "neutral";
  if (value >= 1.5) tier = "up";
  else if (value < 0.7) tier = "down";

  return (
    <span className={`lift-hint ${tier}`}>
      × {value.toFixed(1)}
    </span>
  );
}
