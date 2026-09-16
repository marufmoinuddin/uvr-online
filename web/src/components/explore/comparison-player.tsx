"use client";

import * as React from "react";
import { GitCompareArrows } from "lucide-react";
import { cn } from "@/lib/utils";
import { StemPlayer } from "@/components/ui/stem-player";
import { Button } from "@/components/ui/button";
import type { JobStem } from "@/lib/types";

export interface ComparisonEntry {
  id: string;
  label: string;
  stems: JobStem[];
}

interface ComparisonPlayerProps {
  entries: ComparisonEntry[];
  className?: string;
}

/**
 * A/B comparison — loads 2–4 models side-by-side with synced playback
 * (all players share a sync group) and a waveform overlay.
 */
export function ComparisonPlayer({ entries, className }: ComparisonPlayerProps) {
  const [group] = React.useState(() => `compare-${Math.random().toString(36).slice(2)}`);

  if (entries.length === 0) {
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

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center gap-2">
        <GitCompareArrows className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">A/B comparison</h3>
        <span className="text-xs text-muted-foreground">
          Playback is synchronized across all models
        </span>
      </div>
      <div
        className={cn(
          "grid gap-4",
          entries.length === 2 && "sm:grid-cols-2",
          entries.length === 3 && "sm:grid-cols-2 lg:grid-cols-3",
          entries.length >= 4 && "sm:grid-cols-2 lg:grid-cols-4",
        )}
      >
        {entries.map((entry) => (
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
    </div>
  );
}