/** "What the AI suggests" (P3-03): every kept fix as a card with its own before/after test and
 * where it came from. All are chosen by default; "Accept these changes" saves only the chosen
 * ones. A choice that is not every kept fix was never tested as a whole: accepting it simulates
 * the chosen ones together under the worst attack, and the card says where that stands. */
import { AlertTriangle, ArrowRight, ArrowRightLeft, Check, ChevronRight, DoorOpen, Fence, Hammer, Lock, Megaphone, MoveHorizontal, RotateCcw, Timer, UserRoundCheck, Users, Workflow, Wrench } from "lucide-react";
import type * as React from "react";
import type { AppliedRecord, Fix, PatchOpIn, Venue } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { lockConflicts } from "@/lib/annotations";
import { runBasisLabel } from "@/lib/evidence";
import { fmtClock, fmtDuration, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { describeEvent, describeOp } from "@/panels/describe";
import { DeltaChip } from "./visuals";
import { type FixTest, fixSource, fixTest, type NodeLike, testedTogether } from "./fixes";
import { type TogetherCheck, togetherText } from "./range";
import { actionText } from "./SavedActions";
import type { PlanState } from "./state";

const CONSTRUCTION = new Set(["add_exit", "add_obstacle", "add_barrier_line"]);

export interface FixChooserProps {
  /** kept fixes, in the order the session kept them */
  kept: Fix[];
  selected: ReadonlySet<string>;
  deps: Record<string, string[]>;
  onToggle: (fixId: string) => void;
  nodes: Record<string, NodeLike | undefined>;
  /** the session's events are still loading */
  loading: boolean;
  venue: Venue;
  state: PlanState;
  record: AppliedRecord | null;
  attackTitle: (attackId: string) => string;
  name: (id: string) => string;
  human: (text: string) => string;
  onAccept: () => void;
  accepting: boolean;
  onTestAgain: () => void;
  testing: boolean;
  /** the accepted subset's run of the chosen changes together, and starting it again */
  together?: TogetherCheck | null;
  onTogether?: () => void;
  togetherBusy?: boolean;
}

const TOGETHER_TONE = { egress: "text-egress", caution: "text-ink", neutral: "text-ink" } as const;

function TogetherStatus({ check, onRetry, busy }: { check: TogetherCheck | null | undefined; onRetry?: () => void; busy?: boolean }) {
  const status = togetherText(check);
  if (!check || !status) return null;
  const retry = (check.status === "failed" || check.status === "preview") && onRetry;
  return (
    <div className="space-y-2">
      <p role="status" aria-live="polite" className={cn("flex gap-1.5 text-sm", TOGETHER_TONE[status.tone])}>
        {check.status === "running" ? <Spinner /> : check.status === "done" ? <Check className="mt-0.5 size-4 shrink-0" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />}
        <span>{status.text}</span>
      </p>
      {retry && <Button variant="secondary" onClick={onRetry} disabled={busy}>{busy ? <Spinner /> : <RotateCcw />}{t("together.retry")}</Button>}
    </div>
  );
}

/** What one fix changes, in plain words. */
export function fixSummary(f: Fix, name: (id: string) => string): string {
  const ops = (f.patch?.ops ?? []) as PatchOpIn[];
  return [
    ...ops.map((o) => describeOp(o as Record<string, unknown>, name)),
    ...(f.operational ?? []).map((e) => describeEvent(e as Record<string, unknown>, name)),
    ...[...(f.actions ?? []), ...(f.replace_actions ?? [])].map((a) => {
      const x = actionText(a, name);
      return `${x.what} (${x.when}, ${x.staff})`;
    }),
    ...((f.remove_action_ids ?? []).length ? [t("yourplan.remove_actions", { ids: f.remove_action_ids.join(", ") })] : []),
  ].join(" · ");
}

/** "2:26", "~5:57" (estimated: not everyone was out), "–" (not reached). */
function clockOf(m: Record<string, number | null | undefined>): string {
  if (m.evac_time_p95_s != null) return fmtClock(m.evac_time_p95_s);
  if (m.evac_time_estimate_s != null) return `~${fmtClock(m.evac_time_estimate_s)}`;
  return "–";
}

/** One icon per kind of change: new door, fence, wider door, one-way, held back, stewards, staff. */
export function fixIcon(f: Fix): React.ReactNode {
  const ops = ((f.patch?.ops ?? []) as PatchOpIn[]).map((o) => o.op as string);
  const evs = ((f.operational ?? []) as { type?: string }[]).map((e) => e.type ?? "");
  if (ops.includes("add_exit") || ops.includes("add_door")) return <DoorOpen />;
  if (ops.includes("add_barrier_line") || ops.includes("add_obstacle")) return <Fence />;
  if (ops.includes("resize")) return <MoveHorizontal />;
  if (ops.includes("set_people")) return <Users />;
  if (evs.includes("one_way")) return <ArrowRightLeft />;
  if (evs.includes("staggered_release")) return <Timer />;
  if (evs.includes("marshal_redirect")) return <Megaphone />;
  if ((f.actions ?? []).length || (f.replace_actions ?? []).length) return <UserRoundCheck />;
  return <Wrench />;
}

function FixNumbers({ test, loading, attack }: { test: FixTest; loading: boolean; attack: string }) {
  const { before, after } = test;
  if (!before || !after) {
    return <p className="text-xs text-muted">{loading ? t("yourplan.fix_test_loading") : t("yourplan.fix_untested")}</p>;
  }
  const b = before.metrics ?? {};
  const a = after.metrics ?? {};
  const evacN = (m: Record<string, number | null | undefined>) => m.evac_time_p95_s ?? m.evac_time_estimate_s ?? null;
  const rows: { key: string; label: string; from: string; to: string; b: number | null; a: number | null }[] = [
    { key: "evac", label: t("plan.fix_evac"), from: clockOf(b), to: clockOf(a), b: evacN(b), a: evacN(a) },
    { key: "peak", label: t("plan.fix_peak"), from: fmtNum(b.peak_density_ppm2, 1), to: fmtNum(a.peak_density_ppm2, 1), b: b.peak_density_ppm2 ?? null, a: a.peak_density_ppm2 ?? null },
    { key: "danger", label: t("plan.fix_danger"), from: fmtDuration(b.time_above_danger_s), to: fmtDuration(a.time_above_danger_s), b: b.time_above_danger_s ?? null, a: a.time_above_danger_s ?? null },
  ];
  const labels = [...new Set([runBasisLabel(before), runBasisLabel(after)])].join(" / ");
  return (
    <div className="space-y-1.5">
      <ul className="grid grid-cols-3 gap-1.5">
        {rows.map((r) => (
          <li key={r.key} className="min-w-0 rounded-[8px] bg-surface-2 px-2 py-1.5">
            <p className="truncate text-2xs text-muted">{r.label}</p>
            <p className="flex flex-wrap items-center gap-x-1 text-sm tabular">
              <span className="text-muted line-through decoration-line/60">{r.from}</span>
              <ArrowRight className="size-3 shrink-0 text-muted" aria-label={t("plan.to")} />
              <span className="font-semibold">{r.to}</span>
            </p>
            <DeltaChip before={r.b} after={r.a} />
          </li>
        ))}
      </ul>
      <p className="truncate text-2xs text-muted" title={`${t("yourplan.fix_test", { attack })} · ${labels}`}>{t("yourplan.fix_test", { attack })} · {labels}</p>
    </div>
  );
}

export function FixChooser(p: FixChooserProps) {
  const keptIds = p.kept.map((f) => f.fix_id);
  const deciding = p.state === "pending";
  const chosen = p.kept.filter((f) => p.selected.has(f.fix_id));
  const together = testedTogether(p.selected, keptIds);
  const conflicts = lockConflicts(p.venue, chosen.flatMap((f) => (f.patch?.ops ?? []) as PatchOpIn[]));
  const inPlan = new Set(p.state === "accepted" && !p.record ? keptIds : p.record?.fix_ids ?? []);
  const titleOf = (id: string) => p.human(p.kept.find((f) => f.fix_id === id)?.title ?? id);

  return (
    <section aria-labelledby="suggests-h" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="suggests-h" className="text-lg font-semibold">{t("yourplan.suggests")}</h2>
        {p.kept.length > 0 && deciding && <p className="text-sm text-muted">{t("plan.suggests_short")}</p>}
      </div>
      {p.kept.length === 0 ? <p className="text-sm text-muted">{t("yourplan.no_changes")}</p> : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {p.kept.map((f, i) => {
            const ops = (f.patch?.ops ?? []) as PatchOpIn[];
            const build = ops.some((o) => CONSTRUCTION.has(o.op));
            const on = p.selected.has(f.fix_id);
            const needs = p.deps[f.fix_id] ?? [];
            const locked = lockConflicts(p.venue, ops);
            const test = fixTest(f, i, p.nodes);
            const title = p.human(f.title);
            return (
              <li key={f.fix_id} className={cn("animate-deal-in flex flex-col gap-3 rounded-[var(--radius-panel)] border-2 bg-surface p-4 shadow-sm transition",
                                                deciding && on ? "border-signal/60" : "border-border", deciding && !on && "opacity-75")}
                  style={{ animationDelay: `${Math.min(i, 6) * 60}ms` }}>
                <div className="flex items-start gap-3">
                  <span className={cn("grid size-11 shrink-0 place-items-center rounded-[12px] [&_svg]:size-5", on || !deciding ? "bg-signal-soft text-signal" : "bg-surface-3 text-muted")}>{fixIcon(f)}</span>
                  <div className="min-w-0 flex-1 space-y-1">
                    <p className="font-semibold leading-snug">{title}</p>
                    <span className="flex flex-wrap gap-1.5">
                      <Badge tone={fixSource(f) === "rules" ? "outline" : "signal"}>{t(fixSource(f) === "rules" ? "yourplan.src_rules" : "yourplan.src_ai")}</Badge>
                      {build ? <Badge tone="neutral"><Hammer />{t("yourplan.construction")}</Badge> : <Badge tone="outline"><Workflow />{t("yourplan.operational")}</Badge>}
                    </span>
                  </div>
                  {deciding ? (
                    <span className="relative inline-flex min-h-11 shrink-0 items-center">
                      <input type="checkbox" checked={on} onChange={() => p.onToggle(f.fix_id)} aria-label={t("yourplan.use_fix", { title })}
                             className="peer h-7 w-12 cursor-pointer appearance-none rounded-full bg-surface-3 ring-1 ring-border-strong transition checked:bg-signal checked:ring-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal" />
                      <span aria-hidden className="pointer-events-none absolute left-1 top-1/2 size-5 -translate-y-1/2 rounded-full bg-surface shadow transition peer-checked:translate-x-5" />
                    </span>
                  ) : inPlan.has(f.fix_id) ? <Badge tone="egress"><Check />{t("yourplan.already_accepted_one")}</Badge>
                    : p.state === "accepted_subset" ? <Badge tone="outline">{t("yourplan.not_in_plan")}</Badge> : null}
                </div>
                <FixNumbers test={test} loading={p.loading} attack={p.human(p.attackTitle(test.attackId))} />
                {locked.map((c) => <p key={`${c.id}:${c.op}`} className="flex gap-1.5 text-sm text-danger"><Lock className="mt-0.5 size-3.5 shrink-0" />{t("check.conflict", { name: p.name(c.id) })}</p>)}
                <details className="group mt-auto text-sm">
                  <summary className="flex min-h-9 cursor-pointer list-none items-center gap-1 text-xs font-medium text-signal [&::-webkit-details-marker]:hidden">
                    <ChevronRight className="size-3.5 transition group-open:rotate-90" aria-hidden />{t("plan.what_changes")}
                  </summary>
                  <p className="mt-1 text-muted">{fixSummary(f, p.name)}</p>
                  {needs.length > 0 && <p className="mt-1 text-xs text-muted">{needs.map((id) => t("yourplan.builds_on", { title: titleOf(id) })).join(" ")}</p>}
                </details>
              </li>
            );
          })}
        </ul>
      )}

      {p.kept.length > 0 && deciding && (
        <div className="sticky bottom-2 z-10 space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface/95 p-3 shadow-[var(--shadow-float)] backdrop-blur">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm font-medium tabular">{t("yourplan.selected", { k: chosen.length, n: p.kept.length })}</p>
            <Button variant="primary" size="lg" className="ml-auto max-sm:w-full" disabled={chosen.length === 0 || conflicts.length > 0 || p.accepting} onClick={p.onAccept}>
              {p.accepting ? <Spinner /> : <Check />}{t("yourplan.accept")}
            </Button>
          </div>
          {chosen.length === 0 ? <p className="text-sm text-danger">{t("yourplan.none_selected")}</p>
            : conflicts.length > 0 ? <p className="text-sm text-danger">{t("yourplan.accept_conflicts")}</p>
            : !together ? <p role="status" className="flex gap-1.5 rounded-[8px] bg-caution-soft p-2 text-sm"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />{t("yourplan.subset_note")}</p>
            : <p className="text-xs text-muted">{t("yourplan.accept_hint")}</p>}
        </div>
      )}
      {p.kept.length > 0 && p.state === "accepted" && <p className="flex gap-1.5 text-sm text-egress"><Check className="mt-0.5 size-4 shrink-0" />{t("yourplan.already_accepted")}</p>}
      {p.kept.length > 0 && p.state === "accepted" && p.record?.together && <TogetherStatus check={p.together ?? p.record.together} />}
      {p.kept.length > 0 && p.state === "accepted_subset" && (
        <div role="status" className="space-y-2 rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">
          <p className="font-medium">{t("yourplan.subset_applied", { k: p.record?.fix_ids.length ?? 0, n: p.kept.length, v: p.record?.version ?? "" })}</p>
          <p>{p.record?.note ?? t("yourplan.subset_note")}</p>
          <TogetherStatus check={p.together ?? p.record?.together} onRetry={p.onTogether} busy={p.togetherBusy} />
          <Button variant={p.together?.status === "running" ? "secondary" : "primary"} onClick={p.onTestAgain} disabled={p.testing}><RotateCcw />{t("yourplan.test_again")}</Button>
        </div>
      )}
      {p.kept.length > 0 && p.state === "stale" && <p className="text-sm text-muted">{t("yourplan.accept_stale")}</p>}
    </section>
  );
}
