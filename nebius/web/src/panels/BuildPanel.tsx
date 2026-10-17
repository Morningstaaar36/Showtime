/** Right-hand panel while a building tool is active: what to click, the tool's options, and typed
 * input for rooms and stairs (exact sizes, and a keyboard path that needs no 3D clicks). */
import { Check, CornerUpLeft, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import type { ProjectDetail } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { PanelTitle } from "@/components/ui/misc";
import { t } from "@/i18n";
import { type BuildStep, finishStep, isPolylineTool, roomStep, stairConnects, stairStep } from "@/lib/buildTools";
import { cn } from "@/lib/utils";
import { DIRECTIONS, type Direction, resolveEditFloor } from "@/lib/venueOps";
import { useVenueEdit } from "@/journey/useVenueEdit";
import { useBuild } from "@/state/build";
import { type BuildTool, useUi } from "@/state/ui";
import { floorNamer } from "./FloorMenu";

/** Saves a build step (ops), shows its error, or updates the corners drawn so far. */
export function useApplyStep(projectId: string) {
  const { submit, pending } = useVenueEdit(projectId);
  const apply = (step: BuildStep | null, onSaved?: () => void) => {
    if (!step) return;
    if (step.kind === "draft") useUi.getState().setDraft(step.draft);
    else if (step.kind === "error") toast.error(t(`editor.errors.${step.error}`));
    else submit(step.ops, step.message, () => { useUi.getState().setDraft([]); onSaved?.(); });
  };
  return { apply, pending };
}

function NumberOpt({ id, label, value, step, min, max, unit = "m", optional, onChange }: {
  id: string; label: string; value: number | null; step: number; min?: number; max?: number; unit?: string; optional?: boolean;
  onChange: (v: number | null) => void;
}) {
  const [text, setText] = useState(value == null ? "" : String(value));
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="text-sm text-muted">{label}</Label>
      <div className="flex items-center gap-2">
        <Input id={id} type="number" inputMode="decimal" step={step} min={min} max={max} value={text} className="h-10 w-28 text-base"
               onChange={(e) => {
                 setText(e.target.value);
                 const n = Number(e.target.value);
                 if (e.target.value === "" && optional) onChange(null);
                 else if (Number.isFinite(n) && (min == null || n >= min) && (max == null || n <= max)) onChange(n);
               }} />
        {unit && <span className="text-sm text-muted">{unit}</span>}
      </div>
    </div>
  );
}

