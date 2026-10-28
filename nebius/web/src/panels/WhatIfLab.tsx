import { useQuery } from "@tanstack/react-query";
import { CloudRain, Footprints, Gauge, type LucideIcon, RotateCcw, Users, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { usePatchProject, useStartRun } from "@/api/queries";
import type { PatchOpIn, ProjectDetail, WhatIfOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { Slider } from "@/components/ui/slider";
import { exitName } from "@/lib/venueText";
import { fmtInt } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useUi } from "@/state/ui";
import { ScoreGauge, useCountTo } from "./ScoreGauge";
import { useSpeedPresets } from "./speedPresets";
import { useThresholds } from "./useThresholds";

/** Icons for the server's speed presets; a preset this page does not know yet gets a plain one. */
const SPEED_ICON: Record<string, LucideIcon> = { normal: Footprints, rain: CloudRain, families: Users, smoke: Zap };
/** A what-if is shown as slower only past this share of the plan's own estimate: the instant
 * estimate moves a little with any change, and a few percent is not a finding. */
const SLOWER_RATIO = 1.15;

interface Params { people_scale: number; speed_factor: number; blocked_exits: string[] }
/** The plan as it stands (a constant, so the debounce below settles). */
const BASE: Params = { people_scale: 1, speed_factor: 1, blocked_exits: [] };

function useWhatIf(projectId: string, version: number, params: Params, runId?: string | null) {
  const [debounced, setDebounced] = useState(params);
  useEffect(() => { const h = setTimeout(() => setDebounced(params), 220); return () => clearTimeout(h); }, [params]);
  return useQuery({
    queryKey: ["whatif", projectId, version, runId ?? null, debounced],
    queryFn: () => api.post<WhatIfOut>(`/projects/${projectId}/whatif`, { ...debounced, version, run_id: runId ?? null }),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });
}

function Stat({ label, value, unit, worse, digits = 0 }: { label: string; value: number | null; unit: string; worse?: boolean; digits?: number }) {
  const v = useCountTo(value ?? 0);
  return (
    <div className="rounded-[var(--radius-control)] border border-border px-2.5 py-1.5">
      <p className="text-2xs text-muted">{label}</p>
      <p className={cn("tabular text-sm font-semibold", worse && "text-danger")}>{value === null ? "—" : digits ? v.toFixed(digits) : fmtInt(Math.round(v))}<span className="ml-0.5 text-2xs font-normal text-muted">{unit}</span></p>
    </div>
  );
}

/** Planning score for the plan as it stands (click it for the breakdown). */
export function PlanScore({ project, runId }: { project: ProjectDetail; runId?: string | null }) {
  const base = useWhatIf(project.id, project.version.version, BASE, runId);
  if (!base.data) return null;
  return (
    <div className="rounded-[var(--radius-panel)] bg-gradient-to-br from-signal-soft to-pink-soft/60 p-3">
      <ScoreGauge score={base.data.score} />
    </div>
  );
}

/** What-if lab: change the crowd, the walking speed or close exits; the instant estimate updates live. */
export function WhatIfLab({ project }: { project: ProjectDetail }) {
  const venue = project.version.venue;
  const version = project.version.version;
  const exits = useMemo(() => venue.floors.flatMap((f) => f.exits.map((e) => ({ id: e.id, name: exitName(f, e) }))), [venue]);
  // what-ifs use the instant estimate, so compare them with the instant estimate of the plan
  const baseInstant = useWhatIf(project.id, version, BASE, null);
  const th = useThresholds();
  const [scale, setScale] = useState(1);
  const speeds = useSpeedPresets();
  const [speed, setSpeed] = useState("normal");
  const [closed, setClosed] = useState<string[]>([]);
  const factor = speeds.find((s) => s.key === speed)?.factor ?? 1;
  const changed = scale !== 1 || factor !== 1 || closed.length > 0;
  const params = useMemo(() => ({ people_scale: scale, speed_factor: factor, blocked_exits: closed }), [scale, factor, closed]);
  const lab = useWhatIf(project.id, version, params);
  const patch = usePatchProject(project.id);
  const start = useStartRun();
  const setBlocked = useUi((s) => s.toggleBlocked);
  const clearBlocked = useUi((s) => s.clearBlocked);
  useEffect(() => { setScale(1); setSpeed("normal"); setClosed([]); }, [project.id]);

  const reset = () => { setScale(1); setSpeed("normal"); setClosed([]); clearBlocked(); };
  const applyCrowd = () => {
    const ops = venue.floors.flatMap((f) => f.zones.map((z) => ({ op: "set_people", zone_id: z.id, people: Math.round(z.people * scale) }))) as unknown as PatchOpIn[];
    patch.mutate({ patch: { ops }, message: t("ui.whatiflab.crowd_message", { scale: scale.toFixed(2) }) }, {
      onSuccess: () => { toast.success(t("ui.whatiflab.crowd_size_applied_to_the")); setScale(1); },
      onError: (e) => toast.error(e.message),
    });
  };
  const simulate = () => {
    start.mutate({
      project_id: project.id, tier: 3, blocked_exits: closed,
      events: factor < 1 ? [{ type: "slowdown", factor, at_s: 0 }] : [],
      label: t("ui.whatiflab.run_label"),
    }, {
      onSuccess: () => toast.success(t("ui.whatiflab.what_if_simulation_started_open")),
      onError: (e) => toast.error(e.message),
    });
  };

  const w = lab.data;
  return (
    <section className="space-y-4" aria-label={t("workspace.day_whatif")}>
      <p className="text-xs text-muted">{t("workspace.whatif_lead")}</p>
      <div>
        <div className="flex items-baseline justify-between text-xs"><span>{t("ui.whatiflab.crowd_size")}</span>
          <span className="tabular font-semibold">{t("ui.whatiflab.people_share", { n: fmtInt(Math.round(venue.floors.reduce((n, f) => n + f.zones.reduce((m, z) => m + z.people, 0), 0) * scale)), pct: Math.round(scale * 100) })}</span></div>
        <Slider className="mt-2" min={25} max={300} step={5} value={[Math.round(scale * 100)]} onValueChange={([v]) => setScale(v / 100)} thumbLabel={t("ui.whatiflab.crowd_size")} />
      </div>
      <div>
        <p className="text-xs">{t("ui.whatiflab.walking_speed")}</p>
        <div className="mt-1.5 grid grid-cols-2 gap-1.5">
          {speeds.map((s) => {
            const Icon = SPEED_ICON[s.key] ?? Gauge;
            return (
              <button key={s.key} type="button" onClick={() => setSpeed(s.key)}
                      className={cn("flex items-center gap-1.5 rounded-[var(--radius-control)] border px-2 py-1 text-xs",
                        speed === s.key ? "border-signal bg-signal-soft text-ink" : "border-border text-muted hover:text-ink")}>
                <Icon className="size-3.5" />{t(`ui.whatiflab.speed.${s.key}`)}<span className="ml-auto tabular text-2xs">{Math.round(s.factor * 100)}%</span>
              </button>
            );
          })}
        </div>
      </div>
      {exits.length > 0 && (
        <div>
          <p className="text-xs">{t("ui.whatiflab.close_exits")}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {exits.map((e) => (
              <button key={e.id} type="button"
                      onClick={() => { setClosed((c) => c.includes(e.id) ? c.filter((x) => x !== e.id) : [...c, e.id]); setBlocked(e.id); }}
                      className={cn("rounded-full border px-2 py-0.5 text-xs",
                        closed.includes(e.id) ? "border-danger bg-danger-soft text-danger line-through" : "border-border text-muted hover:text-ink")}>
                {e.name}
              </button>
            ))}
          </div>
        </div>
      )}
      {w && (
        <div className={cn("space-y-2 transition-opacity", lab.isFetching && "opacity-70")}>
          <ScoreGauge score={w.score} size={64} label={t("ui.whatiflab.score")} delta={baseInstant.data ? w.score.score - baseInstant.data.score.score : undefined} />
          <div className="grid grid-cols-3 gap-1.5">
            <Stat label={t("metrics.p95_out")} value={w.metrics.evac_time_p95_s} unit={t("ui.whatiflab.unit_s")} worse={!!baseInstant.data?.metrics.evac_time_p95_s && (w.metrics.evac_time_p95_s ?? 0) > baseInstant.data.metrics.evac_time_p95_s * SLOWER_RATIO} />
            <Stat label={t("ui.whatiflab.peak")} value={w.metrics.peak_density_ppm2} unit="" digits={1} worse={w.metrics.peak_density_ppm2 >= th.danger} />
            <Stat label={t("ui.whatiflab.capacity")} value={w.capacity.safe_people} unit="" worse={w.people > w.capacity.safe_people} />
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" disabled={!changed || scale !== 1 || start.isPending} onClick={simulate}
                title={scale !== 1 ? t("ui.whatiflab.apply_the_crowd_size_first") : undefined}>{t("ui.whatiflab.simulate_this")}</Button>
        {scale !== 1 && <Button size="sm" onClick={applyCrowd} disabled={patch.isPending}>{t("ui.whatiflab.apply_crowd_size")}</Button>}
        {changed && <Button size="sm" variant="ghost" onClick={reset}><RotateCcw />{t("ui.whatiflab.reset")}</Button>}
      </div>
    </section>
  );
}
