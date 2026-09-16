"use client";

import * as React from "react";
import { Check, ChevronsUpDown, Search, Cpu } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import type { Model } from "@/lib/types";

interface ModelComboboxProps {
  models: Model[];
  value: string;
  onValueChange: (id: string) => void;
  placeholder?: string;
  className?: string;
}

/**
 * Searchable model selector grouped by architecture.
 * Mirrors the site's combobox: search input + grouped list + arch badges.
 */
export function ModelCombobox({
  models,
  value,
  onValueChange,
  placeholder = "Select a model…",
  className,
}: ModelComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");

  const selected = models.find((m) => m.id === value);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return models;
    return models.filter(
      (m) =>
        m.name.toLowerCase().includes(q) ||
        m.arch.toLowerCase().includes(q) ||
        m.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [models, query]);

  const grouped = React.useMemo(() => {
    const map = new Map<string, Model[]>();
    for (const m of filtered) {
      const list = map.get(m.arch) ?? [];
      list.push(m);
      map.set(m.arch, list);
    }
    return Array.from(map.entries());
  }, [filtered]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label="Select model"
          className={cn("w-full justify-between font-normal", className)}
        >
          {selected ? (
            <span className="flex items-center gap-2 truncate">
              <Cpu className="h-4 w-4 text-primary" />
              <span className="truncate">{selected.name}</span>
              <Badge variant="secondary" className="hidden sm:inline-flex">
                {selected.arch}
              </Badge>
            </span>
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search models…"
            className="h-8 border-0 bg-transparent px-0 focus-visible:ring-0"
            autoFocus
          />
        </div>
        <ScrollArea className="h-72">
          <div className="p-1">
            {grouped.length === 0 && (
              <p className="px-2 py-6 text-center text-sm text-muted-foreground">
                No models match “{query}”.
              </p>
            )}
            {grouped.map(([arch, items]) => (
              <div key={arch} className="mb-1">
                <p className="px-2 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {arch}
                </p>
                {items.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      onValueChange(m.id);
                      setOpen(false);
                      setQuery("");
                    }}
                    className={cn(
                      "flex w-full items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-control focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                      value === m.id && "bg-control",
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="truncate">{m.name}</span>
                      {m.installed && (
                        <Badge variant="success" className="shrink-0">
                          installed
                        </Badge>
                      )}
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {m.sizeMB} MB
                      </span>
                      {value === m.id && <Check className="h-4 w-4 text-primary" />}
                    </span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}