function Sides({ label, value, onChange }: { label: string; value: Direction; onChange: (d: Direction) => void }) {
  return (
    <fieldset className="grid gap-1">
      <legend className="mb-1 text-sm text-muted">{label}</legend>
      <div className="grid grid-cols-4 rounded-[var(--radius-control)] bg-surface-2 p-0.5">
        {DIRECTIONS.map((d) => (
          <button key={d} type="button" aria-pressed={value === d} onClick={() => onChange(d)}
                  className={cn("min-h-10 rounded-[6px] px-1 text-sm font-medium transition",
                                value === d ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
            {t(`editor.options.${d}`)}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function TextOpt({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="text-sm text-muted">{label}</Label>
      <Input id={id} value={value} maxLength={60} onChange={(e) => onChange(e.target.value)} className="h-10 text-base" />
    </div>
  );
}

/** Typed numbers for a room or a stair: all fields must be numbers before the button enables. */
function TypedForm({ fields, submitLabel, disabled, onSubmit }: {
  fields: { id: string; label: string; initial: string }[]; submitLabel: string; disabled: boolean;
  onSubmit: (values: number[]) => void;
}) {
  const [values, setValues] = useState(() => fields.map((f) => f.initial));
  const nums = values.map((v) => (v.trim() === "" ? NaN : Number(v)));
  const ok = nums.every(Number.isFinite);
  return (
    <form className="grid gap-2" onSubmit={(e) => { e.preventDefault(); if (ok) onSubmit(nums); }}>
      <div className="grid grid-cols-2 gap-2">
        {fields.map((f, i) => (
          <div key={f.id} className="grid gap-1">
            <Label htmlFor={f.id} className="text-sm text-muted">{f.label}</Label>
            <Input id={f.id} type="number" inputMode="decimal" step={0.5} value={values[i]} className="h-10 text-base"
                   onChange={(e) => setValues((v) => v.map((x, j) => (j === i ? e.target.value : x)))} />
          </div>
        ))}
      </div>
      <Button type="submit" variant="primary" disabled={disabled || !ok}>{submitLabel}</Button>
    </form>
  );
}

export function BuildPanel({ project, tool }: { project: ProjectDetail; tool: BuildTool }) {
  const venue = project.version.venue;
  const editFloor = useUi((s) => s.editFloor);
  const draft = useUi((s) => s.draft);
  const floorId = resolveEditFloor(venue, editFloor);
  const name = useMemo(() => floorNamer(venue), [venue]);
  const opts = useBuild((s) => s.opts);
  const setOpt = useBuild((s) => s.setOpt);
  const { apply, pending } = useApplyStep(project.id);
  const polyline = isPolylineTool(tool);
  const hint = tool === "room" && draft.length === 1 ? t("editor.hints.room_second") : t(`editor.hints.${tool}`);
  const connects = tool === "stair" ? stairConnects(venue, floorId, name) : null;
  // typed coordinates start from the middle of the floor
  const floor = venue.floors.find((f) => f.floor_id === floorId) ?? venue.floors[0];
  const xs = floor.walkable.map((p) => p[0]);
  const ys = floor.walkable.map((p) => p[1]);
  const mid = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2].map((v) => String(Math.round(v)));

  return (
    <section aria-label={t(`editor.tools.${tool}`)} className="space-y-5">
      <div>
        <PanelTitle>{t(`editor.tools.${tool}`)}</PanelTitle>
        <p className="mt-0.5 text-sm text-muted">{t("editor.on_floor", { name: name(floorId) })}</p>
      </div>
      <p className="rounded-[10px] bg-signal-soft p-3 text-sm" aria-live="polite">{hint}</p>

      {polyline && (
        <div className="space-y-2">
          <p className="text-sm text-muted tabular" aria-live="polite">{t("editor.points", { n: draft.length })}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" size="sm" disabled={pending || draft.length < 2}
                    onClick={() => apply(finishStep(tool, floorId, draft, opts))}><Check />{t("editor.finish")}</Button>
            <Button variant="secondary" size="sm" disabled={!draft.length}
                    onClick={() => useUi.getState().setDraft(draft.slice(0, -1))}><CornerUpLeft />{t("editor.undo_point")}</Button>
            <Button variant="ghost" size="sm" onClick={() => useUi.getState().setTool("select")}><X />{t("editor.cancel")}</Button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        <PanelTitle>{t("editor.options.title")}</PanelTitle>
        {tool === "wall" && (
          <NumberOpt id="opt-wall-t" label={t("editor.options.thickness")} value={opts.wallThickness} step={0.05} min={0.05} max={1}
                     onChange={(v) => v != null && setOpt("wallThickness", v)} />
        )}
        {tool === "door" && (
          <NumberOpt id="opt-door-w" label={t("editor.options.door_width")} value={opts.doorWidth} step={0.1} min={0.6} max={10}
                     onChange={(v) => v != null && setOpt("doorWidth", v)} />
        )}
        {tool === "room" && (
          <>
            <Sides label={t("editor.options.door_side")} value={opts.roomDoorSide} onChange={(d) => setOpt("roomDoorSide", d)} />
            <NumberOpt id="opt-room-door" label={t("editor.options.door_width")} value={opts.roomDoorWidth} step={0.1} min={0.6} max={10}
                       onChange={(v) => v != null && setOpt("roomDoorWidth", v)} />
            <NumberOpt id="opt-room-people" label={t("editor.options.people")} value={opts.roomPeople} step={5} min={0} unit="" optional
                       onChange={(v) => setOpt("roomPeople", v)} />
            <TextOpt id="opt-room-name" label={t("editor.options.name")} value={opts.roomLabel} onChange={(v) => setOpt("roomLabel", v)} />
          </>
        )}
        {tool === "stair" && (
          <>
            {connects ? <p className="text-sm">{t("editor.options.stair_connects", connects)}</p>
              : <p className="rounded-[8px] bg-caution-soft p-2.5 text-sm">{t("editor.errors.stair_needs_floor")}</p>}
            <Sides label={t("editor.options.direction")} value={opts.stairDirection} onChange={(d) => setOpt("stairDirection", d)} />
            <div className="grid grid-cols-2 gap-2">
              <NumberOpt id="opt-stair-w" label={t("editor.options.width")} value={opts.stairWidth} step={0.1} min={0.8} max={10}
                         onChange={(v) => v != null && setOpt("stairWidth", v)} />
              <NumberOpt id="opt-stair-run" label={t("editor.options.run")} value={opts.stairRun} step={0.5} min={2} max={40}
                         onChange={(v) => v != null && setOpt("stairRun", v)} />
            </div>
          </>
        )}
        {tool === "route" && (
          <>
            <NumberOpt id="opt-route-w" label={t("editor.options.route_width")} value={opts.routeWidth} step={0.5} min={0.5} max={100} optional
                       onChange={(v) => setOpt("routeWidth", v)} />
            <TextOpt id="opt-route-name" label={t("editor.options.name")} value={opts.routeLabel} onChange={(v) => setOpt("routeLabel", v)} />
          </>
        )}
      </div>

      {tool === "room" && (
        <div className="space-y-2">
          <PanelTitle>{t("editor.options.typed_room")}</PanelTitle>
          <TypedForm key={`room-${floorId}`} submitLabel={t("editor.options.add_room")} disabled={pending}
                     fields={[
                       { id: "room-x", label: t("editor.options.x"), initial: mid[0] },
                       { id: "room-y", label: t("editor.options.y"), initial: mid[1] },
                       { id: "room-w", label: t("editor.options.room_width"), initial: "4" },
                       { id: "room-d", label: t("editor.options.room_depth"), initial: "4" },
                     ]}
                     onSubmit={([x, y, w, d]) => apply(roomStep(floorId, { x, y, width_m: w, depth_m: d }, opts))} />
        </div>
      )}
      {tool === "stair" && connects && (
        <div className="space-y-2">
          <PanelTitle>{t("editor.options.typed_stair")}</PanelTitle>
          <TypedForm key={`stair-${floorId}`} submitLabel={t("editor.options.add_stair")} disabled={pending}
                     fields={[
                       { id: "stair-x", label: t("editor.options.x"), initial: mid[0] },
                       { id: "stair-y", label: t("editor.options.y"), initial: mid[1] },
                     ]}
                     onSubmit={([x, y]) => apply(stairStep(venue, floorId, x, y, opts))} />
        </div>
      )}
    </section>
  );
}
