import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Job, Model, SceneKey } from "./types";
import { MODEL_CATALOG } from "./models";

/**
 * Local app state. There is no account, no tier and no credit balance —
 * everything runs on your own machine with no limits.
 */
interface Store {
  jobs: Job[];
  activeJobId: string | null;
  modelCatalog: Model[];
  selectedModelId: string;
  scene: SceneKey;
  theme: "light" | "dark" | "system";
  favorites: string[];
  /** Whether the local GPU worker is reachable (null = not checked yet). */
  backendOnline: boolean | null;

  setModelCatalog: (models: Model[]) => void;
  selectModel: (id: string) => void;
  setScene: (scene: SceneKey) => void;
  setTheme: (theme: "light" | "dark" | "system") => void;
  toggleFavorite: (id: string) => void;
  setBackendOnline: (online: boolean) => void;
  addJob: (job: Job) => void;
  upsertJob: (job: Job) => void;
  syncJobs: (jobs: Job[]) => void;
  removeJob: (id: string) => void;
  setActiveJob: (id: string | null) => void;
  clearJobs: () => void;
}

export const useStore = create<Store>()(
  persist(
    (set, get) => ({
      jobs: [],
      activeJobId: null,
      modelCatalog: MODEL_CATALOG,
      selectedModelId: MODEL_CATALOG[0].id,
      scene: "vocal-remover",
      theme: "system",
      favorites: [],
      backendOnline: null,

      setModelCatalog: (modelCatalog) => set({ modelCatalog }),
      selectModel: (selectedModelId) => set({ selectedModelId }),
      setScene: (scene) => set({ scene }),
      setTheme: (theme) => set({ theme }),
      setBackendOnline: (backendOnline) => set({ backendOnline }),
      toggleFavorite: (id) =>
        set({
          favorites: get().favorites.includes(id)
            ? get().favorites.filter((f) => f !== id)
            : [...get().favorites, id],
        }),

      addJob: (job) => set({ jobs: [job, ...get().jobs] }),
      upsertJob: (job) =>
        set({
          jobs: get().jobs.some((j) => j.id === job.id)
            ? get().jobs.map((j) => (j.id === job.id ? { ...j, ...job } : j))
            : [job, ...get().jobs],
        }),
      /**
       * Reconcile with the worker's authoritative job list.
       *
       * The worker keeps jobs in memory, so after it restarts its list is
       * empty while localStorage still holds the old ones (whose stems then
       * 404). Drop anything the server no longer knows about — but keep jobs
       * submitted in the last 15s so a just-created job isn't pruned while the
       * follow-up poll is still in flight.
       */
      syncJobs: (incoming) => {
        const serverIds = new Set(incoming.map((j) => j.id));
        const GRACE_MS = 15_000;
        const kept = get().jobs.filter(
          (j) => serverIds.has(j.id) || Date.now() - j.createdAt < GRACE_MS,
        );
        const byId = new Map(kept.map((j) => [j.id, j]));
        for (const j of incoming) byId.set(j.id, { ...byId.get(j.id), ...j });
        const merged = Array.from(byId.values()).sort(
          (a, b) => b.createdAt - a.createdAt,
        );
        set({ jobs: merged });
      },
      removeJob: (id) => set({ jobs: get().jobs.filter((j) => j.id !== id) }),
      setActiveJob: (activeJobId) => set({ activeJobId }),
      clearJobs: () => set({ jobs: [] }),
    }),
    {
      name: "uvr-local-store",
      partialize: (s) => ({
        jobs: s.jobs,
        selectedModelId: s.selectedModelId,
        scene: s.scene,
        theme: s.theme,
        favorites: s.favorites,
      }),
    },
  ),
);