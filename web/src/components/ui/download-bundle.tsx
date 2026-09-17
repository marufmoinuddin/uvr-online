"use client";

import * as React from "react";
import { Download, FileArchive, FileAudio } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { JobStem } from "@/lib/types";
import { downloadUrl } from "@/lib/api";

interface DownloadBundleProps {
  stems: JobStem[];
  jobId: string;
  className?: string;
}

/**
 * "Download bundle" — per-stem downloads plus a ZIP of all stems.
 * Lossless (WAV) vs MP3 320 options are surfaced as separate menu items.
 */
export function DownloadBundle({ stems, jobId, className }: DownloadBundleProps) {
  // One `format` parameter per URL. Appending to an existing query produced
  // duplicate `format=` keys (FastAPI keeps the last), which made the MP3
  // option request an unsupported bundle and fail with a 400.
  const bundleUrl = (format: string) =>
    downloadUrl(`/api/jobs/${jobId}/download?format=${format}`);

  const download = (url: string, filename: string) => {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  /** Save a stem under its real filename (with extension), not the bare name. */
  const stemFilename = (url: string, fallback: string) => {
    try {
      const last = new URL(url, window.location.origin).pathname.split("/").pop();
      return last ? decodeURIComponent(last) : fallback;
    } catch {
      return fallback;
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="default" size="sm" className={className}>
          <Download className="h-4 w-4" />
          Download bundle
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>Download stems</DropdownMenuLabel>
        {stems.map((s) => {
          const url = downloadUrl(s.url);
          return (
            <DropdownMenuItem
              key={s.name}
              onSelect={() =>
                download(url, stemFilename(url, `${s.name}.${s.format}`))
              }
            >
              <FileAudio className="h-4 w-4 text-primary" />
              <span className="capitalize">{s.name}</span>
              <span className="ml-auto text-xs text-muted-foreground">
                {s.format.toUpperCase()}
              </span>
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Bundle</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => download(bundleUrl("zip"), `${jobId}.zip`)}>
          <FileArchive className="h-4 w-4 text-primary" />
          All stems as produced (.zip)
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => download(bundleUrl("wav"), `${jobId}-lossless.zip`)}
        >
          <FileArchive className="h-4 w-4 text-emerald-500" />
          Lossless WAV (.zip)
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => download(bundleUrl("mp3"), `${jobId}-mp3.zip`)}
        >
          <FileArchive className="h-4 w-4 text-amber-500" />
          MP3 320 (.zip)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}