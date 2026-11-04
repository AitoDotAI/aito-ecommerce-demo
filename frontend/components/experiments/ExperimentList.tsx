import { ARM_LABEL, KIND_LABEL, STATUS_LABEL, clearWinner, type Experiment, type Status } from "@/lib/experiments";

const CHIP: Record<Status, { colour: string; background: string }> = {
  draft: { colour: "var(--text-muted)", background: "var(--border-light)" },
  running: { colour: "var(--aito-teal)", background: "rgba(0, 168, 150, 0.15)" },
  decided: { colour: "var(--text)", background: "var(--border)" },
};

/** The experiments, one row each: product, kind, state, and what the data says so far. Choosing one shows it. */
export default function ExperimentList({ experiments, selected, onSelect }: { experiments: Experiment[]; selected: string; onSelect: (id: string) => void }) {
  return (
    <div className="card" role="listbox" aria-label="Experiments">
      <div className="card-title" style={{ marginTop: 0 }}>Experiments</div>
      {experiments.map((e) => {
        const winner = clearWinner(e);
        const on = e.experiment_id === selected;
        return (
          <button key={e.experiment_id} role="option" aria-selected={on} onClick={() => onSelect(e.experiment_id)} style={{
            display: "block", width: "100%", textAlign: "left", cursor: "pointer", font: "inherit", color: "var(--text)", padding: "8px 8px",
            border: "none", borderTop: "1px solid var(--border-light)", background: on ? "rgba(0, 168, 150, 0.12)" : "transparent" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
              <span style={{ fontSize: 13, fontWeight: 600, overflowWrap: "anywhere" }}>{e.product}</span>
              <span style={{ fontSize: 11, padding: "1px 8px", borderRadius: 10, whiteSpace: "nowrap", ...CHIP[e.status] }}>{STATUS_LABEL[e.status]}</span>
            </div>
            <div className="card-sub" style={{ fontSize: 12 }}>
              {KIND_LABEL[e.kind]} · {winner ? `${ARM_LABEL[winner]} is ahead` : e.status === "draft" ? "no showings yet" : "no clear difference yet"}
            </div>
          </button>
        );
      })}
    </div>
  );
}
