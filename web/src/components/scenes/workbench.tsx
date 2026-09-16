"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { WorkbenchSidebar } from "@/components/layout/workbench-sidebar";
import { FileUploadCard } from "@/components/scenes/file-upload-card";
import { ModelSelectionCard } from "@/components/scenes/model-selection-card";
import { ResultsCard } from "@/components/scenes/results-card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SCENES, getScene } from "@/lib/models";
import { useStore } from "@/lib/store";
import type { SceneKey } from "@/lib/types";

/**
 * Workbench — the tools page layout mirroring the reference workbench.
 *
 * Structure (measured from uvrvocalremover.com/workbench/vocal-remover):
 *   [sidebar 232px] +24px+ [main flexible]
 *     title block (mb-3) → divider (h-px) → stacked cards (gap-5)
 *     Cards are FULL WIDTH and stack vertically:
 *       File Upload (p-5) → Model Selection (p-4) → Results (p-5)
 */
export function Workbench({
  scene,
  initialModelId,
}: {
  scene: SceneKey;
  initialModelId?: string;
}) {
  const meta = getScene(scene);
  const selectModel = useStore((s) => s.selectModel);
  const router = useRouter();

  // Preselect a model when arriving via ?model= (e.g. "Try" from Explore).
  React.useEffect(() => {
    if (initialModelId) selectModel(initialModelId);
  }, [initialModelId, selectModel]);

  return (
    <div className="mx-auto flex w-full max-w-[1400px] items-start gap-6 px-4 py-6 sm:px-8">
      <WorkbenchSidebar
        active={scene}
        className="sticky top-[97px] hidden max-h-[calc(100dvh-7rem)] shrink-0 overflow-y-auto lg:flex"
      />

      <main id="workbench-main" className="min-w-0 flex-1">
        {/* Mobile tool switcher — the sidebar is hidden below lg */}
        <div className="mb-4 lg:hidden">
          <Select value={scene} onValueChange={(v) => router.push(`/tools/${v}`)}>
            <SelectTrigger aria-label="Switch tool">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCENES.map((s) => (
                <SelectItem key={s.key} value={s.key}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Title */}
        <div className="mb-3">
          <h1 className="text-lg font-semibold leading-7 text-foreground">
            {meta.label}
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {meta.description}
          </p>
        </div>

        {/* Divider */}
        <div className="h-px w-full bg-white/10" aria-hidden />

        {/* Stacked cards (full width, vertical) */}
        <div className="mt-5 flex flex-col gap-5">
          <FileUploadCard scene={scene} />
          <ModelSelectionCard scene={scene} />
          <ResultsCard />
        </div>
      </main>
    </div>
  );
}