"use client";

import * as React from "react";
import Link from "next/link";
import { AudioWaveform } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function DesktopAppBanner({ className }: { className?: string }) {
  return (
    <section className={cn("mx-auto max-w-container px-4 py-16", className)}>
      <div className="glass-card relative overflow-hidden p-8 sm:p-12">
        <div className="u-bg-gradient absolute inset-0" aria-hidden />
        <div className="relative flex flex-col items-center gap-6 text-center sm:flex-row sm:text-left">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-primary-glow">
            <AudioWaveform className="h-8 w-8" />
          </div>
          <div className="flex-1">
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              Everything runs on your machine
            </h2>
            <p className="mt-2 max-w-xl text-muted-foreground">
              No uploads, no accounts, no usage caps. Drag in a track and get
              studio-clean stems back in minutes — all on your own GPU.
            </p>
          </div>
          <Button size="lg" className="shrink-0" asChild>
            <Link href="/tools/vocal-remover">
              <AudioWaveform className="h-5 w-5" />
              Start separating
            </Link>
          </Button>
        </div>
      </div>
    </section>
  );
}