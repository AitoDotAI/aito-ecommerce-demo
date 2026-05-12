"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, confClass } from "@/lib/api";
import { feedbackPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import WhyTooltip from "@/components/prediction/WhyTooltip";
import ErrorState from "@/components/shell/ErrorState";
import type { FeedbackResponse } from "@/lib/types";


/**
 * Feedback — review triage via multi-field `_predict` over `text`.
 * Three parallel `_predict` calls return category / sentiment /
 * assigned_to in one round-trip. Same fanout pattern as Product
 * Filling. See `docs/adr/0012-feedback-multi-predict.md`.
 */
export default function FeedbackPage() {
  usePagePanel(feedbackPanel(), {
    title: "Feedback",
    description:
      "Multi-field `_predict` over a review's free text. Aito returns " +
      "category, sentiment, and the suggested assignee — three predicts " +
      "in parallel from the same `where: {text: ...}` body.",
    breadcrumb: "Feedback",
  });

  const { setPanel } = useShell();
  const [reviewId, setReviewId] = useState<string | undefined>(undefined);
  const [data, setData] = useState<FeedbackResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async (forReview?: string) => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const url = forReview
        ? `/api/feedback?review=${encodeURIComponent(forReview)}`
        : "/api/feedback";
      const res = await apiFetch<FeedbackResponse>(url);
      setData(res);
      setPanel({
        ...feedbackPanel(),
        endpoints: ["_predict"],
        query: highlightQuery({
          ...res.last_query.body,
          predict: "<category | sentiment | assigned_to>",
        }),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => {
    fetchData(reviewId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewId]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Feedback</div>
        <div className="page-desc">
          Three predictions per review — category, sentiment, suggested
          assignee — in one round-trip. The support team's queue triaged
          by Aito reading the same text the agent will read.
        </div>
      </div>

      {/* Review picker */}
      <div className="search-wrap" style={{ flexWrap: "wrap" }}>
        <label
          htmlFor="rev-picker"
          style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}
        >
          Incoming review
        </label>
        <select
          id="rev-picker"
          className="search-input"
          style={{ paddingLeft: 12, width: "auto", minWidth: 420 }}
          value={reviewId ?? data?.review.review_id ?? ""}
          onChange={(e) => setReviewId(e.target.value || undefined)}
        >
          {(data?.candidate_reviews ?? []).map((c) => (
            <option key={c.review_id} value={c.review_id}>
              {"★".repeat(c.rating)}  {c.text_short}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Feedback"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <div className="two-col">
          {/* Incoming review */}
          <div className="card">
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Incoming · what the customer wrote
            </div>
            <div style={{ marginBottom: 12 }}>
              <span style={{ fontSize: 20, letterSpacing: 1, color: "var(--cta)" }}>
                {"★".repeat(data?.review.rating ?? 0)}
              </span>
              <span style={{ color: "var(--border)", fontSize: 20, letterSpacing: 1 }}>
                {"★".repeat(5 - (data?.review.rating ?? 0))}
              </span>
            </div>

            <blockquote style={{
              borderLeft: "3px solid var(--cta)",
              padding: "8px 14px",
              margin: "8px 0 16px",
              fontStyle: "italic",
              color: "var(--text)",
              fontSize: 15,
              lineHeight: 1.5,
            }}>
              {data?.review.text ?? "Loading…"}
            </blockquote>

            <div className="card-sub" style={{ marginBottom: 8 }}>
              <strong>{data?.review.customer_short}</strong>
              {data && (
                <> · review of <code style={{ fontFamily: "var(--mono)" }}>{data.review.product_name}</code></>
              )}
              {data && <> · {data.review.created_at}</>}
            </div>
          </div>

          {/* Aito predictions */}
          <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Aito triage · three `_predict` calls in parallel
            </div>
            <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
              Predicted fields
            </div>
            <div className="card-sub" style={{ marginBottom: 16 }}>
              from <code>text</code> tokens · {data?.last_response_ms ?? "—"} ms total
            </div>

            {(loading || !data) && (
              <div style={{ height: 280, background: "var(--border-light)", borderRadius: 4 }} />
            )}
            {!loading && data?.fields.map((f) => {
              const actualValue =
                f.field === "category"    ? data.review.actual_category :
                f.field === "sentiment"   ? data.review.actual_sentiment :
                f.field === "assigned_to" ? data.review.actual_assigned_to :
                                            null;
              const correct = actualValue !== null && String(f.predicted_value) === actualValue;
              return (
                <div className="fill-field" key={`out-${f.field}`}>
                  <div className="fill-field-label">{f.label}</div>
                  <div className="fill-field-val" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 600 }}>{String(f.predicted_value ?? "—")}</span>
                    <ConfChip p={f.confidence} />
                    {actualValue !== null && (
                      <span
                        className="pill"
                        style={{
                          fontSize: 10,
                          background: correct ? "var(--green-bg)" : "var(--red-bg)",
                          color: correct ? "var(--green)" : "var(--red)",
                        }}
                        title={`Ground truth: ${actualValue}`}
                      >
                        {correct ? "✓ matches stored" : `≠ ${actualValue}`}
                      </span>
                    )}
                    {f.why_factors.length > 0 && (
                      <WhyTooltip
                        factors={f.why_factors.map((w) => ({
                          field: w.field || "text",
                          value: w.value,
                          lift: w.lift,
                        }))}
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}


function ConfChip({ p }: { p: number }) {
  const tier = confClass(p);
  const color =
    tier === "conf-high" ? "var(--green)" :
    tier === "conf-mid"  ? "var(--cta)"   :
    "var(--red)";
  const bg =
    tier === "conf-high" ? "var(--green-bg)" :
    tier === "conf-mid"  ? "var(--cta-bg)"   :
    "var(--red-bg)";
  return (
    <span className="fill-conf" style={{ background: bg, color }}>
      {Math.round(p * 100)}%
    </span>
  );
}


function highlightQuery(body: Record<string, unknown>): string {
  function fmt(value: unknown, indent: number): string {
    const pad = "  ".repeat(indent);
    if (value === null) return `<span class="s">null</span>`;
    if (typeof value === "string") return `<span class="s">"${escape(value)}"</span>`;
    if (typeof value === "boolean") return `<span class="n">${value}</span>`;
    if (typeof value === "number") return `<span class="n">${value}</span>`;
    if (Array.isArray(value)) {
      if (value.length === 0) return "[]";
      const inner = value.map((v) => `${pad}  ${fmt(v, indent + 1)}`).join(",\n");
      return `[\n${inner}\n${pad}]`;
    }
    if (typeof value === "object") {
      const entries = Object.entries(value as Record<string, unknown>);
      if (entries.length === 0) return "{}";
      const inner = entries
        .map(([k, v]) => `${pad}  <span class="k">"${escape(k)}"</span>: ${fmt(v, indent + 1)}`)
        .join(",\n");
      return `{\n${inner}\n${pad}}`;
    }
    return String(value);
  }
  return fmt(body, 0);
}

function escape(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
