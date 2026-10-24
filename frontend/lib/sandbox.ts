/** Sandbox mode (ADR 0043): the page's `?db=<branch>` names a throwaway
 *  branch of the sandbox database, and every API call of the page carries
 *  it as `X-Aito-Env` (lib/api.ts). The URL is the truth, so a link can be
 *  shared in a meeting; the sidebar keeps `?db` on every view's link. */

"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export const SANDBOX_PARAM = "db";
export const SANDBOX_HEADER = "X-Aito-Env";
export const SANDBOX_MONTH = "2026-05";
const ADMIN_TOKEN_KEY = "aitoSandboxAdminToken";
const LAST_LEVER_KEY = "aitoSandboxLastLever";

/** The sandbox the page's URL names, or null. */
export function sandboxEnv(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(SANDBOX_PARAM);
}

/** The same, kept current as the user moves between views. */
export function useSandboxEnv(): string | null {
  const pathname = usePathname();
  const [env, setEnv] = useState<string | null>(null);
  useEffect(() => { setEnv(sandboxEnv()); }, [pathname]);
  return env;
}

/** `href` with the sandbox kept on it. */
export function withSandbox(href: string, env: string | null): string {
  if (!env) return href;
  return `${href}${href.includes("?") ? "&" : "?"}${SANDBOX_PARAM}=${encodeURIComponent(env)}`;
}

/** "tmp-2026-10-26-15-30-00-3f9c2a1b7d4e6f80" → "15:30 · 3f9c". */
export function shortSandboxName(env: string): string {
  const m = env.match(/^tmp-\d{4}-\d{2}-\d{2}-(\d{2})-(\d{2})-\d{2}-([0-9a-f]{4})/);
  return m ? `${m[1]}:${m[2]} · ${m[3]}` : env;
}

/** The operator's admin token, asked once per tab. */
export function adminToken(): string | null {
  try {
    const kept = window.sessionStorage.getItem(ADMIN_TOKEN_KEY);
    if (kept) return kept;
  } catch { /* storage blocked: ask every time */ }
  const typed = window.prompt("Admin token for a new sandbox");
  if (!typed) return null;
  try { window.sessionStorage.setItem(ADMIN_TOKEN_KEY, typed); } catch { /* not kept */ }
  return typed;
}

export function forgetAdminToken(): void {
  try { window.sessionStorage.removeItem(ADMIN_TOKEN_KEY); } catch { /* nothing kept */ }
}

/** The session's last lever, so the Shop can say "since the offer" or "since the review". */
export interface LastLever { sku: string; lever: "offer" | "review" }

export function rememberLever(lever: LastLever): void {
  try { window.sessionStorage.setItem(LAST_LEVER_KEY, JSON.stringify(lever)); } catch { /* not kept */ }
}

export function lastLever(): LastLever | null {
  try {
    const kept = window.sessionStorage.getItem(LAST_LEVER_KEY);
    return kept ? JSON.parse(kept) as LastLever : null;
  } catch { return null; }
}
