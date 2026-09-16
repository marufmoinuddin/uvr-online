"use client";

import * as React from "react";
import { Apple, MonitorDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function DesktopAppBanner({ className }: { className?: string }) {
  return (
    <section className={cn("mx-auto max-w-container px-4 py-16", className)}>
      <div className="glass-card relative overflow-hidden p-8 sm:p-12">
        <div className="u-bg-gradient absolute inset-0" aria-hidden />
        <div className="relative flex flex-col items-center gap-6 text-center sm:flex-row sm:text-left">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-primary-glow">
            <MonitorDown className="h-8 w-8" />
          </div>
          <div className="flex-1">
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              Take it to the desktop
            </h2>
            <p className="mt-2 max-w-xl text-muted-foreground">
              The native macOS app adds drag-and-drop from Finder, batch folders
              and background processing — no browser tab required.
            </p>
          </div>
          <Button size="lg" className="shrink-0">
            <Apple className="h-5 w-5" />
            Download for macOS
          </Button>
        </div>
      </div>
    </section>
  );
}