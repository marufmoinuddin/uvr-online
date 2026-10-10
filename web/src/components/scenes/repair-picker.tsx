"use client";

import * as React from "react";
import { Check, Wrench, Loader2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface RepairOp {
  key: string;
  label: string;
  description: string;
}

interface RepairPickerProps {
  ops: RepairOp[];
  selected: string[];
  onToggle: (key: string) => void;
  loading?: boolean;
  error?: string | null;
  className?: string;
}

/**
 * Repair operation picker for the Audio Repair scene.
 *
 * Replaces the model grid: a repair is corrective DSP, so there is no model to
 * choose. Operations are fetched from the worker (`/api/repair/ops`) rather
 * than hardcoded here, because a filter chain ffmpeg rejects should surface
 * before an upload rather than after one.
 */
export function RepairPicker({
  ops,
  selected,
  onToggle,
  loading = false,
  error = null,
  className,
}: RepairPickerProps) {
  return (
    <section
      id="repair-selection"
      aria-label="Repairs"
      className={cn(
        "scroll-mt-24 rounded-2xl border border-white/10 bg-[#12141A] p-4",
        className,
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-indigo-200">
            <Wrench className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-foreground">Repairs</h2>
        </div>
        <span className="rounded-full border border-white/10 px-3 py-1 text-[11px] text-muted-foreground">
          {selected.length} selected
        </span>
      </div>

      <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
        Repairs fix problems in the recording itself. They are applied in a fixed order, so
        the order you pick them in does not matter. Unlike separation, this does not use a
        model — nothing is downloaded and the GPU stays free.
      </p>

      {loading && (
        <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Loading available repairs…
        </p>
      )}

      {!loading && error && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {error}
        </p>
      )}

      {!loading && !error && (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {ops.map((op) => {
            const isOn = selected.includes(op.key);
            return (
              <li key={op.key}>
                <button
                  type="button"
                  onClick={() => onToggle(op.key)}
                  aria-pressed={isOn}
                  className={cn(
                    "flex h-full w-full items-start gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                    isOn
                      ? "border-indigo-400/40 bg-indigo-500/[0.08]"
                      : "border-white/[0.06] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                      isOn
                        ? "border-indigo-400 bg-indigo-500 text-white"
                        : "border-white/20",
                    )}
                  >
                    {isOn && <Check className="h-3 w-3" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold leading-5 text-foreground">
                      {op.label}
                    </span>
                    <span className="mt-0.5 block text-xs leading-4 text-muted-foreground">
                      {op.description}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {selected.length === 0 && !loading && !error && (
        <p className="mt-3 text-xs text-amber-400">
          Choose at least one repair before processing.
        </p>
      )}
    </section>
  );
}