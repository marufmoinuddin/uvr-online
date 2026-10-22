"use client";

import * as React from "react";
import {
  Cpu,
  Search,
  Star,
  X,
  Info,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useStore } from "@/lib/store";
import {
  SCENES,
  modelTrait,
  modelsForScene,
  modelUsage,
  traitCounts,
  traitDescription,
  usageCounts,
} from "@/lib/models";
import { licenseFor } from "@/lib/licenses";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Model, SceneKey } from "@/lib/types";

interface ModelSelectionCardProps {
  scene: SceneKey;
  className?: string;
  /**
   * Instrument scene only: narrows the grid to models observed to emit this
   * stem. Without it the grid would still offer models the worker rejects for
   * the chosen target, and the failure would only surface after the upload.
   */
  instrumentTarget?: string | null;
}

const ALL_USAGE = "All usage";
const ALL_TRAITS = "All";
const ALL_CATEGORIES = "All";

/**
 * Workbench "Model Selection" card — searchable, filterable grid of model
 * cards (name / architecture / trait / usage / favorite + license badges).
 *
 * Filter options are DERIVED from the scene's model list rather than declared
 * as constants, and each option carries a count. A hand-written option list
 * drifts the moment a model is added or removed, and ends up offering
 * combinations that match nothing, which reads as a broken picker.
 */
