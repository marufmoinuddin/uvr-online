"use client";

import * as React from "react";
import { ListMusic } from "lucide-react";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { useJobs } from "@/hooks/useJobs";
import { JobCard } from "@/components/ui/job-console";

/**
 * Workbench "Results" card — empty state plus submitted job results
 * (queued → processing → ready with stem players).
 */
export function ResultsCard({ className }: { className?: string }) {
  const jobs = useStore((s) => s.jobs);
  // Establish the live job subscription (polling + WebSocket).
  useJobs();

  const sorted = React.useMemo(
    () => [...jobs].sort((a, b) => b.createdAt - a.createdAt),
    [jobs],
  );

  return (
    <section
      className={cn(
        "rounded-2xl border border-white/10 bg-[#12141A] p-5",
        className,
      )}
    >
      {/* Header */}
      <div className="relative mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-indigo-200">
            <ListMusic className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-foreground">Results</h2>
        </div>
        <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-muted-foreground">
          {sorted.length} item{sorted.length === 1 ? "" : "s"}
        </span>
      </div>

      {sorted.length === 0 ? (
        <div className="grid min-h-[68px] min-w-0 content-start gap-2 overflow-hidden">
          <p className="text-sm font-semibold text-foreground">
            No processing results
          </p>
          <p className="text-xs text-muted-foreground">
            Submitted jobs from this Workbench will appear here.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {sorted.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </section>
  );
}