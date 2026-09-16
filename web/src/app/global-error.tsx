"use client";

/**
 * Root error boundary. Must render its own <html>/<body> because the root
 * layout may have failed. Kept dependency-free so it always works.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "1rem",
            padding: "1rem",
            textAlign: "center",
            fontFamily: "system-ui, sans-serif",
            background: "#0F1116",
            color: "#f4f4f5",
          }}
        >
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>
            Something went wrong
          </h1>
          <p style={{ maxWidth: "28rem", color: "#a1a1aa", fontSize: "0.9rem" }}>
            The app hit an unexpected error. Try again, or reload the page.
          </p>
          <button
            onClick={reset}
            style={{
              padding: "0.6rem 1.25rem",
              borderRadius: "9999px",
              border: "none",
              background: "#6366f1",
              color: "#fff",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}