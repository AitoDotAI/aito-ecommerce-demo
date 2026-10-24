/** Demo mode: the app as presented in a meeting. The Aito panel starts
 *  collapsed, "Start free trial" is hidden, and each view keeps one plain
 *  caveat line with its fine print behind "Details" (components/shell/FinePrint).
 *  Presentation only: every number and its basis stay one click away.
 *
 *  On with `?demo=1` (off with `?demo=0`) for the rest of the tab's session,
 *  or by default when the server's config has DEMO_MODE=1 (`/api/version`). */

"use client";

export const DEMO_PARAM = "demo";
const DEMO_KEY = "ecom.demoMode";

/** The tab's own choice: the URL's `?demo=`, kept for the session; else null. */
export function tabDemoChoice(): boolean | null {
  if (typeof window === "undefined") return null;
  const inUrl = new URLSearchParams(window.location.search).get(DEMO_PARAM);
  try {
    if (inUrl === "1" || inUrl === "0") window.sessionStorage.setItem(DEMO_KEY, inUrl);
    const kept = window.sessionStorage.getItem(DEMO_KEY);
    if (kept === "1" || kept === "0") return kept === "1";
  } catch { /* storage blocked: the URL alone decides */ }
  return inUrl === "1" ? true : inUrl === "0" ? false : null;
}

/** The server's default (DEMO_MODE=1). Fetched directly, not through
 *  `apiFetch`, so it never moves the latency pill. Unreachable: off. */
export async function serverDemoMode(): Promise<boolean> {
  try {
    const res = await fetch("/api/version");
    return res.ok && (await res.json()).demo_mode === true;
  } catch {
    return false;
  }
}
