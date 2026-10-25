"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { ApiError, apiFetch } from "@/lib/api";
import { adminToken, forgetAdminToken, useSandboxEnv, withSandbox } from "@/lib/sandbox";
import type { AskAnswer, AskStatus } from "@/lib/types";

const EXAMPLES = [
  "Which products should go on offer this week?",
  "What should I reorder now, and what is stuck on the shelf?",
  "Which customers should I reach out to first, and with what?",
];

/** Ask the store (ADR 0042): a button in the top bar, shown only when the server has a model key.
 *  The question goes to Claude with the lever tools (Product what-if, Supply, Retention), which read
 *  the same numbers the views show; the answer lists the Aito queries it rested on. Read-only. */
export default function AskStore() {
  const env = useSandboxEnv();
  const [status, setStatus] = useState<AskStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { apiFetch<AskStatus>("/api/ask").then(setStatus, () => setStatus(null)); }, []);
  if (!status?.enabled) return null;

  const send = async (text: string) => {
    const token = adminToken("Ask the store");
    if (!token || !text.trim()) return;
    setBusy(true); setError(null); setAnswer(null);
    try {
      setAnswer(await apiFetch<AskAnswer>("/api/ask", {
        method: "POST", headers: { "X-Admin-Token": token }, body: JSON.stringify({ question: text.trim() }),
      }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) forgetAdminToken();
      setError(e instanceof ApiError ? e.serverMessage ?? e.message : String(e));
    } finally { setBusy(false); }
  };

  return (
    <>
      <button type="button" className="btn btn-ghost ask-btn" onClick={() => setOpen(!open)} aria-expanded={open}>Ask</button>
      {open && createPortal(
        <div className="card" role="dialog" aria-label="Ask the store"
             style={{ position: "fixed", top: 64, right: 16, width: "min(520px, calc(100vw - 32px))", maxHeight: "calc(100vh - 88px)",
                      overflowY: "auto", zIndex: 9000, padding: 16, boxShadow: "0 12px 32px rgba(0,0,0,0.25)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <div className="page-title" style={{ fontSize: 16, margin: 0 }}>Ask the store</div>
            <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)} aria-label="Close">✕</button>
          </div>
          <div className="card-sub" style={{ margin: "4px 0 10px" }}>
            Claude reads the owner views' numbers through tools and proposes; it changes nothing.
            {status.model && <> Model: {status.model}.</>}
          </div>
          <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={3} maxLength={500}
                    placeholder="Ask in your own words" style={{ width: "100%", resize: "vertical", padding: 8 }} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "8px 0" }}>
            {EXAMPLES.map((q) => (
              <button key={q} type="button" className="btn btn-ghost" style={{ fontSize: 12 }} disabled={busy}
                      onClick={() => { setQuestion(q); void send(q); }}>{q}</button>
            ))}
          </div>
          <button type="button" className="btn btn-primary" disabled={busy || question.trim().length < 3}
                  onClick={() => void send(question)}>{busy ? "Asking… (can take a minute)" : "Ask"}</button>
          {error && <div style={{ color: "var(--red)", marginTop: 10 }}>{error}</div>}
          {answer && <Answer answer={answer} env={env} />}
        </div>,
        document.body,
      )}
    </>
  );
}

function Answer({ answer, env }: { answer: AskAnswer; env: string | null }) {
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{linked(answer.answer, env)}</div>
      <details style={{ marginTop: 10 }}>
        <summary style={{ cursor: "pointer", color: "var(--text-muted)", fontSize: 12 }}>
          {answer.tool_calls.length} Aito queries it rested on
        </summary>
        {answer.tool_calls.map((c, i) => (
          <div key={i} className="card-sub" style={{ fontFamily: "var(--mono)", fontSize: 11, padding: "2px 0" }}>
            {c.name}({Object.values(c.input).join(", ")}) · {c.ms} ms{c.error && <span style={{ color: "var(--red)" }}> · {c.error}</span>}
          </div>
        ))}
        <div className="card-sub" style={{ fontSize: 11, marginTop: 4 }}>
          {answer.model} · {answer.input_tokens} in / {answer.output_tokens} out tokens. A model's wording varies between runs; the numbers are the tools'.
        </div>
      </details>
    </div>
  );
}

/** The answer's text, with the app paths a tool named (`/product/?sku=…`) as links that keep the sandbox. */
function linked(text: string, env: string | null) {
  return text.split(/(\/(?:product|supply|retention|shop|reviews|acquisition)\/?[^\s),;]*)/).map((part, i) =>
    i % 2 === 1 ? <Link key={i} href={withSandbox(part, env)}>{part}</Link> : <Fragment key={i}>{part}</Fragment>);
}
