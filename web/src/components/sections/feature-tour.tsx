"use client";

import * as React from "react";
import Link from "next/link";
import {
  MicOff,
  Mic,
  Music,
  Layers,
  Waves,
  MicVocal,
  SlidersHorizontal,
  AudioLines,
  Grid2x2,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SCENES } from "@/lib/models";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  "mic-off": MicOff,
  mic: Mic,
  music: Music,
  layers: Layers,
  waves: Waves,
  "mic-vocal": MicVocal,
  "sliders-horizontal": SlidersHorizontal,
  "audio-lines": AudioLines,
  "grid-2x2": Grid2x2,
};

export function FeatureTour({ className }: { className?: string }) {
  return (
    <section className={cn("mx-auto max-w-container px-4 py-16", className)}>
      <div className="mx-auto mb-12 max-w-2xl text-center">
        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Every tool, one click away
        </h2>
        <p className="mt-3 text-muted-foreground">
          Nine professional separation tools backed by 80+ open-source models.
        </p>
      </div>
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {SCENES.map((scene, i) => {
          const Icon = ICONS[scene.icon] ?? Music;
          return (
            <Link
              key={scene.key}
              href={`/tools/${scene.key}`}
              className={cn(
                "glass-card group flex flex-col gap-3 p-6 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg animate-slide-up",
                `animation-delay-${(i % 5 + 1) * 100}`,
              )}
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary transition-transform group-hover:scale-110">
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <h3 className="font-semibold">{scene.label}</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {scene.description}
                </p>
              </div>
              <span className="mt-auto inline-flex items-center gap-1 text-sm font-medium text-primary">
                Try it
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}