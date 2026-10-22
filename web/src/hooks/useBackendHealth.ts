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
  const setDevice = useStore((s) => s.setDevice);
  const setCpuCapability = useStore((s) => s.setCpuCapability);

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
          device?: string;
          cpuModels?: string[];
          cpuLimits?: {
            maxSeconds: number;
            maxBytes: number;
            timeoutSeconds: number;
          } | null;
        };
        // The proxy returns 200 with `error: "worker unreachable"` when the
        // worker is down, so a truthy `error` means offline.
        online = res.ok && !data.error;
        // Capture which device the worker is actually using. The health
        // endpoint has always reported this and nothing ever read it, so a
        // CPU-only install looked identical to a GPU one.
        if (online && data.device) {
          setDevice(data.device.startsWith("cuda") ? "cuda" : "cpu");
          // The worker publishes which models it will accept on a CPU, plus
          // the CPU-mode ceilings. The picker needs both to avoid offering a
          // model that the worker will refuse.
          setCpuCapability(data.cpuModels ?? [], data.cpuLimits ?? null);
        }
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
  }, [setBackendOnline, setDevice, setCpuCapability]);
}