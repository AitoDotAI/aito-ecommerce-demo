"use client";

interface ScaffoldStubProps {
  /** Slug from `TASK.md` (e.g. "smart-search"). */
  view: string;
  /** Build-order step number that ships this view's real content. */
  step: number;
  /** One-line summary of the load-bearing demo moment. Shown so a
   *  visitor lands on the empty page and immediately knows what's
   *  *going* to be here. */
  blurb: string;
}

/**
 * Empty-view placeholder. Used by the seven scaffolded routes
 * (Smart Search, For You, Bought Together, Purchase Analytics,
 * Pattern Explorer, Product Filling, Evaluation) until their real
 * content lands per the build order in `TASK.md`.
 *
 * The shell (TopBar / Sidebar / Aito panel) renders fine around
 * this stub, so the layout is testable without the views being
 * built yet.
 */
export default function ScaffoldStub({ view, step, blurb }: ScaffoldStubProps) {
  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Building this view</div>
        <div className="page-desc">{blurb}</div>
      </div>

      <div className="card">
        <div className="card-title">Scaffold</div>
        <div className="card-sub">
          This route exists so the navigation resolves and the Aito
          panel can preview the right endpoint badges + draft query.
          Real content lands in <strong>build-order step {step}</strong>.
          The panel on the right is already wired and accurate; the
          query body shown will become runnable when the view ADR
          lands.
        </div>

        <div style={{ marginTop: 14 }}>
          <code style={{
            display: "inline-block",
            fontFamily: "var(--mono)",
            fontSize: 12,
            background: "var(--bg)",
            border: "1px solid var(--border)",
            padding: "4px 10px",
            borderRadius: 5,
            color: "var(--text-2)",
          }}>
            frontend/app/{view}/page.tsx
          </code>
        </div>
      </div>
    </div>
  );
}
