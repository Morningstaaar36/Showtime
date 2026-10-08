import { AlertTriangle, CheckCircle2, CircleAlert, Info, ShieldAlert, ShieldCheck, ShieldQuestion, Trash2, Wind } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { usePatchProject, useStageCheck } from "@/api/queries";
import type { Validation } from "@/api/types";
import type { Check, PatchOpIn, ProjectDetail, RunResult, Venue } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { PanelTitle, Separator, Spinner } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { t } from "@/i18n";
import { fmtInt, fmtNum, fmtSpeed } from "@/lib/format";
import { cn } from "@/lib/utils";
import { polygonArea } from "@/scene/geom";
import { useUi } from "@/state/ui";
import { tierLabel, type Thresholds, verdictOf } from "./verdict";
import { EstimatesPanel } from "./EstimatesPanel";
import { OfficerCard } from "./OfficerCard";
import { WhatIfLab } from "./WhatIfLab";
import { WindPanel } from "./WindPanel";
import type { CountdownOut } from "@/api/types";

import { displayNames } from "@/lib/venueText";
export { textHumanizer } from "@/lib/venueText";

export function exitLabeler(venue: Venue): (id: string) => string {
  const names = displayNames(venue);
  const map = new Map<string, string>();
  for (const f of venue.floors) {
    for (const e of f.exits) map.set(e.id, names.get(e.id) ?? e.id);
    for (const o of f.obstacles) map.set(o.id, o.label ?? o.id);
  }
  return (id) => map.get(id) ?? id;
}

export function VerdictCard({ run, th, venue, compact }: { run: RunResult | null | undefined; th: Thresholds; venue: Venue; compact?: boolean }) {
  const v = verdictOf(run, th, exitLabeler(venue));
  const icon = v.level === "fails" ? <ShieldAlert /> : v.level === "at_risk" ? <ShieldQuestion /> : v.level === "holds" ? <ShieldCheck /> : <ShieldQuestion />;
  const tone = v.level === "fails" ? "border-danger/35 bg-danger-soft" : v.level === "at_risk" ? "border-caution/35 bg-caution-soft"
    : v.level === "holds" ? "border-egress/35 bg-egress-soft" : "border-border bg-surface-2";
  const iconTone = v.level === "fails" ? "text-danger" : v.level === "at_risk" ? "text-caution" : v.level === "holds" ? "text-egress" : "text-line";
  return (
    <section aria-label="Plan verdict" className={cn("rounded-[10px] border p-4", tone)}>
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 [&_svg]:size-6", iconTone)}>{icon}</span>
        <div className="min-w-0">
          <p className="text-lg font-semibold leading-tight tracking-tight">{v.headline}</p>
          {run && <p className="mt-0.5 text-xs text-muted">{tierLabel(run)}</p>}
        </div>
      </div>
      {!compact && v.sentences.length > 0 && (
        <div className="mt-3 space-y-1 text-sm">{v.sentences.map((s) => <p key={s}>{s}</p>)}</div>
      )}
      {v.reasons.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {v.reasons.map((r) => <li key={r} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-danger" />{r}</li>)}
        </ul>
      )}
      {!run && <p className="mt-2 text-sm text-muted">{t("workspace.no_run")}</p>}
    </section>
  );
}

function VenueFacts({ venue }: { venue: Venue }) {
  const units = useUi((s) => s.units);
  const people = venue.floors.reduce((a, f) => a + f.zones.reduce((b, z) => b + z.people, 0), 0);
  const width = venue.floors.reduce((a, f) => a + f.exits.filter((e) => !e.blocked).reduce((b, e) => b + e.width_m, 0), 0);
  const area = venue.floors.reduce((a, f) => a + polygonArea(f.walkable), 0);
  const perM = width ? people / width : 0;
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-[8px] border border-border bg-border text-sm">
      {[
        [t("inspector.people_total"), fmtInt(people)],
        ["Exits open", `${venue.floors.reduce((a, f) => a + f.exits.filter((e) => !e.blocked).length, 0)}`],
        [t("inspector.exit_width_total"), units === "imperial" ? `${fmtNum(width * 3.281, 0)} ft` : `${fmtNum(width, 1)} m`],
        ["People per metre of exit", fmtNum(perM, 0)],
        ["Floor area", `${fmtInt(area)} m²`],
        ["Floors", String(venue.floors.length)],
      ].map(([k, val]) => (
        <div key={k} className="bg-surface px-3 py-2">
          <dt className="text-xs text-muted">{k}</dt>
          <dd className="font-semibold tabular">{val}</dd>
        </div>
      ))}
    </dl>
  );
}

