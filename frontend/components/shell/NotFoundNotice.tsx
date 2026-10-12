"use client";

/**
 * Shown when the id in the URL isn't in the data: a typo, or a link sent
 * before the item was removed. Says so plainly and offers the way back,
 * instead of showing another item under the same URL.
 */
export default function NotFoundNotice({
  message,
  resetLabel,
  onReset,
}: {
  message: string;
  resetLabel: string;
  onReset: () => void;
}) {
  return (
    <div className="card" style={{ textAlign: "center", padding: 32 }}>
      <h3 style={{ fontSize: 16, color: "var(--text)", marginBottom: 8 }}>Not in the data</h3>
      <p style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.5 }}>
        {message}. The link may be out of date.
      </p>
      <button className="btn" style={{ marginTop: 12 }} onClick={onReset}>
        {resetLabel}
      </button>
    </div>
  );
}
