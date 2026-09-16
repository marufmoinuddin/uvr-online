"use client";

import * as React from "react";
import { ListMusic, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { useJobs } from "@/hooks/useJobs";
import { clearJobs as clearJobsApi } from "@/lib/api";
import { JobCard } from "@/components/ui/job-console";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

/**
 * Workbench "Results" card — empty state plus submitted job results
 * (queued → processing → ready with stem players).
 */
export function ResultsCard({ className }: { className?: string }) {
  const jobs = useStore((s) => s.jobs);
  const clearJobs = useStore((s) => s.clearJobs);
  const [confirmClear, setConfirmClear] = React.useState(false);
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
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-muted-foreground">
            {sorted.length} item{sorted.length === 1 ? "" : "s"}
          </span>
          {sorted.length > 0 && (
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
            >
              <Trash2 className="h-3 w-3" />
              Clear all
            </button>
          )}
        </div>
      </div>

      <Dialog open={confirmClear} onOpenChange={setConfirmClear}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Clear job history?</DialogTitle>
            <DialogDescription>
              Remove all {sorted.length} job entries from the console? This only
              clears the history — it does not delete processed files.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmClear(false)}>
              Keep them
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                try {
                  await clearJobsApi();
                } catch {
                  /* worker unreachable — still clear the local console */
                }
                clearJobs();
                setConfirmClear(false);
              }}
            >
              Clear all
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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