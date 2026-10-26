/** Your plan › Overview: the verdict as a picture (traffic-light ring and one headline), four key
 * numbers with a picture each, before vs after the fixes, the worst moment replaying in 3D, and
 * one obvious next step. The AI's prose stays one click away. */
import { AlarmClock, CircleAlert, Clock3, Gauge, Info, ShieldCheck, Sparkles, Swords, Users, Wrench } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router";
import type { Countdown, RunResult } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { t } from "@/i18n";
import { type Evaluation, evaluationLabel, evaluationReason } from "@/lib/evidence";
import { fmtDuration, fmtHM, fmtInt, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Thresholds, VerdictLevel } from "@/panels/verdict";
import { stoodInLine } from "./stoodIn";
import { evacValue } from "./fixes";
import { DeltaChip, DensityScale, LEVEL_TONE, Sparkline, TargetBar, VerdictRing } from "./visuals";

const EVAL_TONE = { confirmed: "egress", partially_confirmed: "caution", failed: "danger", unconfirmed: "neutral" } as const;

export interface SessionMetrics {
  evac_time_p95_s?: number | null;
  evac_time_estimate_s?: number | null;
  peak_density_ppm2?: number | null;
  time_above_danger_s?: number | null;
  agents_not_evacuated?: number | null;
  agents_total?: number | null;
}

export interface OverviewProps {
  level: VerdictLevel;
  headline: string;
  evaluation: Evaluation | null | undefined;
  /** the worst attack's title, in organizer words (null: everyone leaving normally) */
  worst: string | null;
  /** fixes included in the numbers */
  fixes: number;
  reasons: string[];
  /** the red team's round in three numbers */
  score: { attacks: number; breaks: number; fixes: number };
  run: RunResult | null;
  basis: string;
  countdown: Countdown | null | undefined;
  countdownBasis: string;
  th: Thresholds;
  /** planning target for "everyone out" (Showtime's default when no hazard time is known) */
  targetS: number;
  /** before (worst attack, no fixes) and after (with the kept fixes) */
  before: SessionMetrics | null | undefined;
  after: SessionMetrics | null | undefined;
  /** people still inside over the verdict run */
  insideSeries: number[];
  hero: React.ReactNode;
  next: React.ReactNode;
  /** the AI's own words (judge text, evaluation reasons, recommendations) */
  summary: { judge: string | null; reasons: string[]; recommendations: string[] };
  /** the real case this venue rebuilds (a compact card above the verdict), if any */
  realCase?: React.ReactNode;
  /** how many sandbox runs and AI-written scripts the test had, and how to open them */
  sandboxes?: { runs: number; scripts: number; onOpen: () => void };
  /** agents whose part built-in rules played because the model didn't answer (agent -> why) */
  stoodIn?: Record<string, string>;
}

function Tile({ icon, tone, label, value, unit, visual, foot, testId }: {
  icon: React.ReactNode; tone: string; label: string; value: React.ReactNode; unit?: string; visual: React.ReactNode; foot: string; testId?: string;
}) {
  return (
    <li data-testid={testId} className="flex min-w-0 flex-col gap-2 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <span className={cn("grid size-8 shrink-0 place-items-center rounded-full [&_svg]:size-4", tone)}>{icon}</span>
        <p className="min-w-0 text-sm font-medium leading-tight text-muted">{label}</p>
      </div>
      <p className="text-2xl font-bold leading-none tabular">{value}{unit && <span className="ml-1 text-sm font-medium text-muted">{unit}</span>}</p>
      <div className="mt-auto min-h-8">{visual}</div>
      <p className="truncate text-2xs text-muted" title={foot}>{foot}</p>
    </li>
  );
}

function countdownValue(c: Countdown | null | undefined): { text: string; tone: "egress" | "danger" | "caution" | "neutral" } {
  if (!c) return { text: t("yourplan.cd_unknown"), tone: "neutral" };
  if (c.status === "ok") return { text: c.t_latest_iso ? fmtHM(c.t_latest_iso) : fmtDuration(c.t_latest_s), tone: "caution" };
  if (c.status === "too_late") return { text: t("plan.cd_too_late"), tone: "danger" };
  if (c.status === "no_hazard") return { text: t("plan.cd_no_hazard"), tone: "egress" };
  return { text: t("yourplan.cd_unknown"), tone: "neutral" };
}

