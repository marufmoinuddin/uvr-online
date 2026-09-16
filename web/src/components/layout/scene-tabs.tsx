"use client";

import * as React from "react";
import { useRouter, usePathname } from "next/navigation";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SCENES } from "@/lib/models";
import type { SceneKey } from "@/lib/types";

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

/**
 * Pill-shaped scene tabs with an animated indigo background indicator.
 * Switches the URL without a full reload (router.push).
 */
export function SceneTabs({
  active,
  className,
}: {
  active: SceneKey;
  className?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();

  const select = (key: SceneKey) => {
    if (key === active) return;
    if (pathname.startsWith("/tools")) {
      router.push(`/tools/${key}`);
    } else {
      router.push(`/tools/${key}`);
    }
  };

  return (
    <div
      role="tablist"
      aria-label="Separation tools"
      className={cn(
        "glass-card mx-auto flex max-w-full flex-wrap items-center justify-center gap-1 p-1.5",
        className,
      )}
    >
      {SCENES.map((scene) => {
        const Icon = ICONS[scene.icon] ?? Music;
        const isActive = scene.key === active;
        return (
          <button
            key={scene.key}
            role="tab"
            aria-selected={isActive}
            onClick={() => select(scene.key)}
            className={cn(
              "relative flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 sm:px-4",
              isActive
                ? "text-primary-foreground"
                : "text-muted-foreground hover:bg-control hover:text-foreground",
            )}
          >
            {isActive && (
              <span
                className="absolute inset-0 rounded-full bg-primary shadow-primary-glow animate-scale-in"
                aria-hidden
              />
            )}
            <Icon className="relative z-10 h-4 w-4" />
            <span className="relative z-10 hidden md:inline">{scene.label}</span>
            <span className="relative z-10 md:hidden">{scene.short}</span>
          </button>
        );
      })}
    </div>
  );
}