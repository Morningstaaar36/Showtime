/** Does a result still describe the current complete plan? Use the backend plan_hash,
 * covering geometry, saved actions, constraints, and environmental inputs. */

import { t } from "@/i18n";

export type Freshness =
  /** results are for the venue as it is now, before the AI's changes */
  | "current_before"
  /** results are for the venue as it is now, with the AI's changes accepted */
  | "current_after"
  /** the venue changed since: results describe an earlier version */
  | "stale"
  /** nothing tested yet */
  | "none";

/** What kind of evidence a run result is (backend `RunResult.basis`, from `result_basis`). */
export type ResultBasis = "instant_estimate" | "partial_simulation" | "completed_simulation" | "preview" | "unknown";

/** What a session's results show, separate from whether the session finished. */
export type EvaluationStatus = "confirmed" | "partially_confirmed" | "unconfirmed" | "failed";

/** `summary.evaluation` of a red-team session. `*_basis` and `*_run_id` describe the
 * confirmation runs attempted; `fallback_run_ids` names the instant estimates shown in place
 * of runs that didn't finish. */
export interface Evaluation {
  status: EvaluationStatus;
  before_basis: ResultBasis | null;
  after_basis: ResultBasis | null;
  reasons: string[];
  before_run_id?: string | null;
  after_run_id?: string | null;
  baseline_basis?: ResultBasis | null;
  fallback_run_ids?: Partial<Record<"baseline" | "before" | "after", string>>;
}

export interface CostBucket {
  calls: number;
  tokens_in: number;
  tokens_out: number;
  usd: number;
}

/** `summary.cost` of a red-team session: measured model and compute usage. */
export interface CostRecord {
  usd_total: number;
  tokens_in: number;
  tokens_out: number;
  calls: number;
  by_role: Record<string, CostBucket>;
  by_model: Record<string, CostBucket>;
  llm_cache_hits: number;
  sims: { instant_estimates: number; quick_sims: number; full_sims: number; failed: number; cache_hits: number; sim_seconds: number };
  wall_s: number;
}

const BASES: ReadonlySet<string> = new Set(["instant_estimate", "partial_simulation", "completed_simulation", "preview", "unknown"]);

export function isResultBasis(value: unknown): value is ResultBasis {
  return typeof value === "string" && BASES.has(value);
}

/** A run as the stream (`run_finished`) or the runs API reports it. */
interface RunLike {
  status?: string;
  provider?: string;
  engine?: string;
  tier?: number;
  is_break?: boolean;
  basis?: string | null;
  fallback_for?: string | null;
  extensions?: { fallback_for?: unknown } | null;
}

/** Plain outcome of a run. Uses the backend basis when present; older results without it
 * fall back to the status/engine rules. Only a finished simulation can "hold". */
export function runOutcome(run: RunLike | undefined): "preview" | "unknown" | "break" | "holds" {
  if (!run) return "unknown";
  if (isResultBasis(run.basis)) {
    if (run.basis === "preview") return "preview";
    if (run.basis === "completed_simulation") return run.is_break ? "break" : "holds";
    if (run.basis === "partial_simulation") return run.is_break ? "break" : "unknown";
    return "unknown"; // instant estimates and unfinished runs never pass or fail a plan
  }
  if (run.provider === "fake" || run.engine === "fake") return "preview";
  if ((run.status !== "ok" && run.status !== "partial") || !run.engine || run.tier === 1) return "unknown";
  if (run.is_break) return "break";
  return run.status === "partial" ? "unknown" : "holds";
}

/** Organizer words for a result basis. Pass the tier to tell a time-capped full simulation
 * from a quick one, and a quick run that reached the end from a full one. */
export function basisLabel(basis: string | null | undefined, tier?: number): string {
  if (!isResultBasis(basis)) return t("evidence.basis.unknown");
  if (basis === "partial_simulation" && tier === 3) return t("evidence.basis.partial_simulation_full");
  if (basis === "completed_simulation" && tier === 2) return t("evidence.basis.completed_simulation_quick");
  return t(`evidence.basis.${basis}`);
}

/** Label for a run, including an instant estimate shown in place of a failed simulation. */
export function runBasisLabel(run: RunLike | null | undefined): string {
  if (!run) return t("evidence.basis.unknown");
  if (run.fallback_for || run.extensions?.fallback_for) return t("evidence.basis.fallback");
  return basisLabel(run.basis, run.tier);
}

/** Organizer words for a session's evaluation status; sessions saved before evaluations
 * existed are "Not confirmed", never confirmed. */
export function evaluationLabel(evaluation: { status?: string | null } | null | undefined): string {
  const status = evaluation?.status;
  if (status === "confirmed" || status === "partially_confirmed" || status === "failed") return t(`evidence.evaluation.${status}`);
  return t("evidence.evaluation.unconfirmed");
}

export function planFreshness(input: { currentHash: string | null | undefined; testedHash: string | null | undefined; fixedHash?: string | null }): Freshness {
  const { currentHash, testedHash, fixedHash } = input;
  if (!testedHash || !currentHash) return "none";
  if (currentHash === testedHash) return "current_before";
  if (fixedHash && currentHash === fixedHash) return "current_after";
  return "stale";
}

/** One line that says why the verdict badge reads as it does ("Not confirmed" because…), from the
 * session evaluation's status and what its confirmation runs were based on. */
export function evaluationReason(evaluation: Evaluation | null | undefined): string {
  const status = evaluation?.status ?? "unconfirmed";
  if (status === "confirmed") return t("evidence.why.confirmed");
  if (status === "partially_confirmed") return t("evidence.why.partially_confirmed");
  if (status === "failed") return t("evidence.why.failed");
  // not confirmed: say what the numbers rest on instead
  const basis = evaluation?.after_basis ?? evaluation?.before_basis ?? null;
  // the banner shows tested plans only: no evaluation means a test from before it was recorded
  if (!evaluation) return t("evidence.why.legacy");
  if (basis === "preview") return t("evidence.why.preview");
  if (basis === "instant_estimate") return t("evidence.why.estimate");
  if (basis === "partial_simulation") return t("evidence.why.quick");
  if (basis === "unknown") return t("evidence.why.unfinished");
  return t("evidence.why.no_final");
}