/** What the latest safe start allows for: people reacting, then evacuating with the safety margin. */
function NeedsBar({ countdown: c }: { countdown: Countdown | null | undefined }) {
  const pre = num(c?.pre_movement_s);
  const rset = num(c?.rset_s);
  if (pre == null || rset == null) return null;
  const sf = num(c?.safety_factor) ?? 1;
  const total = pre + rset * sf;
  return (
    <div className="space-y-1" role="img" aria-label={t("plan.needs", { d: fmtDuration(total) })}>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-surface-3">
        <span className="h-full bg-line" style={{ width: `${(pre / total) * 100}%` }} />
        <span className="h-full bg-sky" style={{ width: `${((rset * sf) / total) * 100}%` }} />
      </div>
      <p className="flex justify-between gap-2 text-2xs text-muted tabular">
        <span>{t("plan.react", { d: fmtDuration(pre) })}</span><span className="font-semibold text-ink">{t("plan.needs", { d: fmtDuration(total) })}</span>
      </p>
    </div>
  );
}

/** Before → after, one metric per row, as two bars on the same scale. */
function CompareRow({ label, icon, before, after, fmt, lowerBetter = true, estimate }: {
  label: string; icon: React.ReactNode; before: number | null; after: number | null; fmt: (v: number | null) => string; lowerBetter?: boolean;
  /** which side is an estimate (extrapolated, not measured): no percentage is shown then */
  estimate?: { before: boolean; after: boolean };
}) {
  const est = estimate?.before || estimate?.after;
  // the row's "Estimate" badge says why; "~" marks the estimated side, as on the fix cards
  const side = (v: number | null, approx?: boolean) => (approx && v != null ? `~${fmt(v)}` : fmt(v));
  const top = Math.max(before ?? 0, after ?? 0, 1e-6);
  const bar = (v: number | null, cls: string) => (
    <div className="h-2.5 flex-1 rounded-full bg-surface-3">
      <div className={cn("h-full rounded-full transition-[width] duration-700", v == null ? "w-full bg-[repeating-linear-gradient(45deg,var(--line)_0_6px,transparent_6px_10px)]" : cls)}
           style={v == null ? undefined : { width: `${Math.max(2, (v / top) * 100)}%` }} />
    </div>
  );
  return (
    <li className="grid grid-cols-[minmax(0,10.5rem)_1fr_auto] items-center gap-x-3 gap-y-1 py-2 max-sm:grid-cols-[1fr_auto]">
      <span className="flex min-w-0 items-center gap-2 text-sm font-medium max-sm:col-span-1"><span className="text-muted [&_svg]:size-4" aria-hidden>{icon}</span><span className="truncate">{label}</span></span>
      <span className="space-y-1 max-sm:col-span-2 max-sm:row-start-2">
        <span className="flex items-center gap-2"><span className="w-10 text-2xs text-muted">{t("yourplan.before")}</span>{bar(before, "bg-line")}<span className="w-24 whitespace-nowrap text-right text-xs tabular">{side(before, estimate?.before)}</span></span>
        <span className="flex items-center gap-2"><span className="w-10 text-2xs font-semibold text-signal">{t("yourplan.after")}</span>{bar(after, "bg-signal")}<span className="w-24 whitespace-nowrap text-right text-xs font-semibold tabular">{side(after, estimate?.after)}</span></span>
      </span>
      <span className="justify-self-end max-sm:row-start-1 max-sm:col-start-2">
        {est ? <span className="rounded-full bg-surface-2 px-2 py-0.5 text-2xs text-muted" title={t("plan.estimate_hint")}>{t("plan.estimate")}</span>
          : <DeltaChip before={before} after={after} lowerBetter={lowerBetter} />}
      </span>
    </li>
  );
}

const num = (v: number | null | undefined) => (typeof v === "number" && Number.isFinite(v) ? v : null);

