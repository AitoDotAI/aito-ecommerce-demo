"use client";

import { useRef, useState } from "react";

import { TRAIT_TITLE, type ProfilesSummary, type SegmentView } from "@/lib/customer-profiles";
import RankingDialog from "@/components/customers/RankingDialog";

/** The selected segment's name and size, and the "?" that opens where it sits in what customers prefer. */
export default function SegmentHeader({ summary, view }: { summary: ProfilesSummary; view: SegmentView }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [opened, setOpened] = useState(false);
  const title = view.conditions.length === 0 ? "Everyone profiled" : view.conditions.map((c) => c.split(":").slice(1).join(":")).join(" · ");
  return (
    <div>
      <div className="card-sub">{view.conditions.length === 0 ? "No condition ticked" : view.conditions.map((c) => TRAIT_TITLE[c.split(":")[0]]).join(" · ")}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "2px 0 6px" }}>
        <div className="page-title" style={{ fontSize: 24, margin: 0 }}>{title}</div>
        <button aria-label="Where this segment sits in what customers prefer" title="Where do they sit in what customers prefer: discounts, dogs, a category, a brand?"
                onClick={() => { setOpened(true); dialog.current?.showModal(); }} style={{ cursor: "pointer", width: 22, height: 22, borderRadius: "50%",
                  border: "1px solid var(--border)", background: "transparent", color: "var(--text)", font: "inherit", fontSize: 13, lineHeight: 1, flex: "none" }}>?</button>
      </div>
      <div className="card-sub">
        {view.customers.toLocaleString("en-GB")} customers, {Math.round((view.customers / summary.profiled) * 100)} % of those profiled.
      </div>
      <dialog ref={dialog} onClick={(e) => { if (e.target === dialog.current) dialog.current?.close(); }}
              style={{ width: "min(640px, 94vw)", maxHeight: "88vh", overflowY: "auto", margin: "auto", border: "1px solid var(--border)", borderRadius: 8, padding: 16,
                background: "var(--bg)", color: "var(--text)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
          <div className="card-title" style={{ margin: 0 }}>Where {title.toLowerCase()} sit in what customers prefer</div>
          <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => dialog.current?.close()}>Close</button>
        </div>
        {opened && <RankingDialog summary={summary} view={view} />}
      </dialog>
    </div>
  );
}
