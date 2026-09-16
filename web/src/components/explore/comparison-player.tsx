"use client";

import * as React from "react";
import { GitCompareArrows } from "lucide-react";
import { cn } from "@/lib/utils";
import { StemPlayer } from "@/components/ui/stem-player";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { JobStem, Model } from "@/lib/types";

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

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center gap-2">
        <GitCompareArrows className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">A/B comparison</h3>
        <span className="text-xs text-muted-foreground">
          {entries.length > 0
            ? "Playback is synchronized across all models"
            : `${count} model${count > 1 ? "s" : ""} selected — run them to generate stems`}
        </span>
      </div>
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
          : models.map((m) => (
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
                <p className="text-xs text-muted-foreground">
                  Run this model to generate comparison stems.
                </p>
                <Button size="sm" asChild>
                  <a href={`/tools/model-picker?model=${m.id}`}>
                    Run this model
                  </a>
                </Button>
              </div>
            ))}
      </div>
    </div>
  );
}