export function ModelSelectionCard({ scene, className, instrumentTarget = null }: ModelSelectionCardProps) {
  const models = useStore((s) => s.modelCatalog);
  const selectedModelId = useStore((s) => s.selectedModelId);
  const selectModel = useStore((s) => s.selectModel);
  const device = useStore((s) => s.device);
  const cpuModels = useStore((s) => s.cpuModels);
  const cpuLimits = useStore((s) => s.cpuLimits);

  // CPU mode changes what can be run at all, so the picker has to know about
  // it before the user picks a model and waits for a refusal.
  const onCpu = device === "cpu";
  /**
   * Can this model run on a CPU?
   *
   * The worker's own list wins when it has answered — it is the component
   * that will actually refuse the job. The catalogue's own `cpuOk` flag is the
   * fallback, and the two are kept in sync by scripts/verify-catalog.py.
   */
  const cpuCapable = React.useCallback(
    (m: Model) => {
      if (!onCpu) return true;
      if (cpuModels.length > 0) return cpuModels.includes(m.id);
      return m.cpuOk === true;
    },
    [onCpu, cpuModels],
  );

  const [query, setQuery] = React.useState("");
  const [usage, setUsage] = React.useState<string>(ALL_USAGE);
  const [trait, setTrait] = React.useState<string>(ALL_TRAITS);
  const [category, setCategory] = React.useState<string>(ALL_CATEGORIES);
  const favorites = useStore((s) => s.favorites);
  const toggleFavorite = useStore((s) => s.toggleFavorite);

  const sceneModels = React.useMemo(
    () => modelsForScene(scene, models, instrumentTarget),
    [scene, models, instrumentTarget],
  );

  // Counts come from the scene's full model list, not from `filtered`, so the
  // numbers describe the whole selection instead of collapsing to whatever
  // option is currently picked (standard faceted-search behaviour).
  const usageFacets = React.useMemo(() => usageCounts(sceneModels), [sceneModels]);
  const traitFacets = React.useMemo(() => traitCounts(sceneModels), [sceneModels]);

  // Scene sub-filters (e.g. Vocal Tools' Center / Male-Female). Only categories
  // that at least one model carries are offered, so a scene never shows a chip
  // that leads to an empty list.
  const sceneMeta = React.useMemo(
    () => SCENES.find((s) => s.key === scene),
    [scene],
  );
  const categoryFacets = React.useMemo(() => {
    const declared = sceneMeta?.subFilters ?? [];
    if (declared.length === 0) return [];
    return declared
      .map((c) => ({
        category: c,
        count: sceneModels.filter((m) => m.categories?.includes(c)).length,
      }))
      .filter((f) => f.count > 0);
  }, [sceneMeta, sceneModels]);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return sceneModels.filter((m) => {
      if (
        q &&
        !`${m.name} ${m.shortName ?? ""} ${m.arch} ${modelTrait(m)}`
          .toLowerCase()
          .includes(q)
      ) {
        return false;
      }
      if (usage !== ALL_USAGE && modelUsage(m) !== usage) return false;
      if (trait !== ALL_TRAITS && modelTrait(m) !== trait) return false;
      if (category !== ALL_CATEGORIES && !m.categories?.includes(category)) {
        return false;
      }
      return true;
    });
  }, [sceneModels, query, usage, trait, category]);

  const selected = sceneModels.find((m) => m.id === selectedModelId);
  const hasFilters =
    query !== "" ||
    usage !== ALL_USAGE ||
    trait !== ALL_TRAITS ||
    category !== ALL_CATEGORIES;

  // A filter whose option no longer exists (model removed, scene switched)
  // must not silently widen the results back to everything.
  React.useEffect(() => {
    if (usage !== ALL_USAGE && !usageFacets.some((f) => f.usage === usage)) {
      setUsage(ALL_USAGE);
    }
    if (trait !== ALL_TRAITS && !traitFacets.some((f) => f.trait === trait)) {
      setTrait(ALL_TRAITS);
    }
    if (
      category !== ALL_CATEGORIES &&
      !categoryFacets.some((f) => f.category === category)
    ) {
      setCategory(ALL_CATEGORIES);
    }
  }, [usageFacets, traitFacets, categoryFacets, usage, trait, category]);

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

      {/* CPU mode notice. Shown before the grid, not as a toast: it changes
          what the user can pick, so it has to be where the choice happens. */}
      {onCpu && (
        <div className="mb-3 flex items-start gap-2 rounded-xl border border-amber-500/25 bg-amber-500/[0.07] px-3 py-2 text-xs text-amber-200">
          <Cpu className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
          <p className="leading-relaxed">
            <span className="font-semibold">CPU mode — much slower than the GPU.</span>{" "}
            Only the models measured to be usable on a CPU can be selected
            (the rest are marked &quot;No CPU&quot;).
            {cpuLimits
              ? ` Clips are limited to ${cpuLimits.maxSeconds}s and files to ${Math.round(
                  cpuLimits.maxBytes / (1024 * 1024),
                )} MB, and a job that exceeds ${Math.round(
                  cpuLimits.timeoutSeconds / 60,
                )} minutes is stopped.`
              : ""}
          </p>
        </div>
      )}

      {/* Filters */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select value={usage} onValueChange={setUsage}>
          <SelectTrigger className="h-8 w-auto gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-foreground" aria-label="Usage">
            <div className="flex items-center gap-1.5">
              Usage
              <span className="text-muted-foreground">{usage}</span>
            </div>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_USAGE}>
              <FacetOption label={ALL_USAGE} count={sceneModels.length} />
            </SelectItem>
            {usageFacets.map(({ usage: u, count }) => (
              <SelectItem key={u} value={u}>
                <FacetOption label={u} count={count} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={trait} onValueChange={setTrait}>
          <SelectTrigger className="h-8 w-auto gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-foreground" aria-label="Traits">
            <div className="flex items-center gap-1.5">
              Traits
              <span className="text-muted-foreground">{trait}</span>
            </div>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_TRAITS}>
              <FacetOption label={ALL_TRAITS} count={sceneModels.length} />
            </SelectItem>
            {traitFacets.map(({ trait: t, count }) => (
              <SelectItem key={t} value={t}>
                <FacetOption label={t} count={count} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {categoryFacets.length > 0 && (
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger className="h-8 w-auto gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-foreground" aria-label="Category">
              <div className="flex items-center gap-1.5">
                Category
                <span className="text-muted-foreground">{category}</span>
              </div>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_CATEGORIES}>
                <FacetOption label={ALL_CATEGORIES} count={sceneModels.length} />
              </SelectItem>
              {categoryFacets.map(({ category: c, count }) => (
                <SelectItem key={c} value={c}>
                  <FacetOption label={c} count={count} />
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <button
          type="button"
          onClick={() => {
            setQuery("");
            setUsage(ALL_USAGE);
            setTrait(ALL_TRAITS);
            setCategory(ALL_CATEGORIES);
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
            {selected?.shortName ?? selected?.name ?? "—"}
          </span>
        </span>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          Showing {filtered.length} models
          <span className="rounded-full border border-white/10 px-2 py-0.5 font-medium text-foreground">
            Estimated usage: {selected ? modelUsage(selected) : "1x"}
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
            cpuBlocked={!cpuCapable(m)}
            onSelect={() => selectModel(m.id)}
            onToggleFavorite={() => toggleFavorite(m.id)}
          />
        ))}
      </div>
      {filtered.length === 0 && (
        <p className="py-10 text-center text-sm text-muted-foreground">
          {sceneModels.length === 0
            ? "No models are available for this tool yet."
            : "No models match those filters."}
        </p>
      )}
    </section>
  );
}

function ModelRow({
  model,
  selected,
  favorite,
  cpuBlocked,
  onSelect,
  onToggleFavorite,
}: {
  model: Model;
  selected: boolean;
  favorite: boolean;
  /** The worker is in CPU mode and will refuse this model. */
  cpuBlocked: boolean;
  onSelect: () => void;
  onToggleFavorite: () => void;
}) {
  const trait = modelTrait(model);
  const usage = modelUsage(model);
  const lic = licenseFor(model.id, model.arch);
  const displayName = model.shortName ?? model.name;

  return (
    <div
      className={cn(
        "group relative flex h-[76px] flex-col rounded-xl border px-3 py-2 transition-colors",
        cpuBlocked
          ? "border-white/[0.04] bg-white/[0.01] opacity-50"
          : selected
            ? "border-indigo-400/40 bg-indigo-500/[0.08]"
            : "border-white/[0.06] bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        disabled={cpuBlocked}
        className="flex min-w-0 flex-1 flex-col justify-between pr-7 text-left focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 disabled:cursor-not-allowed rounded-lg"
        aria-pressed={selected}
        aria-label={
          cpuBlocked
            ? `${model.name} ${model.arch} — not available in CPU mode`
            : `${model.name} ${model.arch} ${trait} ${usage}`
        }
      >
        <span className="min-w-0">
          <span
            className="block truncate text-sm font-semibold leading-5 text-foreground"
            title={model.name}
          >
            {displayName}
          </span>
          <span className="block truncate text-xs leading-4 text-muted-foreground">
            {model.arch}
          </span>
        </span>
        <span className="flex min-w-0 items-center gap-1 overflow-hidden">
          <span className="shrink-0 rounded-md bg-white/[0.06] px-1.5 py-px text-[11px] font-medium text-foreground/80">
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
          {cpuBlocked && (
            <span
              title="This model is too slow to run on a CPU. The worker will refuse it."
              className="shrink-0 rounded-md bg-amber-500/15 px-1.5 py-px text-[10px] font-semibold text-amber-400"
            >
              No CPU
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

      {/* Trait explainer. A real Tooltip (not `title=`) because the native
          tooltip is unreachable by keyboard and disappears on touch. */}
      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={`About the ${trait} trait`}
              className="absolute right-8 top-1.5 rounded-md p-1 text-muted-foreground opacity-0 transition-opacity focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 group-hover:opacity-100 hover:text-foreground"
            >
              <Info className="h-3.5 w-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-[260px] text-xs">
            <p className="font-semibold">{trait}</p>
            <p className="mt-1 leading-relaxed">{traitDescription(trait)}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

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

/** One filter option with its facet count, e.g. "Stable stems   13". */
function FacetOption({ label, count }: { label: string; count: number }) {
  return (
    <span className="flex items-center justify-between gap-4">
      <span>{label}</span>
      <span className="text-xs tabular-nums text-muted-foreground">{count}</span>
    </span>
  );
}