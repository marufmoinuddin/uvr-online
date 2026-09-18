"use client";

import * as React from "react";
import {
  UploadCloud,
  Info,
  FileAudio,
  X,
  ChevronDown,
  ArrowRight,
  Loader2,
} from "lucide-react";
import { cn, formatBytes } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { modelsForScene } from "@/lib/models";
import { createJob } from "@/lib/api";
import { listManagedModels, type ManagedModel } from "@/lib/models-api";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import type { SceneKey } from "@/lib/types";

// Must stay in sync with ALLOWED_EXT in api/main.py — the worker rejects any
// extension it does not list, so advertising one here that the API refuses
// means the user picks a file the dropzone accepts and then gets a 400.
const ACCEPTED = ["mp3", "wav", "flac", "m4a", "ogg", "aac", "wma", "aiff", "mp4", "mov", "mkv", "webm"];
const MAX_FILES = 5;
const MAX_BYTES = 100 * 1024 * 1024; // 100 MB per file

/** Scene-specific CTA so the primary action speaks the user's language. */
const PROCESS_LABEL: Partial<Record<SceneKey, string>> = {
  "vocal-remover": "Separate vocals",
  "extract-vocals": "Extract vocals",
  karaoke: "Make karaoke",
  "stem-splitter": "Split stems",
  denoise: "Remove noise",
  acapella: "Extract acapella",
};

interface FileUploadCardProps {
  scene: SceneKey;
  className?: string;
}

/**
 * Workbench "File Upload" card — multi-file dropzone (up to 5), output
 * format + model controls, Process audio button and a files counter.
 * Mirrors the reference workbench layout.
 */
