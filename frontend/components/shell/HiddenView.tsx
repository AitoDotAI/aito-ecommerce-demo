"use client";

import Link from "next/link";

import { usePagePanel } from "./ShellState";

/**
 * Shown in place of a view listed in `lib/hidden-routes.ts`. It says
 * why the view is hidden rather than pretending the page doesn't exist.
 *
 * The hidden page never mounts, so it never sets the Aito panel; the
 * previous page's query would stay on screen beside this notice. Setting
 * an empty panel and this page's own title keeps the screen coherent.
 */
export default function HiddenView({ reason }: { reason: string }) {
  usePagePanel(null, { title: "Not shown right now", breadcrumb: "Not shown right now" });
  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Not shown right now</div>
        <div className="page-desc">
          This view is hidden while the demo&apos;s synthetic purchase data is
          regenerated with realistic patterns (restocking, a starter kit that
          grows). {reason}
        </div>
      </div>
      <div className="card">
        <div className="card-sub" style={{ lineHeight: 1.6 }}>
          In the meantime, <Link href="/smart-search/">Smart Search</Link>,{" "}
          <Link href="/recommendations/">For You</Link>,{" "}
          <Link href="/bought-together/">Bought Together</Link> and{" "}
          <Link href="/inventory/">Inventory</Link> show the same predictive
          database at work.
        </div>
      </div>
    </div>
  );
}
