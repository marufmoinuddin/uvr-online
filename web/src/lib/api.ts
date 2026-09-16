import type {
  CreateJobRequest,
  CreateJobResponse,
  EnsembleRequest,
  Job,
  Model,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
    : "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function getModels(): Promise<Model[]> {
  return request<Model[]>("/api/models");
}

export async function createJob(
  file: File,
  req: CreateJobRequest,
  onProgress?: (pct: number) => void,
): Promise<CreateJobResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("scene", req.scene);
  form.append("model_id", req.modelId);
  form.append("options", JSON.stringify(req.options));

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/jobs`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress((e.loaded / e.total) * 100);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as CreateJobResponse);
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(form);
  });
}

export async function getJob(id: string): Promise<Job> {
  return request<Job>(`/api/jobs/${id}`);
}

export async function reuseJob(id: string, modelId: string): Promise<CreateJobResponse> {
  return request<CreateJobResponse>(`/api/jobs/${id}/reuse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ modelId }),
  });
}

export async function createEnsemble(req: EnsembleRequest): Promise<CreateJobResponse> {
  return request<CreateJobResponse>("/api/ensemble", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export function downloadUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${API_URL}${path}`;
}

/**
 * Live job updates. Polling is the primary mechanism (robust, no proxy
 * requirements); WebSocket is used as an enhancement when reachable.
 *
 * `onSync` receives the worker's full job list on every poll so the caller
 * can reconcile (and prune jobs the worker no longer knows about).
 * Returns an unsubscribe function.
 */
export function subscribeJobs(
  onJob: (job: Job) => void,
  onSync?: (jobs: Job[]) => void,
  onOpen?: () => void,
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;

  const pollTimer = setInterval(async () => {
    try {
      const jobs = await request<Job[]>("/api/jobs");
      if (onSync) onSync(jobs);
      else jobs.forEach(onJob);
    } catch {
      /* ignore */
    }
  }, 2000);

  try {
    ws = new WebSocket(`${WS_URL}/ws/jobs`);
    ws.onopen = () => onOpen?.();
    ws.onmessage = (ev) => {
      try {
        const job = JSON.parse(ev.data as string) as Job;
        onJob(job);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onerror = () => {
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  } catch {
    /* polling covers it */
  }

  return () => {
    closed = true;
    clearInterval(pollTimer);
    try {
      ws?.close();
    } catch {
      /* ignore */
    }
  };
}