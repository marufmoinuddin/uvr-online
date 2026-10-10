"use client";

import * as React from "react";
import Link from "next/link";
import { History, Trash2, Inbox, ArrowLeft } from "lucide-react";
import { useStore } from "@/lib/store";
import { useJobs } from "@/hooks/useJobs";
import { clearJobs as clearJobsApi } from "@/lib/api";
import { WorkbenchSidebar } from "@/components/layout/workbench-sidebar";
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
import type { Job } from "@/lib/types";

const DAY_MS = 86_400_000;

/** Group job ids under a Today / Yesterday / explicit-date heading. */
function groupByDay(jobs: Job[]): { label: string; jobs: Job[] }[] {
  const now = new Date();
  const buckets = new Map<string, Job[]>();
  for (const job of jobs) {
    const created = new Date(job.createdAt);
    const startOfToday = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate(),
    ).getTime();
    const label =
      job.createdAt >= startOfToday
        ? "Today"
        : job.createdAt >= startOfToday - DAY_MS
          ? "Yesterday"
          : created.toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              ...(created.getFullYear() === now.getFullYear()
                ? {}
                : { year: "numeric" }),
            });
    const list = buckets.get(label) ?? [];
    list.push(job);
    buckets.set(label, list);
  }
  return Array.from(buckets.entries()).map(([label, group]) => ({
    label,
    jobs: group,
  }));
}

/**
 * Recent Jobs — every job this browser knows about, grouped by day.
 *
 * Reads the same persisted store the workbench uses and subscribes through
 * useJobs, so it reflects both localStorage and the worker's authoritative
 * list. Reuses JobCard rather than reimplementing playback, re-run and
 * download — a second implementation of stem playback would be a second set of
 * bugs.
 */
export function HistoryView() {
  const jobs = useStore((s) => s.jobs);
  const clearJobs = useStore((s) => s.clearJobs);
  const [confirmClear, setConfirmClear] = React.useState(false);
  const [clearing, setClearing] = React.useState(false);

  // Keep this list reconciled with the worker (and its WebSocket) so jobs
  // deleted elsewhere disappear here too.
  useJobs();

  const sorted = React.useMemo(
    () => [...jobs].sort((a, b) => b.createdAt - a.createdAt),
    [jobs],
  );
  const groups = React.useMemo(() => groupByDay(sorted), [sorted]);

  const handleClear = async () => {
    setClearing(true);
    try {
      await clearJobsApi();
      clearJobs();
      setConfirmClear(false);
    } catch {
      /* worker unreachable — clear locally anyway rather than trapping the user */
      clearJobs();
      setConfirmClear(false);
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-[1400px] items-start gap-6 px-4 py-6 sm:px-8">
      {/* Same shell as the workbench, so the nav item highlights and there is
          always a way back. The sidebar is desktop-only, hence the mobile
          back link below. */}
      <WorkbenchSidebar
        active="history"
        className="sticky top-[97px] hidden max-h-[calc(100dvh-7rem)] shrink-0 overflow-y-auto lg:flex"
      />

      <section id="workbench-main" className="min-w-0 flex-1" aria-label="History">
        <div className="mb-3">
          <Link
            href="/tools/vocal-remover"
            className="mb-2 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 lg:hidden"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to the workbench
          </Link>
          <h1 className="text-lg font-semibold leading-7 text-foreground">
            Recent Jobs
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Everything processed on this machine, newest first.
          </p>
        </div>

        <div className="h-px w-full bg-white/10" aria-hidden />

      <section className="mt-5 rounded-2xl border border-white/10 bg-[#12141A] p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-indigo-200">
              <History className="h-4 w-4" />
            </span>
            <h2 className="text-base font-bold text-foreground">History</h2>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] text-muted-foreground">
              {sorted.length} job{sorted.length === 1 ? "" : "s"}
            </span>
            {sorted.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmClear(true)}
                className="h-7 gap-1.5 rounded-full px-2.5 text-[11px] font-medium text-muted-foreground hover:text-foreground"
              >
                <Trash2 className="h-3 w-3" />
                Clear all
              </Button>
            )}
          </div>
        </div>

        {sorted.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-white/10 px-6 py-14 text-center">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white/[0.06] text-muted-foreground">
              <Inbox className="h-5 w-5" aria-hidden />
            </span>
            <p className="text-sm font-semibold text-foreground">
              You haven&apos;t had any jobs yet
            </p>
            <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
              Jobs you run appear here automatically — including after a restart —
              with their stems, so you can play or download them again.
            </p>
            <Button asChild size="sm">
              <Link href="/tools/vocal-remover">Open the workbench</Link>
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {groups.map((group) => (
              <div key={group.label}>
                <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {group.label}
                </h3>
                <ul className="flex flex-col gap-2">
                  {group.jobs.map((job) => (
                    <li key={job.id}>
                      <JobCard job={job} showScene />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      <Dialog open={confirmClear} onOpenChange={setConfirmClear}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Clear job history?</DialogTitle>
            <DialogDescription>
              Remove all {sorted.length} job entries? Their stems are deleted from disk
              too, so anything you have not downloaded yet will be lost.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleClear} disabled={clearing}>
              {clearing ? "Clearing…" : "Clear history"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </section>
    </div>
  );
}