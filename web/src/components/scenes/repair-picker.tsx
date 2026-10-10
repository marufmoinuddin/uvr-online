"use client";

import * as React from "react";
import { Wrench, Cpu, Loader2, AlertTriangle, Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface RepairOp {
  key: string;
  label: string;
  description: string;
}

export interface NeuralRepairModel {
  id: string;
  name: string;
  shortName: string;
  arch: string;
  categories: string[];
  outputLabel: string;
}

export interface NeuralRepairCategory {
  key: string;
  label: string;
  models: string[];
}

interface RepairPickerProps {
  ops: RepairOp[];
  selected: string[];
  onToggle: (key: string) => void;
  /** Neural models the worker reports, already filtered to eligible ones. */
  models?: NeuralRepairModel[];
  categories?: NeuralRepairCategory[];
  selectedModel?: string | null;
  onSelectModel?: (id: string | null) => void;
  loading?: boolean;
  error?: string | null;
  className?: string;
}

/**
 * Repair picker for the Audio Repair scene.
 *
 * Replaces the model grid: a repair is corrective, so the choice is between
 * CPU-only fix-ups and an optional neural model — not a separation model.
 *
 * The two are kept VISUALLY DISTINCT on purpose. Fix-ups are instant, need no
 * download and leave the GPU free; a neural model may fetch hundreds of
 * megabytes and will occupy the GPU. Presenting them as one undifferentiated
 * list would let someone pick what looks like a cheap filter and be surprised
 * by a long model run.
 *
 * Everything shown is derived from the worker (`/api/repair/capabilities`), so
 * a category is only offered when a model actually declares it.
 */
export function RepairPicker({
  ops,
  selected,
  onToggle,
  models = [],
  categories = [],
  selectedModel = null,
  onSelectModel,
  loading = false,
  error = null,
  className,
}: RepairPickerProps) {
  const byId = React.useMemo(
    () => new Map(models.map((m) => [m.id, m])),
    [models],
  );
  const chosen = selectedModel ? byId.get(selectedModel) : null;

  // Mirror the worker's stage split so the summary states what will ACTUALLY
  // run. Without a model there is no staging at all — every selected op goes
  // through the plain DSP path, so describing a "finishing" stage would
  // promise a pipeline that never executes.
  // (Must stay in sync with PRE_OPS/POST_OPS in api/repair_workflow.py.)
  const PRE_OPS = ["declick", "declip", "dehum", "normalize"];
  const POST_OPS = ["depop", "denoise", "gate"];
  const pre = chosen ? selected.filter((k) => PRE_OPS.includes(k)) : selected;
  const post = chosen ? selected.filter((k) => POST_OPS.includes(k)) : [];

  const summary = React.useMemo(() => {
    if (!chosen) {
      const n = pre.length;
      return `${n} fix-up${n === 1 ? "" : "s"} → encode once. No model download — the GPU stays free.`;
    }
    const parts: string[] = [];
    if (pre.length) parts.push(`CPU fix-ups (${pre.length})`);
    parts.push(`GPU model — ${chosen.shortName || chosen.name}`);
    if (post.length) parts.push(`finishing fix-ups (${post.length})`);
    parts.push("encode once");
    return `${parts.join(" → ")}. The model is fetched on first use.`;
  }, [pre.length, post.length, chosen]);

  return (
    <section
      id="repair-selection"
      aria-label="Repairs"
      className={cn(
        "scroll-mt-24 space-y-5 rounded-2xl border border-white/10 bg-[#12141A] p-4",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-indigo-200">
            <Wrench className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-foreground">Repairs</h2>
        </div>
        <span className="rounded-full border border-white/10 px-3 py-1 text-[11px] text-muted-foreground">
          {selected.length} fix-up{selected.length === 1 ? "" : "s"}
          {chosen ? " + 1 model" : ""}
        </span>
      </div>

      {loading && (
        <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
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
        <>
          {models.length > 0 && (
            <div>
              <h3 className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <Cpu className="h-3.5 w-3.5" aria-hidden />
                Model cleanup
              </h3>
              <p className="mb-2 text-xs text-muted-foreground">
                A neural model runs on the GPU and is fetched on first use. Pick
                one, or leave this empty and use fix-ups only.
              </p>

              <ul className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                {categories.map((cat) => {
                  const catModels = cat.models
                    .map((id) => byId.get(id))
                    .filter((m): m is NeuralRepairModel => Boolean(m));
                  if (catModels.length === 0) return null;
                  return (
                    <li key={cat.key}>
                      <p className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                        {cat.label}
                        {/* Count comes from the SAME list the cards are rendered
                            from, so a facet can never display a number that
                            disagrees with the cards beneath it. */}
                        <span className="rounded-full border border-white/10 bg-white/5 px-1.5 py-px text-[10px] tabular-nums text-foreground/70">
                          {catModels.length}
                        </span>
                      </p>
                      <ul className="space-y-1.5">
                        {catModels.map((m) => {
                          const isOn = selectedModel === m.id;
                          return (
                            <li key={m.id}>
                              <button
                                type="button"
                                onClick={() =>
                                  onSelectModel?.(isOn ? null : m.id)
                                }
                                aria-pressed={isOn}
                                className={cn(
                                  "flex w-full items-start justify-between gap-2 rounded-xl border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                                  isOn
                                    ? "border-indigo-400/40 bg-indigo-500/[0.08]"
                                    : "border-white/[0.06] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]",
                                )}
                              >
                                <span className="min-w-0">
                                  <span className="block text-sm font-semibold leading-5 text-foreground">
                                    {m.shortName || m.name}
                                  </span>
                                  <span className="block text-[11px] leading-4 text-muted-foreground">
                                    {m.outputLabel}
                                  </span>
                                </span>
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
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          <div>
            <h3 className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Wrench className="h-3.5 w-3.5" aria-hidden />
              Fix-ups
            </h3>
            <p className="mb-2 text-xs text-muted-foreground">
              {models.length > 0
                ? "Applied on the CPU — no download, instant. Fix-ups that polish the result run after the model."
                : "Repairs fix problems in the recording itself. They are applied in a fixed order, so the order you pick them in does not matter. Unlike separation, this does not use a model — nothing is downloaded and the GPU stays free."}
            </p>
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
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Processing summary
            </p>
            <p className="mt-1 text-xs leading-5 text-foreground">
              {selected.length === 0 && !chosen && (
                <span className="text-amber-400">
                  Choose a model or at least one fix-up before processing.
                </span>
              )}
              {summary && <>{summary}</>}
            </p>
          </div>
        </>
      )}
    </section>
  );
}