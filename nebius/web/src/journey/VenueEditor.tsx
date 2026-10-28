/** Collaborative editing on the "Check your venue" screen: one card for the selected door,
 * barrier or area (numbers, existing/proposed, provenance, lock) and lists to find them. */
import { DoorOpen, Fence, Info, Lock, LockOpen, MapPin, Minus, Move, Plus, Trash2, Users } from "lucide-react";
import type * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Exit, Obstacle, ProjectDetail, SceneSnapshot, Venue, Zone } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { t } from "@/i18n";
import { annotateOp, annotationOf, BASES, type Basis, type ChangeStatus, type ObjectAnnotation } from "@/lib/annotations";
import { fmtInt, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { displayNames } from "@/lib/venueText";
import { Tip } from "@/components/ui/tooltip";
import { floorNamer } from "@/panels/FloorMenu";
import { centroid, floorsBottomUp, resolveFloorView } from "@/scene/geom";
import { type Selection, useUi } from "@/state/ui";
import { useVenueEdit } from "./useVenueEdit";
import { ZoneProfileEditor } from "@/panels/ZoneProfile";

type Found =
  | { what: "exit"; item: Exit; floorId: string }
  | { what: "obstacle"; item: Obstacle; floorId: string }
  | { what: "zone"; item: Zone; floorId: string };

function findObject(venue: Venue, id: string): Found | null {
  for (const f of venue.floors) {
    const e = f.exits.find((x) => x.id === id);
    if (e) return { what: "exit", item: e, floorId: f.floor_id };
    const o = f.obstacles.find((x) => x.id === id);
    if (o) return { what: "obstacle", item: o, floorId: f.floor_id };
    const z = f.zones.find((x) => x.id === id);
    if (z) return { what: "zone", item: z, floorId: f.floor_id };
  }
  return null;
}

/** Provenance from the scene contract when it describes this version, else from the venue. */
function annotationWithScene(venue: Venue, scene: SceneSnapshot | undefined, version: number, id: string): ObjectAnnotation {
  const a = annotationOf(venue, id);
  const fromScene = scene?.identity.venue_version === version ? scene.objects.find((o) => o.id === id)?.provenance : undefined;
  return fromScene ? { ...a, provenance: { ...fromScene, basis: fromScene.basis as Basis } } : a;
}

function NumberInput({ id, label, unit, value, step, min, disabled, onCommit }: {
  id: string; label: string; unit: string; value: number; step: number; min?: number; disabled?: boolean; onCommit: (v: number) => void;
}) {
  const [v, setV] = useState(String(value));
  // Enter commits, and the blur that follows must not save the same value a second time
  const sent = useRef<number | null>(null);
  useEffect(() => { setV(String(value)); sent.current = null; }, [value]);
  const commit = () => {
    // an emptied field means "never mind", not 0
    if (!v.trim()) { setV(String(value)); return; }
    const n = Number(v);
    if (n === sent.current) return;
    if (Number.isFinite(n) && n !== value && (min == null || n >= min)) { sent.current = n; onCommit(n); }
    else setV(String(value));
  };
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="text-sm text-muted">{label}</Label>
      <div className="flex items-center gap-2">
        <Input id={id} type="number" inputMode="decimal" step={step} min={min} value={v} disabled={disabled}
               onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()}
               className="h-11 text-base" />
        <span className="text-sm text-muted">{unit}</span>
      </div>
    </div>
  );
}

