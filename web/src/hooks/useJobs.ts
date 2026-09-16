"use client";

import { useEffect } from "react";
import { useStore } from "@/lib/store";
import { subscribeJobs } from "@/lib/api";

export function useJobs() {
  const jobs = useStore((s) => s.jobs);
  const upsertJob = useStore((s) => s.upsertJob);
  const syncJobs = useStore((s) => s.syncJobs);

  useEffect(() => {
    const unsubscribe = subscribeJobs(upsertJob, syncJobs);
    return unsubscribe;
  }, [upsertJob, syncJobs]);

  return { jobs };
}