/** "What the AI suggests" (P3-03): every kept fix as a card with its own before/after test and
 * where it came from. All are chosen by default; "Accept these changes" saves only the chosen
 * ones. A choice that is not every kept fix was never tested as a whole, and says so. */
import { AlertTriangle, Check, Hammer, Lock, RotateCcw, Workflow } from "lucide-react";
import type { AppliedRecord, Fix, PatchOpIn, Venue } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { lockConflicts } from "@/lib/annotations";
import { runBasisLabel } from "@/lib/evidence";
import { fmtDuration, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { describeEvent, describeOp } from "@/panels/describe";
import { evacValue, type FixTest, fixSource, fixTest, type NodeLike, testedTogether } from "./fixes";
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

function FixNumbers({ test, loading, attack }: { test: FixTest; loading: boolean; attack: string }) {
  const { before, after } = test;
  if (!before || !after) {
    return <p className="mt-2 text-xs text-muted">{loading ? t("yourplan.fix_test_loading") : t("yourplan.fix_untested")}</p>;
  }
  const b = before.metrics ?? {};
  const a = after.metrics ?? {};
  const rows: [string, string][] = [
    [t("yourplan.n_evac"), `${evacValue(b)} → ${evacValue(a)}`],
    [t("yourplan.n_peak"), `${fmtNum(b.peak_density_ppm2, 1)} → ${fmtNum(a.peak_density_ppm2, 1)} ${t("yourplan.per_m2")}`],
    [t("yourplan.n_danger"), `${fmtDuration(b.time_above_danger_s)} → ${fmtDuration(a.time_above_danger_s)}`],
  ];
  const labels = [...new Set([runBasisLabel(before), runBasisLabel(after)])].join(" / ");
  return (
    <div className="mt-2 rounded-[8px] bg-surface-2 p-2 text-sm">
      <p className="text-xs text-muted">{t("yourplan.fix_test", { attack })} · {labels}</p>
      <dl className="mt-1 grid gap-x-3 gap-y-0.5 sm:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="font-medium tabular">{value}</dd>
          </div>
        ))}
      </dl>
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
    <section aria-labelledby="suggests-h" className="space-y-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <div>
        <h2 id="suggests-h" className="text-lg font-semibold">{t("yourplan.suggests")}</h2>
        {p.kept.length > 0 && deciding && <p className="max-w-prose text-sm text-muted">{t("yourplan.suggests_body")}</p>}
      </div>
      {p.kept.length === 0 ? <p className="text-sm text-muted">{t("yourplan.no_changes")}</p> : (
        <ul className="space-y-2">
          {p.kept.map((f, i) => {
            const ops = (f.patch?.ops ?? []) as PatchOpIn[];
            const build = ops.some((o) => CONSTRUCTION.has(o.op));
            const on = p.selected.has(f.fix_id);
            const needs = p.deps[f.fix_id] ?? [];
            const locked = lockConflicts(p.venue, ops);
            const test = fixTest(f, i, p.nodes);
            const badges = (
              <span className="flex flex-wrap gap-1.5">
                <Badge tone={fixSource(f) === "rules" ? "outline" : "signal"}>{t(fixSource(f) === "rules" ? "yourplan.src_rules" : "yourplan.src_ai")}</Badge>
                {build ? <Badge tone="neutral"><Hammer />{t("yourplan.construction")}</Badge> : <Badge tone="outline"><Workflow />{t("yourplan.operational")}</Badge>}
              </span>
            );
            return (
              <li key={f.fix_id} className={cn("rounded-[10px] border p-3", deciding && on ? "border-signal/45 bg-signal-soft/40" : "border-border")}>
                {deciding ? (
                  <label className="flex min-h-11 cursor-pointer items-start gap-3">
                    <input type="checkbox" checked={on} onChange={() => p.onToggle(f.fix_id)} aria-label={t("yourplan.use_fix", { title: p.human(f.title) })}
                           className="mt-0.5 size-5 shrink-0 cursor-pointer accent-[var(--signal)]" />
                    <span className="min-w-0 flex-1 space-y-1">
                      <span className="block font-medium">{p.human(f.title)}</span>
                      {badges}
                    </span>
                  </label>
                ) : (
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <span className="min-w-0 flex-1 space-y-1">
                      <span className="block font-medium">{p.human(f.title)}</span>
                      {badges}
                    </span>
                    {inPlan.has(f.fix_id) ? <Badge tone="egress"><Check />{t("yourplan.already_accepted_one")}</Badge>
                      : p.state === "accepted_subset" && <Badge tone="outline">{t("yourplan.not_in_plan")}</Badge>}
                  </div>
                )}
                <p className="mt-1.5 text-sm text-muted">{fixSummary(f, p.name)}</p>
                <FixNumbers test={test} loading={p.loading} attack={p.human(p.attackTitle(test.attackId))} />
                {needs.length > 0 && <p className="mt-1.5 text-xs text-muted">{needs.map((id) => t("yourplan.builds_on", { title: titleOf(id) })).join(" ")}</p>}
                {locked.map((c) => <p key={`${c.id}:${c.op}`} className="mt-1 flex gap-1.5 text-sm text-danger"><Lock className="mt-0.5 size-3.5 shrink-0" />{t("check.conflict", { name: p.name(c.id) })}</p>)}
              </li>
            );
          })}
        </ul>
      )}

      {p.kept.length > 0 && deciding && (
        <div className="space-y-2 pt-1">
          <p className="text-sm text-muted tabular">{t("yourplan.selected", { k: chosen.length, n: p.kept.length })}</p>
          <Button variant="primary" size="lg" className="w-full" disabled={chosen.length === 0 || conflicts.length > 0 || p.accepting} onClick={p.onAccept}>
            {p.accepting ? <Spinner /> : <Check />}{t("yourplan.accept")}
          </Button>
          {chosen.length === 0 ? <p className="text-sm text-danger">{t("yourplan.none_selected")}</p>
            : conflicts.length > 0 ? <p className="text-sm text-danger">{t("yourplan.accept_conflicts")}</p>
            : !together ? <p role="status" className="flex gap-1.5 rounded-[8px] bg-caution-soft p-2 text-sm"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />{t("yourplan.subset_note")}</p>
            : <p className="text-xs text-muted">{t("yourplan.accept_hint")}</p>}
        </div>
      )}
      {p.kept.length > 0 && p.state === "accepted" && <p className="flex gap-1.5 text-sm text-egress"><Check className="mt-0.5 size-4 shrink-0" />{t("yourplan.already_accepted")}</p>}
      {p.kept.length > 0 && p.state === "accepted_subset" && (
        <div role="status" className="space-y-2 rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">
          <p className="font-medium">{t("yourplan.subset_applied", { k: p.record?.fix_ids.length ?? 0, n: p.kept.length, v: p.record?.version ?? "" })}</p>
          <p>{p.record?.note ?? t("yourplan.subset_note")}</p>
          <Button variant="primary" onClick={p.onTestAgain} disabled={p.testing}><RotateCcw />{t("yourplan.test_again")}</Button>
        </div>
      )}
      {p.kept.length > 0 && p.state === "stale" && <p className="text-sm text-muted">{t("yourplan.accept_stale")}</p>}
    </section>
  );
}
