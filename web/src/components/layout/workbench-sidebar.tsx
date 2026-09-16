"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MicOff,
  MicVocal,
  Music,
  SlidersHorizontal,
  Layers,
  Wrench,
  AudioLines,
  ChevronsUpDown,
  AudioWaveform,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";

interface NavItem {
  key: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const GROUPS: NavGroup[] = [
  {
    label: "Vocal",
    items: [
      { key: "vocal-remover", label: "Vocal Remover", href: "/tools/vocal-remover", icon: MicOff },
      { key: "acapella", label: "Acapella Extractor", href: "/tools/acapella", icon: MicVocal },
      { key: "karaoke", label: "Karaoke Maker", href: "/tools/karaoke", icon: Music },
      { key: "vocal-tools", label: "Vocal Tools", href: "/tools/vocal-tools", icon: SlidersHorizontal },
    ],
  },
  {
    label: "Separation",
    items: [
      { key: "stem-splitter", label: "Stem Splitter", href: "/tools/stem-splitter", icon: Layers },
      { key: "extract-vocals", label: "Extract Vocals", href: "/tools/extract-vocals", icon: MicVocal },
    ],
  },
  {
    label: "Repair",
    items: [
      { key: "denoise", label: "Audio Repair", href: "/tools/denoise", icon: Wrench },
    ],
  },
  {
    label: "Production",
    items: [
      { key: "production", label: "Music Production Tools", href: "/tools/production", icon: AudioLines },
    ],
  },
];

/**
 * Workbench sidebar — grouped tool navigation with an active-state pill,
 * mirroring the reference workbench layout.
 */
export function WorkbenchSidebar({
  active,
  className,
}: {
  active: string;
  className?: string;
}) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "flex w-[232px] flex-col gap-4 rounded-2xl border border-white/10 bg-[#0F1116] p-3",
        className,
      )}
    >
      {/* Workspace context — dropdown of all tools */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex h-11 w-full items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-1 pr-2 text-left transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-500/15 text-indigo-300">
              <AudioWaveform className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[11px] font-medium leading-4 text-muted-foreground">
                Workspace
              </span>
              <span className="block truncate text-sm font-semibold leading-5 text-foreground">
                Audio tools
              </span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-60">
          {GROUPS.map((group) => (
            <div key={group.label}>
              <p className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {group.label}
              </p>
              {group.items.map((item) => (
                <DropdownMenuItem key={item.key} asChild>
                  <Link href={item.href} className="flex items-center gap-2">
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                </DropdownMenuItem>
              ))}
            </div>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Grouped nav */}
      <nav className="flex flex-col gap-4" aria-label="Workbench tools">
        {GROUPS.map((group) => (
          <div key={group.label}>
            <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
              {group.label}
            </p>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const isActive =
                  active === item.key || pathname === item.href;
                return (
                  <li key={item.label}>
                    <Link
                      href={item.href}
                      className={cn(
                        "flex h-[38px] items-center gap-2 rounded-2xl px-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                        isActive
                          ? "bg-indigo-500/15 text-indigo-200"
                          : "text-muted-foreground hover:bg-white/[0.05] hover:text-foreground",
                      )}
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}