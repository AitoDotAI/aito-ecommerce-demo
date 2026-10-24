import type { CSSProperties } from "react";

/** Below this width a popover is a bottom sheet, not anchored to its button. */
export const SHEET_BREAKPOINT = 640;
const MARGIN = 12;

/**
 * Where a `position: fixed` popover opened from `anchor` goes, so it never leaves the screen.
 *
 * On a phone (narrower than SHEET_BREAKPOINT) the popover is a bottom sheet: full width less a
 * margin, as tall as the content up to most of the screen, scrolling inside. A fixed pixel
 * width, as the popovers used to have (420 px), is wider than a 414 px phone, so its right
 * side was clipped.
 *
 * On a wide screen it sits under its button, right-aligned to it, clamped inside the viewport
 * on both axes.
 */
export function popoverStyle(
  anchor: DOMRect,
  preferredWidth: number,
  viewport: { width: number; height: number } = { width: window.innerWidth, height: window.innerHeight },
): CSSProperties {
  if (viewport.width < SHEET_BREAKPOINT) {
    return {
      position: "fixed",
      left: MARGIN,
      right: MARGIN,
      bottom: MARGIN,
      width: "auto",
      maxHeight: Math.round(viewport.height * 0.75),
      overflowY: "auto",
    };
  }
  const width = Math.min(preferredWidth, viewport.width - 2 * MARGIN);
  const left = Math.min(Math.max(MARGIN, anchor.right - width), viewport.width - MARGIN - width);
  const top = Math.max(MARGIN, Math.min(anchor.bottom + 8, viewport.height - 240));
  return {
    position: "fixed",
    top,
    left,
    width,
    maxHeight: viewport.height - top - MARGIN,
    overflowY: "auto",
  };
}
