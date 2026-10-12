/** Does a result still describe the current complete plan? Use the backend plan_hash,
 * covering geometry, saved actions, constraints, and environmental inputs. */

export type Freshness =
  /** results are for the venue as it is now, before the AI's changes */
  | "current_before"
  /** results are for the venue as it is now, with the AI's changes accepted */
  | "current_after"
  /** the venue changed since: results describe an earlier version */
  | "stale"
  /** nothing tested yet */
  | "none";

export function runOutcome(run: { status?: string; provider?: string; engine?: string; tier?: number; is_break?: boolean } | undefined): "preview" | "unknown" | "break" | "holds" {
  if (!run) return "unknown";
  if (run.provider === "fake" || run.engine === "fake") return "preview";
  if ((run.status !== "ok" && run.status !== "partial") || !run.engine || run.tier === 1) return "unknown";
  if (run.is_break) return "break";
  return run.status === "partial" ? "unknown" : "holds";
}

export function planFreshness(input: { currentHash: string | null | undefined; testedHash: string | null | undefined; fixedHash?: string | null }): Freshness {
  const { currentHash, testedHash, fixedHash } = input;
  if (!testedHash || !currentHash) return "none";
  if (currentHash === testedHash) return "current_before";
  if (fixedHash && currentHash === fixedHash) return "current_after";
  return "stale";
}
