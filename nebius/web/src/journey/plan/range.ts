/** How sure Your plan's numbers are: the sensitivity check the API keeps (the key run
 * with 20% fewer/more people and walking 15% slower/faster) and the check that simulates a
 * chosen subset of changes together. Numbers come from each run; failures stay listed. */
import { t } from "@/i18n";
import type { Evaluation } from "@/lib/evidence";
import { basisLabel } from "@/lib/evidence";
import { fmtDuration, fmtInt, fmtNum } from "@/lib/format";
import type { RewindNumbers } from "./rewind";

export interface Spread {
  min: number;
  max: number;
  median: number;
  n: number;
}

interface SensitivityMetrics {
  evac_time_p95_s: number | null;
  peak_density_ppm2: number | null;
  agents_not_evacuated: number | null;
  agents_total: number | null;
  time_above_danger_s: number | null;
}

export interface SensitivityItem {
  variant: string;
  label: string;
  people_factor: number | null;
  speed_factor: number | null;
  run_id: string | null;
  original: boolean;
  status: string;
  basis: string;
  tier: number | null;
  progress: number | null;
  metrics: SensitivityMetrics | null;
  error: string | null;
  included: boolean;
  breaks: string[];
}

export interface SensitivityRecord {
  session_id: string;
  available: boolean;
  reason: string | null;
  key: { side: "after" | "baseline" | "together"; run_id: string; label: string; tier: number; seed: number; attack_title: string | null } | null;
  status: "none" | "running" | "done";
  items: SensitivityItem[];
  done: number;
  total: number;
  range: { evac_time_p95_s: Spread | null; peak_density_ppm2: Spread | null; agents_not_evacuated: Spread | null } | null;
  holds_in_all: boolean | null;
  breaks_in: string[];
  notes: string[];
}

/** The check of a version that holds only some kept changes, simulated together. */
export interface TogetherCheck {
  status: "running" | "done" | "preview" | "failed";
  run_id: string;
  fix_ids: string[];
  attack_id: string | null;
  attack_title: string | null;
  tier: number;
  seed: number;
  started_at: string;
  basis?: string;
  evaluation: Evaluation | null;
  error: string | null;
  progress?: number | null;
}

export type Outcome = "breaks" | "holds" | "failed" | "waiting";

export function itemOutcome(item: SensitivityItem): Outcome {
  if (item.status === "queued" || item.status === "running") return "waiting";
  if (!item.included) return "failed";
  return item.breaks.length ? "breaks" : "holds";
}

/** The run's numbers in the shape the other plan tables print. */
export function itemNumbers(item: SensitivityItem): RewindNumbers | undefined {
  const m = item.metrics;
  if (!m) return undefined;
  return {
    evac_time_95_s: m.evac_time_p95_s,
    peak_density_ppm2: m.peak_density_ppm2,
    people_inside: m.agents_not_evacuated,
    time_above_danger_s: m.time_above_danger_s,
  };
}

export function itemEvidence(item: SensitivityItem): string {
  return item.included ? basisLabel(item.basis, item.tier ?? undefined) : "";
}

/** "2 min 10 s – 2 min 40 s" (one value when they agree; "–" with nothing to show). */
export function spreadText(s: Spread | null | undefined, kind: "time" | "density" | "people"): string {
  if (!s) return "–";
  const one = (v: number) => (kind === "time" ? fmtDuration(v) : kind === "density" ? fmtNum(v, 1) : fmtInt(v));
  const text = s.min === s.max ? one(s.min) : t("range.between", { min: one(s.min), max: one(s.max) });
  return kind === "density" ? t("range.per_m2", { n: text }) : text;
}

/** The headline: holds under every assumption, breaks under some (named), or still unknown. */
export function rangeVerdict(r: SensitivityRecord): { tone: "egress" | "danger" | "neutral"; text: string } {
  if (r.status === "running") return { tone: "neutral", text: t("range.running", { done: r.done, total: r.total }) };
  if (r.holds_in_all === true) return { tone: "egress", text: t("range.holds_all") };
  if (r.breaks_in.length) return { tone: "danger", text: t("range.breaks_in", { which: r.breaks_in.join(", ") }) };
  return { tone: "neutral", text: t("range.incomplete") };
}

/** Where a subset of changes stands: being simulated, simulated together, or why not. */
export function togetherText(c: TogetherCheck | null | undefined): { tone: "egress" | "caution" | "neutral"; text: string } | null {
  if (!c) return null;
  if (c.status === "running") return { tone: "neutral", text: t("together.running") };
  if (c.status === "done") {
    const confirmed = c.evaluation?.status === "confirmed";
    return { tone: "egress", text: t(confirmed ? "together.confirmed" : "together.done") };
  }
  if (c.status === "preview") return { tone: "caution", text: t("together.preview") };
  return { tone: "caution", text: t("together.failed", { error: c.error ?? "" }) };
}
