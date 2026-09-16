"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { ModelCard } from "@/components/ui/model-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ARCHITECTURES } from "@/lib/models";
import { licenseFor } from "@/lib/licenses";
import type { Model, ModelTarget } from "@/lib/types";

interface ModelMatrixProps {
  models: Model[];
  className?: string;
}

const TARGETS: (ModelTarget | "all")[] = [
  "all",
  "vocals",
  "instrumental",
  "dual",
  "4-stem",
];
const TIERS = ["all", "permissive", "non-commercial", "unlicensed"] as const;

export function ModelMatrix({ models, className }: ModelMatrixProps) {
  const router = useRouter();
  const [arch, setArch] = React.useState<string>("all");
  const [target, setTarget] = React.useState<ModelTarget | "all">("all");
  const [licenseFilter, setLicenseFilter] =
    React.useState<(typeof TIERS)[number]>("all");
  const [compareIds, setCompareIds] = React.useState<string[]>([]);

  const filtered = React.useMemo(
    () =>
      models.filter((m) => {
        const lic = licenseFor(m.id, m.arch);
        const licenseMatch =
          licenseFilter === "all" ||
          (licenseFilter === "permissive" && lic.commercialOk) ||
          (licenseFilter === "non-commercial" && lic.kind === "CC-BY-NC-4.0") ||
          (licenseFilter === "unlicensed" && lic.kind === "UNSPECIFIED");
        return (
          (arch === "all" || m.arch === arch) &&
          (target === "all" || m.target === target) &&
          licenseMatch
        );
      }),
    [models, arch, target, licenseFilter],
  );

  const toggleCompare = (id: string) => {
    setCompareIds((ids) =>
      ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id].slice(0, 4),
    );
  };

  const tryModel = (id: string) => {
    router.push(`/tools/model-picker?model=${id}`);
  };

  return (
    <div className={cn("space-y-6", className)}>
      {/* Filters */}
      <div className="glass-card flex flex-wrap items-center gap-3 p-4">
        <div className="flex flex-wrap gap-1.5">
          <FilterPill active={arch === "all"} onClick={() => setArch("all")}>
            All arch
          </FilterPill>
          {ARCHITECTURES.map((a) => (
            <FilterPill key={a} active={arch === a} onClick={() => setArch(a)}>
              {a}
            </FilterPill>
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {TARGETS.map((t) => (
            <FilterPill
              key={t}
              active={target === t}
              onClick={() => setTarget(t)}
            >
              {t === "all" ? "All targets" : t}
            </FilterPill>
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {TIERS.map((t) => (
            <FilterPill
              key={t}
              active={licenseFilter === t}
              onClick={() => setLicenseFilter(t)}
            >
              {t === "all" ? "All licenses" : t}
            </FilterPill>
          ))}
        </div>
        {compareIds.length > 0 && (
          <Button
            size="sm"
            variant="default"
            className="ml-auto"
            onClick={() =>
              router.push(`/explore?compare=${compareIds.join(",")}`)
            }
          >
            Compare {compareIds.length} model{compareIds.length > 1 ? "s" : ""}
          </Button>
        )}
      </div>

      {/* Grid */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {filtered.map((m) => (
          <ModelCard
            key={m.id}
            model={m}
            onTry={tryModel}
            onToggleCompare={toggleCompare}
            comparing={compareIds.includes(m.id)}
          />
        ))}
      </div>
      {filtered.length === 0 && (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No models match those filters.
        </p>
      )}
    </div>
  );
}

function FilterPill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
        active
          ? "border-primary bg-primary/10 text-primary"
          : "border-control-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}