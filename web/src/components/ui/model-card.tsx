"use client";

import * as React from "react";
import { Cpu, Sparkles, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { licenseFor } from "@/lib/licenses";
import type { Model } from "@/lib/types";

interface ModelCardProps {
  model: Model;
  onTry?: (id: string) => void;
  selected?: boolean;
  onToggleCompare?: (id: string) => void;
  comparing?: boolean;
  className?: string;
}

/**
 * Model matrix card — glass card with architecture badge, target,
 * SDR chip, verified license chip and a "Try" button.
 */
export function ModelCard({
  model,
  onTry,
  selected,
  onToggleCompare,
  comparing,
  className,
}: ModelCardProps) {
  const lic = licenseFor(model.id, model.arch);
  return (
    <div
      className={cn(
        "glass-card group flex flex-col gap-3 p-5 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg",
        selected && "border-primary/50 shadow-primary-glow",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Cpu className="h-5 w-5" />
        </div>
        <div className="flex gap-1.5">
          <Badge
            variant={lic.commercialOk ? "success" : "warning"}
            title={lic.source}
          >
            {lic.label}
          </Badge>
          {model.sdr != null && (
            <Badge variant="secondary" title="Signal-to-Distortion Ratio — higher means cleaner separation">
              SDR {model.sdr.toFixed(1)}
            </Badge>
          )}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold leading-snug">{model.name}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{model.arch}</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <Badge variant="outline" className="capitalize">
          {model.target}
        </Badge>
        {model.tags.slice(0, 3).map((t) => (
          <Badge key={t} variant="secondary" className="capitalize">
            {t}
          </Badge>
        ))}
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 pt-1">
        <span className="text-xs text-muted-foreground">{model.sizeMB} MB</span>
        <div className="flex items-center gap-1.5">
          {onToggleCompare && (
            <Button
              variant={comparing ? "default" : "outline"}
              size="sm"
              onClick={() => onToggleCompare(model.id)}
              aria-pressed={comparing}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Compare
            </Button>
          )}
          {onTry && (
            <Button size="sm" onClick={() => onTry(model.id)}>
              Try
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}