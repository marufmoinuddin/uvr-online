"use client";

import * as React from "react";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Trash2,
  Clock,
  Cpu,
  Package,
  Upload,
  Ban,
} from "lucide-react";
import { cn, timeAgo, formatEta } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StemPlayer } from "@/components/ui/stem-player";
import { DownloadBundle } from "@/components/ui/download-bundle";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useStore } from "@/lib/store";
import { useJobs } from "@/hooks/useJobs";
import { reuseJob, cancelJob, clearJobs as clearJobsApi, deleteJob } from "@/lib/api";
import { MODEL_CATALOG } from "@/lib/models";
import type { Job } from "@/lib/types";

/** Resolve a model display name from its ID, handling `ensemble:` prefixed IDs. */
function modelDisplayName(modelId: string): string {
  if (modelId.startsWith("ensemble:")) {
    const mode = modelId.slice("ensemble:".length).replace(/_/g, " ");
    return `Ensemble · ${mode}`;
  }
  const m = MODEL_CATALOG.find((c) => c.id === modelId);
  return m?.name ?? modelId;
}

const STAGE_LABELS: Record<Job["stage"], string> = {
  queued: "Queued",
  uploading: "Uploading",
  gpu: "GPU inference",
  assemble: "Assembling",
  done: "Done",
};

const STAGE_ICONS: Record<Job["stage"], React.ReactNode> = {
  queued: <Clock className="h-3.5 w-3.5" />,
  uploading: <Upload className="h-3.5 w-3.5" />,
  gpu: <Cpu className="h-3.5 w-3.5" />,
  assemble: <Package className="h-3.5 w-3.5" />,
  done: <CheckCircle2 className="h-3.5 w-3.5" />,
};

function JobCard({ job }: { job: Job }) {
  const removeJob = useStore((s) => s.removeJob);
  const [reusing, setReusing] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [cancelling, setCancelling] = React.useState(false);

  const handleReuse = async () => {
    setReusing(true);
    try {
      await reuseJob(job.id, job.modelId);
    } finally {
      setReusing(false);
    }
  };

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await cancelJob(job.id);
    } catch {
      /* job may have already finished — the next poll reconciles it */
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div
      className={cn(
        "rounded-xl border p-4 transition-all",
        job.status === "ready"
          ? "border-emerald-500/30 bg-emerald-500/5"
          : job.status === "error"
            ? "border-red-500/30 bg-red-500/5"
            : "border-card-border bg-card",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{job.fileName}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {modelDisplayName(job.modelId)} · {timeAgo(job.createdAt)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {job.status === "queued" && (
            <Badge variant="secondary">
              <Loader2 className="mr-1 h-3 w-3 animate-spin" /> queued
            </Badge>
          )}
          {job.status === "processing" && (
            <Badge variant="default">
              <Loader2 className="mr-1 h-3 w-3 animate-spin" /> {job.progress}%
            </Badge>
          )}
          {job.status === "ready" && (
            <Badge variant="success">
              <CheckCircle2 className="mr-1 h-3 w-3" /> ready
            </Badge>
          )}
          {job.status === "error" && (
            <Badge variant="destructive">
              <XCircle className="mr-1 h-3 w-3" /> error
            </Badge>
          )}
          {job.status === "cancelled" && (
            <Badge variant="secondary">
              <XCircle className="mr-1 h-3 w-3" /> cancelled
            </Badge>
          )}
          {(job.status === "queued" || job.status === "processing") && (
            <button
              type="button"
              onClick={handleCancel}
              disabled={cancelling}
              aria-label="Cancel job"
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-400 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 disabled:opacity-50"
            >
              <Ban className={cn("h-3.5 w-3.5", cancelling && "animate-pulse")} />
            </button>
          )}
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            aria-label="Remove job"
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-control hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {(job.status === "queued" || job.status === "processing") && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {STAGE_ICONS[job.stage]}
            <span>{STAGE_LABELS[job.stage]}</span>
            {job.etaSec != null && job.status === "processing" && (
              <span className="ml-auto">ETA {formatEta(job.etaSec)}</span>
            )}
          </div>
          <Progress value={job.progress} />
        </div>
      )}

      {job.status === "error" && (
        <p className="mt-3 text-xs text-red-600 dark:text-red-400">{job.error}</p>
      )}

      {job.status === "ready" && job.resultStems && (
        <div className="mt-3 space-y-2">
          {job.resultStems.map((stem, i) => (
            <StemPlayer
              key={stem.name}
              name={stem.name}
              url={stem.url}
              group={job.id}
              color={["#6366f1", "#8b5cf6", "#ec4899", "#10b981", "#f59e0b"][i % 5]}
            />
          ))}
          <div className="flex items-center gap-2 pt-1">
            <DownloadBundle stems={job.resultStems} jobId={job.id} />
            <Button
              variant="outline"
              size="sm"
              onClick={handleReuse}
              disabled={reusing}
            >
              <RefreshCw className={cn("h-4 w-4", reusing && "animate-spin")} />
              Re-run
            </Button>
          </div>
        </div>
      )}

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove job?</DialogTitle>
            <DialogDescription>
              Remove &quot;{job.fileName}&quot; from your history? This only clears the
              entry from the console — it does not delete the processed files.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Keep it
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                try {
                  await deleteJob(job.id);
                } catch {
                  /* worker unreachable — still clear the local console */
                }
                removeJob(job.id);
                setConfirmDelete(false);
              }}
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export { JobCard };

/**
 * Job console — bottom sheet on mobile, side panel on lg.
 * Segments: queued → processing (segmented progress) → ready.
 */
export function JobConsole({ className }: { className?: string }) {
  const jobs = useStore((s) => s.jobs);
  const activeJobId = useStore((s) => s.activeJobId);
  const setActiveJob = useStore((s) => s.setActiveJob);
  const clearJobs = useStore((s) => s.clearJobs);
  const [confirmClear, setConfirmClear] = React.useState(false);
  // Establish the live job subscription (polling + WebSocket).
  useJobs();

  const sorted = React.useMemo(
    () => [...jobs].sort((a, b) => b.createdAt - a.createdAt),
    [jobs],
  );

  return (
    <div
      className={cn(
        "glass-card flex flex-col overflow-hidden",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold">Job console</h3>
          <p className="text-xs text-muted-foreground">
            {jobs.filter((j) => j.status === "processing").length} processing ·{" "}
            {jobs.filter((j) => j.status === "queued").length} queued
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 rounded-full bg-control p-0.5">
            <button
              type="button"
              onClick={() => setActiveJob(null)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                activeJobId === null
                  ? "bg-background shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => setActiveJob("active")}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                activeJobId === "active"
                  ? "bg-background shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Active
            </button>
          </div>
          {jobs.length > 0 && (
            <button
              type="button"
              onClick={() => setConfirmClear(true)}
              className="flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
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
              Remove all {jobs.length} job entries from the console? This only
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

      <ScrollArea className="flex-1">
        <div className="space-y-3 p-4">
          {sorted.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <Loader2 className="h-6 w-6 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                No jobs yet. Upload a track to get started.
              </p>
            </div>
          )}
          {sorted
            .filter((j) => (activeJobId === "active" ? j.status !== "ready" : true))
            .map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
        </div>
      </ScrollArea>
    </div>
  );
}