"use client";

import * as React from "react";
import {
  Cpu,
  Search,
  Star,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import { modelTrait, modelsForScene } from "@/lib/models";
import { licenseFor } from "@/lib/licenses";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import type { Model, SceneKey } from "@/lib/types";

interface ModelSelectionCardProps {
  scene: SceneKey;
  className?: string;
}

const USAGE_OPTIONS = ["All passes", "1 pass", "3+ passes"] as const;
const TRAIT_OPTIONS = [
  "All",
  "Low bleed",
  "Stable stems",
  "Detailed split",
  "Fuller sound",
  "Balanced",
  "Natural tone",
  "Dual stems",
  "High quality",
  "Clean boundary",
] as const;

/**
 * Workbench "Model Selection" card — searchable, filterable 2-column grid
 * of model cards (name / provider / trait / passes / favorite + license badges).
 */
export function ModelSelectionCard({ scene, className }: ModelSelectionCardProps) {
  const models = useStore((s) => s.modelCatalog);
  const selectedModelId = useStore((s) => s.selectedModelId);
  const selectModel = useStore((s) => s.selectModel);

  const [query, setQuery] = React.useState("");
  const [usage, setUsage] = React.useState<(typeof USAGE_OPTIONS)[number]>("All passes");
  const [trait, setTrait] = React.useState<(typeof TRAIT_OPTIONS)[number]>("All");
  const favorites = useStore((s) => s.favorites);
  const toggleFavorite = useStore((s) => s.toggleFavorite);

  const sceneModels = React.useMemo(
    () => modelsForScene(scene, models),
    [scene, models],
  );

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return sceneModels.filter((m) => {
      if (q && !`${m.name} ${m.arch} ${modelTrait(m)}`.toLowerCase().includes(q)) return false;
      if (usage === "1 pass" && m.usage === "3+ passes") return false;
      if (usage === "3+ passes" && m.usage !== "3+ passes") return false;
      if (trait !== "All" && modelTrait(m) !== trait) return false;
      return true;
    });
  }, [sceneModels, query, usage, trait]);

  const selected = sceneModels.find((m) => m.id === selectedModelId);
  const hasFilters = query !== "" || usage !== "All passes" || trait !== "All";

  return (
    <section
      id="model-selection"
      className={cn(
        "scroll-mt-24 rounded-2xl border border-white/10 bg-[#12141A] p-4",
        className,
      )}
    >
      {/* Header */}
      <div className="relative mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-indigo-200">
            <Cpu className="h-4 w-4" />
          </span>
          <h2 className="text-base font-bold text-foreground">Model Selection</h2>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search models or traits"
            aria-label="Search models or traits"
            className="h-9 w-full rounded-full border border-white/10 bg-black/20 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 sm:w-96"
          />
        </div>
      </div>

      {/* Filters */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          value={usage}
          onValueChange={(v) => setUsage(v as (typeof USAGE_OPTIONS)[number])}
        >
          <SelectTrigger className="h-8 w-auto gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-foreground" aria-label="Usage">
            <div className="flex items-center gap-1.5">
              Usage
              <span className="text-muted-foreground">{usage}</span>
            </div>
          </SelectTrigger>
          <SelectContent>
            {USAGE_OPTIONS.map((u) => (
              <SelectItem key={u} value={u}>
                {u}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={trait}
          onValueChange={(v) => setTrait(v as (typeof TRAIT_OPTIONS)[number])}
        >
          <SelectTrigger className="h-8 w-auto gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-foreground" aria-label="Traits">
            <div className="flex items-center gap-1.5">
              Traits
              <span className="text-muted-foreground">{trait}</span>
            </div>
          </SelectTrigger>
          <SelectContent>
            {TRAIT_OPTIONS.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <button
          type="button"
          onClick={() => {
            setQuery("");
            setUsage("All passes");
            setTrait("All");
          }}
          disabled={!hasFilters}
          className="flex items-center gap-1 rounded-full px-2 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
        >
          <X className="h-3 w-3" />
          Clear filters
        </button>
      </div>

      {/* Meta */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-3">
        <span className="text-xs text-muted-foreground">
          Selected:{" "}
          <span className="font-semibold text-foreground">
            {selected?.name ?? "—"}
          </span>
        </span>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          Showing {filtered.length} models
          <span className="rounded-full border border-white/10 px-2 py-0.5 font-medium text-foreground">
            {selected?.usage ?? "1 pass"}
          </span>
        </span>
      </div>

      {/* Model grid — 4 columns, scrollable like the reference */}
      <div className="grid max-h-[420px] grid-cols-2 gap-1.5 overflow-y-auto pr-1 sm:grid-cols-3 xl:grid-cols-4">
        {filtered.map((m) => (
          <ModelRow
            key={m.id}
            model={m}
            selected={m.id === selectedModelId}
            favorite={favorites.includes(m.id)}
            onSelect={() => selectModel(m.id)}
            onToggleFavorite={() => toggleFavorite(m.id)}
          />
        ))}
      </div>
      {filtered.length === 0 && (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No models match those filters.
        </p>
      )}
    </section>
  );
}

function ModelRow({
  model,
  selected,
  favorite,
  onSelect,
  onToggleFavorite,
}: {
  model: Model;
  selected: boolean;
  favorite: boolean;
  onSelect: () => void;
  onToggleFavorite: () => void;
}) {
  const trait = modelTrait(model);
  const usage = model.usage ?? "1 pass";
  const lic = licenseFor(model.id, model.arch);

  return (
    <div
      className={cn(
        "group relative flex h-[76px] flex-col rounded-xl border px-3 py-2 transition-colors",
        selected
          ? "border-indigo-400/40 bg-indigo-500/[0.08]"
          : "border-white/[0.06] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className="flex min-w-0 flex-1 flex-col justify-between pr-7 text-left focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 rounded-lg"
        aria-pressed={selected}
        aria-label={`${model.name} ${model.arch} ${trait} ${usage}`}
      >
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold leading-5 text-foreground">
            {model.name}
          </span>
          <span className="block truncate text-xs leading-4 text-muted-foreground">
            {model.arch}
          </span>
        </span>
        <span className="flex min-w-0 items-center gap-1 overflow-hidden">
          <span
            className="shrink-0 rounded-md bg-white/[0.06] px-1.5 py-px text-[11px] font-medium text-foreground/80"
            title={`${trait} — a characteristic describing this model's separation style`}
          >
            {trait}
          </span>
          <span className="shrink-0 text-[11px] text-muted-foreground">{usage}</span>
          {model.ensemble && (
            <span className="shrink-0 rounded-md bg-indigo-500/15 px-1.5 py-px text-[10px] font-semibold text-indigo-300">
              Ensemble
            </span>
          )}
          {model.recommended && (
            <span className="shrink-0 rounded-md bg-emerald-500/15 px-1.5 py-px text-[10px] font-semibold text-emerald-400">
              Recommended
            </span>
          )}
          <span
            title={lic.source}
            className={cn(
              "shrink-0 rounded-md px-1.5 py-px text-[10px] font-semibold",
              lic.commercialOk
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-amber-500/15 text-amber-400",
            )}
          >
            {lic.label}
          </span>
        </span>
      </button>

      <button
        type="button"
        onClick={onToggleFavorite}
        aria-label={favorite ? "Unfavorite model" : "Favorite model"}
        aria-pressed={favorite}
        className={cn(
          "absolute right-1.5 top-1.5 rounded-md p-1 transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
          favorite
            ? "text-amber-400"
            : "text-muted-foreground opacity-60 hover:opacity-100 hover:text-foreground",
        )}
      >
        <Star className={cn("h-3.5 w-3.5", favorite && "fill-current")} />
      </button>
    </div>
  );
}