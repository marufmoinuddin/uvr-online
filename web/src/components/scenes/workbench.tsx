"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { WorkbenchSidebar } from "@/components/layout/workbench-sidebar";
import { FileUploadCard } from "@/components/scenes/file-upload-card";
import { ModelSelectionCard } from "@/components/scenes/model-selection-card";
import { ResultsCard } from "@/components/scenes/results-card";
import { RepairPicker, type RepairOp } from "@/components/scenes/repair-picker";
import { fetchRepairOps } from "@/lib/repair-api";
import {
  InstrumentPicker,
  type InstrumentTarget,
} from "@/components/scenes/instrument-picker";
import { fetchInstruments } from "@/lib/instruments-api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SCENES, getScene, modelsForScene } from "@/lib/models";
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
  const isRepair = meta.repair === true;
  const isInstrument = meta.instrument === true;
  const selectModel = useStore((s) => s.selectModel);
  const selectedModelId = useStore((s) => s.selectedModelId);
  const catalog = useStore((s) => s.modelCatalog);
  const router = useRouter();

  // Which instrument stem this job should keep. Null until chosen, which is
  // what keeps the Process button disabled for this scene.
  const [extractTarget, setExtractTarget] = React.useState<string | null>(null);

  // Instruments come from the worker, not a hardcoded list, so the scene can
  // never offer a stem no model in the catalogue actually produces.
  const [instrumentList, setInstrumentList] = React.useState<InstrumentTarget[]>([]);
  const [instrumentsLoading, setInstrumentsLoading] = React.useState(false);
  const [instrumentsError, setInstrumentsError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!isInstrument) return;
    let cancelled = false;
    setInstrumentsLoading(true);
    setInstrumentsError(null);
    fetchInstruments()
      .then((list) => {
        if (!cancelled) setInstrumentList(list);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setInstrumentsError(
            e instanceof Error
              ? `Could not load the instrument list: ${e.message}`
              : "Could not load the instrument list.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setInstrumentsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isInstrument]);

  // Switching scenes must not leak a stale target into an unrelated job.
  React.useEffect(() => {
    if (!isInstrument) setExtractTarget(null);
  }, [isInstrument, scene]);

  // Preselect a model when arriving via ?model= (e.g. "Try" from Explore).
  React.useEffect(() => {
    if (initialModelId) selectModel(initialModelId);
  }, [initialModelId, selectModel]);

  // Ensure the selected model is valid for the current scene; otherwise fall
  // back to the scene's default model (fixes "Selected: —").
  // In an instrument scene the grid narrows to models that emit the chosen
  // stem, so the default model has to be validated against that narrowed list.
  const sceneModels = React.useMemo(
    () => modelsForScene(scene, catalog, isInstrument ? extractTarget : null),
    [scene, catalog, isInstrument, extractTarget],
  );
  React.useEffect(() => {
    if (
      sceneModels.length > 0 &&
      !sceneModels.some((m) => m.id === selectedModelId)
    ) {
      // Prefer the scene default, but never select something the picker does
      // not actually offer (e.g. a model the backend cannot load) — that
      // would auto-select a model which then fails on Process.
      const preferred =
        meta.defaultModelId && sceneModels.some((m) => m.id === meta.defaultModelId)
          ? meta.defaultModelId
          : sceneModels[0].id;
      selectModel(preferred);
    }
  }, [sceneModels, selectedModelId, selectModel, meta.defaultModelId]);

  // Repair operations come from the worker, not a hardcoded list, so a filter
  // chain ffmpeg rejects surfaces here instead of after an upload.
  const [repairOpList, setRepairOpList] = React.useState<RepairOp[]>([]);
  const [repairOps, setRepairOps] = React.useState<string[]>([]);
  const [repairOpsLoading, setRepairOpsLoading] = React.useState(false);
  const [repairOpsError, setRepairOpsError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!isRepair) return;
    let cancelled = false;
    setRepairOpsLoading(true);
    setRepairOpsError(null);
    fetchRepairOps()
      .then((ops) => {
        if (cancelled) return;
        setRepairOpList(ops);
        // Preselect the two that cover most damaged recordings, so the scene
        // is usable immediately rather than starting on an empty selection.
        setRepairOps((prev) =>
          prev.length ? prev : ops.filter((o) => ["declick", "denoise"].includes(o.key)).map((o) => o.key),
        );
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setRepairOpsError(
            e instanceof Error
              ? `Could not load the repair list: ${e.message}`
              : "Could not load the repair list.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setRepairOpsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isRepair]);

  const toggleRepairOp = React.useCallback((key: string) => {
    setRepairOps((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-[1400px] items-start gap-6 px-4 py-6 sm:px-8">
      <WorkbenchSidebar
        active={scene}
        className="sticky top-[97px] hidden max-h-[calc(100dvh-7rem)] shrink-0 overflow-y-auto lg:flex"
      />

      <section id="workbench-main" className="min-w-0 flex-1" aria-label="Workbench">
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
          <FileUploadCard
            scene={scene}
            repairOps={isRepair ? repairOps : undefined}
            onRepairOpsChange={isRepair ? setRepairOps : undefined}
            extractTarget={isInstrument ? extractTarget : undefined}
          />
          {/* Instrument extraction still runs a model, so its picker sits
              ABOVE the grid rather than replacing it. */}
          {isInstrument && (
            <InstrumentPicker
              targets={instrumentList}
              selected={extractTarget}
              onSelect={setExtractTarget}
              catalog={catalog}
              loading={instrumentsLoading}
              error={instrumentsError}
            />
          )}
          {/* Repair runs ffmpeg DSP, not a model, so the picker replaces the
              model grid entirely rather than sitting alongside it. */}
          {isRepair ? (
            <RepairPicker
              ops={repairOpList}
              selected={repairOps}
              onToggle={toggleRepairOp}
              loading={repairOpsLoading}
              error={repairOpsError}
            />
          ) : (
            <ModelSelectionCard
      scene={scene}
      instrumentTarget={isInstrument ? extractTarget : null}
    />
          )}
          <ResultsCard />
        </div>
      </section>
    </div>
  );
}