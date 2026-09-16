"use client";

import { useEffect } from "react";
import { AudioWaveform, RotateCcw, Home } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * App-level error boundary (Next.js App Router).
 * Catches runtime errors in client components and offers retry + escape.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log for debugging; the user sees a friendly message, not the raw error.
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <AudioWaveform className="h-6 w-6" />
      </span>
      <h1 className="text-2xl font-bold tracking-tight">Something went wrong</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        The app hit an unexpected error. Your jobs and settings are safe — try
        again, or head back to the start.
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        <Button onClick={reset}>
          <RotateCcw className="h-4 w-4" />
          Try again
        </Button>
        <Button variant="outline" asChild>
          <a href="/">
            <Home className="h-4 w-4" />
            Back to home
          </a>
        </Button>
      </div>
    </div>
  );
}