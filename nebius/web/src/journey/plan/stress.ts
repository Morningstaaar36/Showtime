/** Stress test at scale (SANDBOX_SCOPE idea 4): the record the API keeps, the live counter
 * and the per-plan summary. Numbers come from each run; failures stay listed. */
import { t } from "@/i18n";
import { basisLabel } from "@/lib/evidence";
import type { RewindNumbers } from "./rewind";

export interface StressRow {
  attack_id: string;
  attack: string;
  variant: string;
  fix_id: string | null;
  seed: number;
  run_id: string | null;
  status: string;
  basis: string | null;
  metrics: RewindNumbers;
  breaks: boolean | null;
  error: string | null;
}

export interface StressRecord {
  id: string;
  project_id: string;
  status: "running" | "done" | "failed" | "interrupted" | "cancelled";
  tier: number;
  total: number;
  done: number;
  failed: number;
  seeds: number[];
  rows: StressRow[];
  notes: string[];
  parallel: number;
  message: string | null;
}

/** "47 of 60 done" (and how many failed), the share done for the progress bar. */
export function stressCounter(r: StressRecord): { text: string; failed: string; pct: number } {
  const key = r.status === "running" ? "stress.counter" : "stress.finished";
  return {
    text: t(key, { done: r.done, total: r.total }),
    failed: r.failed ? t("stress.failed_n", { n: r.failed }) : "",
    pct: r.total ? Math.round((100 * r.done) / r.total) : 0,
  };
}

export type Outcome = "breaks" | "holds" | "failed" | "waiting";

export function rowOutcome(row: StressRow): Outcome {
  if (row.status === "ok" || row.status === "partial") return row.breaks ? "breaks" : "holds";
  if (row.status === "queued" || row.status === "running") return "waiting";
  return "failed";
}

export function rowEvidence(row: StressRow, tier: number): string {
  return row.status === "ok" || row.status === "partial" ? basisLabel(row.basis, tier) : "";
}

/** Per plan (as it is, or with one kept change): in how many finished runs it broke. */
export function stressSummary(r: StressRecord): { variant: string; runs: number; breaks: number }[] {
  const out = new Map<string, { variant: string; runs: number; breaks: number }>();
  for (const row of r.rows) {
    const o = rowOutcome(row);
    if (o !== "breaks" && o !== "holds") continue;
    const v = out.get(row.variant) ?? { variant: row.variant, runs: 0, breaks: 0 };
    v.runs += 1;
    if (o === "breaks") v.breaks += 1;
    out.set(row.variant, v);
  }
  return [...out.values()];
}

export const failures = (r: StressRecord) => r.rows.filter((row) => rowOutcome(row) === "failed");
