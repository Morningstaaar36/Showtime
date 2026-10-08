import { useQuery } from "@tanstack/react-query";
import { CloudRain, FlaskConical, Footprints, RotateCcw, Users, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { usePatchProject, useStartRun } from "@/api/queries";
import type { PatchOpIn, ProjectDetail, WhatIfOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { PanelTitle } from "@/components/ui/misc";
import { Slider } from "@/components/ui/slider";
import { exitName } from "@/lib/venueText";
import { fmtInt } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useUi } from "@/state/ui";
import { ScoreGauge, useCountTo } from "./ScoreGauge";

const SPEEDS = [
  { key: "normal", label: "Normal", factor: 1.0, icon: Footprints },
  { key: "rain", label: "Rain", factor: 0.85, icon: CloudRain },
  { key: "families", label: "Families, elderly", factor: 0.75, icon: Users },
  { key: "smoke", label: "Smoke or dark", factor: 0.6, icon: Zap },
] as const;

interface Params { people_scale: number; speed_factor: number; blocked_exits: string[] }

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
    <div className="rounded-[8px] border border-border px-2.5 py-1.5">
      <p className="text-2xs text-muted">{label}</p>
      <p className={cn("tabular text-sm font-semibold", worse && "text-danger")}>{value === null ? "—" : digits ? v.toFixed(digits) : fmtInt(Math.round(v))}<span className="ml-0.5 text-2xs font-normal text-muted">{unit}</span></p>
    </div>
  );
}

/** Planning score for the plan as it stands, and a what-if lab that recomputes it live. */
export function WhatIfLab({ project, runId }: { project: ProjectDetail; runId?: string | null }) {
  const venue = project.version.venue;
  const version = project.version.version;
  const exits = useMemo(() => venue.floors.flatMap((f) => f.exits.map((e) => ({ id: e.id, name: exitName(f, e) }))), [venue]);
  const base = useWhatIf(project.id, version, { people_scale: 1, speed_factor: 1, blocked_exits: [] }, runId);
  // what-ifs use the instant estimate, so compare them with the instant estimate of the plan
  const baseInstant = useWhatIf(project.id, version, { people_scale: 1, speed_factor: 1, blocked_exits: [] }, null);
  const [scale, setScale] = useState(1);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]["key"]>("normal");
  const [closed, setClosed] = useState<string[]>([]);
  const factor = SPEEDS.find((s) => s.key === speed)!.factor;
  const changed = scale !== 1 || factor !== 1 || closed.length > 0;
  const lab = useWhatIf(project.id, version, { people_scale: scale, speed_factor: factor, blocked_exits: closed });
  const patch = usePatchProject(project.id);
  const start = useStartRun();
  const setBlocked = useUi((s) => s.toggleBlocked);
  const clearBlocked = useUi((s) => s.clearBlocked);
  useEffect(() => { setScale(1); setSpeed("normal"); setClosed([]); }, [project.id]);

  const reset = () => { setScale(1); setSpeed("normal"); setClosed([]); clearBlocked(); };
  const applyCrowd = () => {
    const ops = venue.floors.flatMap((f) => f.zones.map((z) => ({ op: "set_people", zone_id: z.id, people: Math.round(z.people * scale) }))) as unknown as PatchOpIn[];
    patch.mutate({ patch: { ops }, message: `Crowd × ${scale.toFixed(2)}` }, {
      onSuccess: () => { toast.success("Crowd size applied to the plan"); setScale(1); },
      onError: (e) => toast.error(e.message),
    });
  };
  const simulate = () => {
    start.mutate({
      project_id: project.id, tier: 3, seed: 42, blocked_exits: closed,
      events: factor < 1 ? [{ type: "slowdown", factor, at_s: 0 }] : [],
      label: "What-if",
    }, {
      onSuccess: () => toast.success("What-if simulation started. Open Simulate to watch it."),
      onError: (e) => toast.error(e.message),
    });
  };

  const b = base.data, w = lab.data;
  return (
    <section className="space-y-3" aria-label="Planning score and what-if lab">
      {b && (
        <div className="rounded-[12px] border border-border bg-gradient-to-br from-surface to-signal-soft/40 p-3">
          <ScoreGauge score={b.score} />
        </div>
      )}
      <details className="group rounded-[12px] border border-border p-3" open={changed || undefined}>
        <summary className="flex cursor-pointer items-center justify-between">
          <PanelTitle><FlaskConical className="mr-1.5 inline size-4 text-signal" />What if…</PanelTitle>
          <span className="text-2xs text-muted">instant, nothing is saved</span>
        </summary>
        <div className="mt-3 space-y-4">
          <div>
            <div className="flex items-baseline justify-between text-xs"><span>Crowd size</span>
              <span className="tabular font-semibold">{fmtInt(Math.round(venue.floors.reduce((n, f) => n + f.zones.reduce((m, z) => m + z.people, 0), 0) * scale))} people ({Math.round(scale * 100)}%)</span></div>
            <Slider className="mt-2" min={25} max={300} step={5} value={[Math.round(scale * 100)]} onValueChange={([v]) => setScale(v / 100)} thumbLabel="Crowd size" />
          </div>
          <div>
            <p className="text-xs">Walking speed</p>
            <div className="mt-1.5 grid grid-cols-2 gap-1.5">
              {SPEEDS.map((s) => (
                <button key={s.key} type="button" onClick={() => setSpeed(s.key)}
                        className={cn("flex items-center gap-1.5 rounded-[6px] border px-2 py-1 text-xs",
                          speed === s.key ? "border-signal bg-signal-soft text-ink" : "border-border text-muted hover:text-ink")}>
                  <s.icon className="size-3.5" />{s.label}<span className="ml-auto tabular text-2xs">{Math.round(s.factor * 100)}%</span>
                </button>
              ))}
            </div>
          </div>
          {exits.length > 0 && (
            <div>
              <p className="text-xs">Close exits</p>
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
              <ScoreGauge score={w.score} size={64} label="What-if score" delta={baseInstant.data ? w.score.score - baseInstant.data.score.score : undefined} />
              <div className="grid grid-cols-3 gap-1.5">
                <Stat label="95% out" value={w.metrics.evac_time_p95_s} unit=" s" worse={!!baseInstant.data?.metrics.evac_time_p95_s && (w.metrics.evac_time_p95_s ?? 0) > baseInstant.data.metrics.evac_time_p95_s * 1.15} />
                <Stat label="Peak per m²" value={w.metrics.peak_density_ppm2} unit="" digits={1} worse={w.metrics.peak_density_ppm2 >= 5} />
                <Stat label="Safe capacity" value={w.capacity.safe_people} unit="" worse={w.people > w.capacity.safe_people} />
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="primary" disabled={!changed || scale !== 1 || start.isPending} onClick={simulate}
                    title={scale !== 1 ? "Apply the crowd size first, then simulate" : undefined}>Simulate this</Button>
            {scale !== 1 && <Button size="sm" onClick={applyCrowd} disabled={patch.isPending}>Apply crowd size</Button>}
            {changed && <Button size="sm" variant="ghost" onClick={reset}><RotateCcw />Reset</Button>}
          </div>
        </div>
      </details>
    </section>
  );
}
