import { Ban, Flame, MessageCircleQuestion, Play, Square, X } from "lucide-react";
import { useMemo } from "react";
import { toast } from "sonner";
import { useCancelRun, useStartRun } from "@/api/queries";
import type { Hotspot, ProjectDetail, RunOut, RunResult } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PanelTitle, Progress, Separator, Spinner } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { fmtClock, fmtDuration, fmtInt, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Replay } from "@/replay/useReplay";
import { useUi } from "@/state/ui";
import { ScenarioMatrix } from "./ScenarioMatrix";
import { exitLabeler, VerdictCard } from "./Inspector";
import { DensityCurve, EvacuationCurve, ExitUse, MetricTile } from "./Metrics";
import type { Thresholds } from "./verdict";

export function RunStatus({ run, onCancel }: { run: RunOut; onCancel: () => void }) {
  const p = run.progress;
  const total = p?.agents_total ?? run.tier1?.metrics?.agents_total ?? 0;
  const done = p ? p.agents_total - p.agents_remaining : 0;
  const pct = total ? (done / total) * 100 : 3;
  return (
    <div className="rounded-[var(--radius-panel)] border border-signal/30 bg-signal-soft/50 p-4" role="status" aria-live="polite">
      <div className="flex items-center gap-2">
        <Spinner className="text-signal" />
        <p className="text-sm font-medium">
          {run.status === "queued" ? t("workspace.stress_test_queued")
            : t("workspace.stress_test_running", { people: fmtInt(total), elapsed: fmtDuration(p?.wall_s ?? 0) })}
        </p>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onCancel}><Square className="size-3" />{t("workspace.cancel_run")}</Button>
      </div>
      <Progress className="mt-3" value={pct} />
      {p && <p className="mt-2 text-xs text-muted tabular">{t(p.floor_id ? "ui.simulatepanel.progress_floor" : "ui.simulatepanel.progress", { at: fmtClock(p.sim_time_s), n: fmtInt(p.agents_remaining), floor: p.floor_id ?? "" })}</p>}
    </div>
  );
}

