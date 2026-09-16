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
          className="flex items-center gap-2 font-semibold focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 rounded-lg"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-primary-glow">
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
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Toggle theme">
                {theme === "dark" ? (
                  <Moon className="h-4 w-4" />
                ) : theme === "light" ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Monitor className="h-4 w-4" />
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Theme</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setTheme("light")}>
                <Sun className="h-4 w-4" /> Light
                {theme === "light" && <Check className="ml-auto h-4 w-4" />}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setTheme("dark")}>
                <Moon className="h-4 w-4" /> Dark
                {theme === "dark" && <Check className="ml-auto h-4 w-4" />}
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setTheme("system")}>
                <Monitor className="h-4 w-4" /> System
                {theme === "system" && <Check className="ml-auto h-4 w-4" />}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="hidden items-center gap-2 sm:flex">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="outline" size="sm" className="cursor-default">
                    <span className="flex items-center gap-1.5 text-xs">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      Unlimited · local
                    </span>
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  Runs entirely on your own GPU — no accounts, no credits, no limits.
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