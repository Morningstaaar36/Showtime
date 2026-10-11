/** Collaborative editing on the "Check your venue" screen: one card for the selected door,
 * barrier or area (numbers, existing/proposed, provenance, lock) and lists to find them. */
import { DoorOpen, Lock, LockOpen, MapPin, Move, Trash2, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Exit, Obstacle, ProjectDetail, SceneSnapshot, Venue, Zone } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { PanelTitle } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { t } from "@/i18n";
import { annotateOp, annotationOf, BASES, type Basis, type ChangeStatus, type ObjectAnnotation } from "@/lib/annotations";
import { fmtInt, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { displayNames } from "@/lib/venueText";
import { centroid } from "@/scene/geom";
import { type Selection, useUi } from "@/state/ui";
import { useVenueEdit } from "./useVenueEdit";

type Found =
  | { what: "exit"; item: Exit; floorId: string }
  | { what: "obstacle"; item: Obstacle; floorId: string }
  | { what: "zone"; item: Zone; floorId: string };

export function findObject(venue: Venue, id: string): Found | null {
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
export function annotationWithScene(venue: Venue, scene: SceneSnapshot | undefined, version: number, id: string): ObjectAnnotation {
  const a = annotationOf(venue, id);
  const fromScene = scene?.identity.venue_version === version ? scene.objects.find((o) => o.id === id)?.provenance : undefined;
  return fromScene ? { ...a, provenance: { ...fromScene, basis: fromScene.basis as Basis } } : a;
}

export function AnnotationBadges({ a, blocked }: { a: ObjectAnnotation; blocked?: boolean }) {
  return (
    <span className="flex flex-wrap gap-1">
      {a.change === "proposed" && <Badge tone="signal">{t("check.proposed")}</Badge>}
      {a.change === "existing" && <Badge tone="outline">{t("check.existing")}</Badge>}
      {a.locked && <Badge tone="ink"><Lock className="size-3" />{t("check.locked")}</Badge>}
      {blocked && <Badge tone="danger">{t("check.closed")}</Badge>}
    </span>
  );
}

function NumberInput({ id, label, unit, value, step, min, disabled, onCommit }: {
  id: string; label: string; unit: string; value: number; step: number; min?: number; disabled?: boolean; onCommit: (v: number) => void;
}) {
  const [v, setV] = useState(String(value));
  // Enter commits, and the blur that follows must not save the same value a second time
  const sent = useRef<number | null>(null);
  useEffect(() => { setV(String(value)); sent.current = null; }, [value]);
  const commit = () => {
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

/** Editor for the selected object. Locked objects show their facts but cannot change. */
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

  return (
    <section aria-label={name} className="space-y-4">
      <PanelTitle action={<Badge tone="outline">{kindLabel}</Badge>}>{name}</PanelTitle>
      <AnnotationBadges a={a} blocked={found.what === "exit" && !!found.item.blocked} />

      <div className="flex items-center justify-between gap-3 rounded-[8px] border border-border p-3">
        <label htmlFor={`lock-${id}`} className="flex items-start gap-2 text-sm">
          {locked ? <Lock className="mt-0.5 size-4 shrink-0" /> : <LockOpen className="mt-0.5 size-4 shrink-0 text-muted" />}
          <span><span className="block font-medium">{t("check.lock")}</span><span className="block text-xs text-muted">{t("check.lock_hint")}</span></span>
        </label>
        <Switch id={`lock-${id}`} checked={locked} disabled={pending}
                onCheckedChange={(v) => submit([annotateOp(id, { locked: v })], v ? t("check.msg_locked", { name }) : t("check.msg_unlocked", { name }))} />
      </div>
      {locked && <p className="text-sm text-muted">{t("check.locked_note")}</p>}

      {found.what === "exit" && (
        <>
          <NumberInput id={`w-${id}`} label={t("check.width")} unit="m" step={0.5} min={0.6} value={found.item.width_m} disabled={off}
                       onCommit={(v) => submit([{ op: "resize", target: id, width_m: v } as never], t("check.msg_width", { name, w: fmtNum(v, 1) }))} />
          <div className="flex items-center justify-between gap-3 text-sm">
            <label htmlFor={`blk-${id}`}>{t("check.closed_in_plan")}</label>
            <Switch id={`blk-${id}`} checked={!!found.item.blocked} disabled={off}
                    onCheckedChange={(v) => submit([{ op: "block_exit", exit_id: id, blocked: v } as never], v ? t("check.msg_closed", { name }) : t("check.msg_opened", { name }))} />
          </div>
        </>
      )}

      {found.what === "zone" && (
        <NumberInput id={`p-${id}`} label={t("check.people")} unit={t("check.people_unit")} step={50} min={0} value={found.item.people} disabled={off}
                     onCommit={(v) => submit([{ op: "set_people", zone_id: id, people: Math.round(v) } as never], t("check.msg_people", { name, n: fmtInt(v) }))} />
      )}

      {found.what === "obstacle" && (
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

      {(found.what === "exit" || (found.what === "obstacle" && !isStage)) && (
        <Segmented<ChangeStatus> label={t(found.what === "exit" ? "check.opening_is" : "check.feature_is")} value={a.change} disabled={off}
                                 options={[["existing", t("check.already_there")], ["proposed", t("check.proposed_new")]]}
                                 onChange={(v) => submit([annotateOp(id, { change: v })], t(v === "proposed" ? "check.msg_proposed" : "check.msg_existing", { name }))} />
      )}
      {a.change === "proposed" && found.what === "exit" && <p className="rounded-[8px] bg-caution-soft p-2.5 text-sm">{t("check.proposed_exit_note")}</p>}

      <ProvenanceEditor id={id} a={a} disabled={pending}
                        onSave={(basis, source) => submit([annotateOp(id, { provenance: { basis, ...(source ? { source, recorded_at: new Date().toISOString() } : {}) } })],
                                                         t("check.msg_provenance", { name, basis: t(`provenance.${basis}`).toLowerCase() }))} />

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

/** Everything that can be checked, grouped the way an organizer thinks about a venue. */
export function ObjectLists({ project, scene }: { project: ProjectDetail; scene: SceneSnapshot | undefined }) {
  const venue = project.version.venue;
  const names = useMemo(() => displayNames(venue), [venue]);
  const select = useUi((s) => s.select);
  const fly = useUi((s) => s.flyToPoint);
  const pick = (kind: Selection["kind"], id: string, floorId: string, poly: number[][]) => {
    const [x, y] = centroid(poly);
    select({ kind, id, floorId });
    fly(x, y, floorId);
  };
  const rows = (list: { kind: Selection["kind"]; id: string; floorId: string; poly: number[][]; detail: string; blocked?: boolean }[]) => (
    <ul className="divide-y divide-border rounded-[8px] border border-border">
      {list.map((r) => {
        const a = annotationWithScene(venue, scene, project.current_version, r.id);
        return (
          <li key={r.id}>
            <button type="button" onClick={() => pick(r.kind, r.id, r.floorId, r.poly)}
                    className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{names.get(r.id) ?? r.id}</span>
                <span className="block text-xs text-muted">{r.detail} · {t(`provenance.${a.provenance.basis}`)}</span>
              </span>
              <AnnotationBadges a={a} blocked={r.blocked} />
            </button>
          </li>
        );
      })}
    </ul>
  );
  const exits = venue.floors.flatMap((f) => f.exits.map((e) => ({ kind: "exit" as const, id: e.id, floorId: f.floor_id, poly: e.polygon as number[][], detail: `${fmtNum(e.width_m, 1)} m wide`, blocked: !!e.blocked })));
  const features = venue.floors.flatMap((f) => f.obstacles.filter((o) => o.kind !== "wall").map((o) => ({
    kind: (o.kind === "stage" ? "stage" : "obstacle") as Selection["kind"], id: o.id, floorId: f.floor_id, poly: o.polygon as number[][], detail: o.kind.replace(/_/g, " "),
  })));
  const zones = venue.floors.flatMap((f) => f.zones.map((z) => ({ kind: "zone" as const, id: z.id, floorId: f.floor_id, poly: z.polygon as number[][], detail: `${fmtInt(z.people)} people` })));
  return (
    <div className="space-y-5">
      <section className="space-y-2">
        <PanelTitle action={<DoorOpen className="size-4 text-muted" />}>{t("check.doors")}</PanelTitle>
        {exits.length ? rows(exits) : <p className="text-sm text-danger">{t("check.no_exits")}</p>}
      </section>
      {features.length > 0 && (
        <section className="space-y-2">
          <PanelTitle action={<MapPin className="size-4 text-muted" />}>{t("check.features")}</PanelTitle>
          {rows(features)}
        </section>
      )}
      <section className="space-y-2">
        <PanelTitle action={<Users className="size-4 text-muted" />}>{t("check.zones")}</PanelTitle>
        {rows(zones)}
      </section>
    </div>
  );
}