export function Overview(p: OverviewProps) {
  const m = p.run?.metrics;
  const extra = (m?.extra ?? {}) as Record<string, number | null | undefined>;
  const status = p.evaluation?.status ?? "unconfirmed";
  const evac = num(m?.evac_time_p95_s) ?? num(extra.rset_extrapolated_s);
  const inside = num(m?.agents_not_evacuated);
  const total = num(m?.agents_total);
  const peak = num(m?.peak_density_ppm2);
  const cd = countdownValue(p.countdown);
  const tone = LEVEL_TONE[p.level];
  const b = p.before, a = p.after;
  const evacOf = (x: SessionMetrics | null | undefined) => num(x?.evac_time_p95_s) ?? num(x?.evac_time_estimate_s);
  // an estimate (95% not reached, extrapolated from the exit flow) is never shown as measured
  const isEstimate = (x: SessionMetrics | null | undefined) => num(x?.evac_time_p95_s) == null && num(x?.evac_time_estimate_s) != null;
  const hasCompare = !!b && !!a && p.fixes > 0;
  const hasSummary = !!p.summary.judge || p.summary.reasons.length > 0 || p.summary.recommendations.length > 0;

  const stood = stoodInLine(p.stoodIn);
  return (
    <div className="space-y-4">
      {p.realCase}
      <section aria-label={t("yourplan.verdict")} className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className={cn("relative flex flex-col gap-4 overflow-hidden rounded-[var(--radius-panel)] border-2 p-5 shadow-sm lg:col-span-2",
                           tone.soft, p.level === "holds" ? "border-egress/35" : p.level === "fails" ? "border-danger/35" : p.level === "at_risk" ? "border-caution/35" : "border-border")}>
          <div className="flex items-center gap-4">
            <VerdictRing level={p.level} size={112} />
            <div className="min-w-0 space-y-2">
              <p className="text-balance text-2xl font-bold leading-tight tracking-tight">{p.headline}</p>
              <Popover>
                <PopoverTrigger asChild>
                  <button type="button" className="group inline-flex min-h-8 items-center gap-1 rounded-full focus-visible:outline-2 focus-visible:outline-signal"
                          aria-label={t("plan.why_badge", { label: evaluationLabel(p.evaluation) })}>
                    <Badge tone={EVAL_TONE[status] ?? "neutral"} className="whitespace-normal text-left text-sm">{evaluationLabel(p.evaluation)}</Badge>
                    <Info className="size-4 text-muted group-hover:text-ink" aria-hidden />
                  </button>
                </PopoverTrigger>
                <PopoverContent align="start" className="space-y-2">
                  <p className="font-semibold">{evaluationLabel(p.evaluation)}</p>
                  <p data-testid="verdict-why" className="text-sm">{evaluationReason(p.evaluation)}</p>
                  <Link to="/help#verdict" className="inline-flex min-h-8 items-center text-sm font-medium text-signal underline-offset-4 hover:underline">{t("evidence.why.help")}</Link>
                </PopoverContent>
              </Popover>
            </div>
          </div>
          <ul className="space-y-2 text-sm">
            <li className="flex items-start gap-2">
              <Swords className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
              <span className="min-w-0"><span className="text-muted">{t("plan.worst_case")} </span><span className="font-medium">{p.worst ?? t("plan.normal_exit")}</span></span>
            </li>
            {p.fixes > 0 && (
              <li className="flex items-center gap-2"><Wrench className="size-4 shrink-0 text-muted" aria-hidden />{t(p.fixes === 1 ? "plan.with_fix" : "plan.with_fixes", { n: p.fixes })}</li>
            )}
            {p.reasons.map((r) => (
              <li key={r} className="flex items-start gap-2 font-medium text-[color-mix(in_srgb,var(--danger)_80%,black)] dark:text-danger"><CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />{r}</li>
            ))}
            {stood && (
              <li className="flex items-start gap-2 text-caution-strong" data-testid="stood-in" title={stood.why}>
                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />{stood.text}
              </li>
            )}
          </ul>
          <dl className="mt-auto grid grid-cols-3 gap-2 text-center">
            {([["attacks", p.score.attacks, "text-ink"], ["breaks", p.score.breaks, p.score.breaks ? "text-danger" : "text-ink"], ["fixes", p.score.fixes, "text-signal"]] as const).map(([k, v, c]) => (
              <div key={k} className="flex flex-col-reverse rounded-[10px] bg-surface/70 px-2 py-2">
                <dt className="mt-1 text-2xs text-muted">{t(`plan.score_${k}`)}</dt>
                <dd className={cn("text-2xl font-bold leading-none tabular", c)}>{fmtInt(v)}</dd>
              </div>
            ))}
          </dl>
          {p.sandboxes && p.sandboxes.runs > 0 && (
            <button type="button" onClick={p.sandboxes.onOpen} data-testid="watch-sandboxes"
                    className="flex min-h-11 items-center justify-center gap-2 rounded-[10px] border border-egress/30 bg-surface/70 px-3 text-sm font-semibold text-egress-strong hover:bg-surface">
              <ShieldCheck className="size-4" aria-hidden />
              {t("plan.sbx_watch", { runs: p.sandboxes.runs, scripts: p.sandboxes.scripts })}
            </button>
          )}
        </div>

        <div className="min-w-0 lg:col-span-3">{p.hero}</div>

        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-5 lg:grid-cols-4" aria-label={t("plan.key_numbers")}>
          <Tile icon={<Clock3 />} tone="bg-sky-soft text-sky-strong" label={t("yourplan.n_evac")} testId="kpi-evac"
                value={m ? evacValue({ evac_time_p95_s: m.evac_time_p95_s, evac_time_estimate_s: extra.rset_extrapolated_s }) : "–"}
                visual={<TargetBar value={evac} target={p.targetS} over={evac == null || evac > p.targetS}
                                   targetLabel={t("plan.target", { d: fmtDuration(p.targetS) })} />}
                foot={p.basis} />
          <Tile icon={<Gauge />} tone="bg-signal-soft text-signal" label={t("yourplan.n_peak")} testId="kpi-peak"
                value={peak != null ? fmtNum(peak, 1) : "–"} unit={t("yourplan.per_m2")}
                visual={<DensityScale value={peak} warn={p.th.warn} danger={p.th.danger} />}
                foot={p.basis} />
          <Tile icon={<Users />} tone={inside ? "bg-danger-soft text-danger-strong" : "bg-egress-soft text-egress-strong"} label={t("plan.n_inside")} testId="kpi-inside"
                value={inside != null ? fmtInt(inside) : "–"} unit={total != null ? t("plan.of_total", { n: fmtInt(total) }) : undefined}
                visual={<Sparkline values={p.insideSeries} tone={inside ? "var(--danger)" : "var(--egress)"} label={t("plan.inside_curve", { n: fmtInt(inside ?? 0) })} />}
                foot={p.basis} />
          <Tile icon={<AlarmClock />} tone={cd.tone === "egress" ? "bg-egress-soft text-egress-strong" : cd.tone === "danger" ? "bg-danger-soft text-danger-strong" : "bg-caution-soft text-caution-strong"}
                label={t("yourplan.n_start")} testId="kpi-start"
                value={<span className="text-xl">{cd.text}</span>}
                visual={<NeedsBar countdown={p.countdown} />}
                foot={p.countdownBasis} />
        </ul>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <section aria-labelledby="ba-h" className="rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm lg:col-span-3">
          <h2 id="ba-h" className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-signal" aria-hidden />{t("plan.before_after")}</h2>
          {hasCompare ? (
            <ul className="mt-1 divide-y divide-border">
              <CompareRow label={t("plan.fix_evac")} icon={<Clock3 />} before={evacOf(b)} after={evacOf(a)}
                          estimate={{ before: isEstimate(b), after: isEstimate(a) }}
                          fmt={(v) => (v == null ? t("plan.not_all_out") : fmtDuration(v))} />
              <CompareRow label={t("yourplan.n_peak")} icon={<Gauge />} before={num(b?.peak_density_ppm2)} after={num(a?.peak_density_ppm2)}
                          fmt={(v) => (v == null ? "–" : `${fmtNum(v, 1)} /m²`)} />
              <CompareRow label={t("yourplan.n_danger")} icon={<CircleAlert />} before={num(b?.time_above_danger_s)} after={num(a?.time_above_danger_s)}
                          fmt={(v) => (v == null ? "–" : fmtDuration(v))} />
              <CompareRow label={t("plan.n_inside")} icon={<Users />} before={num(b?.agents_not_evacuated)} after={num(a?.agents_not_evacuated)}
                          fmt={(v) => (v == null ? "–" : fmtInt(v))} />
            </ul>
          ) : <p className="mt-2 text-sm text-muted">{t("plan.no_compare")}</p>}
        </section>
        <div className="lg:col-span-2">{p.next}</div>
      </div>

      {hasSummary && (
        <details className="group rounded-[var(--radius-panel)] border border-border bg-surface shadow-sm">
          <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-4 text-sm font-semibold [&::-webkit-details-marker]:hidden">
            <Sparkles className="size-4 text-signal" aria-hidden />{t("plan.ai_summary")}
            <span className="ml-auto text-xs font-normal text-muted group-open:hidden">{t("plan.show")}</span>
          </summary>
          <div className="space-y-3 border-t border-border p-4 text-sm">
            {p.summary.reasons.length > 0 && <ul className="list-disc space-y-0.5 pl-5">{p.summary.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            {p.summary.judge && <p className="max-w-prose text-muted">{p.summary.judge}</p>}
            {p.summary.recommendations.length > 0 && (
              <div>
                <p className="font-medium">{t("plan.recommendations")}</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted">{p.summary.recommendations.map((r) => <li key={r}>{r}</li>)}</ul>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}
