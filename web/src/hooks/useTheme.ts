"use client";

import { useEffect } from "react";
import { useStore } from "@/lib/store";

/**
 * The app is DARK ONLY, matching uvrvocalremover.com (whose own theme toggle
 * does not actually switch).
 *
 * This is not a shortcut — light mode was reachable and visibly broken.
 * Component surfaces are hardcoded dark (`bg-[#0F1116]`, `bg-[#141721]`,
 * `bg-[#12141A]`) and borders use `border-white/10`, so on a light background
 * ~120 elements rendered white-on-white borders and dark-on-dark text. The
 * header toggle was therefore a promise the app could not keep.
 *
 * Supporting light means replacing every hardcoded surface with a token
 * (`bg-card`, `bg-surface`, `border-border`) and re-auditing contrast. Until
 * that migration is done, `dark` is forced rather than shipping a broken
 * theme. `theme`/`setTheme` stay in the store so re-enabling is a one-line
 * change here plus the surface migration.
 */
function resolveTheme(_theme: "light" | "dark" | "system"): "light" | "dark" {
  return "dark";
}

export function useTheme() {
  const theme = useStore((s) => s.theme);
  const setTheme = useStore((s) => s.setTheme);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.add("dark");
    root.style.colorScheme = "dark";
  }, [theme]);

  return { theme, setTheme, resolved: resolveTheme(theme) };
}