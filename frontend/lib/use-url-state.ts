"use client";

import { useCallback } from "react";
import { usePathname, useSearchParams } from "next/navigation";

/**
 * A piece of view state kept in the URL's query string, so a pasted link
 * opens the view exactly as it was shared, and back/forward step through
 * the user's choices.
 *
 * The default is left out of the URL, so a plain link to a view stays
 * plain. Each change pushes a history entry; a component reading
 * `useSearchParams` must sit under a <Suspense> boundary for the static
 * export, so pages wrap their view in one.
 *
 * Changes go through the native `history.pushState`, which Next syncs into
 * `useSearchParams`. `router.push` would first fetch the route's server
 * payload, and in the static export that request doesn't resolve, so the
 * click silently did nothing (seen in scripts/deeplink-test.cjs).
 */
export function useUrlState(key: string, fallback: string): [string, (next: string) => void] {
  const params = useSearchParams();
  const pathname = usePathname();
  const value = params.get(key) ?? fallback;

  const set = useCallback((next: string) => {
    const query = new URLSearchParams(params.toString());
    if (next === fallback) {
      query.delete(key);
    } else {
      query.set(key, next);
    }
    const qs = query.toString();
    window.history.pushState(null, "", qs ? `${pathname}?${qs}` : pathname);
  }, [params, pathname, key, fallback]);

  return [value, set];
}
