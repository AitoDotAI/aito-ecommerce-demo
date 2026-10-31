"use client";

import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { SANDBOX_PARAM, adminToken, forgetAdminToken, shortSandboxName, useSandboxEnv } from "@/lib/sandbox";
import type { SandboxStatus } from "@/lib/types";

/** Sandbox mode (ADR 0043). Shown only on a server with a sandbox database
 *  (`/api/sandbox`): in a sandbox, which one, when it expires, and that it
 *  starts from the release data; outside one, "New sandbox" for the operator.
 *  The sandbox is a throwaway branch, so "New sandbox" is also the reset. */
export default function SandboxBanner() {
  const env = useSandboxEnv();
  const [status, setStatus] = useState<SandboxStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    apiFetch<SandboxStatus>("/api/sandbox").then(setStatus, (e) =>
      setError(e instanceof ApiError ? e.serverMessage ?? e.message : String(e)));
  }, [env]);

  if (!status?.configured && !error) return null;

  const create = async () => {
    const token = adminToken();
    if (!token) return;
    setError(null);
    try {
      const made = await apiFetch<{ env: string }>("/api/sandbox", { method: "POST", headers: { "X-Admin-Token": token } });
      const url = new URL(window.location.href);
      url.searchParams.set(SANDBOX_PARAM, made.env);
      window.location.assign(url.toString());
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) forgetAdminToken();
      setError(e instanceof ApiError ? e.serverMessage ?? e.message : String(e));
    }
  };
  const copyLink = () => navigator.clipboard.writeText(window.location.href).then(() => setCopied(true));
  const leave = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete(SANDBOX_PARAM);
    window.location.assign(url.toString());
  };
  const sandbox = status?.sandbox;
  const expires = sandbox && new Date(sandbox.expires_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

  return (
    <div className="card sandbox-banner" role="status">
      {error && <span style={{ color: "var(--red)" }}>Sandbox: {error}</span>}
      {!error && sandbox && (
        <span>
          <strong>Sandbox {shortSandboxName(sandbox.env)}</strong>, expires ~{expires}. Your changes go to this
          sandbox only. It starts from the release data, not from the live shop.
        </span>
      )}
      {!error && !sandbox && status?.configured && (
        <span>Sandbox mode is available: pull a lever without touching the shop&apos;s data.</span>
      )}
      <span style={{ display: "inline-flex", gap: 6, marginLeft: "auto" }}>
        {status?.can_create && (
          <button className="btn" onClick={create} title={sandbox ? "A fresh sandbox from the release data; this one is deleted" : undefined}>
            {sandbox ? "Reset: new sandbox" : "New sandbox"}
          </button>
        )}
        {sandbox && <button className="btn btn-ghost" onClick={copyLink}>{copied ? "Link copied" : "Copy link"}</button>}
        {env && <button className="btn btn-ghost" onClick={leave}>Leave</button>}
      </span>
    </div>
  );
}