function Segmented<T extends string>({ label, value, options, onChange, disabled }: {
  label: string; value: T | null; options: [T, string][]; onChange: (v: T) => void; disabled?: boolean;
}) {
  return (
    <fieldset className="grid gap-1" disabled={disabled}>
      <legend className="mb-1 text-sm text-muted">{label}</legend>
      <div className="flex rounded-[var(--radius-control)] bg-surface-2 p-0.5">
        {options.map(([v, l]) => (
          <button key={v} type="button" aria-pressed={value === v} onClick={() => value !== v && onChange(v)}
                  className={cn("min-h-11 flex-1 rounded-[6px] px-3 text-sm font-medium transition disabled:opacity-50",
                    value === v ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
            {l}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function ProvenanceEditor({ id, a, disabled, onSave }: {
  id: string; a: ObjectAnnotation; disabled: boolean;
  onSave: (basis: Basis, source: string | null) => void;
}) {
  const [basis, setBasis] = useState<Basis>(a.provenance.basis);
  const [source, setSource] = useState(a.provenance.source ?? "");
  useEffect(() => { setBasis(a.provenance.basis); setSource(a.provenance.source ?? ""); }, [a.provenance.basis, a.provenance.source]);
  const needsSource = basis === "measured";
  return (
    <div className="grid gap-2">
      <Label htmlFor={`basis-${id}`} className="text-sm text-muted">{t("check.provenance")}</Label>
      <select id={`basis-${id}`} value={basis} disabled={disabled}
              onChange={(e) => {
                const b = e.target.value as Basis;
                setBasis(b);
                if (b !== "measured") onSave(b, null);
              }}
              className="h-11 rounded-[var(--radius-control)] border border-border bg-surface px-3 text-base disabled:opacity-60">
        {BASES.map((b) => <option key={b} value={b}>{t(`provenance.${b}`)}</option>)}
      </select>
      {needsSource && (
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (source.trim()) onSave("measured", source.trim()); }}>
          <Label htmlFor={`src-${id}`} className="sr-only">{t("check.source")}</Label>
          <Input id={`src-${id}`} value={source} onChange={(e) => setSource(e.target.value)} disabled={disabled}
                 placeholder={t("check.source_ph")} className="h-11 text-base" maxLength={200} />
          <Button type="submit" disabled={disabled || !source.trim()} className="h-11">{t("check.record")}</Button>
        </form>
      )}
      {a.provenance.source && !needsSource && <p className="text-sm text-muted">{t("check.source")}: {a.provenance.source}</p>}
      <p className="text-xs text-muted">{t("check.provenance_hint")}</p>
    </div>
  );
}

/** Editor for the selected object: the few things an organizer changes, the rest under "More details".
 * Locked objects show their facts but cannot change. */
export function ObjectCard({ project, scene, selection }: { project: ProjectDetail; scene: SceneSnapshot | undefined; selection: Selection }) {
  const venue = project.version.venue;
  const names = useMemo(() => displayNames(venue), [venue]);
  const select = useUi((s) => s.select);
  const { submit, pending } = useVenueEdit(project.id);
  const [move, setMove] = useState({ dx: 0, dy: 0 });
  const found = findObject(venue, selection.id);
  if (!found) return <p className="text-sm text-muted">{t("check.nothing_selected")}</p>;
  const id = found.item.id;
  const name = names.get(id) ?? id;
  const a = annotationWithScene(venue, scene, project.current_version, id);
  const isStage = found.what === "obstacle" && found.item.kind === "stage";
  const locked = a.locked;
  const off = locked || pending;
  const kindLabel = found.what === "exit" ? t("check.kind_exit") : found.what === "zone" ? t("check.kind_zone")
    : isStage ? t("check.kind_stage") : t("check.kind_obstacle");
  const tone = found.what === "exit" ? "bg-emerald-500" : found.what === "zone" ? "bg-sky-500" : isStage ? "bg-violet-500" : "bg-amber-500";
  const icon = found.what === "exit" ? <DoorOpen /> : found.what === "zone" ? <Users /> : <MapPin />;

  return (
    <section aria-label={name} className="space-y-4">
      <div className="flex items-center gap-3">
        <span className={cn("grid size-10 shrink-0 place-items-center rounded-full text-white shadow-sm [&_svg]:size-5", tone)}>{icon}</span>
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold">{name}</h2>
          <p className="text-sm text-muted">{kindLabel}</p>
        </div>
      </div>
      <SimpleBadges a={a} blocked={found.what === "exit" && !!found.item.blocked} />

      {found.what === "exit" && (
        <>
          <NumberInput id={`w-${id}`} label={t("check.width")} unit={t("units.m")} step={0.5} min={0.6} value={found.item.width_m} disabled={off}
                       onCommit={(v) => submit([{ op: "resize", target: id, width_m: v } as never], t("check.msg_width", { name, w: fmtNum(v, 1) }))} />
          <div className="flex items-center justify-between gap-3 text-sm">
            <label htmlFor={`blk-${id}`}>{t("check.closed_in_plan")}</label>
            <Switch id={`blk-${id}`} checked={!!found.item.blocked} disabled={off}
                    onCheckedChange={(v) => submit([{ op: "block_exit", exit_id: id, blocked: v } as never], v ? t("check.msg_closed", { name }) : t("check.msg_opened", { name }))} />
          </div>
        </>
      )}

      {found.what === "zone" && (
        <>
          <NumberInput id={`p-${id}`} label={t("check.people")} unit={t("check.people_unit")} step={50} min={0} value={found.item.people} disabled={off}
                       onCommit={(v) => submit([{ op: "set_people", zone_id: id, people: Math.round(v) } as never], t("check.msg_people", { name, n: fmtInt(v) }))} />
          <ZoneProfileEditor project={project} zoneId={id} disabled={locked} />
        </>
      )}

      {!locked && <p className="flex items-center gap-2 text-sm text-muted"><Move className="size-4 shrink-0" />{t("check.drag_to_move")}</p>}

      <div className="flex items-center justify-between gap-3 rounded-[10px] bg-surface-2 p-3">
        <label htmlFor={`lock-${id}`} className="flex items-start gap-2 text-sm">
          {locked ? <Lock className="mt-0.5 size-4 shrink-0" /> : <LockOpen className="mt-0.5 size-4 shrink-0 text-muted" />}
          <span><span className="block font-medium">{t("check.lock")}</span><span className="block text-xs text-muted">{t("check.locked_note")}</span></span>
        </label>
        <Switch id={`lock-${id}`} checked={locked} disabled={pending}
                onCheckedChange={(v) => submit([annotateOp(id, { locked: v })], v ? t("check.msg_locked", { name }) : t("check.msg_unlocked", { name }))} />
      </div>

      <details className="group rounded-[10px] border border-border">
        <summary className="flex min-h-11 cursor-pointer items-center px-3 text-sm font-medium text-muted hover:text-ink">{t("check.more_details")}</summary>
        <div className="space-y-4 border-t border-border p-3">
          {(found.what === "exit" || (found.what === "obstacle" && !isStage)) && (
            <Segmented<ChangeStatus> label={t(found.what === "exit" ? "check.opening_is" : "check.feature_is")} value={a.change} disabled={off}
                                     options={[["existing", t("check.already_there")], ["proposed", t("check.proposed_new")]]}
                                     onChange={(v) => submit([annotateOp(id, { change: v })], t(v === "proposed" ? "check.msg_proposed" : "check.msg_existing", { name }))} />
          )}
          {a.change === "proposed" && found.what === "exit" && <p className="rounded-[8px] bg-caution-soft p-2.5 text-sm">{t("check.proposed_exit_note")}</p>}
          {found.what !== "exit" && (
            <form className="grid gap-2" onSubmit={(e) => {
              e.preventDefault();
              if (move.dx || move.dy) submit([{ op: "move", target: id, dx: move.dx, dy: move.dy } as never], t("check.msg_moved", { name }), () => setMove({ dx: 0, dy: 0 }));
            }}>
              <p className="text-sm text-muted">{t("check.move_hint")}</p>
              <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
                {(["dx", "dy"] as const).map((k) => (
                  <div key={k} className="grid gap-1">
                    <Label htmlFor={`${k}-${id}`} className="text-sm text-muted">{t(k === "dx" ? "check.east" : "check.north")}</Label>
                    <Input id={`${k}-${id}`} type="number" step={0.5} value={move[k]} disabled={off} className="h-11 text-base"
                           onChange={(e) => setMove((m) => ({ ...m, [k]: Number(e.target.value) || 0 }))} />
                  </div>
                ))}
                <Button type="submit" className="h-11" disabled={off || (!move.dx && !move.dy)}><Move />{t("check.move")}</Button>
              </div>
            </form>
          )}
          <ProvenanceEditor id={id} a={a} disabled={pending}
                            onSave={(basis, source) => submit([annotateOp(id, { provenance: { basis, ...(source ? { source, recorded_at: new Date().toISOString() } : {}) } })],
                                                             t("check.msg_provenance", { name, basis: t(`provenance.${basis}`).toLowerCase() }))} />
        </div>
      </details>

      {!isStage && (
        <Button variant="danger-ghost" disabled={off}
                onClick={() => {
                  const op = found.what === "exit" ? { op: "remove_exit", exit_id: id } : found.what === "zone" ? { op: "remove_zone", zone_id: id } : { op: "remove_obstacle", obstacle_id: id };
                  submit([op as never], t("check.msg_removed", { name }), () => select(null));
                }}>
          <Trash2 />{t("check.remove")}
        </Button>
      )}
    </section>
  );
}

/** Only what an organizer needs to see at a glance: new, closed, locked. */
function SimpleBadges({ a, blocked }: { a: ObjectAnnotation; blocked?: boolean }) {
  if (!blocked && !a.locked && a.change !== "proposed") return null;
  return (
    <span className="flex shrink-0 flex-wrap gap-1">
      {a.change === "proposed" && <Badge tone="signal">{t("check.new")}</Badge>}
      {a.locked && <Badge tone="ink"><Lock className="size-3" />{t("check.locked")}</Badge>}
      {blocked && <Badge tone="danger">{t("check.closed")}</Badge>}
    </span>
  );
}

function Step({ icon, tone, title, hint, aside, children }: {
  icon: React.ReactNode; tone: string; title: string; hint?: string; aside?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className="space-y-2.5">
      <div className="flex items-center gap-2.5">
        <span className={cn("grid size-8 shrink-0 place-items-center rounded-full text-white [&_svg]:size-4", tone)} aria-hidden>{icon}</span>
        <h2 className="text-base font-semibold">{title}</h2>
        {hint && (
          <Tip content={hint} side="bottom">
            <button type="button" aria-label={hint} className="grid size-8 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-ink"><Info className="size-4" /></button>
          </Tip>
        )}
        <span className="ml-auto">{aside}</span>
      </div>
      {children}
    </section>
  );
}

/** Headcount for one crowd area: − / number / + (saved on Enter, when leaving the field, or per press). */
function PeopleInput({ id, name, value, disabled, onCommit }: { id: string; name: string; value: number; disabled: boolean; onCommit: (v: number) => void }) {
  const [v, setV] = useState(String(value));
  const sent = useRef<number | null>(null);
  useEffect(() => { setV(String(value)); sent.current = null; }, [value]);
  const commit = () => {
    if (!v.trim()) { setV(String(value)); return; }
    const n = Math.round(Number(v));
    if (n === sent.current) return;
    if (Number.isFinite(n) && n >= 0 && n !== value) { sent.current = n; onCommit(n); } else setV(String(value));
  };
  const step = value < 50 ? 5 : value < 500 ? 10 : 50;
  const bump = (d: number) => {
    const n = Math.max(0, value + d);
    if (n !== value) { sent.current = n; setV(String(n)); onCommit(n); }
  };
  const btn = "grid size-10 place-items-center text-muted transition hover:bg-surface-2 hover:text-ink disabled:opacity-40";
  return (
    <div className="flex h-10 shrink-0 items-center overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface">
      <button type="button" className={btn} disabled={disabled || value <= 0} onClick={() => bump(-step)} aria-label={t("check.fewer", { n: step, name })}><Minus className="size-4" /></button>
      <input id={`pp-${id}`} aria-label={t("check.people_of", { name })} type="number" inputMode="numeric" min={0} step={step}
             value={v} disabled={disabled} onChange={(e) => setV(e.target.value)} onBlur={commit}
             onKeyDown={(e) => e.key === "Enter" && commit()}
             className="h-full w-16 border-x border-border bg-transparent text-center text-base font-semibold tabular outline-none [appearance:textfield] focus-visible:bg-signal-soft [&::-webkit-inner-spin-button]:appearance-none" />
      <button type="button" className={btn} disabled={disabled} onClick={() => bump(step)} aria-label={t("check.more", { n: step, name })}><Plus className="size-4" /></button>
    </div>
  );
}

const kindName = (kind: string) => {
  const name = t(`check.kinds.${kind}`);
  return name.startsWith("check.") ? kind.replace(/_/g, " ") : name;
};

/** The venue as three glances: the doors as chips, the people per area with steppers (grouped
 * per floor), and what is in the way. Several floors: tabs pick the floor, in the list and in 3D. */
export function VenueChecklist({ project, scene }: { project: ProjectDetail; scene: SceneSnapshot | undefined }) {
  const venue = project.version.venue;
  const names = useMemo(() => displayNames(venue), [venue]);
  const floorName = useMemo(() => floorNamer(venue), [venue]);
  const select = useUi((s) => s.select);
  const fly = useUi((s) => s.flyToPoint);
  const floorView = useUi((s) => s.floorView);
  const { submit, pending } = useVenueEdit(project.id);
  const multi = venue.floors.length > 1;
  const view = resolveFloorView(venue, floorView);
  const onFloor = multi && view !== "all" && view !== "exploded" ? view : null;
  const floors = onFloor ? venue.floors.filter((f) => f.floor_id === onFloor) : floorsBottomUp(venue);
  const pick = (kind: Selection["kind"], id: string, floorId: string, poly: number[][]) => {
    const [x, y] = centroid(poly);
    select({ kind, id, floorId });
    fly(x, y, floorId);
  };
  const chip = (r: { kind: Selection["kind"]; id: string; floorId: string; poly: number[][]; detail: string; blocked?: boolean; dot: string }) => {
    const a = annotationWithScene(venue, scene, project.current_version, r.id);
    return (
      <li key={r.id}>
        <button type="button" onClick={() => pick(r.kind, r.id, r.floorId, r.poly)}
                className={cn("inline-flex min-h-10 max-w-full items-center gap-2 rounded-full border bg-surface px-3 text-left text-sm shadow-sm transition hover:border-signal hover:bg-signal-soft/50",
                              r.blocked ? "border-danger/40" : "border-border")}>
          <span className={cn("size-2.5 shrink-0 rounded-full", r.dot)} aria-hidden />
          <span className="truncate font-medium">{names.get(r.id) ?? r.id}</span>
          <span className="shrink-0 text-xs text-muted tabular">{r.detail}</span>
          <SimpleBadges a={a} blocked={r.blocked} />
        </button>
      </li>
    );
  };
  const exits = floors.flatMap((f) => f.exits.map((e) => ({ kind: "exit" as const, id: e.id, floorId: f.floor_id, poly: e.polygon as number[][], detail: t("units.n_m", { n: fmtNum(e.width_m, 1) }), blocked: !!e.blocked, dot: e.blocked ? "bg-danger" : "bg-egress" })));
  const features = floors.flatMap((f) => f.obstacles.filter((o) => o.kind !== "wall").map((o) => ({
    kind: (o.kind === "stage" ? "stage" : "obstacle") as Selection["kind"], id: o.id, floorId: f.floor_id, poly: o.polygon as number[][],
    detail: kindName(o.kind), dot: o.kind === "stage" ? "bg-signal" : "bg-orange",
  })));
  const peopleOn = (fl: typeof venue.floors[number]) => fl.zones.reduce((n, z) => n + z.people, 0);
  const total = venue.floors.reduce((n, f) => n + peopleOn(f), 0);
  const allExits = venue.floors.reduce((n, f) => n + f.exits.length, 0);

  return (
    <div className="space-y-5">
      {multi && (
        <div role="group" aria-label={t("check.floor_tabs")} className="flex flex-wrap gap-1">
          {[{ id: "all", label: t("check.all_floors"), n: total }, ...floorsBottomUp(venue).map((f) => ({ id: f.floor_id, label: floorName(f.floor_id), n: peopleOn(f) }))].map((o) => {
            const on = o.id === "all" ? !onFloor : onFloor === o.id;
            return (
              <button key={o.id} type="button" aria-pressed={on} onClick={() => useUi.getState().setFloorView(o.id)}
                      className={cn("flex min-h-11 shrink-0 flex-col items-start justify-center rounded-[10px] border px-3 py-1 text-left transition",
                                    on ? "border-signal bg-signal text-signal-ink" : "border-border bg-surface hover:border-border-strong")}>
                <span className="text-sm font-semibold leading-tight">{o.label}</span>
                <span className={cn("flex items-center gap-1 text-2xs tabular", on ? "text-signal-ink/85" : "text-muted")}><Users className="size-3" aria-hidden />{fmtInt(o.n)}</span>
              </button>
            );
          })}
        </div>
      )}

      <Step icon={<DoorOpen />} tone="bg-egress-strong" title={t("check.step_doors")} hint={t("check.step_doors_hint")}
            aside={<Badge tone="neutral" className="tabular">{onFloor ? `${exits.length} / ${allExits}` : exits.length}</Badge>}>
        {exits.length ? <ul className="flex flex-wrap gap-1.5">{exits.map(chip)}</ul>
          : <p className="text-sm text-muted">{allExits ? t("check.no_exits_here") : <span className="text-danger">{t("check.no_exits")}</span>}</p>}
      </Step>

      <Step icon={<Users />} tone="bg-sky-strong" title={t("check.step_people")}
            aside={<span className="text-right"><span className="block text-xl font-bold leading-none tabular">{fmtInt(onFloor ? peopleOn(floors[0]) : total)}</span><span className="text-2xs text-muted">{t(onFloor ? "check.on_floor" : "check.in_total")}</span></span>}>
        <div className="space-y-3">
          {floors.map((fl) => (
            <div key={fl.floor_id} className="space-y-1">
              {multi && !onFloor && (
                <p className="flex items-center justify-between text-xs font-semibold text-muted">
                  <span>{floorName(fl.floor_id)}</span><span className="tabular">{fmtInt(peopleOn(fl))}</span>
                </p>
              )}
              <ul className="space-y-1">
                {fl.zones.map((z) => {
                  const name = names.get(z.id) ?? z.id;
                  const locked = annotationWithScene(venue, scene, project.current_version, z.id).locked;
                  const share = total ? z.people / Math.max(...fl.zones.map((x) => x.people), 1) : 0;
                  return (
                    <li key={z.id} className="flex items-center gap-2">
                      <button type="button" onClick={() => pick("zone", z.id, fl.floor_id, z.polygon as number[][])}
                              className="relative flex min-h-10 min-w-0 flex-1 items-center overflow-hidden rounded-[10px] px-2.5 text-left text-sm font-medium hover:bg-surface-2">
                        <span aria-hidden className="absolute inset-y-1.5 left-0 rounded-r-[6px] bg-sky-soft" style={{ width: `${Math.max(4, share * 100)}%` }} />
                        <span className="relative truncate">{name}</span>
                      </button>
                      <PeopleInput id={z.id} name={name} value={z.people} disabled={pending || locked}
                                   onCommit={(v) => submit([{ op: "set_people", zone_id: z.id, people: v } as never], t("check.msg_people", { name, n: fmtInt(v) }))} />
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </Step>

      {features.length > 0 && (
        <Step icon={<Fence />} tone="bg-orange" title={t("check.step_things")} hint={t("check.step_things_hint")}
              aside={<Badge tone="neutral" className="tabular">{features.length}</Badge>}>
          <ul className="flex flex-wrap gap-1.5">{features.map(chip)}</ul>
        </Step>
      )}
    </div>
  );
}
