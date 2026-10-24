"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { MOVED_ROUTES } from "@/lib/moved-routes";
import { usePagePanel } from "./ShellState";

/**
 * The page left at an old route (ADR 0041): it forwards to the route's new
 * home, with the link's query string and hash, and replaces the history
 * entry so Back doesn't bounce through the old address.
 */
export default function MovedRoute({ from }: { from: string }) {
  const moved = MOVED_ROUTES[from];
  if (!moved) throw new Error(`MovedRoute: ${from} is not in lib/moved-routes.ts`);
  const router = useRouter();
  usePagePanel(null, { title: "Moved", breadcrumb: "Moved" });

  useEffect(() => {
    router.replace(moved.to + window.location.search + window.location.hash);
  }, [router, moved.to]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">This view has moved</div>
        <div className="page-desc">
          It now lives in <Link href={moved.to}>{moved.label}</Link>. Taking you there…
        </div>
      </div>
    </div>
  );
}
