/** Plain-language verdict on a run, from computed numbers only. */
import type { RunResult } from "@/api/types";
import { t } from "@/i18n";
import { runBasisLabel } from "@/lib/evidence";
import { fmtDuration, fmtInt, fmtNum } from "@/lib/format";

export type VerdictLevel = "holds" | "at_risk" | "fails" | "unknown";

export interface Verdict {
  level: VerdictLevel;
  headline: string;
  sentences: string[];
  reasons: string[];
}

/** The rules a run is judged by: the server's settings, so the page and the server agree. */
export interface Thresholds {
  warn: number;
  danger: number;
  dangerMinS: number;
  /** people still inside at the end that are noise: the larger of the two */
  stuckPeople: number;
  stuckFraction: number;
  /** a quick simulation fails only if fewer than this share got out before it stopped */
  quickMinOut: number;
  /** seconds above the warning density that mark a plan "at risk" */
  atRiskS: number;
}

/** Used only until the settings arrive: the documented defaults (docs/ASSUMPTIONS.md). */
const DEFAULTS: Thresholds = { warn: 3.5, danger: 5, dangerMinS: 5, stuckPeople: 5, stuckFraction: 0.005, quickMinOut: 0.5, atRiskS: 30 };

/** Thresholds from the effective settings (`GET /settings`). */
export function thresholdsOf(eff: Record<string, unknown>): Thresholds {
  const num = (key: string, fallback: number) => (typeof eff[key] === "number" ? (eff[key] as number) : fallback);
  return {
    warn: num("density_warn_ppm2", DEFAULTS.warn),
    danger: num("density_danger_ppm2", DEFAULTS.danger),
    dangerMinS: num("danger_min_duration_s", DEFAULTS.dangerMinS),
    stuckPeople: num("stuck_tolerance_people", DEFAULTS.stuckPeople),
    stuckFraction: num("stuck_tolerance_fraction", DEFAULTS.stuckFraction),
    quickMinOut: num("quick_min_out_fraction", DEFAULTS.quickMinOut),
    atRiskS: num("at_risk_warning_s", DEFAULTS.atRiskS),
  };
}

/** People still inside at the end that count as noise, not a failure (as on the server). */
export const stuckTolerance = (total: number, th: Thresholds) => Math.max(th.stuckPeople, Math.round(total * th.stuckFraction));

/** What a result is, from the backend's evidence basis (older results: from tier and status).
 * Never says "confirmed": a plan is confirmed by its evaluation, not by one run. */
export function tierLabel(r: RunResult | null | undefined): string {
  if (!r) return "";
  if (r.provider === "fake" || r.engine === "fake") return t("verdict.tier_preview");
  const run = t("verdict.run_ref", { id: r.run_id.slice(2, 8) });
  if (r.basis) return r.tier === 1 ? runBasisLabel(r) : `${runBasisLabel(r)} ${run}`;
  if (r.status !== "ok" && r.status !== "partial") return t("verdict.incomplete");
  if (r.status === "partial") return t("verdict.tier_partial");
  if (r.tier === 1) return t("verdict.tier_instant");
  if (r.tier === 2) return `${t("verdict.tier_quick")} ${run}`;
  return `${t("verdict.tier_full")} ${run}`;
}

const unknown = (headline: string): Verdict => ({ level: "unknown", headline, sentences: [], reasons: [] });

export function verdictOf(r: RunResult | null | undefined, th: Thresholds, exitLabel: (id: string) => string): Verdict {
  if (!r || !r.metrics) return unknown(t("verdict.not_tested"));
  if (r.provider === "fake" || r.engine === "fake") return unknown(t("verdict.preview"));
  if (r.status !== "ok" && r.status !== "partial") return unknown(t("verdict.incomplete"));
  const m = r.metrics;
  const reasons: string[] = [];
  const total = m.agents_total ?? 0;
  const notEvac = m.agents_not_evacuated ?? 0;
  const trapped = (m.extra as Record<string, number> | undefined)?.trapped ?? 0;
  const tol = stuckTolerance(total, th);
  const dangerS = m.time_above_danger_s ?? 0;
  const warnS = m.time_above_warning_s ?? 0;
  const peak = m.peak_density_ppm2 ?? 0;
  const top = r.hotspots?.[0];
  if (dangerS >= th.dangerMinS) reasons.push(t("verdict.r_danger", { danger: fmtNum(th.danger, 0), time: fmtDuration(dangerS) }));
  if (trapped > 0) reasons.push(t("verdict.r_trapped", { n: fmtInt(trapped) }));
  const frac = (m.extra as Record<string, number> | undefined)?.evacuated_fraction;
  if (notEvac > tol && r.tier === 2 && m.evac_time_p95_s == null) {
    // a quick simulation stops after its first minutes: people still walking then are not
    // trapped. As on the server (break_reasons), it fails only if too few got out
    if (frac != null && frac < th.quickMinOut) reasons.push(t("verdict.r_quick", { pct: Math.round(frac * 100), time: fmtDuration(r.sim_time_s ?? 0) }));
  } else if (notEvac > tol) reasons.push(t("verdict.r_inside", { n: fmtInt(notEvac) }));
  const level: VerdictLevel = reasons.length ? "fails" : r.status === "partial" ? "unknown" : peak >= th.warn || warnS > th.atRiskS ? "at_risk" : "holds";
  const sentences: string[] = [];
  if (m.evac_time_p95_s != null) {
    sentences.push(t("verdict.s_out", { n: fmtInt(total), time: fmtDuration(m.evac_time_p95_s) }));
  } else if (total) {
    sentences.push(frac != null ? t("verdict.s_some_out", { pct: Math.round(frac * 100), n: fmtInt(total) }) : t("verdict.s_not_all_out", { n: fmtInt(total) }));
  }
  if (top) {
    const ppm2 = fmtNum(top.peak_density_ppm2, 1);
    const peakText = top.near ? t("verdict.s_peak_near", { ppm2, near: exitLabel(top.near) }) : t("verdict.s_peak", { ppm2 });
    sentences.push(warnS > 0 ? t("verdict.s_peak_warn", { peak: peakText, time: fmtDuration(warnS) }) : `${peakText}.`);
  } else {
    sentences.push(t("verdict.s_calm", { warn: fmtNum(th.warn, 1) }));
  }
  const headline = t(`verdict.h_${level === "unknown" ? "incomplete" : level}`);
  return { level, headline, sentences, reasons };
}
