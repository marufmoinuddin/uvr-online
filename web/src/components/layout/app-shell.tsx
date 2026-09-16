"use client";

import * as React from "react";
import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useBackendHealth } from "@/hooks/useBackendHealth";
import { useStore } from "@/lib/store";

export function AppShell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  useBackendHealth();
  const backendOnline = useStore((s) => s.backendOnline);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex min-h-[100dvh] flex-col">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:border focus:border-white/10 focus:bg-[#12141A] focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-lg"
        >
          Skip to content
        </a>
        <Header />
        {backendOnline === false && (
          <div
            className="fixed inset-x-0 top-[81px] z-30 border-b border-red-500/30 bg-red-500/10 px-4 py-2 text-center text-sm font-medium text-red-300 backdrop-blur-sm"
            role="alert"
          >
            The processing service is offline. Jobs cannot be submitted until it comes back.
          </div>
        )}
        <main
          id="main-content"
          className={cn(
            "u-bg-gradient relative flex-1 pt-[81px]",
            className,
          )}
        >
          <div className="u-noise-overlay" aria-hidden />
          <div className="relative">{children}</div>
        </main>
        <Footer />
      </div>
    </TooltipProvider>
  );
}