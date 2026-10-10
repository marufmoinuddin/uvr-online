"use client";

import * as React from "react";
import { GitCompareArrows, Loader2, AlertTriangle, Play } from "lucide-react";
import { cn } from "@/lib/utils";
import { StemPlayer } from "@/components/ui/stem-player";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { createJob, friendlyApiError } from "@/lib/api";
import { useJobs } from "@/hooks/useJobs";
import type { Job, JobStem, Model } from "@/lib/types";

export interface ComparisonEntry {
  id: string;
  label: string;
  stems: JobStem[];
}

interface ComparisonPlayerProps {
  entries: ComparisonEntry[];
  /** Models selected via ?compare= on the explore page (no stems yet). */
  models?: Model[];
  className?: string;
}

/**
 * A/B comparison — loads 2–4 models side-by-side with synced playback
 * (all players share a sync group) and a waveform overlay.
 *
 * When models are selected but no stems exist yet, shows the selected
 * models with a "Run" action so the flow is never a dead end.
 */
export function ComparisonPlayer({
  entries,
  models = [],
  className,
}: ComparisonPlayerProps) {
  const [group] = React.useState(
    () => `compare-${Math.random().toString(36).slice(2)}`,
  );
  const count = entries.length || models.length;

  // Real comparison: run the selected models over ONE file so the results are
  // actually comparable. Previously this panel only ever rendered the
  // "run them" placeholder and its button linked away to the workbench, so
  // `entries` was permanently empty and the synced-playback view below was
  // unreachable — the feature was a dead end.
  const { jobs } = useJobs();
  const [file, setFile] = React.useState<File | null>(null);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [jobIds, setJobIds] = React.useState<string[]>([]);

  const runComparison = async () => {
    if (!file || models.length === 0) return;
    setRunning(true);
    setError(null);
    try {
      // Sequentially, not in parallel: the worker serialises GPU jobs anyway,
      // and firing N uploads at once just queues them without any progress
      // being attributable to a specific model.
      const ids: string[] = [];
      for (const m of models) {
        const res = await createJob(
          file,
          { scene: "model-picker", modelId: m.id, options: { outputFormat: "wav" } },
        );
        ids.push(res.jobId);
        setJobIds([...ids]);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? friendlyApiError(0, err.message)
          : "Could not start the comparison.",
      );
    } finally {
      setRunning(false);
    }
  };

  if (count === 0) {
    return (
      <div
        className={cn(
          "glass-card flex flex-col items-center gap-3 p-10 text-center",
          className,
        )}
      >
        <GitCompareArrows className="h-8 w-8 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">
          Select 2–4 models on the explore page to compare them side-by-side.
        </p>
        <Button variant="outline" size="sm" asChild>
          <a href="/explore">Browse models</a>
        </Button>
      </div>
    );
  }

  const resolved: ComparisonEntry[] = jobIds.length
    ? jobIds.flatMap((id) => {
        const job = jobs.find((j) => j.id === id);
        if (!job || job.status !== "ready" || !job.resultStems?.length) return [];
        const model = models.find((m) => job.modelId === m.id);
        return [{
          id,
          label: model?.name ?? job.modelId,
          stems: job.resultStems,
        }];
      })
    : entries;

  const allDone =
    jobIds.length > 0 &&
    resolved.length === jobIds.length &&
    jobIds.every((id) => jobs.find((j) => j.id === id)?.status === "ready");
  const anyFailed = jobIds.some((id) => {
    const s = jobs.find((j) => j.id === id)?.status;
    return s === "error" || s === "cancelled";
  });

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center gap-2">
        <GitCompareArrows className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">A/B comparison</h3>
        <span className="text-xs text-muted-foreground">
          {entries.length > 0 && !jobIds.length
            ? "Playback is synchronized across all models"
            : jobIds.length
              ? allDone
                ? "Playback is synchronized across all models"
                : "Each model runs in turn — results appear as they finish"
              : `${count} model${count > 1 ? "s" : ""} selected`}
        </span>
      </div>

      {/* One file, run through every selected model, so the outputs are
          genuinely comparable. Without this the panel could only describe a
          comparison it had no way to produce. */}
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.02] p-3">
        <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-xs text-muted-foreground hover:text-foreground">
          <input
            type="file"
            accept="audio/*,video/*"
            className="sr-only"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setJobIds([]);
            }}
          />
          <span className="truncate rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
            {file ? file.name : "Choose an audio file to compare on…"}
          </span>
        </label>
        <Button size="sm" onClick={runComparison} disabled={!file || running || models.length < 2}>
          {running ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
              Starting…
            </>
          ) : (
            <>Run comparison</>
          )}
        </Button>
      </div>

      {error && (
        <p
          role="alert"
          className="flex items-start gap-1.5 text-xs text-amber-300"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {error}
        </p>
      )}
      <div
        className={cn(
          "grid gap-4",
          count === 2 && "sm:grid-cols-2",
          count === 3 && "sm:grid-cols-2 lg:grid-cols-3",
          count >= 4 && "sm:grid-cols-2 lg:grid-cols-4",
        )}
      >
        {entries.length > 0
          ? entries.map((entry) => (
              <div key={entry.id} className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">
                  {entry.label}
                </p>
                {entry.stems.map((stem, i) => (
                  <StemPlayer
                    key={stem.name}
                    name={stem.name}
                    url={stem.url}
                    group={group}
                    color={["#6366f1", "#8b5cf6", "#ec4899", "#10b981"][i % 4]}
                  />
                ))}
              </div>
            ))
          : models.map((m) => {
              const job = jobs.find((j) => j.modelId === m.id && jobIds.includes(j.id));
              const state = job?.status;
              const failed = state === "error" || state === "cancelled";
              return (
                <div key={m.id} className="glass-card flex flex-col gap-3 p-5">
                  <div>
                    <p className="text-sm font-semibold leading-snug">{m.name}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{m.arch}</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="outline" className="capitalize">
                      {m.target}
                    </Badge>
                    {m.tags.slice(0, 2).map((t) => (
                      <Badge key={t} variant="secondary" className="capitalize">
                        {t}
                      </Badge>
                    ))}
                  </div>
                  {job ? (
                    failed ? (
                      <p className="flex items-start gap-1.5 text-xs text-amber-400">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                        {job.error ?? "Run failed."}
                      </p>
                    ) : state === "ready" ? (
                      <p className="flex items-center gap-1.5 text-xs text-emerald-400">
                        <Play className="h-3.5 w-3.5" aria-hidden />
                        Ready — playback below is synced across models.
                      </p>
                    ) : (
                      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                        {state === "queued" ? "Queued…" : "Separating…"}
                        {job.progress > 0 ? ` ${Math.round(job.progress)}%` : ""}
                      </p>
                    )
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Waiting to run.
                    </p>
                  )}
                </div>
              );
            })}
      </div>

      {resolved.length > 0 && (
        <div
          className={cn(
            "grid gap-4",
            resolved.length === 2 && "sm:grid-cols-2",
            resolved.length === 3 && "sm:grid-cols-2 lg:grid-cols-3",
            resolved.length >= 4 && "sm:grid-cols-2 lg:grid-cols-4",
          )}
        >
          {resolved.map((entry) => (
            <div key={entry.id} className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">
                {entry.label}
              </p>
              {entry.stems.map((stem, i) => (
                <StemPlayer
                  key={stem.name}
                  name={stem.name}
                  url={stem.url}
                  group={group}
                  color={["#6366f1", "#8b5cf6", "#ec4899", "#10b981"][i % 4]}
                />
              ))}
            </div>
          ))}
        </div>
      )}

      {anyFailed && (
        <p className="flex items-start gap-1.5 text-xs text-amber-400">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          One or more runs failed. The models that succeeded are still shown
          below — remove the failing one and run again.
        </p>
      )}
    </div>
  );
}