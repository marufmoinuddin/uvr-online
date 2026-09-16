"use client";

import * as React from "react";
import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function AppShell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex min-h-[100dvh] flex-col">
        <Header />
        <main
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