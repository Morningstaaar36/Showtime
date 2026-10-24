/** The red team's failure map: a MAP-Elites grid of hazard kind × where (docs/RAINBOW.md).
 *  Every severity comes from a simulation (a formula over its metrics), never from the AI. */
import { ArrowLeftRight, CloudFog, CodeXml, DoorClosed, Eye, type LucideIcon, ShieldAlert, ShieldCheck, Signpost, TriangleAlert, Users, Wrench } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { fmtDuration, fmtInt, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { best, buildGrid, current, type FailureMap as FailureMapData, type FailureMapCell, fmtCoverage, fmtSeverity, historyLine, tone, TONE_LABEL, type Tone } from "./failureMap";

const KIND_ICON: Record<string, LucideIcon> = {
  exit_blocked: DoorClosed,
  surge: Users,
  counterflow: ArrowLeftRight,
  slowdown: CloudFog,
  route_change: Signpost,
  adaptive: CodeXml,
};

const TONE_CLASS: Record<Tone, string> = {
  empty: "border-dashed border-line bg-transparent text-muted",
  holds: "border-egress/40 bg-egress-soft text-[color-mix(in_srgb,var(--egress)_68%,black)] dark:text-egress",
  near: "border-caution/50 bg-caution-soft text-[color-mix(in_srgb,var(--caution)_62%,black)] dark:text-caution",
  break: "border-danger/50 bg-danger-soft text-[color-mix(in_srgb,var(--danger)_80%,black)] dark:text-danger",
};

const TONE_ICON: Record<Exclude<Tone, "empty">, LucideIcon> = { holds: ShieldCheck, near: TriangleAlert, break: ShieldAlert };

/** Failure map with coverage and QD-score; clicking a filled cell shows its strongest attack
 *  and calls `onSelectRun` with that attack's simulation. */
export function FailureMap({ map, onSelectRun, activeRunId, className }: {
  map: FailureMapData | null | undefined; onSelectRun?: (runId: string) => void; activeRunId?: string | null; className?: string;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  if (!map) {
    return <p className={cn("text-sm text-muted", className)}>The failure map fills in as the red team’s attacks are simulated.</p>;
  }
  const grid = buildGrid(map);
  const sel = picked ? map.cells.find((c) => `${c.kind}|${c.where}` === picked) ?? null : null;
  const kindLabel = (id: string) => map.kinds.find((k) => k.id === id)?.label ?? id;
  const whereLabel = (id: string) => map.wheres.find((w) => w.id === id)?.label ?? id;
  // picking a cell shows what landed there; its buttons play the attack or the fixed plan
  const choose = (c: FailureMapCell) => setPicked(`${c.kind}|${c.where}`);
  return (
    <section aria-label="Failure map" className={cn("space-y-3", className)}>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-[var(--radius-panel)] border border-border p-2.5">
          <span className="block text-2xl font-semibold leading-none tabular">{fmtCoverage(map)}</span>
          <span className="text-2xs text-muted">of the map tried · {map.filled} of {map.cells_total} places and hazards</span>
        </div>
        <div className="rounded-[var(--radius-panel)] border border-border p-2.5">
          <span className="block text-2xl font-semibold leading-none tabular">{fmtSeverity(map.qd_score)}</span>
          <span className="text-2xs text-muted">total severity · of the worst attack in each place</span>
        </div>
      </div>
      {map.history.length > 0 && <p className="text-xs text-muted tabular">{historyLine(map)}</p>}

      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th scope="col" className="sr-only">Hazard</th>
              {grid.cols.map((w) => <th key={w.id} scope="col" className="px-1 text-left font-medium text-muted">{w.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {grid.rows.map((r) => {
              const Icon = KIND_ICON[r.id] ?? CodeXml;
              return (
                <tr key={r.id}>
                  <th scope="row" className="whitespace-nowrap pr-1 text-left font-medium">
                    <span className="flex items-center gap-1.5"><Icon className="size-3.5 shrink-0 text-muted" aria-hidden />{r.label}</span>
                  </th>
                  {r.cells.map((c, i) => {
                    if (!c) return <td key={i} aria-label="Not possible here" className="rounded-[var(--radius-control)] bg-surface-2/40" />;
                    const b = best(c);
                    const sev = b ? current(b) : null;
                    const tn = tone(sev);
                    const TIcon = tn === "empty" ? null : TONE_ICON[tn];
                    const key = `${c.kind}|${c.where}`;
                    return (
                      <td key={i} className="p-0">
                        <button type="button" onClick={() => choose(c)} aria-pressed={picked === key}
                                aria-label={`${r.label}, ${grid.cols[i].label}: ${TONE_LABEL[tn]}${sev != null ? `, severity ${fmtSeverity(sev)}` : ""}`}
                                className={cn("flex h-12 w-full min-w-14 flex-col items-center justify-center gap-0.5 rounded-[var(--radius-control)] border px-1 tabular transition-colors hover:brightness-95",
                                  TONE_CLASS[tn], picked === key && "ring-2 ring-signal", b && activeRunId === b.run_id && "outline outline-2 outline-offset-1 outline-signal")}>
                          {TIcon ? <TIcon className="size-3.5" aria-hidden /> : <span aria-hidden>—</span>}
                          <span className="font-semibold">{sev != null ? fmtSeverity(sev) : "gap"}</span>
                          {b?.fixed_by && <Wrench className="size-3" aria-label="a kept fix was tested here" />}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-2xs text-muted" aria-label="Legend">
        <li className="flex items-center gap-1"><ShieldAlert className="size-3 text-danger" aria-hidden />≥ 1.00 breaks the plan</li>
        <li className="flex items-center gap-1"><TriangleAlert className="size-3 text-caution" aria-hidden />0.70–0.99 close</li>
        <li className="flex items-center gap-1"><ShieldCheck className="size-3 text-egress" aria-hidden />below 0.70 holds</li>
        <li className="flex items-center gap-1"><span className="inline-block size-3 rounded-sm border border-dashed border-line" aria-hidden />gap: not tested yet</li>
      </ul>

      {sel && (
        <div className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface p-3" aria-live="polite">
          <p className="text-2xs font-medium text-muted">{kindLabel(sel.kind)} · {whereLabel(sel.where)}</p>
          {!sel.elites.length && <p className="text-sm text-muted">No attack has landed here yet. The red team aims at gaps like this one first.</p>}
          {sel.elites.map((e) => {
            const m = e.metrics;
            return (
              <div key={e.attack_id} className="space-y-1 border-t border-border pt-2 first:border-t-0 first:pt-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold leading-snug">{e.title}</p>
                  <span className="text-xs text-muted tabular">round {e.round}</span>
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs tabular">
                  <span>Severity <b>{fmtSeverity(e.severity)}</b>{e.severity >= 1 ? " (breaks)" : ""}</span>
                  <span>Peak <b>{fmtNum((m.peak_density_ppm2 as number | null) ?? null, 1)}</b> per m²</span>
                  <span>Danger <b>{fmtDuration((m.time_above_danger_s as number | null) ?? 0)}</b></span>
                  <span>95% out <b>{fmtDuration((m.evac_time_p95_s as number | null) ?? (m.evac_time_estimate_s as number | null) ?? null)}</b></span>
                  {Number(m.agents_not_evacuated ?? 0) > 0 && <span>Still inside <b>{fmtInt(m.agents_not_evacuated as number)}</b></span>}
                </div>
                {e.fixed_by && e.severity_after != null && (
                  <p className="flex items-center gap-1 text-xs text-muted"><Wrench className="size-3" aria-hidden />With the kept fix: severity {fmtSeverity(e.severity)} → <b className="text-ink">{fmtSeverity(e.severity_after)}</b></p>
                )}
                <div className="flex flex-wrap gap-1">
                  {onSelectRun && <Button size="sm" variant="ghost" className="h-7" onClick={() => onSelectRun(e.run_id)}><Eye />Show attack</Button>}
                  {onSelectRun && e.after_run_id && <Button size="sm" variant="ghost" className="h-7" onClick={() => onSelectRun(e.after_run_id as string)}><Eye />Show with fix</Button>}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <details className="text-2xs text-muted">
        <summary className="cursor-pointer">Scored by the simulator, never by the AI. How?</summary>
        <p className="mt-1">Severity comes from each simulation’s numbers only: {map.fitness}. 1 or more means the run breaks the plan.
          {map.aim.targeted > 0 && ` The red team was aimed at ${map.aim.targeted} gaps and landed in ${map.aim.hit}.`}</p>
      </details>
    </section>
  );
}
