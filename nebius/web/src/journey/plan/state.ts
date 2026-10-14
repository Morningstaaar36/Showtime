/** Where the current plan stands against a session's test (the same rules as the backend's
 * `plan_state` for the handover checklist), from complete plan identities. */
import type { AppliedRecord } from "@/api/types";

export type PlanState =
  /** nothing tested yet */
  | "none"
  /** the tested plan, its kept fixes not accepted yet */
  | "pending"
  /** the tested plan; the session kept no fixes */
  | "tested"
  /** every kept fix accepted: the plan that was tested together */
  | "accepted"
  /** only some kept fixes accepted: tested one by one, not together */
  | "accepted_subset"
  /** changed since the test */
  | "stale";

export function planState(input: {
  currentHash: string | null | undefined;
  testedHash: string | null | undefined;
  kept: number;
  applied?: AppliedRecord[] | null;
  /** plan identity of the session's final run, for versions saved before `applied` existed */
  fixedHash?: string | null;
}): { state: PlanState; record: AppliedRecord | null } {
  const { currentHash, testedHash, kept, applied, fixedHash } = input;
  if (!currentHash || !testedHash) return { state: "none", record: null };
  if (currentHash === testedHash) return { state: kept > 0 ? "pending" : "tested", record: null };
  const record = [...(applied ?? [])].reverse().find((r) => r.plan_hash === currentHash) ?? null;
  if (record) return { state: record.tested_together ? "accepted" : "accepted_subset", record };
  if (fixedHash && currentHash === fixedHash) return { state: "accepted", record: null };
  return { state: "stale", record: null };
}
