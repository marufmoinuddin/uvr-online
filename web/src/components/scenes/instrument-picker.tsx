"use client";

import * as React from "react";
import { Target, Loader2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Model } from "@/lib/types";

export interface InstrumentTarget {
  key: string;
  label: string;
  /** Model ids observed to emit this stem. */
  models: string[];
}

interface InstrumentPickerProps {
  targets: InstrumentTarget[];
  selected: string | null;
  onSelect: (key: string | null) => void;
  /** Full catalogue, used to render each candidate model's real display name. */
  catalog?: Model[];
  loading?: boolean;
  error?: string | null;
  className?: string;
}

/**
 * Instrument picker for the Instrument Extractor scene.
 *
 * Single-select by design: the worker resolves exactly one stem per job and
 * returns a one-element result list, so offering a multi-select here would
 * only produce jobs the scene cannot express.
 *
 * Targets are fetched from the worker (`/api/instruments`), which derives them
 * from the models' OBSERVED output stems. Choosing an instrument also narrows
 * the model grid to models that emit it — see `modelsForScene`.
 */
export function InstrumentPicker({
  targets,
  selected,
  onSelect,
  catalog = [],
  loading = false,
  error = null,
  className,
}: InstrumentPickerProps) {
  const nameOf = React.useCallback(
    (id: string) => catalog.find((m) => m.id === id)?.shortName ?? undefined,
    [catalog],
  );

  return (
    <section
      id="instrument-selection"
      aria-label="Instrument"
      className={cn(
        "scroll-mt-24 rounded-2xl border border-white/10 bg-[#12141A] p-4",
        className,
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-indigo-200">
            <Target className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-foreground">Instrument</h2>
        </div>
        {selected && (
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            Clear
          </button>
        )}
      </div>

      <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
        Pick the one instrument you want. A multi-stem model runs first, then
        only that instrument is kept — you get a single file back, not a full
        split. Only instruments this catalogue has been verified to produce are
        listed.
      </p>

      {loading && (
        <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Loading available instruments…
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

      {!loading && !error && targets.length === 0 && (
        <p className="py-6 text-sm text-muted-foreground">
          No instrument-capable models are available.
        </p>
      )}

      {!loading && !error && targets.length > 0 && (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {targets.map((t) => {
            const isOn = selected === t.key;
            return (
              <li key={t.key}>
                <button
                  type="button"
                  onClick={() => onSelect(isOn ? null : t.key)}
                  aria-pressed={isOn}
                  className={cn(
                    "flex h-full w-full items-center justify-between gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                    isOn
                      ? "border-indigo-400/40 bg-indigo-500/[0.08]"
                      : "border-white/[0.06] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]",
                  )}
                >
                  <span className="text-sm font-semibold text-foreground">
                    {t.label}
                  </span>
                  <span className="shrink-0 text-right text-[11px] leading-4 text-muted-foreground">
                    {t.models.length} model{t.models.length === 1 ? "" : "s"}
                    <br />
                    {t.models.map(nameOf).filter(Boolean).join(", ") || t.key}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {!selected && !loading && !error && targets.length > 0 && (
        <p className="mt-3 text-xs text-amber-400">
          Choose an instrument before processing.
        </p>
      )}
    </section>
  );
}