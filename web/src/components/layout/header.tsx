"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Moon, Sun, Monitor, AudioWaveform, X, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import { useTheme } from "@/hooks/useTheme";
import { useStore } from "@/lib/store";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/tools/vocal-remover", label: "Workbench" },
  { href: "/tools", label: "Tools" },
  { href: "/explore", label: "Explore models" },
  { href: "/pricing", label: "Pricing" },
  { href: "/faq", label: "FAQ" },
];

export function Header() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const menuToggleRef = React.useRef<HTMLButtonElement>(null);

  // Read ONCE at the top level. These were previously called inline inside a
  // ternary in the status badge, which is a conditional hook call — the exact
  // thing the rules-of-hooks lint error exists to catch.
  const backendOnline = useStore((s) => s.backendOnline);
  const device = useStore((s) => s.device);
  const onCpu = device === "cpu";
  const online = backendOnline !== false;

  // Close mobile menu on Escape and restore focus to the toggle.
  React.useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileOpen(false);
        menuToggleRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href;

  return (
    <header className="glass-surface fixed inset-x-0 top-0 z-40 border-b border-glass-border">
      <div className="mx-auto flex h-[81px] w-full items-center justify-between gap-4 px-4 sm:px-8">
        <Link
          href="/"
          aria-label="UVR Local"
          className="flex items-center gap-2 font-semibold focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 rounded-lg"
        >
          <span
            className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-primary-glow"
            aria-hidden
          >
            <AudioWaveform className="h-4 w-4" />
          </span>
          <span className="hidden sm:inline">UVR Local</span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-full px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50",
                isActive(item.href)
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-control hover:text-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {/* Theme switcher removed: the app is dark-only (see
              `hooks/useTheme.ts` — component surfaces are hardcoded dark, so
              light mode rendered dark-on-dark text and white-on-white
              borders). Offering Light/System here was a promise the UI could
              not keep. Re-add with the surface migration, not before. */}
          <div className="hidden items-center gap-2 sm:flex">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="outline" size="sm" className="cursor-default">
                    <span className="flex items-center gap-1.5 text-xs">
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          online
                            ? // Amber, not green: the worker is up, but model
                              // separation runs on the CPU and is far too slow
                              // to be practical. A green dot here would promise
                              // a speed the user will never get.
                              onCpu
                              ? "bg-amber-400"
                              : "bg-emerald-500"
                            : "bg-red-500",
                        )}
                      />
                      {onCpu ? "Unlimited · local · CPU" : "Unlimited · local"}
                    </span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  {onCpu
                    ? "No GPU is being used. Separation runs on the CPU: slower than the GPU (1.5–7× depending on the model), so CPU mode caps the clip length and refuses the heaviest models. The lighter models still finish a short clip in seconds."
                    : "Runs entirely on your own GPU — no accounts, no credits, no limits."}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <Button size="sm" asChild>
              <Link href="/tools/vocal-remover">Start separating</Link>
            </Button>
          </div>

          <Button
            ref={menuToggleRef}
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setMobileOpen((o) => !o)}
            aria-label="Toggle menu"
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
        </div>
      </div>

      {mobileOpen && (
        <nav
          className="border-t border-glass-border bg-background/95 px-4 py-3 md:hidden animate-fade-in"
          aria-label="Mobile"
        >
          <div className="flex flex-col gap-1">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive(item.href)
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-control",
                )}
              >
                {item.label}
              </Link>
            ))}
            <Button className="mt-2 w-full" asChild>
              <Link href="/tools/vocal-remover" onClick={() => setMobileOpen(false)}>
                Start separating
              </Link>
            </Button>
          </div>
        </nav>
      )}
    </header>
  );
}