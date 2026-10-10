import type { RepairOp } from "@/components/scenes/repair-picker";

/**
 * Fetch the repair operations the worker can actually perform.
 *
 * Deliberately fetched rather than bundled: the filter chains live in
 * `api/repair.py`, and a copy in the frontend would drift until a user picked
 * an operation the worker then rejected.
 */
export async function fetchRepairOps(): Promise<RepairOp[]> {
  const res = await fetch("/api/repair/ops");
  if (!res.ok) {
    throw new Error(`worker responded ${res.status}`);
  }
  const body = (await res.json()) as { ops?: RepairOp[] };
  return body.ops ?? [];
}