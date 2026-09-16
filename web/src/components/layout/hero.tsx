"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, ShieldCheck, Zap, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const TRUST = [
  { icon: ShieldCheck, label: "Private — runs on your GPU" },
  { icon: Zap, label: "Up to 10× faster than realtime" },
  { icon: Cpu, label: "80+ models, one click" },
];

export function Hero({ className }: { className?: string }) {
  return (
    <section
      className={cn(
        "relative mx-auto flex max-w-container flex-col items-center px-4 pb-16 pt-16 text-center sm:pt-20",
        className,
      )}
    >
      <div className="animate-slide-up">
        <span className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-4 py-1.5 text-xs font-medium text-primary">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary" />
          Now with BS-RoFormer &amp; Mel-Band models
        </span>
      </div>

      <h1
        className="mt-6 max-w-4xl animate-slide-up text-4xl font-bold leading-tight tracking-tight sm:text-5xl lg:text-6xl animation-delay-100"
      >
        Separate vocals &amp; instruments{" "}
        <span className="bg-gradient-to-r from-indigo-600 via-purple-500 to-pink-500 bg-clip-text text-transparent dark:from-indigo-300 dark:via-purple-300 dark:to-pink-300">
          on your own GPU
        </span>
      </h1>

      <p className="mt-6 max-w-2xl animate-slide-up text-lg text-muted-foreground animation-delay-200">
        The professional vocal remover, karaoke maker and stem splitter — running
        locally with zero uploads. Powered by the same open-source models the
        pros use.
      </p>

      <div className="mt-8 flex animate-slide-up flex-col items-center gap-3 sm:flex-row animation-delay-300">
        <Button size="lg" asChild>
          <Link href="/tools/vocal-remover">
            Remove vocals free
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
        <Button size="lg" variant="outline" asChild>
          <Link href="/explore">Explore 80+ models</Link>
        </Button>
      </div>

      <div className="mt-10 flex animate-slide-up flex-wrap items-center justify-center gap-x-8 gap-y-3 animation-delay-400">
        {TRUST.map((t) => (
          <span
            key={t.label}
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <t.icon className="h-4 w-4 text-primary" />
            {t.label}
          </span>
        ))}
      </div>
    </section>
  );
}