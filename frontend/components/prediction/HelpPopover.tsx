"use client";

import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { popoverStyle } from "@/lib/popover-placement";

/**
 * A "?" button that opens a short plain-language explanation of a number on the page.
 * Same look and placement as WhyPopover, but the body is text, not an Aito `$why` chain:
 * for explaining what a figure means, not why Aito predicted it.
 */
export default function HelpPopover({ label, title, children }: {
  label: string;      // the button's accessible name, e.g. "What does this percentage mean?"
  title: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<CSSProperties>({});
  const btnRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      const inside = (el: HTMLElement | null) => el?.contains(e.target as Node);
      if (!inside(btnRef.current) && !inside(tipRef.current)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  function toggle() {
    if (!open && btnRef.current) setPlacement(popoverStyle(btnRef.current.getBoundingClientRect(), 380));
    setOpen(!open);
  }

  return (
    <>
      <button
        ref={btnRef}
        onClick={toggle}
        aria-label={label}
        aria-expanded={open}
        style={{
          width: 18, height: 18, borderRadius: "50%", border: "none", padding: 0, flexShrink: 0,
          background: open ? "var(--cta)" : "var(--cta-bg)", color: open ? "white" : "var(--cta)",
          fontSize: 11, fontWeight: 700, fontFamily: "var(--mono)", lineHeight: 1, cursor: "pointer",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}
      >
        ?
      </button>
      {open && typeof document !== "undefined" && createPortal(
        <div
          ref={tipRef}
          style={{
            ...placement, zIndex: 9999, background: "var(--white)", border: "2px solid var(--cta)",
            borderRadius: 10, padding: "14px 16px", boxShadow: "0 12px 32px rgba(0,0,0,0.25)",
            color: "var(--text)", fontSize: 13, lineHeight: 1.5,
          }}
        >
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>{title}</div>
          {children}
        </div>,
        document.body,
      )}
    </>
  );
}
