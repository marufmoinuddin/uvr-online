"use client";

import * as React from "react";
import {
  HardDrive,
  Download,
  Trash2,
  Loader2,
  CheckCircle2,
  AlertCircle,
  X,
  RefreshCw,
  FolderOpen,
  Ban,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  listManagedModels,
  getModelStorage,
  startModelDownload,
  cancelModelDownload,
  deleteModel,
  formatBytes,
  formatSpeed,
  formatEta,
  type ManagedModel,
  type StorageInfo,
} from "@/lib/models-api";
import { licenseFor } from "@/lib/licenses";

/**
 * Model Management panel — shows every catalog model with its local cache
 * status, size, license, storage path, and lets the user download or delete
 * each one individually. Downloads show live progress with cancel/retry.
 *
 * Deleting never triggers a re-download; the model is fetched again the next
 * time a feature actually needs it.
 */
export function ModelManager({ className }: { className?: string }) {
  const [models, setModels] = React.useState<ManagedModel[]>([]);
  const [storage, setStorage] = React.useState<StorageInfo | null>(null);
  const [busy, setBusy] = React.useState<Record<string, boolean>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [filter, setFilter] = React.useState<"all" | "installed" | "available">(
    "all",
  );

  const refresh = React.useCallback(async () => {
    try {
      const [list, st] = await Promise.all([
        listManagedModels(),
        getModelStorage(),
      ]);
      setModels(list);
      setStorage(st);
    } catch {
      /* worker unreachable — keep the last snapshot */
    }
  }, []);

  // Poll while any download is in flight, otherwise refresh on an interval.
  React.useEffect(() => {
    refresh();
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [refresh]);

  const act = async (id: string, fn: () => Promise<unknown>) => {
    setBusy((b) => ({ ...b, [id]: true }));
    setErrors((e) => ({ ...e, [id]: "" }));
    try {
      await fn();
    } catch (err) {
      setErrors((e) => ({
        ...e,
        [id]: err instanceof Error ? err.message : "Action failed",
      }));
    } finally {
      setBusy((b) => ({ ...b, [id]: false }));
      refresh();
    }
  };

  const shown = models.filter((m) => {
    if (m.ensemble) return false; // presets fuse other models; nothing to download
    if (filter === "installed") return m.installed;
    if (filter === "available") return m.downloadable && !m.installed;
    return true;
  });

  const anyDownloading = models.some(
    (m) => m.download.status === "downloading" || m.download.status === "verifying",
  );

  return (
    <section
      className={cn(
        "rounded-2xl border border-white/10 bg-[#12141A] p-4",
        className,
      )}
    >
      {/* Header */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-indigo-200">
            <HardDrive className="h-4 w-4" />
          </span>
          <div>
            <h2 className="text-base font-bold text-foreground">
              Model Management
            </h2>
            {storage && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <FolderOpen className="h-3 w-3" />
                <span className="font-mono">{storage.storePath}</span>
                <span>
                  · {storage.installedCount}/{storage.catalogCount} installed ·{" "}
                  {formatBytes(storage.totalBytes)}
                </span>
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {anyDownloading && (
            <span className="flex items-center gap-1.5 text-xs text-indigo-300">
              <Loader2 className="h-3 w-3 animate-spin" /> downloading
            </span>
          )}
          <div className="flex gap-1 rounded-full bg-white/[0.04] p-0.5">
            {(["all", "installed", "available"] as const).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                  filter === f
                    ? "bg-white/10 text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* List */}
      <div className="flex flex-col gap-1.5">
        {shown.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Nothing to show for this filter.
          </p>
        )}
        {shown.map((m) => (
          <ModelRowView
            key={m.id}
            model={m}
            busy={!!busy[m.id]}
            error={errors[m.id]}
            onDownload={() => act(m.id, () => startModelDownload(m.id))}
            onCancel={() => act(m.id, () => cancelModelDownload(m.id))}
            onDelete={() => act(m.id, () => deleteModel(m.id))}
          />
        ))}
      </div>
    </section>
  );
}

function ModelRowView({
  model,
  busy,
  error,
  onDownload,
  onCancel,
  onDelete,
}: {
  model: ManagedModel;
  busy: boolean;
  error?: string;
  onDownload: () => void;
  onCancel: () => void;
  onDelete: () => void;
}) {
  const lic = licenseFor(model.id, model.arch);
  const dl = model.download;
  const downloading = dl.status === "downloading" || dl.status === "verifying";
  const failed = dl.status === "error" || !!error;
  // Prefer the real on-disk size once installed, else the catalog estimate.
  const size = model.installed ? model.sizeBytes : model.sizeMB * 1e6;

  return (
    <div
      className={cn(
        "rounded-xl border px-3 py-2.5 transition-colors",
        downloading
          ? "border-indigo-400/40 bg-indigo-500/[0.06]"
          : model.installed
            ? "border-emerald-500/25 bg-emerald-500/[0.04]"
            : failed
              ? "border-amber-500/30 bg-amber-500/[0.05]"
              : "border-white/[0.06] bg-white/[0.02]",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Identity */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-sm font-semibold text-foreground">
              {model.name}
            </span>
            <span
              title={lic.source}
              className={cn(
                "rounded-md px-1.5 py-px text-[10px] font-semibold",
                lic.commercialOk
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "bg-amber-500/15 text-amber-400",
              )}
            >
              {lic.label}
            </span>
            {model.installed ? (
              <span className="flex items-center gap-1 rounded-md bg-emerald-500/15 px-1.5 py-px text-[10px] font-semibold text-emerald-400">
                <CheckCircle2 className="h-2.5 w-2.5" />
                {model.installedVia === "msst" ? "installed (MSST)" : "installed"}
              </span>
            ) : model.downloadable ? (
              <span className="rounded-md bg-white/[0.06] px-1.5 py-px text-[10px] font-medium text-muted-foreground">
                not downloaded
              </span>
            ) : (
              <span
                title="No verified automatic source — install manually from the upstream repo."
                className="rounded-md bg-white/[0.06] px-1.5 py-px text-[10px] font-medium text-muted-foreground"
              >
                manual
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {model.arch}
            {model.repo && (
              <>
                {" · "}
                <span className="font-mono">{model.repo}</span>
                {model.revision && `@${model.revision}`}
              </>
            )}
            {" · "}
            {formatBytes(size)}
          </p>
          {model.installed && model.path && (
            <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground/70">
              {model.path}
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-1.5">
          {downloading ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground disabled:opacity-50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
            >
              <Ban className="h-3.5 w-3.5" /> Cancel
            </button>
          ) : model.installed ? (
            <button
              type="button"
              onClick={onDelete}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-red-500/50"
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
              Delete
            </button>
          ) : (
            <button
              type="button"
              onClick={onDownload}
              disabled={busy || !model.downloadable}
              title={
                model.downloadable
                  ? undefined
                  : "No verified automatic source for this model."
              }
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-40 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                model.downloadable
                  ? "bg-white text-black hover:bg-white/90"
                  : "bg-white/[0.06] text-muted-foreground",
              )}
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : failed ? (
                <RefreshCw className="h-3.5 w-3.5" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              {failed ? "Retry" : "Download"}
            </button>
          )}
        </div>
      </div>

      {/* Progress */}
      {downloading && (
        <div className="mt-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.08]">
            <div
              className="h-full rounded-full bg-indigo-400 transition-[width] duration-300"
              style={{ width: `${dl.percent}%` }}
            />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
            <span className="font-medium text-indigo-300">
              {dl.status === "verifying"
                ? "Verifying…"
                : `Downloading ${dl.percent.toFixed(1)}%`}
            </span>
            {dl.totalBytes > 0 && (
              <span>
                {formatBytes(dl.receivedBytes)} / {formatBytes(dl.totalBytes)}
              </span>
            )}
            <span>{formatSpeed(dl.speedBps)}</span>
            <span>ETA {formatEta(dl.etaSec)}</span>
            {dl.currentFile && (
              <span className="font-mono opacity-70">{dl.currentFile}</span>
            )}
          </div>
        </div>
      )}

      {/* Error */}
      {(error || dl.error) && !downloading && (
        <p className="mt-1.5 flex items-start gap-1.5 text-[11px] text-amber-400">
          <AlertCircle className="mt-px h-3 w-3 shrink-0" />
          <span className="break-all">{error || dl.error}</span>
        </p>
      )}
    </div>
  );
}
