"use client";

import { Suspense, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { shopkeeperPanel } from "@/lib/panel-content";
import { readBrowserState, settingsQuery, writeBrowserState, type GateSettings, type Run, type ShopkeeperOverview } from "@/lib/shopkeeper";
import { useUrlState } from "@/lib/use-url-state";
import { usePagePanel } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import GateSettingsForm from "@/components/shopkeeper/GateSettingsForm";
import LeftLists from "@/components/shopkeeper/LeftLists";
import RunPane from "@/components/shopkeeper/RunPane";

type Decisions = Record<string, "approved" | "rejected">;

/**
 * Shopkeeper (ADR 0052): an agent's routine runs, judged by the store's own gate. On the left the Board of
 * improvements, the routines and the past conversations; on the right the selected run. Runs are stored and
 * simulated; the settings and approvals stay in this browser.
 */
function ShopkeeperView() {
  usePagePanel(shopkeeperPanel(), {
    title: "Shopkeeper",
    description: "An agent that runs the shop's routines, acts when it is sure, and asks when it is not.",
    breadcrumb: "Operate › Shopkeeper",
  });
  const [selected, setSelected] = useUrlState("run", "winback");
  const [overview, setOverview] = useState<ShopkeeperOverview | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [settings, setSettings] = useState<GateSettings | null>(null);
  const [decisions, setDecisions] = useState<Decisions>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const saved = readBrowserState();
    setDecisions(saved.decisions ?? {});
    apiFetch<ShopkeeperOverview>("/api/shopkeeper")
      .then((res) => { setOverview(res); setSettings(saved.settings ?? res.settings.recommended); })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!overview || !settings) return;
    const query = settingsQuery(settings, overview.settings.recommended);
    apiFetch<ShopkeeperOverview>(`/api/shopkeeper${query}`).then(setOverview).catch((e) => setError(String(e)));
    apiFetch<Run>(`/api/shopkeeper/runs/${selected}${query}`).then(setRun).catch((e) => setError(String(e)));
    // The overview is refetched on a settings change only; `overview` itself is not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings, selected]);

  const changeSettings = (next: GateSettings) => { setSettings(next); writeBrowserState({ settings: next, decisions }); };
  const decide = (key: string, choice: "approved" | "rejected" | null) => {
    const next = { ...decisions };
    if (choice) next[key] = choice; else delete next[key];
    setDecisions(next);
    writeBrowserState({ settings: settings ?? undefined, decisions: next });
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Shopkeeper</div>
        <div className="page-desc">
          An agent that runs the shop&apos;s routines. It acts when the evidence is there, proposes when it is
          not sure, stays quiet when there is none, and always asks before the kinds you name. Simulated: nothing is sent.
        </div>
      </div>
      {error && <ErrorState title="Couldn't load Shopkeeper" message={error} command="./do dev" />}
      {!overview && !error && <div className="card" style={{ height: 160, background: "var(--border-light)" }} />}
      {overview && settings && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(240px, 1fr) minmax(0, 2fr)", gap: 16, alignItems: "start" }}>
          <LeftLists board={overview.board} routines={overview.routines} conversations={overview.conversations}
            selected={selected} onSelect={setSelected} />
          <div>
            <GateSettingsForm view={overview.settings} value={settings} onChange={changeSettings} />
            {run && <RunPane run={run} decisions={decisions} onDecide={decide} />}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ShopkeeperPage() {
  return <Suspense fallback={null}><ShopkeeperView /></Suspense>;
}
