"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { initAnalytics, trackPage } from "@/lib/analytics";

/**
 * Mounts the Segment + GA loaders on first render and fires a
 * page() event on every Next route change. No-op on localhost
 * (see `isProductionHost` in `lib/analytics.ts`) so dev runs
 * don't pollute analytics.
 *
 * Render once near the top of the app tree (currently in
 * `app/layout.tsx`).
 */
export default function Analytics() {
  const pathname = usePathname();

  useEffect(() => {
    initAnalytics();
  }, []);

  useEffect(() => {
    if (!pathname) return;
    trackPage(pathname);
  }, [pathname]);

  return null;
}
