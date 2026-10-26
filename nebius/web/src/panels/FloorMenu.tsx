/** Floors in the building editor: pick the floor the tools act on, add a storey on top, remove one.
 * Every change is a patch (a new version with Undo), like any other edit. */
import { Building2, Layers3, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { ProjectDetail, Venue } from "@/api/types";
import { Confirm } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { Tip } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { fmtInt } from "@/lib/format";
import { cn } from "@/lib/utils";
import { addFloorOp, floorLabels, floorsByElevation, nextFloorName, removeFloorOp, resolveEditFloor } from "@/lib/venueOps";
import { useVenueEdit } from "@/journey/useVenueEdit";
import { useUi } from "@/state/ui";

/** "Mezzanine", else "Ground floor", "1st floor", "B1". */
export function floorNamer(venue: Venue): (floorId: string) => string {
  const labels = floorLabels(venue);
  const names = new Map(venue.floors.map((f) => [f.floor_id, f.name?.trim() || ""]));
  return (id) => {
    const name = names.get(id);
    if (name) return name;
    const l = labels.get(id) ?? id;
    return l === "Ground" ? t("editor.floor.ground") : l.startsWith("B") ? l : `${l} floor`;
  };
}

/** Make `floorId` the floor the tools act on, and show it alone when there are several. */
export function editOnFloor(venue: Venue, floorId: string): void {
  const ui = useUi.getState();
  ui.setEditFloor(floorId);
  if (venue.floors.length > 1) ui.setFloorView(floorId);
}

function useFloorActions(project: ProjectDetail) {
  const venue = project.version.venue;
  const { submit, pending } = useVenueEdit(project.id);
  const name = floorNamer(venue);
  return {
    pending,
    add: (opts: { name: string; height_m: number; copy_walls: boolean }, onDone?: () => void) => {
      const op = addFloorOp(venue, opts) as unknown as { floor_id: string; name: string };
      submit([op as never], t("editor.floor.msg_added", { name: op.name }), () => {
        // the new storey becomes the one the tools act on; its stairs come next
        useUi.getState().setEditFloor(op.floor_id);
        useUi.getState().setFloorView(op.floor_id);
        onDone?.();
      });
    },
    remove: (floorId: string) => {
      submit([removeFloorOp(floorId)], t("editor.floor.msg_removed", { name: name(floorId) }), () => {
        useUi.getState().setEditFloor(null);
        useUi.getState().setFloorView("all");
      });
    },
  };
}

export function AddFloorDialog({ venue, open, onOpenChange, pending, onAdd }: {
  venue: Venue; open: boolean; onOpenChange: (v: boolean) => void; pending: boolean;
  onAdd: (opts: { name: string; height_m: number; copy_walls: boolean }) => void;
}) {
  const [name, setName] = useState("");
  const [height, setHeight] = useState("3.5");
  const [copy, setCopy] = useState(true);
  const fallback = nextFloorName(venue);
  const h = Number(height);
  const ok = Number.isFinite(h) && h >= 2 && h <= 20;
  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (v) { setName(""); setHeight("3.5"); setCopy(true); } }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("editor.floor.add_title")}</DialogTitle>
          <DialogDescription>{t("editor.floor.add_lead")}</DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); if (ok) onAdd({ name: name.trim() || fallback, height_m: h, copy_walls: copy }); }}>
          <div className="grid gap-1.5">
            <Label htmlFor="floor-name">{t("editor.floor.name")}</Label>
            <Input id="floor-name" value={name} placeholder={fallback} maxLength={60} onChange={(e) => setName(e.target.value)} className="h-11 text-base" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="floor-height">{t("editor.floor.height")}</Label>
            <div className="flex items-center gap-2">
              <Input id="floor-height" type="number" inputMode="decimal" min={2} max={20} step={0.5} value={height}
                     onChange={(e) => setHeight(e.target.value)} className="h-11 w-28 text-base" aria-invalid={!ok} />
              <span className="text-sm text-muted">m</span>
            </div>
          </div>
          <div className="flex items-center justify-between gap-3 rounded-[10px] bg-surface-2 p-3">
            <label htmlFor="floor-copy" className="text-sm">
              <span className="block font-medium">{t("editor.floor.copy_walls")}</span>
              <span className="block text-xs text-muted">{t("editor.floor.copy_walls_hint")}</span>
            </label>
            <Switch id="floor-copy" checked={copy} onCheckedChange={setCopy} />
          </div>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
            <Button type="submit" variant="primary" disabled={!ok || pending}><Plus />{t("editor.floor.add")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The floor button on the tool rail: which floor the tools act on, add and remove floors. */
export function FloorPicker({ project }: { project: ProjectDetail }) {
  const venue = project.version.venue;
  const editFloor = useUi((s) => s.editFloor);
  const current = resolveEditFloor(venue, editFloor);
  const name = useMemo(() => floorNamer(venue), [venue]);
  const short = floorLabels(venue).get(current) ?? "";
  const actions = useFloorActions(project);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState(false);
  const floors = floorsByElevation(venue).reverse();
  const label = `${t("editor.floor.switcher")}: ${name(current)}`;
  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <Tip side="right" content={label}>
          <PopoverTrigger asChild>
            <button type="button" aria-label={label}
                    className="grid size-10 place-items-center rounded-[var(--radius-control)] text-muted hover:bg-surface-2 hover:text-ink">
              <span className="flex flex-col items-center leading-none">
                <Layers3 className="size-[16px]" aria-hidden />
                <span className="mt-0.5 max-w-9 truncate text-[10px] font-semibold tabular">{short === t("ui.floormenu.ground") ? "G" : short}</span>
              </span>
            </button>
          </PopoverTrigger>
        </Tip>
        <PopoverContent side="right" align="start" className="w-64 p-2">
          <div role="radiogroup" aria-label={t("editor.floor.switcher")} className="grid gap-0.5">
            <p className="px-2 pb-1 pt-0.5 text-xs font-medium text-muted">{t("editor.floor.switcher")}</p>
            {floors.map((f) => (
              <button key={f.floor_id} type="button" role="radio" aria-checked={f.floor_id === current}
                      onClick={() => { editOnFloor(venue, f.floor_id); setOpen(false); }}
                      className={cn("flex min-h-10 items-center justify-between gap-2 rounded-[6px] px-2 text-left text-sm",
                                    f.floor_id === current ? "bg-signal-soft font-semibold text-signal" : "hover:bg-surface-2")}>
                <span className="truncate">{name(f.floor_id)}</span>
                <span className="shrink-0 text-xs text-muted tabular">{fmtInt(f.zones.reduce((n, z) => n + z.people, 0))}</span>
              </button>
            ))}
          </div>
          <div className="mt-2 grid gap-1 border-t border-border pt-2">
            <Button variant="ghost" className="justify-start" disabled={actions.pending} onClick={() => { setOpen(false); setAdding(true); }}>
              <Plus />{t("editor.floor.add")}
            </Button>
            <Button variant="danger-ghost" className="justify-start" disabled={actions.pending || venue.floors.length < 2}
                    onClick={() => { setOpen(false); setRemoving(true); }}>
              <Trash2 />{t("editor.floor.remove")}
            </Button>
            {venue.floors.length < 2 && <p className="px-2 text-xs text-muted">{t("editor.floor.last")}</p>}
          </div>
        </PopoverContent>
      </Popover>
      <AddFloorDialog venue={venue} open={adding} onOpenChange={setAdding} pending={actions.pending}
                      onAdd={(o) => actions.add(o, () => setAdding(false))} />
      <Confirm open={removing} onOpenChange={setRemoving} danger
               title={t("editor.floor.remove_title", { name: name(current) })} body={t("editor.floor.remove_body")}
               confirmLabel={t("editor.floor.remove")} onConfirm={() => actions.remove(current)} />
    </>
  );
}

