"use client";

import { fmtEur } from "@/lib/api";
import type { BoardItem, Conversation, Routine } from "@/lib/shopkeeper";

const ICON: Record<BoardItem["kind"], string> = { evidence: "🧪", approval: "✋", root_cause: "🔎" };

/** The view's three lists, top to bottom: the Board, the routines, the past conversations. */
export default function LeftLists({ board, routines, conversations, selected, onSelect }: {
  board: BoardItem[]; routines: Routine[]; conversations: Conversation[];
  selected: string; onSelect: (id: string) => void;
}) {
  const pick = (id: string | null) => id && onSelect(id);
  return (
    <div>
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-title">Board · what to improve</div>
        {board.length === 0 && <div className="card-sub">Nothing open.</div>}
        {board.map((item) => (
          <button key={item.id} className="btn btn-ghost" onClick={() => pick(item.raised_by)}
            style={{ display: "block", width: "100%", textAlign: "left", marginBottom: 6, whiteSpace: "normal" }}>
            <span>{ICON[item.kind]} {item.title}</span>
            <span className="card-sub" style={{ display: "block" }}>
              {item.owner === "agent" ? "Agent" : "You"} · {item.status}
            </span>
          </button>
        ))}
      </div>
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-title">Agents and routines</div>
        {routines.map((r) => (
          <button key={r.id} className="btn btn-ghost" disabled={!r.latest_run} onClick={() => pick(r.latest_run)}
            title={r.does} style={{ display: "block", width: "100%", textAlign: "left", marginBottom: 6, whiteSpace: "normal", opacity: r.built ? 1 : 0.55 }}>
            <span>{r.name}</span>
            <span className="card-sub" style={{ display: "block" }}>{r.built ? r.schedule : "Not built yet"}</span>
          </button>
        ))}
      </div>
      <div className="card">
        <div className="card-title">Past conversations</div>
        {conversations.map((c) => (
          <button key={c.id} className="btn btn-ghost" onClick={() => onSelect(c.id)}
            style={{ display: "block", width: "100%", textAlign: "left", whiteSpace: "normal",
              borderColor: selected === c.id ? "var(--aito-teal)" : undefined }}>
            <span>{c.title} · {c.as_of_month}{c.stale ? " (stale)" : ""}</span>
            <span className="card-sub" style={{ display: "block" }}>
              Acted {c.tally.act.steps} · {fmtEur(c.tally.act.expected_net_eur)} expected · waiting {c.tally.suggest.steps + c.tally.never_auto.steps}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