function HotspotList({ hotspots, onPick, label }: { hotspots: Hotspot[]; onPick: (h: Hotspot) => void; label: (id: string) => string }) {
  if (!hotspots.length) return <p className="text-sm text-muted">{t("metrics.no_hotspots")}</p>;
  return (
    <ul className="space-y-1.5">
      {hotspots.slice(0, 6).map((h, i) => (
        <li key={i}>
          <button type="button" onClick={() => onPick(h)}
                  className="flex w-full items-center gap-2 rounded-[var(--radius-control)] border border-border px-2.5 py-2 text-left text-sm hover:bg-surface-2">
            <Flame className={cn("size-4 shrink-0", h.level === "danger" ? "text-danger" : "text-caution")} />
            <span className="min-w-0 flex-1 truncate">{h.near ? `Near ${label(h.near)}` : `At ${fmtNum(h.x, 0)}, ${fmtNum(h.y, 0)} m`}</span>
            <span className="tabular text-muted">{fmtNum(h.peak_density_ppm2, 1)}</span>
            <span className="text-xs tabular text-muted">{fmtClock(h.t_s)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Right-hand panel in Simulate mode. */
export function SimulatePanel({ project, run, estimate, replay, th, onAsk }: {
  project: ProjectDetail; run: RunOut | undefined; estimate: RunResult | null | undefined; replay: Replay | null;
  th: Thresholds; onAsk: (h: Hotspot) => void;
}) {
  const venue = project.version.venue;
  const label = useMemo(() => exitLabeler(venue), [venue]);
  const start = useStartRun();
  const cancel = useCancelRun();
  const setActive = useUi((s) => s.setActiveRun);
  const blocked = useUi((s) => s.blockedExits);
  const clearBlocked = useUi((s) => s.clearBlocked);
  const preview = useUi((s) => s.tier1Preview);
  const fly = useUi((s) => s.flyToPoint);
  const select = useUi((s) => s.select);
  const running = run && (run.status === "queued" || run.status === "running");
  const result = run?.result ?? null;
  const counts = useMemo(() => replay?.traj.counts() ?? [], [replay]);

  const launch = (tier: 2 | 3, withBlocked: boolean) =>
    start.mutate({ project_id: project.id, tier, blocked_exits: withBlocked ? blocked : [],
                   label: withBlocked ? `Blocked: ${blocked.map(label).join(", ")}` : "Stress test" },
                 { onSuccess: (r) => setActive(r.id), onError: (e) => toast.error(e.message) });

  const pick = (h: Hotspot) => {
    fly(h.x, h.y, h.floor_id);
    select({ kind: "hotspot", id: `${h.floor_id}:${h.x}:${h.y}`, floorId: h.floor_id, x: h.x, y: h.y });
  };

  return (
    <div className="space-y-5">
      {!running && (
        <Button variant="primary" size="lg" className="w-full" disabled={!project.validation.ok || start.isPending}
                onClick={() => launch(3, false)}>
          <Play />{t("workspace.run_stress_test")}
        </Button>
      )}
      {!project.validation.ok && <p className="text-sm text-danger">{t("workspace.invalid_venue")}</p>}
      {project.validation.ok && <ScenarioMatrix projectId={project.id} version={project.version.version} danger={th.danger} warn={th.warn} />}
      {running && run && <RunStatus run={run} onCancel={() => cancel.mutate(run.id)} />}
      {run?.status === "failed" && <ErrorState title={t("workspace.stress_test_failed")} message={run.error ?? ""} />}
      {run?.status === "timeout" && <ErrorState title={t("workspace.stress_test_failed")} message={run.error ?? t("ui.simulatepanel.stopped_at_the_time_limit")} />}

      {blocked.length > 0 && (
        <section className="rounded-[var(--radius-panel)] border border-danger/30 bg-danger-soft/60 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold"><Ban className="size-4 text-danger" />{t("ui.simulatepanel.break_it_yourself")}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {blocked.map((id) => <Badge key={id} tone="danger">{label(id)}</Badge>)}
          </div>
          {preview?.metrics && (
            <p className="mt-2 text-sm">
              {t("ui.simulatepanel.estimate_out")} <b className="tabular">{fmtDuration(preview.metrics.evac_time_p95_s)}</b>
              {estimate?.metrics?.evac_time_p95_s != null && preview.metrics.evac_time_p95_s != null && (
                <> ({preview.metrics.evac_time_p95_s >= estimate.metrics.evac_time_p95_s ? "+" : ""}{fmtDuration(preview.metrics.evac_time_p95_s - estimate.metrics.evac_time_p95_s)})</>
              )}{t("ui.simulatepanel.density_up_to")} <b className="tabular">{fmtNum(preview.metrics.peak_density_ppm2, 1)}</b>.
              {(preview.metrics.agents_not_evacuated ?? 0) > 0 && <> <b className="text-danger">{t("ui.simulatepanel.no_way_out", { n: fmtInt(preview.metrics.agents_not_evacuated) })}</b></>}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="primary" onClick={() => launch(2, true)} disabled={start.isPending}>{t("workspace.confirm_with_simulation")}</Button>
            <Button size="sm" variant="ghost" onClick={clearBlocked}><X />{t("ui.simulatepanel.reopen_all")}</Button>
          </div>
        </section>
      )}

      <VerdictCard run={result ?? estimate} th={th} venue={venue} />

      {result?.metrics && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <MetricTile label={t("metrics.evac_p95")} value={result.metrics.evac_time_p95_s != null ? fmtDuration(result.metrics.evac_time_p95_s) : "–"} run={result}
                        formula="95th percentile of the times people pass an exit, from the start of movement (pre-movement excluded)." />
            <MetricTile label={t("metrics.peak_density")} value={fmtNum(result.metrics.peak_density_ppm2, 1)} unit="per m²" run={result}
                        tone={(result.metrics.peak_density_ppm2 ?? 0) >= th.danger ? "danger" : (result.metrics.peak_density_ppm2 ?? 0) >= th.warn ? "caution" : "egress"}
                        formula="Max over time of the Gaussian-smoothed 1 m density grid, divided by the walkable area of each cell." />
            <MetricTile label={t("metrics.above_danger")} value={fmtDuration(result.metrics.time_above_danger_s)} run={result}
                        tone={(result.metrics.time_above_danger_s ?? 0) >= th.dangerMinS ? "danger" : "egress"}
                        formula={t("ui.simulatepanel.danger_time_help", { danger: th.danger })} />
            <MetricTile label={t("metrics.not_evacuated")} value={fmtInt(result.metrics.agents_not_evacuated)} run={result}
                        tone={(result.metrics.agents_not_evacuated ?? 0) > 0 ? "caution" : "egress"}
                        formula="People still inside when the run stopped (time limit or no route)." />
          </div>
          {replay && counts.length > 1 && (
            <section>
              <PanelTitle>{t("metrics.people_inside")}</PanelTitle>
              <EvacuationCurve times={replay.traj.index.times} counts={counts} p95={result.metrics.evac_time_p95_s} />
            </section>
          )}
          {replay?.density && replay.density.index.peak_series.length > 1 && (
            <section>
              <PanelTitle>{t("metrics.density_over_time")}</PanelTitle>
              <DensityCurve series={replay.density.index.peak_series} duration={replay.traj.duration} warn={th.warn} danger={th.danger} />
            </section>
          )}
          <Separator />
          <section className="space-y-2">
            <PanelTitle>{t("metrics.per_exit")}</PanelTitle>
            <ExitUse run={result} label={label} />
          </section>
          <section className="space-y-2">
            <PanelTitle action={result.hotspots?.length ? (
              <Button size="sm" variant="ghost" onClick={() => result.hotspots?.[0] && onAsk(result.hotspots[0])}>
                <MessageCircleQuestion />{t("redteam.ask")}
              </Button>) : undefined}>{t("metrics.hotspots")}</PanelTitle>
            <HotspotList hotspots={result.hotspots ?? []} onPick={pick} label={label} />
          </section>
          {result.notes && result.notes.length > 0 && (
            <ul className="space-y-1 text-xs text-muted">{result.notes.map((n) => <li key={n}>· {n}</li>)}</ul>
          )}
        </>
      )}
      <p className="text-xs text-muted">{t("tools.block_hint")}</p>
    </div>
  );
}