export function FileUploadCard({ scene, className }: FileUploadCardProps) {
  const selectedModelId = useStore((s) => s.selectedModelId);
  const addJob = useStore((s) => s.addJob);
  const backendOnline = useStore((s) => s.backendOnline);
  const catalog = useStore((s) => s.modelCatalog);
  const modelCount = React.useMemo(
    () => modelsForScene(scene, catalog).length,
    [scene, catalog],
  );
  // Ensemble presets fuse the output of *existing* jobs (2-6 model passes),
  // so they cannot be submitted as a plain single-model separation.
  const isEnsemble =
    catalog.find((m) => m.id === selectedModelId)?.ensemble ?? false;

  // Is the selected model already cached locally? If not, it is fetched on
  // demand the first time it is actually used (no manual file hunting).
  const [selectedStatus, setSelectedStatus] =
    React.useState<ManagedModel | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    const load = async () => {
      try {
        const all = await listManagedModels();
        if (cancelled) return;
        const found = all.find((m) => m.id === selectedModelId) ?? null;
        setSelectedStatus(found);
        // Poll fast only while a download is in flight; otherwise settle into
        // a slow cadence so we don't hammer the worker.
        const downloading =
          found?.download?.status === "downloading" ||
          found?.download?.status === "verifying";
        if (timer) clearInterval(timer);
        timer = setInterval(load, downloading ? 1500 : 15_000);
      } catch {
        /* worker unreachable — leave the last known state */
      }
    };
    load();
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [selectedModelId]);

  const [files, setFiles] = React.useState<File[]>([]);
  const [dragActive, setDragActive] = React.useState(false);
  const [outputFormat, setOutputFormat] = React.useState<"mp3" | "wav" | "flac">("mp3");
  const [submitting, setSubmitting] = React.useState(false);
  const [uploadPct, setUploadPct] = React.useState(0);
  const [rejectionMessage, setRejectionMessage] = React.useState("");
  const [jobError, setJobError] = React.useState("");
  const [confirmBatch, setConfirmBatch] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const addFiles = React.useCallback((list: FileList | File[] | null) => {
    if (!list) return;
    setJobError("");
    const all = Array.from(list);
    const incoming = all.filter((f) => {
      const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
      return ACCEPTED.includes(ext) && f.size <= MAX_BYTES;
    });
    setFiles((prev) => [...prev, ...incoming].slice(0, MAX_FILES));
    if (incoming.length < all.length) {
      const count = all.length - incoming.length;
      setRejectionMessage(
        `${count} file${count > 1 ? "s" : ""} rejected (unsupported format or exceeds ${formatBytes(MAX_BYTES)})`,
      );
      setTimeout(() => setRejectionMessage(""), 5000);
    }
  }, []);

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleProcess = async () => {
    if (files.length === 0 || submitting || isEnsemble) return;
    setSubmitting(true);
    setUploadPct(0);
    try {
      for (const file of files) {
        const res = await createJob(
          file,
          {
            scene,
            modelId: selectedModelId,
            options: { outputFormat, extractInstrumental: scene === "vocal-remover" || scene === "karaoke" },
          },
          setUploadPct,
        );
        addJob({
          id: res.jobId,
          status: "queued",
          scene,
          modelId: selectedModelId,
          fileName: file.name,
          progress: 0,
          stage: "queued",
          etaSec: res.etaSec,
          createdAt: Date.now(),
        });
      }
      setFiles([]);
    } catch (err) {
      console.error(err);
      setJobError(err instanceof Error ? err.message : "Failed to start job");
    } finally {
      setSubmitting(false);
    }
  };

  // Ctrl/Cmd+Enter submits the queued files — an accelerator for repeat users.
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        if (files.length > 0 && !submitting && !isEnsemble && backendOnline !== false) {
          e.preventDefault();
          if (files.length > 1) setConfirmBatch(true);
          else handleProcess();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files.length, submitting, isEnsemble, backendOnline]);

  const processLabel = PROCESS_LABEL[scene] ?? "Process audio";
  const offline = backendOnline === false;

  return (
    <section
      className={cn(
        "rounded-2xl border border-white/10 bg-[#141721] p-5",
        className,
      )}
    >
      {/* Header */}
      <div className="relative mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-indigo-200">
            <UploadCloud className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-foreground">File Upload</h2>
        </div>
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label="Supported formats and limits"
              className="rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
            >
              <Info className="h-4 w-4" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-72">
            <div className="space-y-2">
              <p className="text-sm font-semibold">Supported files</p>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {ACCEPTED.map((e) => e.toUpperCase()).join(", ")}
              </p>
              <p className="text-xs leading-relaxed text-muted-foreground">
                Up to {MAX_FILES} files at once, max {formatBytes(MAX_BYTES)}{" "}
                each.
              </p>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        {/* Dropzone */}
        <div
          className="relative"
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setDragActive(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            addFiles(e.dataTransfer.files);
          }}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED.map((e) => `.${e}`).join(",")}
            className="hidden"
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          {files.length === 0 ? (
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className={cn(
                "flex h-40 w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-white/[0.12] bg-black/70 px-6 text-center transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                dragActive
                  ? "border-indigo-400/70 bg-indigo-500/[0.06]"
                  : "hover:border-white/25",
              )}
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/[0.06] text-muted-foreground">
                <UploadCloud className="h-6 w-6" />
              </span>
              <span>
                <span className="block text-sm font-semibold text-foreground">
                  Drop up to {MAX_FILES} audio or video files here
                </span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  Each file will create its own processing job.
                </span>
              </span>
            </button>
          ) : (
            <div className="flex min-h-[160px] flex-col gap-2 rounded-2xl border border-white/10 bg-black/40 p-3">
              {files.map((f, i) => (
                <div
                  key={`${f.name}-${i}`}
                  className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2"
                >
                  <FileAudio className="h-4 w-4 shrink-0 text-indigo-300" />
                  <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                    {f.name}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatBytes(f.size)}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeFile(i)}
                    aria-label={`Remove ${f.name}`}
                    className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="mt-auto rounded-xl border border-dashed border-white/15 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-white/30 hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
              >
                Add more files
              </button>
            </div>
          )}
        </div>
      {/* Error messages */}
      {rejectionMessage && (
        <p className="mt-2 text-xs text-amber-500">{rejectionMessage}</p>
      )}
      {jobError && (
        <p className="mt-2 text-xs text-red-500">{jobError}</p>
      )}
        {/* Controls — 360px column, 12px padding, 72px group + 20px gap + 44px row */}
        <div className="flex flex-col gap-5 p-3">
          {/* Output format + Models (2-col, 72px tall) */}
          <div className="grid grid-cols-2 gap-2">
            <Select
              value={outputFormat}
              onValueChange={(v) => setOutputFormat(v as "mp3" | "wav" | "flac")}
            >
              <SelectTrigger className="h-[72px] w-full flex-col items-start justify-center gap-0.5 rounded-2xl border border-white/10 bg-white/[0.03] px-3 text-left [&>svg]:hidden" aria-label="Output format">
                {/* div, not span: the trigger's `[&>span]:` rules outrank a
                    plain `flex` utility, so a span here is forced to
                    display:block and the chevron drops to its own line. */}
                <div className="flex w-full items-center justify-between">
                  <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Output format
                  </span>
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                </div>
                <div className="text-sm font-semibold leading-5 text-foreground">
                  {outputFormat.toUpperCase()}
                </div>
                <div className="text-xs leading-4 text-muted-foreground">
                  {outputFormat === "mp3" ? "320 kbps" : "Lossless"}
                </div>
              </SelectTrigger>
              <SelectContent>
                {(["mp3", "wav", "flac"] as const).map((f) => (
                  <SelectItem key={f} value={f}>
                    <span className="flex items-center justify-between gap-4">
                      <span>{f.toUpperCase()}</span>
                      <span className="text-xs text-muted-foreground">
                        {f === "mp3" ? "320 kbps" : "Lossless"}
                      </span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Models — every model is open-source and free */}
            <a
              href="#model-selection"
              className="flex h-[72px] w-full flex-col items-start justify-center gap-0.5 rounded-2xl border border-white/10 bg-white/[0.03] px-3 text-left transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
            >
              <span className="flex w-full items-center justify-between">
                <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Models
                </span>
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </span>
              <span className="text-sm font-semibold leading-5 text-foreground">
                {modelCount} available
              </span>
              <span className="text-xs leading-4 text-muted-foreground">
                All open-source
              </span>
            </a>

            {/* Selected model cache state */}
            {selectedStatus && !isEnsemble && (
              <p className="text-[11px] leading-4 text-muted-foreground">
                {selectedStatus.installed ? (
                  <>
                    <span className="text-emerald-400">Cached locally</span>{" "}
                    · {formatBytes(selectedStatus.sizeBytes)}
                  </>
                ) : selectedStatus.download?.status === "downloading" ? (
                  <span className="text-indigo-300">
                    Downloading model… {selectedStatus.download?.percent.toFixed(0)}%
                  </span>
                ) : selectedStatus.downloadable ? (
                  <>
                    Not downloaded · {selectedStatus.sizeMB} MB — downloads
                    automatically on first run
                  </>
                ) : (
                  <span className="text-amber-400">
                    Not runnable — this entry has no download source configured
                  </span>
                )}
              </p>
            )}
          </div>

          {/* Process audio + files counter (44px) */}
          <div className="grid grid-cols-[minmax(0,1fr)_112px] gap-2">
            <button
              type="button"
              onClick={() => {
                if (files.length > 1) setConfirmBatch(true);
                else handleProcess();
              }}
              disabled={files.length === 0 || submitting || isEnsemble || offline}
              title={
                offline
                  ? "The processing service is offline — jobs cannot be submitted until it comes back."
                  : isEnsemble
                    ? "Ensemble presets fuse the results of existing jobs — run 2 or more separations first, then use the Ensemble builder on the Explore page."
                    : undefined
              }
              className={cn(
                "flex h-11 items-center justify-center gap-2 rounded-2xl px-3 text-sm font-bold transition-all focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                files.length > 0 && !submitting && !isEnsemble && !offline
                  ? "bg-white text-black hover:bg-white/90 shadow-[0_0_22px_-6px_rgba(255,255,255,0.4)]"
                  : "bg-white/[0.05] text-muted-foreground",
              )}
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {uploadPct > 0 && uploadPct < 100 ? "Uploading…" : "Processing…"}
                </>
              ) : (
                <>
                  {processLabel}
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>

            {/* Files counter */}
            <div className="flex h-11 flex-col items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03] px-2 leading-tight">
              <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                Files
              </span>
              <span className="text-sm font-semibold text-foreground">
                {files.length}/{MAX_FILES}
              </span>
            </div>
          </div>
          {submitting && uploadPct > 0 && uploadPct < 100 && (
            <div className="space-y-1">
              <Progress value={uploadPct} />
              <p className="text-center text-[11px] text-muted-foreground">
                Uploading… {uploadPct}%
              </p>
            </div>
          )}
          {isEnsemble && (
            <p className="text-xs text-amber-400">
              Ensemble preset selected — run 2+ separations, then fuse them with
              the Ensemble builder on <a className="underline" href="/explore">Explore</a>.
            </p>
          )}
        </div>
      </div>

      {/* Batch submit confirm — only when more than one file is queued */}
      <Dialog open={confirmBatch} onOpenChange={(open) => !open && setConfirmBatch(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Process {files.length} files?</DialogTitle>
            <DialogDescription>
              Each file will be separated with the selected model. This queues{" "}
              {files.length} jobs on the GPU worker.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-32 space-y-1 overflow-y-auto rounded-lg border border-white/10 bg-white/[0.03] p-2 text-xs text-muted-foreground">
            {files.map((f) => (
              <div key={f.name} className="flex items-center justify-between gap-2">
                <span className="truncate">{f.name}</span>
                <span className="shrink-0">{formatBytes(f.size)}</span>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmBatch(false)}>
              Keep editing
            </Button>
            <Button
              onClick={() => {
                setConfirmBatch(false);
                handleProcess();
              }}
            >
              Process all
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}