/** "Floors and rooms" on the simple check screen: the storeys, add one, and the way to the drawing tools. */
export function FloorsCard({ project }: { project: ProjectDetail }) {
  const venue = project.version.venue;
  const name = useMemo(() => floorNamer(venue), [venue]);
  const actions = useFloorActions(project);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const floors = floorsByElevation(venue).reverse();
  const rooms = (f: (typeof floors)[number]) => f.obstacles.filter((o) => o.kind === "wall").length;
  return (
    <section aria-labelledby="floors-title" className="space-y-2.5">
      <div className="flex items-start gap-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-slate-500 text-white [&_svg]:size-4"><Building2 /></span>
        <div className="min-w-0 flex-1">
          <h2 id="floors-title" className="text-base font-semibold">{t("editor.building.title")}</h2>
          <p className="text-sm text-muted">{t("editor.building.lead")}</p>
        </div>
      </div>
      <ul className="space-y-1 pl-10">
        {floors.map((f) => (
          <li key={f.floor_id} className="flex min-h-11 items-center gap-2 text-sm">
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{name(f.floor_id)}</span>
              <span className="block text-xs text-muted">
                {t("editor.floor.summary", { n: fmtInt(f.zones.reduce((n, z) => n + z.people, 0)), w: rooms(f) })}
              </span>
            </span>
            {venue.floors.length > 1 && (
              <Button variant="danger-ghost" size="icon" aria-label={t("editor.floor.remove_named", { name: name(f.floor_id) })}
                      disabled={actions.pending} onClick={() => setRemoving(f.floor_id)}>
                <Trash2 />
              </Button>
            )}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2 pl-10">
        <Button variant="secondary" disabled={actions.pending} onClick={() => setAdding(true)}><Plus />{t("editor.floor.add")}</Button>
        <Button asChild variant="ghost"><Link to={`/p/${project.id}/expert`}>{t("editor.building.open_expert")}</Link></Button>
      </div>
      <AddFloorDialog venue={venue} open={adding} onOpenChange={setAdding} pending={actions.pending}
                      onAdd={(o) => actions.add(o, () => setAdding(false))} />
      <Confirm open={!!removing} onOpenChange={(v) => !v && setRemoving(null)} danger
               title={t("editor.floor.remove_title", { name: removing ? name(removing) : "" })} body={t("editor.floor.remove_body")}
               confirmLabel={t("editor.floor.remove")} onConfirm={() => removing && actions.remove(removing)} />
    </section>
  );
}
