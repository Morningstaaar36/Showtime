/** Your plan › Overview: one honest verdict (a ring, one sentence about the plan as it stands
 * today and at most one primary button), the key numbers with a picture each, the replay, before
 * vs after the fixes and the start of the AI's summary. Deeper analysis is in Expert view. */
import { AlarmClock, CircleAlert, Clock3, Gauge, Info, PanelsTopLeft, ShieldCheck, Sparkles, Swords, Users, Wrench } from "lucide-react";
import type * as React from "react";
import { useState } from "react";
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

interface OverviewProps {
  level: VerdictLevel;
  headline: string;
  evaluation: Evaluation | null | undefined;
  /** the worst attack's title, in organizer words (null: everyone leaving normally) */
  worst: string | null;
  /** fixes included in the numbers */
  fixes: number;
  /** fixes in the before vs after comparison */
  compared: number;
  reasons: string[];
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
  /** the one primary action of the page (accept the fixes, test again, hand over), if any */
  action: React.ReactNode;
  /** the replay of the plan, under the verdict */
  replay: React.ReactNode;
  /** the AI's own words (judge text, evaluation reasons, recommendations) */
  summary: { judge: string | null; reasons: string[]; recommendations: string[] };
  /** the real case this venue rebuilds (a compact card above the verdict), if any */
  realCase?: React.ReactNode;
  /** Expert view's analysis of this test, and how many sandbox runs and AI-written scripts it had */
  more: { href: string; sandboxesHref: string; runs: number; scripts: number };
  /** agents whose part built-in rules played because the model didn't answer (agent -> why) */
  stoodIn?: Record<string, string>;
}

/** One key number. The icon is neutral: the number's picture and the verdict carry the safety
 * colours, so a green icon never reads as "safe". */
function Tile({ icon, label, value, unit, visual, foot, testId }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; unit?: string; visual: React.ReactNode; foot: string; testId?: string;
}) {
  return (
    <li data-testid={testId} className="flex min-w-0 flex-col gap-2 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-2 text-muted [&_svg]:size-4">{icon}</span>
        <p className="min-w-0 text-sm font-medium leading-tight text-muted">{label}</p>
      </div>
      {/* one line on a phone: a qualifier such as "estimated" goes in the caption below */}
      <p className="whitespace-nowrap text-2xl font-bold leading-none tabular">{value}{unit && <span className="ml-1 text-sm font-medium text-muted">{unit}</span>}</p>
      <div className="mt-auto min-h-8">{visual}</div>
      <p className="truncate text-2xs text-muted" title={foot}>{foot}</p>
    </li>
  );
}