function Checks({ checks }: { checks: Check[] }) {
  const fly = useUi((s) => s.flyToPoint);
  const select = useUi((s) => s.select);
  const items = checks.filter((c) => c.severity !== "info");
  if (!items.length) {
    return <p className="flex items-center gap-2 text-sm text-egress"><CheckCircle2 className="size-4" />{t("inspector.checks_ok")}</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((c, i) => (
        <li key={i}>
          <button type="button" className="flex w-full gap-2 rounded-[8px] border border-border p-2.5 text-left text-sm hover:bg-surface-2"
                  onClick={() => {
                    if (c.x != null && c.y != null) fly(c.x, c.y, c.floor_id ?? "F0");
                    if (c.target_ids?.[0]) select({ kind: "obstacle", id: c.target_ids[0], floorId: c.floor_id ?? "F0" });
                  }}>
            {c.severity === "error" ? <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />}
            <span><span className="block">{c.message}</span>{c.hint && <span className="block text-xs text-muted">{c.hint}</span>}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function StagePanel({ project }: { project: ProjectDetail }) {
  const venue = project.version.venue;
  const stage = venue.stage!;
  const units = useUi((s) => s.units);
  const check = useStageCheck(project.id, JSON.stringify(stage), true);
  const patch = usePatchProject(project.id);
  const set = (param: string, value: number) =>
    patch.mutate({ patch: { ops: [{ op: "set_stage_param", param, value } as PatchOpIn] } },
                 { onError: (e) => toast.error(e.message) });
  return (
    <section className="space-y-3">
      <PanelTitle>{t("inspector.stage")}</PanelTitle>
      <div className="rounded-[8px] border border-border bg-surface-2 p-3">
        <div className="flex items-center gap-2 text-sm text-muted"><Wind className="size-4" />{t("inspector.wind_limit")}</div>
        {check.isLoading ? <Spinner className="mt-2" /> : check.data ? (
          <>
            <p className="mt-1 text-xl font-semibold tabular">{fmtSpeed(check.data.v_limit_ms, units)}</p>
            <p className="text-xs text-muted">Screening estimate · governed by {check.data.governing} · Pynite frame model</p>
          </>
        ) : <p className="mt-1 text-sm text-muted">Unavailable</p>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <NumberField label={t("inspector.ballast")} unit="kg" value={stage.ballast_kg_per_leg} step={100} onCommit={(v) => set("ballast_kg_per_leg", v)} />
        <NumberField label={t("inspector.legs")} unit="" value={stage.legs} step={2} onCommit={(v) => set("legs", v)} />
        <NumberField label={t("inspector.roof_area")} unit="m²" value={stage.roof_area_m2} step={10} onCommit={(v) => set("roof_area_m2", v)} />
        <NumberField label={t("inspector.banner_area")} unit="m²" value={stage.banner_area_m2 ?? 0} step={5} onCommit={(v) => set("banner_area_m2", v)} />
      </div>
    </section>
  );
}

function NumberField({ label, unit, value, step, onCommit }: { label: string; unit: string; value: number; step: number; onCommit: (v: number) => void }) {
  const [v, setV] = useState(String(value));
  useEffect(() => setV(String(value)), [value]);
  const commit = () => {
    const n = Number(v);
    if (Number.isFinite(n) && n !== value) onCommit(n);
  };
  const id = `f-${label.replace(/\W/g, "")}`;
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="text-xs text-muted">{label}</Label>
      <div className="flex items-center gap-1.5">
        <Input id={id} type="number" step={step} value={v} onChange={(e) => setV(e.target.value)} onBlur={commit}
               onKeyDown={(e) => e.key === "Enter" && commit()} className="h-8" />
        {unit && <span className="text-xs text-muted">{unit}</span>}
      </div>
    </div>
  );
}

function SelectionEditor({ project }: { project: ProjectDetail }) {
  const selection = useUi((s) => s.selection)!;
  const select = useUi((s) => s.select);
  const venue = project.version.venue;
  const patch = usePatchProject(project.id);
  const run = (ops: PatchOpIn[], msg?: string) => patch.mutate({ patch: { ops }, message: msg },
    { onSuccess: (r) => toast.success(t("workspace.saved", { n: r.version.version })), onError: (e) => toast.error(e.message) });
  const floor = venue.floors.find((f) => f.floor_id === selection.floorId) ?? venue.floors[0];
  const exit = floor.exits.find((e) => e.id === selection.id);
  const zone = floor.zones.find((z) => z.id === selection.id);
  const obstacle = floor.obstacles.find((o) => o.id === selection.id);

  if (exit) {
    return (
      <section className="space-y-3">
        <PanelTitle action={<Badge tone={exit.blocked ? "danger" : "egress"}>{exit.blocked ? "Blocked" : "Exit"}</Badge>}>{exit.label ?? exit.id}</PanelTitle>
        <NumberField label={t("inspector.width")} unit="m" value={exit.width_m} step={0.5}
                     onCommit={(v) => run([{ op: "resize", target: exit.id, width_m: v } as PatchOpIn])} />
        <div className="flex items-center justify-between text-sm">
          <label htmlFor="blk">Blocked in the plan</label>
          <Switch id="blk" checked={!!exit.blocked} onCheckedChange={(v) => run([{ op: "block_exit", exit_id: exit.id, blocked: v } as PatchOpIn])} />
        </div>
        <Button variant="danger-ghost" size="sm" onClick={() => { run([{ op: "remove_exit", exit_id: exit.id } as PatchOpIn]); select(null); }}><Trash2 />{t("inspector.remove")}</Button>
      </section>
    );
  }
  if (zone) {
    const area = polygonArea(zone.polygon);
    return (
      <section className="space-y-3">
        <PanelTitle action={<Badge tone="signal">Zone</Badge>}>{zone.label ?? zone.id}</PanelTitle>
        <NumberField label={t("inspector.people")} unit="people" value={zone.people} step={50}
                     onCommit={(v) => run([{ op: "set_people", zone_id: zone.id, people: Math.round(v) } as PatchOpIn])} />
        <p className="text-sm text-muted">{t("inspector.people_per_m2", { n: fmtNum(zone.people / Math.max(area, 1), 1) })} · {fmtInt(area)} m²</p>
        <Button variant="danger-ghost" size="sm" onClick={() => { run([{ op: "remove_zone", zone_id: zone.id } as PatchOpIn]); select(null); }}><Trash2 />{t("inspector.remove")}</Button>
      </section>
    );
  }
  if (obstacle) {
    return (
      <section className="space-y-3">
        <PanelTitle action={<Badge tone="outline">{obstacle.kind}</Badge>}>{obstacle.label ?? obstacle.id}</PanelTitle>
        <p className="text-sm text-muted">Drag the arrows in 3D to move it (snaps to 0.5 m), or type a change below.</p>
        <div className="flex gap-2">
          {([[0, 2, "North 2 m"], [0, -2, "South 2 m"], [-2, 0, "West 2 m"], [2, 0, "East 2 m"]] as const).map(([dx, dy, l]) => (
            <Button key={l} size="sm" variant="subtle" onClick={() => run([{ op: "move", target: obstacle.id, dx, dy } as PatchOpIn])}>{l}</Button>
          ))}
        </div>
        {obstacle.kind !== "stage" && (
          <Button variant="danger-ghost" size="sm" onClick={() => { run([{ op: "remove_obstacle", obstacle_id: obstacle.id } as PatchOpIn]); select(null); }}><Trash2 />{t("inspector.remove")}</Button>
        )}
      </section>
    );
  }
  return <p className="text-sm text-muted">{t("inspector.nothing")}</p>;
}

function RulesSection({ project }: { project: ProjectDetail }) {
  const rules = useQuery({
    queryKey: ["rules", project.id, project.current_version],
    queryFn: () => api.post<Validation>(`/venues/${project.id}/validate`),
    staleTime: 60_000,
  });
  const rows = rules.data?.rules ?? [];
  if (!rows.length) return null;
  const fails = rows.filter((r) => r.status === "fail").length;
  return (
    <section className="space-y-2">
      <PanelTitle action={<Badge tone={fails ? "caution" : "egress"}>{fails ? `${fails} to review` : "all pass"}</Badge>}>
        {t("inspector.rules")}
      </PanelTitle>
      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li key={r.rule_id} className="flex gap-2 text-sm">
            {r.status === "pass" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-egress" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />}
            <span>
              {r.message}{" "}
              {r.source_url && <a className="text-xs text-signal hover:underline" href={r.source_url} target="_blank" rel="noreferrer">source</a>}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted">{t("inspector.rule_unconfirmed")}. Local codes differ.</p>
    </section>
  );
}

/** Right-hand panel in Plan mode. */
export function PlanInspector({ project, estimate, th, countdown }: { project: ProjectDetail; estimate: RunResult | null | undefined; th: Thresholds; countdown?: CountdownOut }) {
  const selection = useUi((s) => s.selection);
  const venue = project.version.venue;
  const stageSelected = selection?.kind === "stage" || (selection && venue.stage && selection.id === "stage");
  return (
    <div className="space-y-5">
      <VerdictCard run={estimate} th={th} venue={venue} />
      {!selection && <WhatIfLab project={project} runId={estimate?.tier === 3 ? estimate.run_id : null} />}
      {selection && selection.kind !== "hotspot" && !stageSelected && <><SelectionEditor project={project} /><Separator /></>}
      {venue.stage && (stageSelected || !selection) && <><StagePanel project={project} /><Separator /></>}
      {!selection && <><OfficerCard projectId={project.id} /><Separator /></>}
      {!selection && <><EstimatesPanel project={project} /><Separator /></>}
      {venue.mode === "outdoor" && !selection && countdown && (
        <><WindPanel data={countdown} eventStart={venue.location?.event_start} /><Separator /></>
      )}
      <section className="space-y-3">
        <PanelTitle>{t("inspector.venue")}</PanelTitle>
        <VenueFacts venue={venue} />
      </section>
      <section className="space-y-3">
        <PanelTitle>{t("inspector.checks")}</PanelTitle>
        <Checks checks={project.validation.checks} />
      </section>
      {!selection && <RulesSection project={project} />}
      <p className="flex gap-2 text-xs text-muted"><Info className="mt-0.5 size-3.5 shrink-0" />{t("app.disclaimer")}</p>
    </div>
  );
}
