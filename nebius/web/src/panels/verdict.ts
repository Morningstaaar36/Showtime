/** Plain-language verdict on a run, from computed numbers only. */
import type { RunResult } from "@/api/types";
import { runBasisLabel } from "@/lib/evidence";
import { fmtDuration, fmtNum } from "@/lib/format";

export type VerdictLevel = "holds" | "at_risk" | "fails" | "unknown";

export interface Verdict {
  level: VerdictLevel;
  headline: string;
  sentences: string[];
  reasons: string[];
}

export interface Thresholds {
  warn: number;
  danger: number;
  dangerMinS: number;
}

/** What a result is, from the backend's evidence basis (older results: from tier and status).
 * Never says "confirmed": a plan is confirmed by its evaluation, not by one run. */
export function tierLabel(r: RunResult | null | undefined): string {
  if (!r) return "";
  if (r.provider === "fake" || r.engine === "fake") return "Preview only (no simulation)";
  const run = ` (run ${r.run_id.slice(2, 8)})`;
  if (r.basis) return r.tier === 1 ? runBasisLabel(r) : `${runBasisLabel(r)}${run}`;
  if (r.status !== "ok" && r.status !== "partial") return "Simulation did not complete";
  if (r.status === "partial") return "Partial simulation (stopped early)";
  if (r.tier === 1) return "Instant estimate (formula)";
  if (r.tier === 2) return `Quick simulation (first minutes only)${run}`;
  return `Full simulation${run}`;
}

export function verdictOf(r: RunResult | null | undefined, th: Thresholds, exitLabel: (id: string) => string): Verdict {
  if (!r || !r.metrics) return { level: "unknown", headline: "Not tested yet", sentences: [], reasons: [] };
  if (r.provider === "fake" || r.engine === "fake") return { level: "unknown", headline: "Preview only — not simulated", sentences: [], reasons: [] };
  if (r.status !== "ok" && r.status !== "partial") return { level: "unknown", headline: "Simulation did not complete", sentences: [], reasons: [] };
  const m = r.metrics;
  const reasons: string[] = [];
  const total = m.agents_total ?? 0;
  const notEvac = m.agents_not_evacuated ?? 0;
  const trapped = (m.extra as Record<string, number> | undefined)?.trapped ?? 0;
  const tol = Math.max(5, Math.round(total * 0.005));
  const dangerS = m.time_above_danger_s ?? 0;
  const warnS = m.time_above_warning_s ?? 0;
  const peak = m.peak_density_ppm2 ?? 0;
  const top = r.hotspots?.[0];
  if (dangerS >= th.dangerMinS) reasons.push(`density above ${fmtNum(th.danger, 0)} people per m² for ${fmtDuration(dangerS)}`);
  if (trapped > 0) reasons.push(`${trapped} people trapped with no open exit`);
  const frac = (m.extra as Record<string, number> | undefined)?.evacuated_fraction;
  if (notEvac > tol && r.tier === 2 && m.evac_time_p95_s == null) {
    // a quick simulation stops after its first minutes: people still walking then are not
    // trapped. As on the server (break_reasons), it fails only if fewer than half got out
    if (frac != null && frac < 0.5) reasons.push(`only ${Math.round(frac * 100)}% out when the quick simulation stopped at ${fmtDuration(r.sim_time_s ?? 0)}`);
  } else if (notEvac > tol) reasons.push(`${notEvac.toLocaleString()} people still inside at the end`);
  const level: VerdictLevel = reasons.length ? "fails" : r.status === "partial" ? "unknown" : peak >= th.warn || warnS > 30 ? "at_risk" : "holds";
  const sentences: string[] = [];
  if (m.evac_time_p95_s != null) {
    sentences.push(`95% of ${total.toLocaleString()} people are out in ${fmtDuration(m.evac_time_p95_s)}.`);
  } else if (total) {
    sentences.push(`${frac != null ? `${Math.round(frac * 100)}%` : "Not all"} of ${total.toLocaleString()} people got out within the simulated time.`);
  }
  if (top) {
    const where = top.near ? ` near ${exitLabel(top.near)}` : "";
    sentences.push(`The crowd peaks at ${fmtNum(top.peak_density_ppm2, 1)} people per m²${where}` +
      (warnS > 0 ? `, above the warning level for ${fmtDuration(warnS)}.` : "."));
  } else {
    sentences.push(`Density stays below ${fmtNum(th.warn, 1)} people per m² everywhere.`);
  }
  const headline = level === "fails" ? "This plan fails" : level === "at_risk" ? "This plan is at risk" : level === "unknown" ? "Test incomplete" : "This plan holds";
  return { level, headline, sentences, reasons };
}
