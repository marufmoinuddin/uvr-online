"use client";

import * as React from "react";
import { Check, ShieldCheck, HardDrive, Infinity as InfinityIcon, Scale } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { MODEL_CATALOG } from "@/lib/models";
import { licenseFor, LICENSES, type LicenseKind } from "@/lib/licenses";

const INCLUDED = [
  {
    icon: InfinityIcon,
    title: "No credits, no metering",
    body: "Unlimited runs of unlimited length. There is no account, no quota and nothing to top up.",
  },
  {
    icon: HardDrive,
    title: "Runs on your own machine",
    body: "Separation happens on your GPU through the local worker. Audio never leaves your computer.",
  },
  {
    icon: ShieldCheck,
    title: "No paid services behind it",
    body: "This app makes zero calls to commercial separation APIs. Every model is an open checkpoint you host yourself.",
  },
  {
    icon: Scale,
    title: "Honest about licenses",
    body: "Each model's real upstream license is shown in the model list — including the ones that are NOT permissive.",
  },
];

const INCLUDED_FEATURES = [
  "All 9 tools — vocal remover, karaoke, 4-stem, denoise, acapella…",
  "Every model in the catalog, with no gating",
  "Ensemble engine (2–6 model fusion, 6 modes)",
  "Lossless WAV / FLAC / MP3 320 export",
  "Batch uploads (up to 5 files at once)",
  "Unlimited history and re-processing",
];

/** Count models by license kind so the table reflects the real catalog. */
function licenseBreakdown() {
  const counts = new Map<LicenseKind, number>();
  for (const m of MODEL_CATALOG) {
    const kind = licenseFor(m.id, m.arch).kind;
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return counts;
}

export function FreeOpenSection({ className }: { className?: string }) {
  const breakdown = React.useMemo(licenseBreakdown, []);

  return (
    <section className={cn("mx-auto max-w-container px-4 py-16", className)}>
      <div className="mx-auto mb-12 max-w-2xl text-center">
        <Badge variant="success" className="mb-4">
          No paid tiers
        </Badge>
        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Everything is free, because everything is local
        </h2>
        <p className="mt-3 text-muted-foreground">
          There is no subscription, no credit system and no paid API. The only
          cost is your own electricity.
        </p>
      </div>

      {/* What you get */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {INCLUDED.map((item, i) => (
          <div
            key={item.title}
            className={cn(
              "glass-card flex flex-col gap-3 p-6 animate-slide-up",
              `animation-delay-${(i + 1) * 100}`,
            )}
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
              <item.icon className="h-5 w-5" />
            </span>
            <h3 className="text-sm font-semibold">{item.title}</h3>
            <p className="text-sm text-muted-foreground">{item.body}</p>
          </div>
        ))}
      </div>

      {/* Included features */}
      <div className="glass-card mt-6 p-6">
        <h3 className="text-sm font-semibold">Included with every run</h3>
        <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {INCLUDED_FEATURES.map((f) => (
            <li key={f} className="flex items-start gap-2 text-sm text-muted-foreground">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
              <span>{f}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Model license breakdown */}
      <div className="glass-card mt-6 p-6">
        <h3 className="text-sm font-semibold">Model licenses in this catalog</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          “Available on Hugging Face” is not the same as “free to use”. These are
          the licenses actually declared upstream, verified against each model
          repository.
        </p>
        <div
          className="mt-4 overflow-x-auto focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 rounded-lg"
          role="region"
          aria-label="Model license breakdown"
          tabIndex={0}
        >
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-4 font-medium">License</th>
                <th className="py-2 pr-4 font-medium">Models</th>
                <th className="py-2 pr-4 font-medium">Commercial use</th>
                <th className="py-2 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {Array.from(breakdown.entries())
                .sort((a, b) => b[1] - a[1])
                .map(([kind, count]) => {
                  const info = LICENSES[kind];
                  return (
                    <tr key={kind} className="border-b border-border/50">
                      <td className="py-2.5 pr-4">
                        <Badge variant={info.commercialOk ? "success" : "warning"}>
                          {info.label}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{count}</td>
                      <td className="py-2.5 pr-4">
                        {info.commercialOk ? (
                          <span className="text-emerald-500">Yes</span>
                        ) : (
                          <span className="text-amber-500">No / unclear</span>
                        )}
                      </td>
                      <td className="py-2.5 text-xs text-muted-foreground">
                        {info.source}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}