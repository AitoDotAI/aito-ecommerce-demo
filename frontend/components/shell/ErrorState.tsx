"use client";

interface ErrorStateProps {
  title?: string;
  message?: string;
  command?: string;
}

/**
 * Single error component, used everywhere a fetch can fail.
 * Surfaces the *actual* error — never "something went wrong".
 *
 * CLAUDE.md prime directive #2: silent failures hide bugs and
 * teach the wrong pattern to a reader.
 */
export default function ErrorState({
  title = "Couldn't load this view",
  message = "Aito returned an error. Check the panel for the query body, or retry.",
  command,
}: ErrorStateProps) {
  return (
    <div className="card" style={{ textAlign: "center", padding: 32 }}>
      <div style={{ fontSize: 28, marginBottom: 12 }} aria-hidden="true">⚠️</div>
      <h3 style={{ fontSize: 16, color: "var(--text)", marginBottom: 8 }}>{title}</h3>
      <p style={{ fontSize: 13, color: "var(--text-2)", lineHeight: 1.5 }}>{message}</p>
      {command && (
        <code
          style={{
            display: "inline-block", marginTop: 12,
            fontFamily: "var(--mono)", fontSize: 12,
            background: "var(--bg)", border: "1px solid var(--border)",
            padding: "6px 12px", borderRadius: 6, color: "var(--text-2)",
          }}
        >
          {command}
        </code>
      )}
    </div>
  );
}
