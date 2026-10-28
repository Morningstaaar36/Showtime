/** Rewind the worst moment: the record the API keeps and the rows of
 * the small comparison table. Every number comes from a branch's own run; lower is better in
 * every column. */
import { t } from "@/i18n";
import { basisLabel } from "@/lib/evidence";
import { fmtDuration, fmtInt, fmtNum } from "@/lib/format";

export interface RewindNumbers {
  evac_time_95_s?: number | null;
  evac_is_estimate?: boolean;
  people_inside?: number | null;
  peak_density_ppm2?: number | null;
  time_above_danger_s?: number | null;
}

export type MetricKey = "evac_time_95_s" | "people_inside" | "peak_density_ppm2" | "time_above_danger_s";
export const METRICS: MetricKey[] = ["evac_time_95_s", "people_inside", "peak_density_ppm2", "time_above_danger_s"];

interface RewindBranch {
  key: string;
  label: string;
  kind: "nothing" | "kept_fix" | "quick_action" | "custom";
  events: Record<string, unknown>[];
  run_id?: string | null;
  status?: string;
  basis?: string | null;
  error?: string | null;
  metrics?: RewindNumbers;
  vs_nothing?: Partial<Record<MetricKey, number | null>>;
  comparable?: boolean;
  better?: boolean;
}

export interface RewindRecord {
  id: string;
  session_id: string;
  project_id: string;
  status: "running" | "done" | "failed" | "unsupported" | "interrupted" | "cancelled";
  message: string | null;
  attack: { attack_id: string; title: string } | null;
  moment: { at_s: number; why: string; source: string; run_id?: string } | null;
  source_run_id: string | null;
  checkpoint_run_id: string | null;
  tier: number | null;
  done: number;
  total: number;
  branches: RewindBranch[];
  best: string | null;
  notes: string[];
}

/** What the panel says while the rewind runs. */
export function rewindProgress(r: RewindRecord): string {
  if (r.status !== "running") return "";
  if (!r.checkpoint_run_id || r.total === 0) return t("rewind.saving", { time: fmtDuration(r.moment?.at_s ?? null) });
  return t("rewind.progress", { done: r.done, total: r.total });
}

/** One value as the table shows it. */
export function metricText(key: MetricKey, m: RewindNumbers | undefined): string {
  if (!m) return "–";
  const v = m[key];
  if (key === "evac_time_95_s") {
    if (v == null) return t("rewind.not_out");
    return m.evac_is_estimate ? t("rewind.estimate", { d: fmtDuration(v) }) : fmtDuration(v);
  }
  if (key === "peak_density_ppm2") return v == null ? "–" : t("rewind.per_m2", { n: fmtNum(v, 1) });
  if (key === "people_inside") return fmtInt(v);
  return fmtDuration(v);
}

/** A change against "do nothing", signed, in the column's unit; "same" when nothing moved. */
export function deltaText(key: MetricKey, d: number | null | undefined): string {
  if (d == null) return "";
  const small = key === "peak_density_ppm2" ? Math.abs(d) < 0.05 : Math.abs(d) < 0.5;
  if (small) return t("rewind.same");
  const sign = d > 0 ? "+" : "−";
  const abs = Math.abs(d);
  if (key === "peak_density_ppm2") return `${sign}${fmtNum(abs, 1)}`;
  if (key === "people_inside") return `${sign}${fmtInt(abs)}`;
  return `${sign}${fmtDuration(abs)}`;
}

/** Lower is better: "better" | "worse" | "same" for a change against "do nothing". */
export function deltaTone(key: MetricKey, d: number | null | undefined): "better" | "worse" | "same" {
  if (d == null || deltaText(key, d) === t("rewind.same")) return "same";
  return d < 0 ? "better" : "worse";
}

interface RewindRow {
  key: string;
  label: string;
  kind: RewindBranch["kind"];
  best: boolean;
  nothing: boolean;
  /** why there are no numbers (not possible, failed, waiting), else null */
  problem: string | null;
  cells: { key: MetricKey; value: string; delta: string; tone: "better" | "worse" | "same" }[];
  evidence: string;
}

/** The comparison table: "do nothing" first, then each response in the order tried. */
export function rewindRows(r: RewindRecord): RewindRow[] {
  return r.branches.map((b) => {
    const nothing = b.key === "nothing";
    const finished = b.status === "ok" || b.status === "partial";
    const problem = b.status === "not_possible" ? t("rewind.not_possible", { reason: b.error ?? "" })
      : finished ? null
      : b.status === "queued" || b.status === "running" || !b.status ? t("rewind.waiting")
      : t("rewind.branch_failed", { reason: b.error || b.status || "" });
    return {
      key: b.key,
      label: nothing ? t("rewind.nothing") : b.label,
      kind: b.kind,
      best: r.best === b.key,
      nothing,
      problem,
      cells: METRICS.map((k) => ({
        key: k,
        value: finished ? metricText(k, b.metrics) : "–",
        delta: !nothing && finished ? deltaText(k, b.vs_nothing?.[k]) : "",
        tone: !nothing && finished ? deltaTone(k, b.vs_nothing?.[k]) : "same",
      })),
      evidence: finished ? basisLabel(b.basis, r.tier ?? undefined) : "",
    };
  });
}

/** The one-line conclusion under the table. */
export function bestLine(r: RewindRecord): string {
  if (r.status !== "done") return "";
  const best = r.branches.find((b) => b.key === r.best);
  return best ? t("rewind.best_line", { label: best.label }) : t("rewind.no_best");
}
