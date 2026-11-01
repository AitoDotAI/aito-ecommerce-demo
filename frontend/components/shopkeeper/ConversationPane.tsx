"use client";

import type { Conversation } from "@/lib/shopkeeper";

/**
 * A stored conversation with Ask the store (ADR 0054): the question, each tool call the model made with what it was
 * given back, the answer, and what it cost in tokens. Replayed from a file: nothing here calls a model.
 */
export default function ConversationPane({ conversation }: { conversation: Conversation }) {
  const c = conversation;
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div className="card">
        <div className="card-sub">Asked {c.asked_at.slice(0, 10)} · stored, replayed without a model · data release {c.release}</div>
        <div className="page-title" style={{ fontSize: 20, margin: "4px 0 0" }}>{c.question}</div>
      </div>
      {c.tool_calls.map((t, i) => (
        <div key={i} className="card" style={{ borderLeft: `4px solid ${t.error ? "var(--cta)" : "var(--aito-teal)"}` }}>
          <div className="card-title" style={{ margin: 0 }}>{i + 1}. {t.name} <span className="card-sub">· {t.ms} ms{t.error ? ` · ${t.error}` : ""}</span></div>
          <div className="card-sub" style={{ marginTop: 6 }}>Input</div>
          <pre style={{ margin: 0, fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(t.input, null, 2)}</pre>
          <details style={{ marginTop: 6 }}>
            <summary className="card-sub" style={{ cursor: "pointer" }}>What the model was given back</summary>
            <pre style={{ margin: "6px 0 0", fontSize: 12, whiteSpace: "pre-wrap", maxHeight: 280, overflow: "auto" }}>
              {t.error ?? JSON.stringify(t.result, null, 2)}
            </pre>
          </details>
        </div>
      ))}
      <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
        <div className="card-title" style={{ margin: 0 }}>Answer</div>
        <div style={{ whiteSpace: "pre-wrap", margin: "6px 0", lineHeight: 1.5 }}>{c.answer}</div>
        <div className="card-sub">{c.model} · {c.input_tokens.toLocaleString("en-GB")} tokens in, {c.output_tokens.toLocaleString("en-GB")} out · read-only: it proposes, nothing is changed</div>
      </div>
    </div>
  );
}
