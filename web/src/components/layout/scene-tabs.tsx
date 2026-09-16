"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
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
  const tabRefs = React.useRef<(HTMLButtonElement | null)[]>([]);

  const select = (key: SceneKey) => {
    if (key === active) return;
    router.push(`/tools/${key}`);
  };

  // Arrow-key navigation per the WAI-ARIA tabs pattern. Each tab navigates
  // to its own page, so arrow keys move focus and activate the next tab.
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const idx = SCENES.findIndex((s) => s.key === active);
    let next = -1;
    if (e.key === "ArrowRight") next = (idx + 1) % SCENES.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + SCENES.length) % SCENES.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = SCENES.length - 1;
    if (next === -1) return;
    e.preventDefault();
    const key = SCENES[next].key;
    select(key);
    tabRefs.current[next]?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label="Separation tools"
      onKeyDown={onKeyDown}
      className={cn(
        "glass-card mx-auto flex max-w-full flex-wrap items-center justify-center gap-1 p-1.5",
        className,
      )}
    >
      {SCENES.map((scene, i) => {
        const Icon = ICONS[scene.icon] ?? Music;
        const isActive = scene.key === active;
        return (
          <button
            key={scene.key}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            role="tab"
            aria-selected={isActive}
            aria-controls="workbench-main"
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