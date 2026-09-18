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

/**
 * Turn an HTTP failure into a human-readable message. Prefers a message the
 * backend actually sent (FastAPI `detail` or our proxy `error`), falling back
 * to a plain-language explanation of the status code.
 */
export function friendlyApiError(status: number, body?: string): string {
  if (body) {
    try {
      const parsed = JSON.parse(body) as { error?: unknown; detail?: unknown };
      const msg =
        typeof parsed.error === "string"
          ? parsed.error
          : typeof parsed.detail === "string"
            ? parsed.detail
            : null;
      if (msg) return msg;
    } catch {
      /* not JSON — fall through to the status mapping */
    }
  }
  switch (status) {
    case 0:
      return "Network error — the processing service is unreachable.";
    case 400:
      return "The request was rejected. Check the file and settings, then try again.";
    case 404:
      return "That item no longer exists. Refresh and try again.";
    case 410:
      return "The original file is no longer available on disk.";
    case 413:
      return "That file is too large to process.";
    case 500:
      return "The processing service hit an internal error. Please try again.";
    case 502:
      return "The processing service is unreachable. Make sure the API container is running.";
    case 503:
      return "The processing service is busy. Try again in a moment.";
    default:
      return `Something went wrong (${status}). Please try again.`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(friendlyApiError(res.status, body));
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
        reject(new Error(friendlyApiError(xhr.status, xhr.responseText)));
      }
    };
    xhr.onerror = () => reject(new Error(friendlyApiError(0)));
    xhr.send(form);
  });
}

export async function cancelJob(id: string): Promise<{ id: string; cancelled: boolean }> {
  return request<{ id: string; cancelled: boolean }>(`/api/jobs/${id}/cancel`, {
    method: "POST",
  });
}

export async function clearJobs(): Promise<{ cleared: number }> {
  return request<{ cleared: number }>("/api/jobs", { method: "DELETE" });
}

export async function deleteJob(id: string): Promise<{ id: string; deleted: boolean }> {
  return request<{ id: string; deleted: boolean }>(`/api/jobs/${id}`, {
    method: "DELETE",
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
 * `onSync` receives the worker's full job list on every sync so the caller
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
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let delay = 2000;
  let wsConnected = false;
  /** Re-sync cadence while the socket is live (see schedulePoll). */
  const RECONCILE_MS = 30_000;

  const sync = async () => {
    const jobs = await request<Job[]>("/api/jobs");
    if (onSync) onSync(jobs);
    else jobs.forEach(onJob);
  };

  const schedulePoll = () => {
    if (closed) return;
    // The socket pushes every job change in real time, so while it is up we
    // only reconcile on a slow cadence rather than every 2s. That pass is what
    // prunes jobs deleted in another tab, or jobs the worker forgot when it
    // restarted: the socket only ever adds/merges a job, it never reports that
    // one is gone.
    pollTimer = setTimeout(
      async () => {
        try {
          await sync();
          delay = 2000; // healthy — resume normal cadence
        } catch {
          // Worker unreachable — back off so we don't hammer it.
          delay = Math.min(delay * 2, 30_000);
        }
        schedulePoll();
      },
      wsConnected ? RECONCILE_MS : delay,
    );
  };
  schedulePoll();

  try {
    ws = new WebSocket(`${WS_URL}/ws/jobs`);
    ws.onopen = () => {
      wsConnected = true;
      onOpen?.();
      // A (re)connect can follow a worker restart (its in-memory jobs are gone)
      // or a delete in another tab, so reconcile once straight away.
      void sync().catch(() => {});
    };
    ws.onmessage = (ev) => {
      try {
        const job = JSON.parse(ev.data as string) as Job;
        onJob(job);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onerror = () => {
      wsConnected = false;
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => {
      wsConnected = false;
    };
  } catch {
    /* polling covers it */
  }

  return () => {
    closed = true;
    if (pollTimer) clearTimeout(pollTimer);
    try {
      ws?.close();
    } catch {
      /* ignore */
    }
  };
}