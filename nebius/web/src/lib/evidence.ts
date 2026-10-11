/** Does a result still describe the current venue? Compared by simulation hash, which covers
 * geometry and headcounts but not names or annotations (locks and provenance never make
 * results stale). */

export type Freshness =
  /** results are for the venue as it is now, before the AI's changes */
  | "current_before"
  /** results are for the venue as it is now, with the AI's changes accepted */
  | "current_after"
  /** the venue changed since: results describe an earlier version */
  | "stale"
  /** nothing tested yet */
  | "none";

export function planFreshness(input: { currentHash: string | null | undefined; testedHash: string | null | undefined; fixedHash?: string | null }): Freshness {
  const { currentHash, testedHash, fixedHash } = input;
  if (!testedHash || !currentHash) return "none";
  if (currentHash === testedHash) return "current_before";
  if (fixedHash && currentHash === fixedHash) return "current_after";
  return "stale";
}
