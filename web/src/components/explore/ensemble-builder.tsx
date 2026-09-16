"use client";

import * as React from "react";
import { Plus, Trash2, GitMerge, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ModelCombobox } from "@/components/ui/combobox";
import { ENSEMBLE_MODES, defaultPlan, normalizeWeights, validatePlan, type EnsembleMember, type EnsemblePlan } from "@/lib/ensemble";
import { useStore } from "@/lib/store";
import { createEnsemble } from "@/lib/api";
import type { EnsembleMode } from "@/lib/types";

/**
 * Ensemble Builder drawer — pick models, set weights, pick a fusion mode.
 * These are the presets the commercial site sells; here they run locally.
 */
export function EnsembleBuilder({ className }: { className?: string }) {
  const models = useStore((s) => s.modelCatalog);
  const addJob = useStore((s) => s.addJob);
  const [open, setOpen] = React.useState(false);
  const [plan, setPlan] = React.useState<EnsemblePlan>(defaultPlan());
  const [running, setRunning] = React.useState(false);

  const addMember = (modelId: string) => {
    const model = models.find((m) => m.id === modelId);
    if (!model || plan.members.some((m) => m.modelId === modelId)) return;
    setPlan((p) => ({
      ...p,
      members: [
        ...p.members,
        { jobId: "", modelId, modelName: model.name, weight: 1 },
      ],
    }));
  };

  const removeMember = (modelId: string) => {
    setPlan((p) => ({
      ...p,
      members: p.members.filter((m) => m.modelId !== modelId),
    }));
  };

  const setWeight = (modelId: string, weight: number) => {
    setPlan((p) => ({
      ...p,
      members: p.members.map((m) =>
        m.modelId === modelId ? { ...m, weight } : m,
      ),
    }));
  };

  const run = async () => {
    const error = validatePlan(plan);
    if (error) {
      alert(error);
      return;
    }
    setRunning(true);
    try {
      const res = await createEnsemble({
        jobIds: plan.members.map((m) => m.jobId).filter(Boolean),
        mode: plan.mode,
        weights: normalizeWeights(plan.members),
      });
      addJob({
        id: res.jobId,
        status: "queued",
        scene: "model-picker",
        modelId: `ensemble:${plan.mode}`,
        fileName: `Ensemble (${plan.members.length} models)`,
        progress: 0,
        stage: "queued",
        etaSec: res.etaSec,
        createdAt: Date.now(),
      });
      setOpen(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Ensemble failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className={className}>
          <GitMerge className="h-4 w-4" />
          Ensemble builder
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Ensemble builder</DialogTitle>
          <DialogDescription>
            Combine 2–6 models for cleaner separation. Weights are normalized
            automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Add a model</Label>
            <ModelCombobox
              models={models.filter(
                (m) => !plan.members.some((x) => x.modelId === m.id),
              )}
              value=""
              onValueChange={addMember}
              placeholder="Search models to add…"
            />
          </div>

          <div className="space-y-2">
            <Label>Fusion mode</Label>
            <Select
              value={plan.mode}
              onValueChange={(v) =>
                setPlan((p) => ({ ...p, mode: v as EnsembleMode }))
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ENSEMBLE_MODES.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {ENSEMBLE_MODES.find((m) => m.id === plan.mode)?.description}
            </p>
          </div>

          <div className="space-y-3">
            <Label>Members ({plan.members.length})</Label>
            {plan.members.length === 0 && (
              <p className="rounded-lg border border-dashed border-control-border p-4 text-center text-xs text-muted-foreground">
                Add at least 2 models to build an ensemble.
              </p>
            )}
            {plan.members.map((m) => (
              <div
                key={m.modelId}
                className="flex items-center gap-3 rounded-lg border border-control-border bg-control p-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{m.modelName}</p>
                  <p className="text-xs text-muted-foreground">
                    weight {m.weight.toFixed(2)}
                  </p>
                </div>
                <Slider
                  className="w-32"
                  min={0.1}
                  max={3}
                  step={0.1}
                  value={[m.weight]}
                  onValueChange={([v]) => setWeight(m.modelId, v)}
                  aria-label={`Weight for ${m.modelName}`}
                />
                <Badge variant="secondary">
                  {(m.weight / (plan.members.reduce((a, x) => a + x.weight, 0) || 1)).toFixed(2)}
                </Badge>
                <button
                  type="button"
                  onClick={() => removeMember(m.modelId)}
                  aria-label={`Remove ${m.modelName}`}
                  className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={run} disabled={running}>
            {running ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Run ensemble
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}