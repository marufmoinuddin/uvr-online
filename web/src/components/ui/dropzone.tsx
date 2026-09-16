"use client";

import * as React from "react";
import { UploadCloud, FileAudio, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/lib/utils";

const ACCEPTED = ["mp3", "wav", "flac", "m4a", "ogg", "aac", "wma", "aiff"];
const MAX_BYTES = 1024 * 1024 * 1024; // 1 GB

interface DropZoneProps {
  file: File | null;
  onFile: (file: File | null) => void;
  onDuration?: (sec: number) => void;
  className?: string;
}

/**
 * Centered glass-card dropzone with drag-over glow, format badges and
 * size limits — matches the site's dropzone exactly.
 */
export function DropZone({ file, onFile, onDuration, className }: DropZoneProps) {
  const [dragActive, setDragActive] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const handleFiles = React.useCallback(
    (files: FileList | null) => {
      const f = files?.[0];
      if (!f) return;
      const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
      if (!ACCEPTED.includes(ext)) {
        alert(`Unsupported format: .${ext}. Please use ${ACCEPTED.join(", ").toUpperCase()}.`);
        return;
      }
      if (f.size > MAX_BYTES) {
        alert(`File too large (${formatBytes(f.size)}). Max is 1 GB.`);
        return;
      }
      onFile(f);
      if (onDuration) {
        const url = URL.createObjectURL(f);
        const audio = new Audio();
        audio.preload = "metadata";
        audio.src = url;
        audio.onloadedmetadata = () => {
          onDuration(audio.duration);
          URL.revokeObjectURL(url);
        };
      }
    },
    [onFile, onDuration],
  );

  return (
    <div
      className={cn("relative", className)}
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
        handleFiles(e.dataTransfer.files);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.map((e) => `.${e}`).join(",")}
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
      {!file ? (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className={cn(
            "glass-card group flex w-full max-w-2xl flex-col items-center justify-center gap-3 border-2 border-dashed px-6 py-14 text-center transition-all duration-300 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
            dragActive
              ? "border-primary bg-primary/5 shadow-primary-glow"
              : "border-control-border hover:border-primary/50",
          )}
        >
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary transition-transform group-hover:scale-110">
            <UploadCloud className="h-7 w-7" />
          </div>
          <div>
            <p className="text-base font-semibold">
              {dragActive ? "Drop it like it's hot" : "Drag & drop your audio"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              or <span className="font-medium text-primary underline-offset-4 group-hover:underline">browse files</span> — MP3, WAV, FLAC, M4A
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2">
            {ACCEPTED.slice(0, 4).map((ext) => (
              <span
                key={ext}
                className="rounded-full border border-control-border bg-control px-2.5 py-0.5 text-xs font-medium text-muted-foreground"
              >
                {ext.toUpperCase()}
              </span>
            ))}
            <span className="text-xs text-muted-foreground">· up to 1 GB</span>
          </div>
        </button>
      ) : (
        <div className="glass-card flex w-full max-w-2xl items-center gap-4 border border-primary/30 px-5 py-4 animate-scale-in">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <FileAudio className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{file.name}</p>
            <p className="text-xs text-muted-foreground">
              {formatBytes(file.size)}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onFile(null)}
            aria-label="Remove file"
            className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-control hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}