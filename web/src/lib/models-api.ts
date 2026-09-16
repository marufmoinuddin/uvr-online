import type { Model } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export type DownloadStatus =
  | "idle"
  | "downloading"
  | "verifying"
  | "installed"
  | "error";

export interface DownloadState {
  status: DownloadStatus;
  error: string | null;
  receivedBytes: number;
  totalBytes: number;
  percent: number;
  speedBps: number;
  etaSec: number | null;
  retries: number;
  currentFile: string | null;
}

/** A catalog model plus its live local cache state. */
export interface ManagedModel extends Model {
  installed: boolean;
  installedVia?: "store" | "msst";
  path: string;
  sizeBytes: number;
  downloadable: boolean;
  repo: string | null;
  revision: string | null;
  download: DownloadState;
}

export interface StorageInfo {
  storePath: string;
  installedCount: number;
  catalogCount: number;
  totalBytes: number;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(body || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const listManagedModels = () => req<ManagedModel[]>("/api/models");

export const getModelStorage = () => req<StorageInfo>("/api/models/storage");

export const startModelDownload = (id: string) =>
  req<{ status: string }>(`/api/models/${id}/download`, { method: "POST" });

export const cancelModelDownload = (id: string) =>
  req<{ cancelled: boolean }>(`/api/models/${id}/cancel`, { method: "POST" });

export const deleteModel = (id: string) =>
  req<{ id: string; freedBytes: number; installed: boolean }>(
    `/api/models/${id}`,
    { method: "DELETE" },
  );

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), u.length - 1);
  return `${(bytes / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${u[i]}`;
}

export function formatSpeed(bps: number): string {
  return bps > 0 ? `${formatBytes(bps)}/s` : "—";
}

export function formatEta(sec: number | null): string {
  if (sec == null || !Number.isFinite(sec)) return "—";
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  return `${m}m ${Math.round(sec % 60)}s`;
}
