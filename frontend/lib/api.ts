/** Frontend API helpers.
 *
 * Single-tenant: no `X-Tenant` header (the multi-tenant routing in
 * `aito-erp-demo` was deliberately dropped — see ADR 0001). Other
 * cross-demo affordances kept verbatim:
 *
 *   - `apiFetch<T>` — JSON wrapper with same-origin proxy via
 *     `frontend/next.config.ts` rewrites.
 *   - `AITO_CALLS_EVENT` — the latency badge listens to this event
 *     and renders a per-call breakdown from the `X-Aito-Calls`
 *     response header.
 *   - `fmtEur`, `fmtAmount`, `confClass` — small UI primitives
 *     reused across views.
 */

const API_BASE = typeof window !== "undefined"
  ? `${window.location.protocol}//${window.location.host}`
  : "";

/** One Aito API call's wall time, parsed from `X-Aito-Calls`. */
export interface AitoCall {
  endpoint: string;     // "_predict", "_relate", ...
  ms: number;
}

/** Event payload broadcast on every API response that included Aito work.
 *  The latency pill subscribes via `window.addEventListener("aito:calls", ...)`. */
export interface AitoCallsEvent {
  path: string;         // backend route (e.g. "/api/health")
  calls: AitoCall[];    // empty for cache-hit responses (no header)
  cached: boolean;      // true when no X-Aito-Calls header present
}

export const AITO_CALLS_EVENT = "aito:calls";

// Marker so an aggressive auto-reload can't loop. sessionStorage scope
// = one auto-recovery attempt per tab visit.
const STALE_STATE_RECOVERY_KEY = "aitoStaleStateRecoveryAttempted";

/** Best-effort recovery from a fetch-level TypeError ("Failed to fetch" /
 *  "Load failed"). The most common cause in this demo is a stale cached
 *  HTML+JS bundle from before nginx started sending `Cache-Control: no-
 *  store` on HTML — an old bundle issues requests the current backend
 *  doesn't satisfy and fetch() rejects with a TypeError. Clear local
 *  state + reload to force a fresh HTML fetch and current bundle hashes.
 *
 *  Returns true when a reload was triggered so the caller can stall
 *  instead of surfacing the original error to the user mid-navigation. */
async function tryStaleStateRecovery(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (window.sessionStorage.getItem(STALE_STATE_RECOVERY_KEY) === "1") return false;
  window.sessionStorage.setItem(STALE_STATE_RECOVERY_KEY, "1");
  try { window.localStorage.clear(); } catch { /* private mode etc. */ }
  try {
    if (typeof caches !== "undefined") {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch { /* CacheStorage may be denied */ }
  window.location.reload();
  return true;
}

function parseAitoCalls(header: string | null): AitoCall[] {
  if (!header) return [];
  return header
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((token) => {
      const [endpoint, ms] = token.split(":");
      return { endpoint, ms: Number(ms) || 0 };
    });
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (err) {
    // TypeError from fetch() = network-level failure (offline, DNS, TLS,
    // request aborted by extension/data-saver, *or* — most common cause
    // for this demo's existing prospects — a stale cached bundle).
    // Try a one-shot self-heal. On success the page is reloading, so
    // return a never-resolving promise to stop the caller from briefly
    // rendering its error UI before navigation completes.
    if (err instanceof TypeError && await tryStaleStateRecovery()) {
      return new Promise<T>(() => { /* page is reloading */ });
    }
    throw err;
  }
  // Broadcast every successful response's Aito-call timings (or empty
  // list for cache hits). The latency pill listens; pages that don't
  // care can ignore. Done before .json() so the pill updates as soon
  // as the headers land, not after the body parses.
  if (typeof window !== "undefined" && res.ok) {
    const detail: AitoCallsEvent = {
      path,
      calls: parseAitoCalls(res.headers.get("X-Aito-Calls")),
      cached: !res.headers.has("X-Aito-Calls"),
    };
    window.dispatchEvent(new CustomEvent(AITO_CALLS_EVENT, { detail }));
  }
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

/** "€ 1 234" — Finnish space-grouping, no decimals by default. */
export function fmtEur(n: number, decimals: number = 0): string {
  return "€ " + n.toLocaleString("fi-FI", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Alias for cross-demo familiarity (the ERP/accounting demos use
 *  `fmtAmount`). Same behaviour as `fmtEur` for default decimals. */
export const fmtAmount = fmtEur;

/** Confidence-tier class for `PredictionBadge` / `ConfidenceBar` /
 *  `WhyTooltip`. Thresholds locked across every demo. */
export function confClass(p: number): string {
  if (p >= 0.80) return "conf-high";
  if (p >= 0.50) return "conf-mid";
  return "conf-low";
}
