"use client";

import { useEffect } from "react";
import { useStore } from "@/lib/store";
import { getModels } from "@/lib/api";

export function useModels() {
  const modelCatalog = useStore((s) => s.modelCatalog);
  const setModelCatalog = useStore((s) => s.setModelCatalog);

  useEffect(() => {
    let cancelled = false;
    getModels()
      .then((models) => {
        if (!cancelled && models.length > 0) setModelCatalog(models);
      })
      .catch(() => {
        /* keep the seeded catalog on failure */
      });
    return () => {
      cancelled = true;
    };
  }, [setModelCatalog]);

  return { models: modelCatalog };
}