import type { Metadata } from "next";
import { ModelMatrix } from "@/components/explore/model-matrix";
import { ComparisonPlayer } from "@/components/explore/comparison-player";
import { EnsembleBuilder } from "@/components/explore/ensemble-builder";
import { ModelManager } from "@/components/models/model-manager";
import { MODEL_CATALOG } from "@/lib/models";

export const metadata: Metadata = {
  title: "Explore models",
  description:
    "Browse 80+ open-source separation models — BS-RoFormer, Mel-Band RoFormer, MDX23C, HTDemucs and more.",
};

export default function ExplorePage({
  searchParams,
}: {
  searchParams: { compare?: string };
}) {
  const compareIds = (searchParams.compare ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const compareModels = MODEL_CATALOG.filter((m) =>
    compareIds.includes(m.id),
  );

  return (
    <div className="mx-auto max-w-container space-y-10 px-4 py-10">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Explore models
          </h1>
          <p className="mt-2 max-w-xl text-muted-foreground">
            Filter by architecture, target and license. Compare up to 4 models
            side-by-side, or fuse them with the ensemble builder.
          </p>
        </div>
        <EnsembleBuilder />
      </div>
      <ModelManager />
      <ModelMatrix models={MODEL_CATALOG} />
      <ComparisonPlayer entries={[]} models={compareModels} />
    </div>
  );
}