/** The latest safe start, only when a hazard sets one: without a hazard there is no deadline to show. */
function countdownValue(c: Countdown | null | undefined): string | null {
  if (c?.status === "ok") return c.t_latest_iso ? fmtHM(c.t_latest_iso) : fmtDuration(c.t_latest_s);
  if (c?.status === "too_late") return t("plan.cd_too_late");
  return null;
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
        <span className="flex items-center gap-2"><span className="w-10 text-2xs text-muted">{t("yourplan.before")}</span>{bar(before, "bg-line")}<span className="w-28 whitespace-nowrap text-right text-xs tabular">{side(before, estimate?.before)}</span></span>
        <span className="flex items-center gap-2"><span className="w-10 text-2xs font-semibold text-signal">{t("yourplan.after")}</span>{bar(after, "bg-signal")}<span className="w-28 whitespace-nowrap text-right text-xs font-semibold tabular">{side(after, estimate?.after)}</span></span>
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
  const measured = num(m?.evac_time_p95_s);
  const estimated = measured == null ? num(extra.rset_extrapolated_s) : null;
  const evac = measured ?? estimated;
  const inside = num(m?.agents_not_evacuated);
  const total = num(m?.agents_total);
  const peak = num(m?.peak_density_ppm2);
  const cd = countdownValue(p.countdown);
  const tone = LEVEL_TONE[p.level];
  const b = p.before, a = p.after;
  const evacOf = (x: SessionMetrics | null | undefined) => num(x?.evac_time_p95_s) ?? num(x?.evac_time_estimate_s);
  // an estimate (95% not reached, extrapolated from the exit flow) is never shown as measured
  const isEstimate = (x: SessionMetrics | null | undefined) => num(x?.evac_time_p95_s) == null && num(x?.evac_time_estimate_s) != null;
  const hasCompare = !!b && !!a && p.compared > 0;
  const stood = stoodInLine(p.stoodIn);
  return (
    <div className="space-y-4">
      {p.realCase}
      <section aria-label={t("yourplan.verdict")} className="space-y-3">
        <div className={cn("flex flex-col gap-4 rounded-[var(--radius-panel)] border border-border p-5 shadow-sm sm:flex-row sm:items-center", tone.soft)}>
          <VerdictRing level={p.level} size={88} />
          <div className="min-w-0 flex-1 space-y-2">
            <p className="text-balance text-2xl font-bold leading-tight tracking-tight" data-testid="verdict-sentence">{p.headline}</p>
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
            <ul className="space-y-1 text-sm">
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
          </div>
          {p.action && <div className="shrink-0">{p.action}</div>}
        </div>

        <ul className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2", cd ? "lg:grid-cols-4" : "lg:grid-cols-3")} aria-label={t("plan.key_numbers")}>
          <Tile icon={<Clock3 />} label={t("yourplan.n_evac")} testId="kpi-evac"
                value={m ? evacValue({ evac_time_p95_s: m.evac_time_p95_s, evac_time_estimate_s: extra.rset_extrapolated_s }) : "–"}
                visual={<TargetBar value={evac} target={p.targetS} over={evac == null || evac > p.targetS}
                                   targetLabel={t("plan.target", { d: fmtDuration(p.targetS) })} />}
                foot={estimated != null ? t("plan.estimated_foot", { basis: p.basis }) : p.basis} />
          <Tile icon={<Gauge />} label={t("yourplan.n_peak")} testId="kpi-peak"
                value={peak != null ? fmtNum(peak, 1) : "–"} unit={t("yourplan.per_m2")}
                visual={<DensityScale value={peak} warn={p.th.warn} danger={p.th.danger} />}
                foot={p.basis} />
          <Tile icon={<Users />} label={t("plan.n_inside")} testId="kpi-inside"
                value={inside != null ? fmtInt(inside) : "–"} unit={total != null ? t("plan.of_total", { n: fmtInt(total) }) : undefined}
                visual={<Sparkline values={p.insideSeries} tone={inside ? "var(--danger)" : "var(--line)"} label={t("plan.inside_curve", { n: fmtInt(inside ?? 0) })} />}
                foot={p.basis} />
          {cd && (
            <Tile icon={<AlarmClock />} label={t("yourplan.n_start")} testId="kpi-start"
                  value={<span className="text-xl">{cd}</span>}
                  visual={<NeedsBar countdown={p.countdown} />}
                  foot={p.countdownBasis} />
          )}
        </ul>
        {!cd && p.countdown?.status === "no_hazard" && <p className="text-sm text-muted" data-testid="kpi-start">{t("plan.cd_none_line")}</p>}
      </section>

      {p.replay}

      <section aria-labelledby="ba-h" className="rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
        <h2 id="ba-h" className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-signal" aria-hidden />{t("plan.before_after")}</h2>
        {hasCompare ? (
          <ul className="mt-1 divide-y divide-border">
            <CompareRow label={t("plan.fix_evac")} icon={<Clock3 />} before={evacOf(b)} after={evacOf(a)}
                        estimate={{ before: isEstimate(b), after: isEstimate(a) }}
                        fmt={(v) => (v == null ? t("plan.not_all_out") : fmtDuration(v))} />
            <CompareRow label={t("yourplan.n_peak")} icon={<Gauge />} before={num(b?.peak_density_ppm2)} after={num(a?.peak_density_ppm2)}
                        fmt={(v) => (v == null ? "–" : t("plan.per_m2_value", { v: fmtNum(v, 1) }))} />
            <CompareRow label={t("yourplan.n_danger")} icon={<CircleAlert />} before={num(b?.time_above_danger_s)} after={num(a?.time_above_danger_s)}
                        fmt={(v) => (v == null ? "–" : fmtDuration(v))} />
            <CompareRow label={t("plan.n_inside")} icon={<Users />} before={num(b?.agents_not_evacuated)} after={num(a?.agents_not_evacuated)}
                        fmt={(v) => (v == null ? "–" : fmtInt(v))} />
          </ul>
        ) : <p className="mt-2 text-sm text-muted">{t("plan.no_compare")}</p>}
      </section>

      <AiSummary summary={p.summary} />

      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <Link to={p.more.href} className="inline-flex min-h-11 items-center gap-1.5 font-medium text-signal underline-offset-4 hover:underline">
          <PanelsTopLeft className="size-4" aria-hidden />{t("plan.more_analysis")}
        </Link>
        {p.more.runs > 0 && (
          <Link to={p.more.sandboxesHref} data-testid="watch-sandboxes" className="inline-flex min-h-11 items-center gap-1.5 text-muted underline-offset-4 hover:text-ink hover:underline">
            <ShieldCheck className="size-4" aria-hidden />{t("plan.sbx_watch", { runs: p.more.runs, scripts: p.more.scripts })}
          </Link>
        )}
      </p>
    </div>
  );
}

/** The AI's own words: its first two lines show at once, the rest (reasons, recommendations) on "Read more". */
function AiSummary({ summary }: { summary: OverviewProps["summary"] }) {
  const [open, setOpen] = useState(false);
  const lead = summary.judge ?? summary.reasons.join(" ");
  if (!lead && !summary.recommendations.length) return null;
  const more = (!!summary.judge && summary.reasons.length > 0) || summary.recommendations.length > 0 || lead.length > 180;
  return (
    <section aria-labelledby="ai-h" className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface p-4 text-sm shadow-sm">
      <h2 id="ai-h" className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-signal" aria-hidden />{t("plan.ai_summary")}</h2>
      {lead && <p className={cn("max-w-prose", !open && "line-clamp-2")}>{lead}</p>}
      {open && (
        <div className="space-y-3">
          {summary.judge && summary.reasons.length > 0 && <ul className="list-disc space-y-0.5 pl-5">{summary.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
          {summary.recommendations.length > 0 && (
            <div>
              <p className="font-medium">{t("plan.recommendations")}</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted">{summary.recommendations.map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          )}
        </div>
      )}
      {more && (
        <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)}
                className="inline-flex min-h-11 items-center text-sm font-medium text-signal underline-offset-4 hover:underline">
          {open ? t("plan.read_less") : t("plan.read_more")}
        </button>
      )}
    </section>
  );
}
