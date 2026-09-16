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
  const zipUrl = downloadUrl(`/api/jobs/${jobId}/download?format=zip`);

  const download = (url: string, filename: string) => {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
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
        {stems.map((s) => (
          <DropdownMenuItem
            key={s.name}
            onSelect={() => download(downloadUrl(s.url), s.name)}
          >
            <FileAudio className="h-4 w-4 text-primary" />
            <span className="capitalize">{s.name}</span>
            <span className="ml-auto text-xs text-muted-foreground">
              {s.format.toUpperCase()}
            </span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuLabel>Bundle</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => download(zipUrl, `${jobId}.zip`)}>
          <FileArchive className="h-4 w-4 text-primary" />
          All stems (.zip)
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => download(`${zipUrl}&lossless=1`, `${jobId}-lossless.zip`)}>
          <FileArchive className="h-4 w-4 text-emerald-500" />
          Lossless WAV (.zip)
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => download(`${zipUrl}&format=mp3`, `${jobId}-mp3.zip`)}>
          <FileArchive className="h-4 w-4 text-amber-500" />
          MP3 320 (.zip)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}