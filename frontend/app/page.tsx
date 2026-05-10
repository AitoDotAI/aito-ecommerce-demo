"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

/**
 * Scaffold-step landing page.
 *
 * Renders the brand mark, a one-line description, and a live health
 * pill that hits `/api/health` to confirm:
 *
 *   1. The Next.js → FastAPI proxy works.
 *   2. The backend can reach Aito with the configured credentials.
 *
 * Replaced in build-order step 4 with the full layout shell + the
 * Dashboard view content. Until then this is the smoke-test surface
 * for `./do dev`.
 */
export default function ScaffoldHome() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<HealthResponse>("/api/health")
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  let pillClass = "health-pill";
  let pillLabel = "Checking backend…";
  if (error) {
    pillClass = "health-pill error";
    pillLabel = `Backend unreachable: ${error}`;
  } else if (health) {
    if (health.aito_connected) {
      pillClass = "health-pill ok";
      pillLabel = "Backend up · Aito connected";
    } else {
      pillClass = "health-pill degraded";
      pillLabel = "Backend up · Aito unreachable (check .env)";
    }
  }

  return (
    <main className="scaffold-placeholder">
      <div className="logo-mark" aria-hidden="true">
        <span>
          aito<em>..</em>
        </span>
      </div>

      <h1>Predictive E-commerce — scaffold up</h1>
      <p>
        PetNord, the third Aito vertical demo. The full UI lands in
        build-order step 4 (layout shell + Dashboard view). Until then
        this page exists to smoke-test that <code>./do dev</code>
        wires Next.js → FastAPI → Aito end-to-end.
      </p>

      <span className={pillClass}>
        <span className="dot" aria-hidden="true" />
        {pillLabel}
      </span>

      <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
        Next:{" "}
        <code>docs/adr/0002-fixtures.md</code> →{" "}
        <code>data/generate_fixtures.py</code> →{" "}
        <code>./do load-data</code>.
      </p>
    </main>
  );
}
