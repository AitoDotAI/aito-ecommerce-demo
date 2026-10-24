"use client";

import { Suspense, useCallback, useEffect, useState } from "react";

import { ApiError, apiFetch, confClass } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { reviewTriagePanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import WhyPopover from "@/components/prediction/WhyPopover";
import ErrorState from "@/components/shell/ErrorState";
import NotFoundNotice from "@/components/shell/NotFoundNotice";
import type { ReviewTriageResponse } from "@/lib/types";
import { useUrlState } from "@/lib/use-url-state";


/**
 * Review triage (ADR 0041; called Feedback before): route a review with a
 * multi-field `_predict` over its text. Three parallel `_predict` calls
 * return category / sentiment / assigned_to in one round-trip. Same fanout
 * pattern as Product Filling. See `docs/adr/0012-feedback-multi-predict.md`.
 *
 * It no longer predicts churn risk from the text: the data copies churn
 * into reviews, so that prediction runs backwards (ADR 0039). Retention
 * answers who is leaving.
 */
function ReviewTriageView() {
  usePagePanel(reviewTriagePanel(), {
    title: "Review triage",
    description:
      "Multi-field `_predict` over a review's free text. Aito returns " +
      "category, sentiment, and the suggested assignee — three predicts " +
      "in parallel from the same `where: {text: ...}` body.",
    breadcrumb: "Operate › Review triage",
  });

  const { setPanel } = useShell();
  // No `review` in the URL means the backend's default review.
  const [reviewParam, setReviewParam] = useUrlState("review", "");
  const reviewId = reviewParam || undefined;
  const setReviewId = (next: string | undefined) => setReviewParam(next ?? "");
  const [data, setData] = useState<ReviewTriageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<string | null>(null);
  // Kept across a failed load, so the picker still works after a bad link.
  const [candidates, setCandidates] = useState<ReviewTriageResponse["candidate_reviews"]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async (forReview?: string) => {
    setLoading(true);
    setError(null);
    setNotFound(null);
    setData(null);
    try {
      const url = forReview
        ? `/api/review-triage?review=${encodeURIComponent(forReview)}`
        : "/api/review-triage";
      const res = await apiFetch<ReviewTriageResponse>(url);
      setData(res);
      setCandidates(res.candidate_reviews);
      setPanel({
        ...reviewTriagePanel(),
        endpoints: ["_predict"],
        query: highlightQuery({
          ...res.last_query.body,
          predict: "<category | sentiment | assigned_to>",
        }),
      });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setNotFound(e.serverMessage ?? e.message);
      else setError(String(e));
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
        <div className="page-title">Review triage</div>
        <div className="page-desc">
          Route this review: Aito reads its text and rating and predicts the
          issue category, the sentiment and who should take it, in one
          round-trip.
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
          style={{ paddingLeft: 12, width: "auto", minWidth: "min(420px, 100%)" }}
          value={reviewId ?? data?.review.review_id ?? ""}
          onChange={(e) => setReviewId(e.target.value || undefined)}
        >
          {candidates.map((c) => (
            <option key={c.review_id} value={c.review_id}>
              {"★".repeat(c.rating)}  {c.text_short}
            </option>
          ))}
        </select>
      </div>

      {notFound && (
        <NotFoundNotice message={notFound} resetLabel="Show the default review" onReset={() => setReviewId(undefined)} />
      )}

      {error && (
        <ErrorState
          title="Couldn't load Review triage"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && !notFound && (
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
              {data ? routeLine(data) : "Predicted fields"}
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
                    {f.why_explanation && (
                      <WhyPopover
                        why={f.why_explanation}
                        title={`${f.label.toLowerCase()} = ${String(f.predicted_value)}`}
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


/** The decision the fields add up to: who takes the review, and as what. */
function routeLine(data: ReviewTriageResponse): string {
  const value = (field: string) => String(data.fields.find((f) => f.field === field)?.predicted_value ?? "—");
  return `Route to ${value("assigned_to")} as ${value("category")}`;
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


// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function ReviewTriagePage() {
  return (
    <Suspense>
      <ReviewTriageView />
    </Suspense>
  );
}
