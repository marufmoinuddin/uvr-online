"use client";

import { useEffect } from "react";
import { useStore } from "@/lib/store";

/**
 * Polls the worker health endpoint and keeps `backendOnline` in the store
 * up to date. Polls fast while the worker is down (so the banner appears
 * quickly) and backs off to a slower cadence once it's healthy.
 *
 * Mounted once in AppShell so every page reflects the same status.
 */
export function useBackendHealth() {
  const setBackendOnline = useStore((s) => s.setBackendOnline);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let delay = 2000;

    const check = async () => {
      let online = false;
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        const data = (await res.json().catch(() => ({}))) as {
          error?: string;
        };
        // The proxy returns 200 with `error: "worker unreachable"` when the
        // worker is down, so a truthy `error` means offline.
        online = res.ok && !data.error;
      } catch {
        online = false;
      }
      if (cancelled) return;
      setBackendOnline(online);
      // Use the same cadence both ways to avoid flooding the console with
      // ERR_CONNECTION_REFUSED when the worker is unreachable.
      delay = 5000;
      timer = setTimeout(check, delay);
    };

    check();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [setBackendOnline]);
}